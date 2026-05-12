from __future__ import annotations

from dataclasses import dataclass

import pytest


@dataclass
class FakeEvent:
    type: str
    task_id: str | None = None
    task_name: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    task_prompt: str | None = None
    tool_name: str | None = None
    tool_args: dict | None = None
    output: str | None = None
    error: str | None = None


class RecordingWriter:
    def __init__(self):
        self.events = []

    def add_event(self, **kwargs):
        self.events.append(kwargs)


class FakeEventBus:
    def __init__(self, *, flush_error: Exception | None = None):
        self.calls = []
        self.handlers = {}
        self.flush_error = flush_error

    def register_handler(self, event_type, handler):
        self.calls.append(("register", event_type, handler))
        self.handlers.setdefault(event_type, []).append(handler)

    def off(self, event_type, handler):
        self.calls.append(("off", event_type, handler))
        self.handlers[event_type].remove(handler)

    def flush(self):
        self.calls.append(("flush",))
        if self.flush_error is not None:
            raise self.flush_error


def test_bridge_records_task_started_event():
    from api.runtime.crewai_event_bridge import CrewAIEventBridge

    writer = RecordingWriter()
    bridge = CrewAIEventBridge(writer=writer, run_id="run-1", node_id="crew:alpha")

    bridge.record_task_started(
        source=None,
        event=FakeEvent(type="task_started", task_id="task-1", task_name="Research"),
    )

    assert writer.events == [
        {
            "run_id": "run-1",
            "node_id": "crew:alpha",
            "event_type": "task_started",
            "payload": {
                "type": "task_started",
                "run_id": "run-1",
                "node_id": "crew:alpha",
                "task_id": "task-1",
                "task_name": "Research",
            },
        }
    ]


def test_direct_bridge_records_outside_active_context():
    from api.runtime.crewai_event_bridge import CrewAIEventBridge

    writer = RecordingWriter()
    bridge = CrewAIEventBridge(writer=writer, run_id="run-1", node_id="crew:alpha")

    bridge.record_task_started(
        source=None,
        event=FakeEvent(type="task_started", task_id="task-1"),
    )

    assert [event["run_id"] for event in writer.events] == ["run-1"]


def test_bridge_records_task_completed_event_with_output_preview():
    from api.runtime.crewai_event_bridge import CrewAIEventBridge

    writer = RecordingWriter()
    bridge = CrewAIEventBridge(writer=writer, run_id="run-1", node_id="crew:alpha")

    bridge.record_task_completed(
        source=None,
        event=FakeEvent(
            type="task_completed",
            task_id="task-1",
            task_name="Research",
            output="Found the relevant sources",
        ),
    )

    assert writer.events == [
        {
            "run_id": "run-1",
            "node_id": "crew:alpha",
            "event_type": "task_completed",
            "payload": {
                "type": "task_completed",
                "run_id": "run-1",
                "node_id": "crew:alpha",
                "task_id": "task-1",
                "task_name": "Research",
                "output_preview": "Found the relevant sources",
            },
        }
    ]


def test_bridge_records_task_failed_event_as_fatal_with_error_message():
    from api.runtime.crewai_event_bridge import CrewAIEventBridge

    writer = RecordingWriter()
    bridge = CrewAIEventBridge(writer=writer, run_id="run-1", node_id="crew:alpha")

    bridge.record_task_failed(
        source=None,
        event=FakeEvent(
            type="task_failed",
            task_id="task-1",
            task_name="Research",
            error="Could not access source",
        ),
    )

    assert writer.events == [
        {
            "run_id": "run-1",
            "node_id": "crew:alpha",
            "event_type": "task_failed",
            "payload": {
                "type": "task_failed",
                "run_id": "run-1",
                "node_id": "crew:alpha",
                "task_id": "task-1",
                "task_name": "Research",
                "error_message": "Could not access source",
                "fatal": True,
            },
        }
    ]


def test_bridge_records_collaboration_started_event():
    from api.runtime.crewai_event_bridge import CrewAIEventBridge

    writer = RecordingWriter()
    bridge = CrewAIEventBridge(writer=writer, run_id="run-1", node_id="crew:alpha")

    bridge.record_tool_started(
        source=None,
        event=FakeEvent(
            type="tool_usage_started",
            tool_name="ask_question_to_coworker",
            tool_args={
                "question": "Can you verify this?",
                "context": "Need a second opinion",
                "coworker": "Reviewer",
            },
            agent_role="Writer",
            task_id="task-1",
            task_name="Draft",
        ),
    )

    assert writer.events[0]["event_type"] == "collaboration_started"
    assert writer.events[0]["payload"]["collaboration_kind"] == "ask_question"
    assert writer.events[0]["payload"]["from_agent_role"] == "Writer"
    assert writer.events[0]["payload"]["to_agent_role"] == "Reviewer"


def test_bridge_records_normal_tool_started_event():
    from api.runtime.crewai_event_bridge import CrewAIEventBridge

    writer = RecordingWriter()
    bridge = CrewAIEventBridge(writer=writer, run_id="run-1", node_id="crew:alpha")

    bridge.record_tool_started(
        source=None,
        event=FakeEvent(
            type="tool_usage_started",
            tool_name="serper_search",
            tool_args={
                "search_query": "CrewAI event bridge",
                "note": "x" * 530,
            },
            agent_role="Researcher",
            task_id="task-1",
            task_name="Research",
        ),
    )

    assert writer.events[0]["event_type"] == "tool_execution_started"
    assert writer.events[0]["payload"] == {
        "type": "tool_execution_started",
        "run_id": "run-1",
        "node_id": "crew:alpha",
        "activity_kind": "tool",
        "tool_name": "serper_search",
        "tool_args_preview": {
            "search_query": "CrewAI event bridge",
            "note": f"{'x' * 500}...[truncated]",
        },
        "agent_role": "Researcher",
        "task_id": "task-1",
        "task_name": "Research",
    }


def test_bridge_records_tool_failed_event():
    from api.runtime.crewai_event_bridge import CrewAIEventBridge

    writer = RecordingWriter()
    bridge = CrewAIEventBridge(writer=writer, run_id="run-1", node_id="crew:alpha")

    bridge.record_tool_error(
        source=None,
        event=FakeEvent(
            type="tool_usage_error",
            tool_name="serper_search",
            tool_args={"search_query": "CrewAI"},
            agent_role="Researcher",
            error="provider rejected request",
        ),
    )

    assert writer.events[0]["event_type"] == "tool_execution_failed"
    assert writer.events[0]["payload"]["type"] == "tool_execution_failed"
    assert writer.events[0]["payload"]["fatal"] is False


def test_bridge_records_agent_started_contract_event():
    from api.runtime.crewai_event_bridge import CrewAIEventBridge

    writer = RecordingWriter()
    bridge = CrewAIEventBridge(writer=writer, run_id="run-1", node_id="crew:alpha")

    bridge.record_agent_started(
        source=None,
        event=FakeEvent(
            type="agent_execution_started",
            agent_id="agent-1",
            agent_role="Writer",
            task_id="task-1",
            task_name="Draft",
            task_prompt="Write the final response",
        ),
    )

    assert writer.events[0]["event_type"] == "agent_started"
    assert writer.events[0]["payload"]["type"] == "agent_started"


def test_bridge_uses_nested_task_description_when_name_is_missing():
    from api.runtime.crewai_event_bridge import CrewAIEventBridge

    class Task:
        id = "task-1"
        name = None
        description = "Draft the release summary"

    writer = RecordingWriter()
    bridge = CrewAIEventBridge(writer=writer, run_id="run-1", node_id="crew:alpha")

    bridge.record_agent_started(
        source=None,
        event=type(
            "Event",
            (),
            {
                "agent_role": "Writer",
                "task": Task(),
            },
        )(),
    )

    assert writer.events[0]["payload"]["task_name"] == "Draft the release summary"


def test_bridge_records_agent_completed_as_final_answer():
    from api.runtime.crewai_event_bridge import CrewAIEventBridge

    writer = RecordingWriter()
    bridge = CrewAIEventBridge(writer=writer, run_id="run-1", node_id="crew:alpha")

    bridge.record_agent_completed(
        source=None,
        event=FakeEvent(
            type="agent_execution_completed",
            agent_role="Writer",
            task_id="task-1",
            task_name="Draft",
            output="Final answer",
        ),
    )

    assert writer.events == [
        {
            "run_id": "run-1",
            "node_id": "crew:alpha",
            "event_type": "agent_final_answer",
            "payload": {
                "type": "agent_final_answer",
                "run_id": "run-1",
                "node_id": "crew:alpha",
                "agent_role": "Writer",
                "task_id": "task-1",
                "task_name": "Draft",
                "output_preview": "Final answer",
            },
        }
    ]


def test_bridge_records_agent_error_as_fatal_failed_event():
    from api.runtime.crewai_event_bridge import CrewAIEventBridge

    writer = RecordingWriter()
    bridge = CrewAIEventBridge(writer=writer, run_id="run-1", node_id="crew:alpha")

    bridge.record_agent_error(
        source=None,
        event=FakeEvent(
            type="agent_execution_error",
            agent_id="agent-1",
            agent_role="Writer",
            task_id="task-1",
            task_name="Draft",
            error="model call failed",
        ),
    )

    assert writer.events[0]["event_type"] == "agent_failed"
    assert writer.events[0]["payload"]["type"] == "agent_failed"
    assert writer.events[0]["payload"]["fatal"] is True


def test_bridge_records_tool_finished_event():
    from api.runtime.crewai_event_bridge import CrewAIEventBridge

    writer = RecordingWriter()
    bridge = CrewAIEventBridge(writer=writer, run_id="run-1", node_id="crew:alpha")

    bridge.record_tool_finished(
        source=None,
        event=FakeEvent(
            type="tool_usage_finished",
            tool_name="serper_search",
            tool_args={"search_query": "CrewAI"},
            agent_role="Researcher",
            output="result",
        ),
    )

    assert writer.events[0]["event_type"] == "tool_execution_completed"
    assert writer.events[0]["payload"]["output_preview"] == "result"


def test_crewai_event_bridge_registers_flushes_and_unregisters(monkeypatch):
    import api.runtime.crewai_event_bridge as bridge_module

    fake_bus = FakeEventBus()

    monkeypatch.setattr(bridge_module, "crewai_event_bus", fake_bus)

    with bridge_module.crewai_event_bridge(
        RecordingWriter(),
        run_id="run-1",
        node_id="crew:alpha",
    ):
        registered = [call[1] for call in fake_bus.calls if call[0] == "register"]
        assert registered == [
            bridge_module.TaskStartedEvent,
            bridge_module.TaskCompletedEvent,
            bridge_module.TaskFailedEvent,
            bridge_module.AgentExecutionStartedEvent,
            bridge_module.AgentExecutionCompletedEvent,
            bridge_module.AgentExecutionErrorEvent,
            bridge_module.ToolUsageStartedEvent,
            bridge_module.ToolUsageFinishedEvent,
            bridge_module.ToolUsageErrorEvent,
        ]

    call_names = [call[0] for call in fake_bus.calls]
    flush_index = call_names.index("flush")
    off_indexes = [index for index, name in enumerate(call_names) if name == "off"]

    assert all(index < flush_index for index, name in enumerate(call_names) if name == "register")
    assert all(flush_index < index for index in off_indexes)
    assert [call[1] for call in fake_bus.calls if call[0] == "off"] == registered


def test_context_manager_records_only_events_for_active_run(monkeypatch):
    import api.runtime.crewai_event_bridge as bridge_module

    fake_bus = FakeEventBus()
    writer_1 = RecordingWriter()
    writer_2 = RecordingWriter()
    monkeypatch.setattr(bridge_module, "crewai_event_bus", fake_bus)

    with bridge_module.crewai_event_bridge(writer_1, run_id="run-1", node_id="crew:alpha"):
        with bridge_module.crewai_event_bridge(writer_2, run_id="run-2", node_id="crew:beta"):
            for handler in list(fake_bus.handlers[bridge_module.TaskStartedEvent]):
                handler(
                    None,
                    FakeEvent(
                        type="task_started",
                        task_id="task-1",
                        task_name="Research",
                    ),
                )

    assert writer_1.events == []
    assert [event["run_id"] for event in writer_2.events] == ["run-2"]


def test_context_manager_records_only_events_for_active_run_and_node(monkeypatch):
    import api.runtime.crewai_event_bridge as bridge_module

    fake_bus = FakeEventBus()
    writer_a = RecordingWriter()
    writer_b = RecordingWriter()
    monkeypatch.setattr(bridge_module, "crewai_event_bus", fake_bus)

    with bridge_module.crewai_event_bridge(writer_a, run_id="run-1", node_id="crew:a"):
        with bridge_module.crewai_event_bridge(writer_b, run_id="run-1", node_id="crew:b"):
            for handler in list(fake_bus.handlers[bridge_module.TaskStartedEvent]):
                handler(
                    None,
                    FakeEvent(
                        type="task_started",
                        task_id="task-1",
                        task_name="Research",
                    ),
                )

    assert writer_a.events == []
    assert [event["node_id"] for event in writer_b.events] == ["crew:b"]


def test_context_manager_bridge_skips_global_event_without_active_context(monkeypatch):
    import api.runtime.crewai_event_bridge as bridge_module

    fake_bus = FakeEventBus()
    writer = RecordingWriter()
    monkeypatch.setattr(bridge_module, "crewai_event_bus", fake_bus)

    with bridge_module.crewai_event_bridge(writer, run_id="run-1", node_id="crew:alpha"):
        handler = fake_bus.handlers[bridge_module.TaskStartedEvent][0]
        handler(
            None,
            FakeEvent(type="task_started", task_id="task-1", task_name="Research"),
        )

    handler(
        None,
        FakeEvent(type="task_started", task_id="task-2", task_name="After context"),
    )

    assert [event["payload"]["task_id"] for event in writer.events] == ["task-1"]


def test_context_manager_unregisters_handlers_when_body_raises(monkeypatch):
    import api.runtime.crewai_event_bridge as bridge_module

    fake_bus = FakeEventBus()
    monkeypatch.setattr(bridge_module, "crewai_event_bus", fake_bus)

    with pytest.raises(RuntimeError, match="body failed"):
        with bridge_module.crewai_event_bridge(
            RecordingWriter(),
            run_id="run-1",
            node_id="crew:alpha",
        ):
            raise RuntimeError("body failed")

    registered = [call[1] for call in fake_bus.calls if call[0] == "register"]
    unregistered = [call[1] for call in fake_bus.calls if call[0] == "off"]

    assert unregistered == registered


def test_context_manager_unregisters_handlers_when_flush_raises(monkeypatch):
    import api.runtime.crewai_event_bridge as bridge_module

    fake_bus = FakeEventBus(flush_error=RuntimeError("flush failed"))
    monkeypatch.setattr(bridge_module, "crewai_event_bus", fake_bus)

    with pytest.raises(RuntimeError, match="flush failed"):
        with bridge_module.crewai_event_bridge(
            RecordingWriter(),
            run_id="run-1",
            node_id="crew:alpha",
        ):
            pass

    registered = [call[1] for call in fake_bus.calls if call[0] == "register"]
    unregistered = [call[1] for call in fake_bus.calls if call[0] == "off"]

    assert unregistered == registered


def test_context_manager_preserves_body_exception_when_flush_raises(monkeypatch):
    import api.runtime.crewai_event_bridge as bridge_module

    fake_bus = FakeEventBus(flush_error=RuntimeError("flush failed"))
    monkeypatch.setattr(bridge_module, "crewai_event_bus", fake_bus)

    with pytest.raises(ValueError, match="body failed"):
        with bridge_module.crewai_event_bridge(
            RecordingWriter(),
            run_id="run-1",
            node_id="crew:alpha",
        ):
            raise ValueError("body failed")

    registered = [call[1] for call in fake_bus.calls if call[0] == "register"]
    unregistered = [call[1] for call in fake_bus.calls if call[0] == "off"]

    assert unregistered == registered
