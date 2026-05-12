from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from crewai.events.event_bus import crewai_event_bus
from crewai.events.types.agent_events import (
    AgentExecutionCompletedEvent,
    AgentExecutionErrorEvent,
    AgentExecutionStartedEvent,
)
from crewai.events.types.task_events import (
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskStartedEvent,
)
from crewai.events.types.tool_usage_events import (
    ToolUsageErrorEvent,
    ToolUsageFinishedEvent,
    ToolUsageStartedEvent,
)

from api.runtime.run_events import (
    preview_text,
    semantic_tool_failed_payload,
    semantic_tool_finished_payload,
    semantic_tool_started_payload,
)


_CrewAIScopeToken = tuple[str, str | None]


_active_crewai_scope: ContextVar[_CrewAIScopeToken | None] = ContextVar(
    "active_crewai_scope",
    default=None,
)


def _event_value(event: object, name: str) -> Any:
    return getattr(event, name, None)


def _nested_value(event: object, object_name: str, field_name: str) -> Any:
    nested = getattr(event, object_name, None)
    if nested is None:
        return None
    return getattr(nested, field_name, None)


def _task_id(event: object) -> str | None:
    value = _event_value(event, "task_id")
    if value is None:
        value = _nested_value(event, "task", "id")
    return str(value) if value is not None else None


def _task_name(event: object) -> str | None:
    value = _event_value(event, "task_name")
    if value is None:
        task = getattr(event, "task", None)
        if task is not None:
            value = getattr(task, "name", None) or getattr(task, "description", None)
    return str(value) if value is not None else None


def _agent_id(event: object) -> str | None:
    value = _event_value(event, "agent_id")
    if value is None:
        value = _nested_value(event, "agent", "id")
    return str(value) if value is not None else None


def _agent_role(event: object) -> str | None:
    value = _event_value(event, "agent_role")
    if value is None:
        value = _nested_value(event, "agent", "role")
    return str(value) if value is not None else None


def _raw_output(event: object) -> Any:
    output = _event_value(event, "output")
    return getattr(output, "raw", output)


def _without_none(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


class CrewAIEventBridge:
    def __init__(
        self,
        *,
        writer: Any,
        run_id: str,
        node_id: str | None,
        require_active_context: bool = False,
    ):
        self.writer = writer
        self.run_id = run_id
        self.node_id = node_id
        self.require_active_context = require_active_context

    def _add(self, event_type: str, payload: Mapping[str, Any]) -> None:
        active_scope = _active_crewai_scope.get()
        bridge_scope = (self.run_id, self.node_id)
        if self.require_active_context and active_scope != bridge_scope:
            return
        if active_scope is not None and active_scope != bridge_scope:
            return

        self.writer.add_event(
            run_id=self.run_id,
            node_id=self.node_id,
            event_type=event_type,
            payload=dict(payload),
        )

    def record_task_started(self, source: object, event: object) -> None:
        del source
        payload = _without_none(
            {
                "type": "task_started",
                "run_id": self.run_id,
                "node_id": self.node_id,
                "task_id": _task_id(event),
                "task_name": _task_name(event),
            }
        )
        self._add(payload["type"], payload)

    def record_task_completed(self, source: object, event: object) -> None:
        del source
        payload = _without_none(
            {
                "type": "task_completed",
                "run_id": self.run_id,
                "node_id": self.node_id,
                "task_id": _task_id(event),
                "task_name": _task_name(event),
                "output_preview": preview_text(_raw_output(event)),
            }
        )
        self._add(payload["type"], payload)

    def record_task_failed(self, source: object, event: object) -> None:
        del source
        payload = _without_none(
            {
                "type": "task_failed",
                "run_id": self.run_id,
                "node_id": self.node_id,
                "task_id": _task_id(event),
                "task_name": _task_name(event),
                "error_message": preview_text(_event_value(event, "error")),
                "fatal": True,
            }
        )
        self._add(payload["type"], payload)

    def record_agent_started(self, source: object, event: object) -> None:
        del source
        payload = _without_none(
            {
                "type": "agent_started",
                "run_id": self.run_id,
                "node_id": self.node_id,
                "agent_id": _agent_id(event),
                "agent_role": _agent_role(event),
                "task_id": _task_id(event),
                "task_name": _task_name(event),
                "task_prompt_preview": preview_text(_event_value(event, "task_prompt")),
            }
        )
        self._add(payload["type"], payload)

    def record_agent_completed(self, source: object, event: object) -> None:
        del source
        payload = _without_none(
            {
                "type": "agent_final_answer",
                "run_id": self.run_id,
                "node_id": self.node_id,
                "agent_id": _agent_id(event),
                "agent_role": _agent_role(event),
                "task_id": _task_id(event),
                "task_name": _task_name(event),
                "output_preview": preview_text(_raw_output(event)),
            }
        )
        self._add(payload["type"], payload)

    def record_agent_error(self, source: object, event: object) -> None:
        del source
        payload = _without_none(
            {
                "type": "agent_failed",
                "run_id": self.run_id,
                "node_id": self.node_id,
                "agent_id": _agent_id(event),
                "agent_role": _agent_role(event),
                "task_id": _task_id(event),
                "task_name": _task_name(event),
                "error_message": preview_text(_event_value(event, "error")),
                "fatal": True,
            }
        )
        self._add(payload["type"], payload)

    def record_tool_started(self, source: object, event: object) -> None:
        del source
        payload = semantic_tool_started_payload(
            run_id=self.run_id,
            node_id=self.node_id,
            raw_tool_name=_event_value(event, "tool_name"),
            tool_args=_event_value(event, "tool_args"),
            agent_role=_agent_role(event),
            task_id=_task_id(event),
            task_name=_task_name(event),
        )
        self._add(payload["type"], payload)

    def record_tool_finished(self, source: object, event: object) -> None:
        del source
        payload = semantic_tool_finished_payload(
            run_id=self.run_id,
            node_id=self.node_id,
            raw_tool_name=_event_value(event, "tool_name"),
            tool_args=_event_value(event, "tool_args"),
            output=_raw_output(event),
            agent_role=_agent_role(event),
            task_id=_task_id(event),
            task_name=_task_name(event),
        )
        self._add(payload["type"], payload)

    def record_tool_error(self, source: object, event: object) -> None:
        del source
        payload = semantic_tool_failed_payload(
            run_id=self.run_id,
            node_id=self.node_id,
            raw_tool_name=_event_value(event, "tool_name"),
            tool_args=_event_value(event, "tool_args"),
            error=_event_value(event, "error"),
            agent_role=_agent_role(event),
            task_id=_task_id(event),
            task_name=_task_name(event),
            fatal=False,
        )
        self._add(payload["type"], payload)


@contextmanager
def crewai_event_bridge(
    writer: Any,
    *,
    run_id: str,
    node_id: str | None,
) -> Iterator[CrewAIEventBridge]:
    bridge = CrewAIEventBridge(
        writer=writer,
        run_id=run_id,
        node_id=node_id,
        require_active_context=True,
    )
    handlers = [
        (TaskStartedEvent, bridge.record_task_started),
        (TaskCompletedEvent, bridge.record_task_completed),
        (TaskFailedEvent, bridge.record_task_failed),
        (AgentExecutionStartedEvent, bridge.record_agent_started),
        (AgentExecutionCompletedEvent, bridge.record_agent_completed),
        (AgentExecutionErrorEvent, bridge.record_agent_error),
        (ToolUsageStartedEvent, bridge.record_tool_started),
        (ToolUsageFinishedEvent, bridge.record_tool_finished),
        (ToolUsageErrorEvent, bridge.record_tool_error),
    ]

    for event_type, handler in handlers:
        crewai_event_bus.register_handler(event_type, handler)

    token = _active_crewai_scope.set((run_id, node_id))
    body_exception: BaseException | None = None
    try:
        try:
            yield bridge
        except BaseException as exc:
            body_exception = exc
            raise
    finally:
        flush_exception: BaseException | None = None
        off_exception: BaseException | None = None
        try:
            crewai_event_bus.flush()
        except BaseException as exc:
            flush_exception = exc

        for event_type, handler in handlers:
            try:
                crewai_event_bus.off(event_type, handler)
            except BaseException as exc:
                if off_exception is None:
                    off_exception = exc

        _active_crewai_scope.reset(token)

        if body_exception is None:
            if flush_exception is not None:
                raise flush_exception
            if off_exception is not None:
                raise off_exception
