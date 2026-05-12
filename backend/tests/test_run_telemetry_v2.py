import pytest

from api.runtime.run_telemetry import redact_event_payload, redact_secret_text, serialize_step_payload


def test_redact_secret_text_masks_active_provider_env_values(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "serper-secret")

    assert redact_secret_text("request failed with serper-secret") == "request failed with [redacted]"


def test_redact_secret_text_accepts_resolved_values_after_env_overlay_exits(monkeypatch):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)

    assert (
        redact_secret_text("request failed with serper-secret", extra_values=("serper-secret",))
        == "request failed with [redacted]"
    )


def test_redact_event_payload_masks_secret_fields_and_env_values(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "serper-secret")

    payload = redact_event_payload(
        {
            "api_key": "sk-runtime-secret",
            "headers": {"Authorization": "Bearer serper-secret"},
            "message": "provider rejected serper-secret",
            "nested": [{"token": "raw-token"}],
        }
    )

    assert payload["api_key"] == "[redacted]"
    assert payload["headers"]["Authorization"] == "[redacted]"
    assert payload["message"] == "provider rejected [redacted]"
    assert payload["nested"][0]["token"] == "[redacted]"
    assert "serper-secret" not in str(payload)
    assert "sk-runtime-secret" not in str(payload)
    assert "raw-token" not in str(payload)


def test_serialize_step_payload_redacts_sensitive_callback_payloads(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-secret")

    event_type, payload = serialize_step_payload(
        {"output": "failed with sk-openai-secret", "api_key": "literal-secret"},
        crew_node_id="crew-1",
    )

    assert event_type == "agent_finish"
    assert payload["output"] == "failed with [redacted]"
    assert payload["api_key"] == "[redacted]"
    assert "sk-openai-secret" not in str(payload)
    assert "literal-secret" not in str(payload)


def test_serialize_step_payload_redacts_extra_transfer_values():
    transfer_text = "raw=Launch AI Ops"

    event_type, payload = serialize_step_payload(
        {"output": f"Rendered prompt includes {transfer_text}"},
        crew_node_id="crew-1",
        extra_values=(transfer_text,),
    )

    assert event_type == "agent_finish"
    assert payload["output"] == "Rendered prompt includes [redacted]"
    assert transfer_text not in str(payload)


def test_flow_run_event_sink_commits_events_for_stream_visibility(db):
    from api.db.models import FlowRun, FlowRunEvent
    from api.runtime.run_telemetry import FlowRunEventSink

    run_id = "11111111-1111-4111-8111-111111111111"
    run = FlowRun(
        id=run_id,
        flow_version_id="22222222-2222-4222-8222-222222222222",
        status="running",
        input_json={},
    )
    db.add(run)
    db.commit()

    sink = FlowRunEventSink(
        db,
        run_id=run_id,
        node_id="crew:stream",
        commit_immediately=True,
    )
    sink.add_event(event_type="agent_started", payload={"type": "agent_started"})

    db.expire_all()
    event = db.query(FlowRunEvent).filter(FlowRunEvent.run_id == run_id).one()
    assert event.event_type == "agent_started"
    assert event.event_payload_json["type"] == "agent_started"


def test_flow_run_event_sink_rejects_immediate_commit_with_pending_changes(db):
    from api.db.models import FlowRun, FlowRunEvent
    from api.runtime.run_telemetry import FlowRunEventSink

    run_id = "11111111-1111-4111-8111-111111111112"
    run = FlowRun(
        id=run_id,
        flow_version_id="22222222-2222-4222-8222-222222222222",
        status="running",
        input_json={},
    )
    db.add(run)
    db.commit()

    unrelated_id = "33333333-3333-4333-8333-333333333333"
    unrelated = FlowRun(
        id=unrelated_id,
        flow_version_id="22222222-2222-4222-8222-222222222222",
        status="pending",
        input_json={},
    )
    db.add(unrelated)

    sink = FlowRunEventSink(
        db,
        run_id=run_id,
        node_id="crew:stream",
        commit_immediately=True,
    )
    with pytest.raises(RuntimeError, match="FlowRunEventWriter"):
        sink.add_event(event_type="agent_started", payload={"type": "agent_started"})

    db.rollback()
    assert db.query(FlowRun).filter(FlowRun.id == unrelated_id).one_or_none() is None
    assert db.query(FlowRunEvent).filter(FlowRunEvent.run_id == run_id).count() == 0


def test_flow_run_event_sink_rejects_immediate_commit_with_flushed_transaction(db):
    from api.db.models import FlowRun, FlowRunEvent
    from api.runtime.run_telemetry import FlowRunEventSink

    run_id = "11111111-1111-4111-8111-111111111115"
    run = FlowRun(
        id=run_id,
        flow_version_id="22222222-2222-4222-8222-222222222222",
        status="running",
        input_json={},
    )
    db.add(run)
    db.commit()

    unrelated_id = "33333333-3333-4333-8333-333333333334"
    db.add(
        FlowRun(
            id=unrelated_id,
            flow_version_id="22222222-2222-4222-8222-222222222222",
            status="pending",
            input_json={},
        )
    )
    db.flush()

    sink = FlowRunEventSink(
        db,
        run_id=run_id,
        node_id="crew:stream",
        commit_immediately=True,
    )
    with pytest.raises(RuntimeError, match="FlowRunEventWriter"):
        sink.add_event(event_type="agent_started", payload={"type": "agent_started"})

    db.rollback()
    assert db.query(FlowRun).filter(FlowRun.id == unrelated_id).one_or_none() is None
    assert db.query(FlowRunEvent).filter(FlowRunEvent.run_id == run_id).count() == 0


def test_flow_run_event_sink_rolls_back_when_immediate_commit_fails():
    from api.runtime.run_telemetry import FlowRunEventSink

    class FakeSession:
        new = ()
        dirty = ()
        deleted = ()

        def __init__(self):
            self.added = []
            self.rolled_back = False

        def in_transaction(self):
            return False

        def add(self, value):
            self.added.append(value)

        def commit(self):
            raise RuntimeError("commit failed")

        def rollback(self):
            self.rolled_back = True

    session = FakeSession()
    sink = FlowRunEventSink(
        session,
        run_id="11111111-1111-4111-8111-111111111116",
        node_id="crew:stream",
        commit_immediately=True,
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        sink.add_event(event_type="agent_started", payload={"type": "agent_started"})

    assert session.rolled_back is True


def test_flow_run_event_writer_persists_redacts_and_closes(monkeypatch):
    from api.runtime.event_writer import FlowRunEventWriter

    monkeypatch.setenv("SERPER_API_KEY", "serper-secret")

    class FakeSession:
        def __init__(self):
            self.added = []
            self.committed = False
            self.closed = False

        def add(self, value):
            self.added.append(value)

        def commit(self):
            self.committed = True

        def rollback(self):
            raise AssertionError("rollback should not be called")

        def close(self):
            self.closed = True

    session = FakeSession()
    writer = FlowRunEventWriter(session_factory=lambda: session)

    writer.add_event(
        run_id="11111111-1111-4111-8111-111111111113",
        node_id="crew:stream",
        event_type="agent_started",
        payload={"type": "agent_started", "message": "failed with serper-secret"},
    )

    assert session.committed is True
    assert session.closed is True
    event = session.added[0]
    assert event.run_id == "11111111-1111-4111-8111-111111111113"
    assert event.node_id == "crew:stream"
    assert event.event_type == "agent_started"
    assert event.event_payload_json["message"] == "failed with [redacted]"


def test_flow_run_event_writer_rolls_back_and_closes_when_commit_fails():
    from api.runtime.event_writer import FlowRunEventWriter

    class FakeSession:
        def __init__(self):
            self.added = []
            self.rolled_back = False
            self.closed = False

        def add(self, value):
            self.added.append(value)

        def commit(self):
            raise RuntimeError("commit failed")

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    session = FakeSession()
    writer = FlowRunEventWriter(session_factory=lambda: session)

    with pytest.raises(RuntimeError, match="commit failed"):
        writer.add_event(
            run_id="11111111-1111-4111-8111-111111111114",
            node_id="crew:stream",
            event_type="agent_started",
            payload={"type": "agent_started"},
        )

    assert session.rolled_back is True
    assert session.closed is True
