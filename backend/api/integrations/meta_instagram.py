from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any
from typing import Iterator
from urllib.parse import quote

import requests
from sqlalchemy.orm import Session

from api.runtime.credential_resolver import CredentialResolutionError
from api.runtime.oauth_clients import RuntimeOAuthToken, resolve_oauth_token_payload


META_INSTAGRAM_BASIC_SCOPE = "instagram_basic"
META_INSTAGRAM_CONTENT_PUBLISH_SCOPE = "instagram_content_publish"
META_INSTAGRAM_PROVIDER = "meta_instagram"


@dataclass(frozen=True)
class MetaInstagramRuntimeContext:
    db: Session
    owner_user_id: str
    run_id: str
    token: RuntimeOAuthToken | None = None


_runtime_context: ContextVar[MetaInstagramRuntimeContext | None] = ContextVar(
    "meta_instagram_runtime_context",
    default=None,
)


class MetaInstagramIntegrationError(RuntimeError):
    pass


class MetaInstagramClient:
    def __init__(
        self,
        *,
        ig_user_id: str,
        access_token: str,
        graph_base_url: str = "https://graph.facebook.com/v24.0",
        poll_timeout_seconds: int = 60,
        poll_interval_seconds: int = 3,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ig_user_id = ig_user_id
        self._access_token = access_token
        self._graph_base_url = graph_base_url.rstrip("/")
        self._poll_timeout_seconds = _positive_int(
            poll_timeout_seconds,
            field_name="poll_timeout_seconds",
        )
        self._poll_interval_seconds = _positive_int(
            poll_interval_seconds,
            field_name="poll_interval_seconds",
        )
        if self._poll_interval_seconds > self._poll_timeout_seconds:
            raise ValueError("poll_interval_seconds must not exceed poll_timeout_seconds.")
        self._sleeper = sleeper
        self._monotonic_clock = monotonic_clock

    def publish_image(self, *, image_url: str, caption: str) -> dict[str, Any]:
        container_id = self._create_media_container(
            data={
                "image_url": image_url,
                "caption": caption,
                "access_token": self._access_token,
            },
            field_label="media container id",
            step="media creation",
        )
        self._wait_for_container_finished(container_id, step="media readiness")
        return self._publish_container(container_id)

    def publish_carousel(self, *, image_urls: list[str], caption: str) -> dict[str, Any]:
        if len(image_urls) != 3:
            raise ValueError("Instagram carousel publishing requires exactly 3 image URLs.")
        child_container_ids = [
            self._create_media_container(
                data={
                    "image_url": image_url,
                    "is_carousel_item": "true",
                    "access_token": self._access_token,
                },
                field_label="carousel item container id",
                step="carousel item creation",
            )
            for image_url in image_urls
        ]
        parent_container_id = self._create_media_container(
            data={
                "media_type": "CAROUSEL",
                "children": ",".join(child_container_ids),
                "caption": caption,
                "access_token": self._access_token,
            },
            field_label="carousel container id",
            step="carousel creation",
        )
        self._wait_for_container_finished(parent_container_id, step="carousel readiness")
        return self._publish_container(parent_container_id)

    def _create_media_container(
        self,
        *,
        data: dict[str, Any],
        field_label: str,
        step: str,
    ) -> str:
        create_response = requests.post(
            f"{self._graph_base_url}/{self._ig_user_id}/media",
            data=data,
            timeout=30,
        )
        _raise_for_meta_error(
            create_response,
            step=step,
            access_token=self._access_token,
        )
        return _required_response_id(
            _response_json(create_response, step=step),
            field_label=field_label,
        )

    def _wait_for_container_finished(self, container_id: str, *, step: str) -> dict[str, Any]:
        deadline = self._monotonic_clock() + self._poll_timeout_seconds
        last_payload: dict[str, Any] | None = None
        while True:
            status_response = requests.get(
                f"{self._graph_base_url}/{container_id}",
                params={
                    "fields": "status_code,status",
                    "access_token": self._access_token,
                },
                timeout=30,
            )
            _raise_for_meta_error(
                status_response,
                step=step,
                access_token=self._access_token,
            )
            payload = _response_json(status_response, step=step)
            last_payload = payload
            status_code = payload.get("status_code")
            if status_code == "FINISHED":
                return payload
            if status_code in {"ERROR", "EXPIRED"}:
                raise MetaInstagramIntegrationError(
                    _sanitize_meta_message(
                        f"Meta Instagram {step} failed: {_compact_payload(payload)}",
                        access_token=self._access_token,
                    )
                )
            if status_code != "IN_PROGRESS":
                raise MetaInstagramIntegrationError(
                    _sanitize_meta_message(
                        f"Meta Instagram {step} returned unexpected status_code: "
                        f"{_compact_payload(payload)}",
                        access_token=self._access_token,
                    )
                )
            if self._monotonic_clock() >= deadline:
                raise MetaInstagramIntegrationError(
                    _sanitize_meta_message(
                        "Meta Instagram "
                        f"{step} timed out after {self._poll_timeout_seconds} seconds: "
                        f"{_compact_payload(last_payload)}",
                        access_token=self._access_token,
                    )
                )
            self._sleeper(self._poll_interval_seconds)

    def _publish_container(self, container_id: str) -> dict[str, Any]:
        publish_response = requests.post(
            f"{self._graph_base_url}/{self._ig_user_id}/media_publish",
            data={
                "creation_id": container_id,
                "access_token": self._access_token,
            },
            timeout=30,
        )
        _raise_for_meta_error(
            publish_response,
            step="publish",
            access_token=self._access_token,
        )
        media_id = _optional_response_id(
            _response_json_or_none(publish_response),
        )
        if media_id is None:
            return {
                "ig_container_id": container_id,
                "ig_media_id": None,
                "status": "publish_state_ambiguous",
            }
        return {
            "ig_container_id": container_id,
            "ig_media_id": media_id,
            "status": "published",
        }


@contextmanager
def meta_instagram_runtime_context(
    *,
    db: Session,
    owner_user_id: str,
    run_id: str,
    token: RuntimeOAuthToken | None = None,
) -> Iterator[None]:
    context_token = _runtime_context.set(
        MetaInstagramRuntimeContext(
            db=db,
            owner_user_id=owner_user_id,
            run_id=run_id,
            token=token,
        )
    )
    try:
        yield
    finally:
        _runtime_context.reset(context_token)


def current_meta_instagram_runtime_context() -> MetaInstagramRuntimeContext:
    context = _runtime_context.get()
    if context is None:
        raise CredentialResolutionError("Meta Instagram runtime context is unavailable.")
    return context


def resolve_meta_instagram_runtime_token(
    db: Session,
    *,
    owner_user_id: str,
) -> RuntimeOAuthToken:
    return resolve_oauth_token_payload(
        db,
        owner_user_id=owner_user_id,
        provider=META_INSTAGRAM_PROVIDER,
        required_scopes=[
            META_INSTAGRAM_BASIC_SCOPE,
            META_INSTAGRAM_CONTENT_PUBLISH_SCOPE,
        ],
    )


def build_meta_instagram_client_from_runtime(
    *,
    db: Session | None = None,
    owner_user_id: str | None = None,
    poll_timeout_seconds: int = 60,
    poll_interval_seconds: int = 3,
) -> MetaInstagramClient:
    context = _runtime_context.get()
    if context is not None:
        if context.token is None:
            raise CredentialResolutionError(
                "Meta Instagram OAuth token was not prepared for runtime execution."
            )
        if not context.token.provider_account_id:
            raise CredentialResolutionError("Instagram account id is unavailable.")
        return MetaInstagramClient(
            ig_user_id=context.token.provider_account_id,
            access_token=context.token.access_token,
            poll_timeout_seconds=poll_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )

    runtime_db = db if db is not None else None
    runtime_owner_user_id = owner_user_id if owner_user_id is not None else None
    if runtime_db is None or not runtime_owner_user_id:
        raise CredentialResolutionError("Meta Instagram runtime context is unavailable.")
    token_payload = resolve_meta_instagram_runtime_token(
        runtime_db,
        owner_user_id=runtime_owner_user_id,
    )
    if not token_payload.provider_account_id:
        raise CredentialResolutionError("Instagram account id is unavailable.")
    return MetaInstagramClient(
        ig_user_id=token_payload.provider_account_id,
        access_token=token_payload.access_token,
        poll_timeout_seconds=poll_timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )


def _response_json(response: requests.Response, *, step: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise MetaInstagramIntegrationError(
            f"Meta Instagram {step} returned invalid JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise MetaInstagramIntegrationError(
            f"Meta Instagram {step} returned an unexpected response."
        )
    return payload


def _positive_int(value: object, *, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")
    return value


def _raise_for_meta_error(
    response: requests.Response,
    *,
    step: str,
    access_token: str,
) -> None:
    status_code = getattr(response, "status_code", None)
    ok = getattr(response, "ok", None)
    if ok is True or (ok is None and isinstance(status_code, int) and 200 <= status_code < 300):
        return
    if ok is None and status_code is None:
        return

    payload = _response_json_or_none(response)
    detail = _meta_error_detail(payload)
    if not detail:
        text = getattr(response, "text", "")
        detail = text[:500] if isinstance(text, str) and text else "no response body"
    status_label = f"HTTP {status_code}" if isinstance(status_code, int) else "HTTP error"
    raise MetaInstagramIntegrationError(
        _sanitize_meta_message(
            f"Meta Instagram {step} failed: {status_label}; {detail}",
            access_token=access_token,
        )
    )


def _meta_error_detail(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return ""
    error = payload.get("error")
    if isinstance(error, Mapping):
        parts: list[str] = []
        for key in ("message", "type", "code", "error_subcode", "status_code", "fbtrace_id"):
            value = error.get(key)
            if value is not None:
                parts.append(f"{key}={value}")
        return "; ".join(parts)
    return _compact_payload(payload)


def _compact_payload(payload: object) -> str:
    if payload is None:
        return "none"
    return str(payload)[:500]


def _sanitize_meta_message(message: str, *, access_token: str) -> str:
    if not access_token:
        return message
    sanitized = message.replace(access_token, "[REDACTED]")
    encoded_token = quote(access_token, safe="")
    if encoded_token and encoded_token != access_token:
        sanitized = sanitized.replace(encoded_token, "[REDACTED]")
    return sanitized


def _response_json_or_none(response: requests.Response) -> dict[str, Any] | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _required_response_id(payload: dict[str, Any], *, field_label: str) -> str:
    response_id = payload.get("id")
    if not isinstance(response_id, str) or not response_id.strip():
        raise MetaInstagramIntegrationError(f"Meta Instagram response is missing {field_label}.")
    return response_id.strip()


def _optional_response_id(payload: dict[str, Any] | None) -> str | None:
    if payload is None:
        return None
    response_id = payload.get("id")
    if not isinstance(response_id, str) or not response_id.strip():
        return None
    return response_id.strip()


def resolve_meta_instagram_runtime_token_for_crew(
    db: Session,
    *,
    owner_user_id: str,
    crew_snapshot: Mapping[str, Any],
) -> RuntimeOAuthToken | None:
    if not crew_snapshot_uses_meta_instagram(crew_snapshot):
        return None
    return resolve_meta_instagram_runtime_token(db, owner_user_id=owner_user_id)


def crew_snapshot_uses_meta_instagram(crew_snapshot: Mapping[str, Any]) -> bool:
    return any(
        _tool_payload_uses_meta_instagram(tool_key, tool_payload)
        for tool_key, tool_payload in _reachable_tool_payloads(crew_snapshot)
    )


def _reachable_tool_payloads(
    crew_snapshot: Mapping[str, Any],
) -> list[tuple[str, Mapping[str, Any]]]:
    runtime_crew = crew_snapshot.get("runtime_crew")
    runtime_crew = runtime_crew if isinstance(runtime_crew, Mapping) else {}
    agent_ids = _string_set(runtime_crew.get("agent_version_ids"))
    manager_agent_id = runtime_crew.get("manager_agent_version_id")
    if isinstance(manager_agent_id, str) and manager_agent_id.strip():
        agent_ids.add(manager_agent_id.strip())
    task_ids = _string_set(runtime_crew.get("task_version_ids"))
    task_agent_links = crew_snapshot.get("task_agent_links")
    if isinstance(task_agent_links, Mapping):
        for task_id in task_ids:
            agent_id = task_agent_links.get(task_id)
            if isinstance(agent_id, str) and agent_id.strip():
                agent_ids.add(agent_id.strip())

    tool_keys: set[str] = set()
    agent_tool_links = crew_snapshot.get("agent_tool_links") or crew_snapshot.get("tool_links")
    if isinstance(agent_tool_links, Mapping):
        for agent_id in agent_ids:
            tool_keys.update(_string_set(agent_tool_links.get(agent_id)))

    task_tool_links = crew_snapshot.get("task_tool_links")
    if isinstance(task_tool_links, Mapping):
        for task_id in task_ids:
            tool_keys.update(_string_set(task_tool_links.get(task_id)))

    runtime_tools = crew_snapshot.get("runtime_tools")
    runtime_tools = runtime_tools if isinstance(runtime_tools, Mapping) else {}
    payloads: list[tuple[str, Mapping[str, Any]]] = []
    for tool_key in tool_keys:
        tool_payload = runtime_tools.get(tool_key)
        if isinstance(tool_payload, Mapping):
            payloads.append((tool_key, tool_payload))
        else:
            payloads.append((tool_key, {}))
    return payloads


def _tool_payload_uses_meta_instagram(tool_key: str, tool_payload: Mapping[str, Any]) -> bool:
    if tool_key == "ax.instagram_publish_tool":
        return True
    if (
        tool_payload.get("module_path") == "api.tools.instagram_publish_tool"
        and tool_payload.get("class_name") == "AXInstagramPublishTool"
    ):
        return True
    credential_requirements = tool_payload.get("credential_requirements")
    if isinstance(credential_requirements, Sequence) and not isinstance(
        credential_requirements, bytes | bytearray | str
    ):
        for requirement in credential_requirements:
            if not isinstance(requirement, Mapping):
                continue
            if (
                requirement.get("provider") == META_INSTAGRAM_PROVIDER
                and requirement.get("injection") == "runtime_context"
                and requirement.get("required") is not False
            ):
                return True
    credentials = tool_payload.get("credentials")
    if isinstance(credentials, Sequence) and not isinstance(credentials, bytes | bytearray | str):
        for credential in credentials:
            if not isinstance(credential, Mapping):
                continue
            if (
                credential.get("provider") == META_INSTAGRAM_PROVIDER
                and credential.get("required") is not False
            ):
                return True
    return False


def _string_set(value: object) -> set[str]:
    if isinstance(value, str) and value.strip():
        return {value.strip()}
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        return {item.strip() for item in value if isinstance(item, str) and item.strip()}
    return set()
