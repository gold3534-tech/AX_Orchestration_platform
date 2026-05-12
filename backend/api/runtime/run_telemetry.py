from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any

from sqlalchemy.orm import Session

from api.db.models import FlowRunEvent

MAX_EVENT_TEXT_LENGTH = 4000
MAX_EVENT_SEQUENCE_ITEMS = 50
MAX_EVENT_DEPTH = 6
SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
)
SENSITIVE_ENV_SUFFIXES = (
    "API_KEY",
    "AUTHORIZATION",
    "PASSWORD",
    "SECRET",
    "TOKEN",
)


def _is_sensitive_key(value: str) -> bool:
    normalized = value.lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def _sensitive_env_values(extra_values: Sequence[str] = ()) -> list[str]:
    values: list[str] = [value for value in extra_values if len(value) >= 4]
    for key, value in os.environ.items():
        if not value or len(value) < 4:
            continue
        if key in SENSITIVE_ENV_SUFFIXES or key.endswith(SENSITIVE_ENV_SUFFIXES):
            values.append(value)
    return sorted(set(values), key=len, reverse=True)


def redact_secret_text(value: str, *, extra_values: Sequence[str] = ()) -> str:
    redacted = value
    for secret_value in _sensitive_env_values(extra_values):
        redacted = redacted.replace(secret_value, "[redacted]")
    return redacted


def _truncate(value: str) -> str:
    if len(value) <= MAX_EVENT_TEXT_LENGTH:
        return value
    return f"{value[:MAX_EVENT_TEXT_LENGTH]}...[truncated]"


def _safe_text(value: Any, *, extra_values: Sequence[str] = ()) -> str:
    try:
        return redact_secret_text(_truncate(str(value)), extra_values=extra_values)
    except Exception:
        return f"<unserializable {value.__class__.__name__}>"


def _json_safe(
    value: Any,
    *,
    depth: int = 0,
    key_hint: str | None = None,
    extra_values: Sequence[str] = (),
) -> Any:
    if key_hint and _is_sensitive_key(key_hint):
        return "[redacted]"
    if isinstance(value, str):
        return redact_secret_text(_truncate(value), extra_values=extra_values)
    if value is None or isinstance(value, bool | int | float):
        return value
    if depth >= MAX_EVENT_DEPTH:
        return _safe_text(value, extra_values=extra_values)
    if is_dataclass(value):
        return _json_safe(asdict(value), depth=depth + 1, extra_values=extra_values)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return _json_safe(dumped, depth=depth + 1, extra_values=extra_values)
    if isinstance(value, Mapping):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            safe_key = _safe_text(key, extra_values=extra_values)
            safe[safe_key] = _json_safe(
                item,
                depth=depth + 1,
                key_hint=safe_key,
                extra_values=extra_values,
            )
        return safe
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [
            _json_safe(item, depth=depth + 1, extra_values=extra_values)
            for item in list(value)[:MAX_EVENT_SEQUENCE_ITEMS]
        ]
    return _safe_text(value, extra_values=extra_values)


def _safe_payload(value: Any, *, extra_values: Sequence[str] = ()) -> dict[str, Any]:
    try:
        if is_dataclass(value):
            raw = asdict(value)
        elif hasattr(value, "model_dump"):
            dumped = value.model_dump()
            raw = dumped if isinstance(dumped, Mapping) else {"value": dumped}
        elif isinstance(value, Mapping):
            raw = value
        else:
            raw = {
                "type": value.__class__.__name__,
                "text": _safe_text(value, extra_values=extra_values),
            }
        safe = _json_safe(raw, extra_values=extra_values)
        if isinstance(safe, dict):
            return {str(key): item for key, item in safe.items()}
        return {"value": safe}
    except Exception as exc:
        raise ValueError(f"Unable to serialize telemetry payload: {exc}") from exc


def redact_event_payload(value: dict[str, Any], *, extra_values: Sequence[str] = ()) -> dict[str, Any]:
    safe = _json_safe(value, extra_values=extra_values)
    if isinstance(safe, dict):
        return {str(key): item for key, item in safe.items()}
    return {"value": safe}


def serialize_step_payload(
    value: Any,
    *,
    crew_node_id: str,
    extra_values: Sequence[str] = (),
) -> tuple[str, dict[str, Any]]:
    payload = _safe_payload(value, extra_values=extra_values)
    payload["crew_node_id"] = crew_node_id
    payload["kind"] = "agent_step"

    value_type = value.__class__.__name__
    if value_type == "AgentFinish" or "output" in payload:
        payload["kind"] = "agent_finish"
        return "agent_finish", payload
    if "result" in payload and payload.get("result") is not None:
        payload["kind"] = "agent_tool_result"
        return "agent_tool_result", payload
    return "agent_step", payload


def serialize_task_payload(
    value: Any,
    *,
    crew_node_id: str,
    extra_values: Sequence[str] = (),
) -> dict[str, Any]:
    payload = _safe_payload(value, extra_values=extra_values)
    payload["crew_node_id"] = crew_node_id
    payload["kind"] = "task_completed"
    return payload


class FlowRunEventSink:
    def __init__(
        self,
        db: Session,
        *,
        run_id: str,
        node_id: str,
        extra_redaction_values: Sequence[str] = (),
        commit_immediately: bool = False,
    ) -> None:
        self._db = db
        self._run_id = run_id
        self._node_id = node_id
        self._extra_redaction_values = extra_redaction_values
        # Only use immediate commits with a clean, isolated session. Stream paths
        # that must not share a transaction should use FlowRunEventWriter instead.
        self._commit_immediately = commit_immediately

    def add_event(self, *, event_type: str, payload: dict[str, Any]) -> None:
        if self._commit_immediately and (
            self._db.in_transaction() or self._db.new or self._db.dirty or self._db.deleted
        ):
            raise RuntimeError(
                "FlowRunEventSink(commit_immediately=True) requires a clean session. "
                "Use FlowRunEventWriter for stream-visible events that must not share a transaction."
            )
        self._db.add(
            FlowRunEvent(
                run_id=self._run_id,
                node_id=self._node_id,
                event_type=event_type,
                event_payload_json=redact_event_payload(
                    payload,
                    extra_values=tuple(self._extra_redaction_values),
                ),
            )
        )
        if self._commit_immediately:
            try:
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise

    def step_callback(self, value: Any) -> None:
        try:
            event_type, payload = serialize_step_payload(
                value,
                crew_node_id=self._node_id,
                extra_values=tuple(self._extra_redaction_values),
            )
            self.add_event(event_type=event_type, payload=payload)
        except Exception as exc:
            self.add_event(
                event_type="telemetry_error",
                payload={
                    "crew_node_id": self._node_id,
                    "kind": "telemetry_error",
                    "error": _safe_text(exc, extra_values=tuple(self._extra_redaction_values)),
                },
            )

    def task_callback(self, value: Any) -> None:
        try:
            self.add_event(
                event_type="task_completed",
                payload=serialize_task_payload(
                    value,
                    crew_node_id=self._node_id,
                    extra_values=tuple(self._extra_redaction_values),
                ),
            )
        except Exception as exc:
            self.add_event(
                event_type="telemetry_error",
                payload={
                    "crew_node_id": self._node_id,
                    "kind": "telemetry_error",
                    "error": _safe_text(exc, extra_values=tuple(self._extra_redaction_values)),
                },
            )

    def callback_bundle(self) -> dict[str, object]:
        return {
            "step_callback": self.step_callback,
            "task_callback": self.task_callback,
        }
