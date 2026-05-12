from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import sessionmaker

from tests.test_flow_run_skeleton_v2 import _create_published_crew_with_snapshot, _create_published_flow


def test_create_flow_run_route_enqueues_background_execution_without_running_it(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from api.db.models import FlowRun

    queued: list[tuple[str, str]] = []

    def fake_enqueue(background_tasks, *, run_id: str, owner_user_id: str) -> None:
        queued.append((run_id, owner_user_id))

    monkeypatch.setattr("api.routes.runs.enqueue_flow_run_execution", fake_enqueue)

    flow = _create_published_flow(client, db, auth_headers, name="Async Flow")
    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "Async"}},
        headers=auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "running"
    assert body["output_json"] is None
    assert queued == [(body["id"], "test-user")]

    run = db.get(FlowRun, body["id"])
    assert run.status == "running"
    assert run.input_json == {"topic": "Async"}


def test_execute_flow_run_background_completes_existing_run(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from api.db.models import FlowRun
    from api.runtime.flow_snapshot_executor import FlowSnapshotExecutor
    from api.services.runs import execute_flow_run_background

    testing_session_local = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    monkeypatch.setattr("api.services.runs.SessionLocal", testing_session_local)

    flow = _create_published_flow(client, db, auth_headers, name="Execute Existing Flow")
    run = FlowSnapshotExecutor(db).create_run_record(
        flow_version_id=flow["current_version"]["id"],
        owner_user_id="test-user",
        inputs={"topic": "Existing"},
    )

    execute_flow_run_background(run_id=str(run.id), owner_user_id="test-user")

    db.expire_all()
    completed = db.get(FlowRun, run.id)
    assert completed.status == "completed"
    assert completed.output_json == {"Topic": "Existing"}


def test_background_execution_fallback_fails_run_when_executor_method_is_missing(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from api.db.models import FlowRun, FlowRunEvent
    from api.runtime.flow_snapshot_executor import FlowSnapshotExecutor
    from api.services.runs import execute_flow_run_background

    queued: list[tuple[str, str]] = []

    def fake_enqueue(background_tasks, *, run_id: str, owner_user_id: str) -> None:
        queued.append((run_id, owner_user_id))

    testing_session_local = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)

    monkeypatch.setattr("api.routes.runs.enqueue_flow_run_execution", fake_enqueue)
    monkeypatch.setattr("api.services.runs.SessionLocal", testing_session_local)
    monkeypatch.delattr(FlowSnapshotExecutor, "execute_existing_run")

    flow = _create_published_flow(client, db, auth_headers, name="Async Flow Missing Executor")
    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "Async"}},
        headers=auth_headers,
    )

    assert response.status_code == 201
    run_id = response.json()["id"]
    assert queued == [(run_id, "test-user")]

    execute_flow_run_background(run_id=run_id, owner_user_id="test-user")

    db.expire_all()
    run = db.get(FlowRun, run_id)
    assert run.status == "failed"
    assert run.finished_at is not None
    assert run.error_message is not None
    assert "execute_existing_run" in run.error_message

    run_failed_event = (
        db.query(FlowRunEvent)
        .filter(FlowRunEvent.run_id == run_id, FlowRunEvent.event_type == "run_failed")
        .one()
    )
    assert run_failed_event.node_id is None
    assert "execute_existing_run" in run_failed_event.event_payload_json["error"]


def test_execute_flow_run_background_marks_run_failed_for_generic_executor_error(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from api.db.models import FlowRun, FlowRunEvent
    from api.runtime.flow_snapshot_executor import FlowSnapshotExecutor
    from api.services.runs import execute_flow_run_background

    testing_session_local = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    monkeypatch.setattr("api.services.runs.SessionLocal", testing_session_local)

    flow = _create_published_flow(client, db, auth_headers, name="Generic Background Error Flow")
    run = FlowSnapshotExecutor(db).create_run_record(
        flow_version_id=flow["current_version"]["id"],
        owner_user_id="test-user",
        inputs={"topic": "Generic"},
    )

    def fail_existing_run(self, *, run_id: str, owner_user_id: str):
        raise RuntimeError("catalog exploded")

    monkeypatch.setattr(FlowSnapshotExecutor, "execute_existing_run", fail_existing_run)

    execute_flow_run_background(run_id=str(run.id), owner_user_id="test-user")

    db.expire_all()
    failed = db.get(FlowRun, run.id)
    assert failed.status == "failed"
    assert failed.error_message == "catalog exploded"
    assert failed.finished_at is not None

    run_failed_event = (
        db.query(FlowRunEvent)
        .filter(FlowRunEvent.run_id == str(run.id), FlowRunEvent.event_type == "run_failed")
        .one()
    )
    assert run_failed_event.node_id is None
    assert run_failed_event.event_payload_json == {
        "type": "run_failed",
        "run_id": str(run.id),
        "node_id": None,
        "error_message": "catalog exploded",
        "error": "catalog exploded",
    }


def test_background_crew_execution_records_semantic_failure_event(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from api.db.models import FlowRun, FlowRunEvent
    from api.services.runs import execute_flow_run_background

    class FailingCrew:
        def kickoff(self, *, inputs):
            del inputs
            raise RuntimeError("crew exploded")

    class FakeFactory:
        def __init__(self, *, execution_mode="validation", llm_catalog=None):
            del llm_catalog
            self.execution_mode = execution_mode

        def build_crew(self, **kwargs):
            del kwargs
            assert self.execution_mode == "live"
            return FailingCrew()

    testing_session_local = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    monkeypatch.setattr("api.services.runs.SessionLocal", testing_session_local)
    monkeypatch.setattr("api.runtime.flow_snapshot_executor.CrewAIFactory", FakeFactory)

    crew = _create_published_crew_with_snapshot(
        client,
        db,
        auth_headers,
        runtime_snapshot_json={
            "schemaVersion": 1,
            "required_inputs": ["topic"],
            "runtime_crew": {"agent_version_ids": [], "task_version_ids": []},
            "runtime_agents": {},
            "runtime_tasks": {},
            "task_agent_links": {},
        },
    )
    flow = _create_published_flow(
        client,
        db,
        auth_headers,
        name="Semantic Crew Failure Flow",
        runtime_snapshot_json={
            "schemaVersion": 1,
            "graph": {
                "nodes": [
                    {"id": "input:main", "type": "input", "data": {}},
                    {"id": "start:main", "type": "start", "data": {}},
                    {
                        "id": "crew:research",
                        "type": "crew",
                        "data": {"assetId": crew["id"], "versionId": crew["current_version"]["id"]},
                    },
                    {"id": "output:main", "type": "output", "data": {}},
                ],
                "edges": [
                    {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
                    {"id": "edge:start:crew", "source": "start:main", "target": "crew:research", "type": "flow"},
                    {"id": "edge:crew:output", "source": "crew:research", "target": "output:main", "type": "flow"},
                ],
            },
            "crew_refs": [
                {
                    "node_id": "crew:research",
                    "asset_id": crew["id"],
                    "version_id": crew["current_version"]["id"],
                    "latest_version_id": crew["current_version"]["id"],
                    "status": "latest",
                }
            ],
            "crew_input_mappings": {
                "crew:research": {
                    "topic": {"source": "state", "path": "topic"},
                }
            },
            "output_fields": [
                {"label": "Raw", "source": "node", "nodeId": "crew:research", "path": "output.raw"}
            ],
        },
    )

    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "CrewAI"}},
        headers=auth_headers,
    )

    assert response.status_code == 201
    run_id = response.json()["id"]

    execute_flow_run_background(run_id=run_id, owner_user_id="test-user")

    db.expire_all()
    failed = db.get(FlowRun, run_id)
    assert failed.status == "failed"

    events = (
        db.query(FlowRunEvent)
        .filter(FlowRunEvent.run_id == run_id)
        .order_by(FlowRunEvent.created_at.asc(), FlowRunEvent.id.asc())
        .all()
    )
    event_types = [event.event_type for event in events]
    assert "crew_started" in event_types
    assert event_types.count("crew_failed") == 1
    assert "run_failed" in event_types

    crew_failed_event = next(event for event in events if event.event_type == "crew_failed")
    assert crew_failed_event.node_id == "crew:research"
    assert crew_failed_event.event_payload_json == {
        "type": "crew_failed",
        "run_id": run_id,
        "node_id": "crew:research",
        "error_message": "crew exploded",
        "fatal": True,
    }

    run_failed_event = next(event for event in events if event.event_type == "run_failed")
    assert run_failed_event.node_id == "crew:research"
    assert run_failed_event.event_payload_json["type"] == "run_failed"
    assert run_failed_event.event_payload_json["run_id"] == run_id
    assert run_failed_event.event_payload_json["node_id"] == "crew:research"
    assert run_failed_event.event_payload_json["error_message"] == "crew exploded"
    assert run_failed_event.event_payload_json["error"] == "crew exploded"


def test_background_crew_execution_persists_crewai_event_bridge_output(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from api.db.models import FlowRunEvent
    from api.services.runs import execute_flow_run_background
    from crewai.events.event_bus import crewai_event_bus
    from crewai.events.types.tool_usage_events import ToolUsageStartedEvent

    class EventfulCrew:
        def kickoff(self, *, inputs):
            crewai_event_bus.emit(
                self,
                ToolUsageStartedEvent(
                    tool_name="serper_search",
                    tool_args={"search_query": inputs["topic"]},
                    agent_role="Researcher",
                    task_id="task-1",
                    task_name="Research",
                ),
            )
            return {"raw": f"topic={inputs['topic']}"}

    class FakeFactory:
        def __init__(self, *, execution_mode="validation", llm_catalog=None):
            del llm_catalog
            self.execution_mode = execution_mode

        def build_crew(self, **kwargs):
            del kwargs
            assert self.execution_mode == "live"
            return EventfulCrew()

    testing_session_local = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    monkeypatch.setattr("api.services.runs.SessionLocal", testing_session_local)
    monkeypatch.setattr("api.runtime.flow_snapshot_executor.CrewAIFactory", FakeFactory)

    crew = _create_published_crew_with_snapshot(
        client,
        db,
        auth_headers,
        runtime_snapshot_json={
            "schemaVersion": 1,
            "required_inputs": ["topic"],
            "runtime_crew": {"agent_version_ids": [], "task_version_ids": []},
            "runtime_agents": {},
            "runtime_tasks": {},
            "task_agent_links": {},
        },
    )
    flow = _create_published_flow(
        client,
        db,
        auth_headers,
        name="Background Crew Bridge Flow",
        runtime_snapshot_json={
            "schemaVersion": 1,
            "graph": {
                "nodes": [
                    {"id": "input:main", "type": "input", "data": {}},
                    {"id": "start:main", "type": "start", "data": {}},
                    {
                        "id": "crew:research",
                        "type": "crew",
                        "data": {"assetId": crew["id"], "versionId": crew["current_version"]["id"]},
                    },
                    {"id": "output:main", "type": "output", "data": {}},
                ],
                "edges": [
                    {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
                    {"id": "edge:start:crew", "source": "start:main", "target": "crew:research", "type": "flow"},
                    {"id": "edge:crew:output", "source": "crew:research", "target": "output:main", "type": "flow"},
                ],
            },
            "crew_refs": [
                {
                    "node_id": "crew:research",
                    "asset_id": crew["id"],
                    "version_id": crew["current_version"]["id"],
                    "latest_version_id": crew["current_version"]["id"],
                    "status": "latest",
                }
            ],
            "crew_input_mappings": {
                "crew:research": {
                    "topic": {"source": "state", "path": "topic"},
                }
            },
            "output_fields": [
                {"label": "Raw", "source": "node", "nodeId": "crew:research", "path": "output.raw"}
            ],
        },
    )

    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "CrewAI"}},
        headers=auth_headers,
    )

    assert response.status_code == 201
    run_id = response.json()["id"]

    execute_flow_run_background(run_id=run_id, owner_user_id="test-user")

    semantic_event = (
        db.query(FlowRunEvent)
        .filter(
            FlowRunEvent.run_id == run_id,
            FlowRunEvent.node_id == "crew:research",
            FlowRunEvent.event_type == "tool_execution_started",
        )
        .one()
    )
    assert semantic_event.event_payload_json["type"] == "tool_execution_started"
    assert semantic_event.event_payload_json["tool_name"] == "serper_search"
    assert semantic_event.event_payload_json["tool_args_preview"] == {"search_query": "[redacted]"}


def test_execute_existing_run_claims_running_run_before_execution(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from api.runtime.flow_snapshot_executor import FlowSnapshotExecutor

    flow = _create_published_flow(client, db, auth_headers, name="Claim Existing Flow")
    run = FlowSnapshotExecutor(db).create_run_record(
        flow_version_id=flow["current_version"]["id"],
        owner_user_id="test-user",
        inputs={"topic": "Claim"},
    )
    executor = FlowSnapshotExecutor(db)
    observed_statuses: list[str] = []

    def complete_without_replaying(
        self,
        *,
        run,
        snapshot,
        state,
        owner_user_id,
        capture_agent_execution_logs,
        use_immediate_event_writer=True,
    ):
        assert use_immediate_event_writer is True
        observed_statuses.append(run.status)
        run.status = "completed"
        run.output_json = {"Topic": state["state"]["topic"]}
        self._db.add(run)
        self._db.commit()
        self._db.refresh(run)
        return run

    monkeypatch.setattr(FlowSnapshotExecutor, "_execute_run_path", complete_without_replaying)

    completed = executor.execute_existing_run(run_id=str(run.id), owner_user_id="test-user")
    replayed = executor.execute_existing_run(run_id=str(run.id), owner_user_id="test-user")

    assert observed_statuses == ["executing"]
    assert completed.status == "completed"
    assert replayed.status == "completed"


def test_mark_stale_running_runs_failed(db):
    from api.db.models import FlowRun, FlowRunEvent
    from api.services.run_recovery import mark_stale_running_runs_failed

    running_run = FlowRun(
        id="33333333-3333-4333-8333-333333333333",
        flow_version_id="44444444-4444-4444-8444-444444444444",
        status="running",
        input_json={},
    )
    executing_run = FlowRun(
        id="33333333-3333-4333-8333-333333333334",
        flow_version_id="44444444-4444-4444-8444-444444444444",
        status="executing",
        input_json={},
    )
    completed_run = FlowRun(
        id="33333333-3333-4333-8333-333333333335",
        flow_version_id="44444444-4444-4444-8444-444444444444",
        status="completed",
        input_json={},
        output_json={"ok": True},
    )
    failed_run = FlowRun(
        id="33333333-3333-4333-8333-333333333336",
        flow_version_id="44444444-4444-4444-8444-444444444444",
        status="failed",
        input_json={},
        error_message="existing failure",
    )
    db.add_all([running_run, executing_run, completed_run, failed_run])
    db.commit()

    count = mark_stale_running_runs_failed(db)

    db.expire_all()
    failed_running = db.get(FlowRun, running_run.id)
    failed_executing = db.get(FlowRun, executing_run.id)
    unchanged_completed = db.get(FlowRun, completed_run.id)
    unchanged_failed = db.get(FlowRun, failed_run.id)
    events = (
        db.query(FlowRunEvent)
        .filter(FlowRunEvent.run_id.in_([running_run.id, executing_run.id]))
        .order_by(FlowRunEvent.run_id.asc())
        .all()
    )

    assert count == 2
    assert failed_running.status == "failed"
    assert failed_running.error_message == "Run interrupted before completion. Retry the run."
    assert failed_running.finished_at is not None
    assert failed_executing.status == "failed"
    assert failed_executing.error_message == "Run interrupted before completion. Retry the run."
    assert failed_executing.finished_at is not None
    assert unchanged_completed.status == "completed"
    assert unchanged_completed.error_message is None
    assert unchanged_completed.finished_at is None
    assert unchanged_failed.status == "failed"
    assert unchanged_failed.error_message == "existing failure"
    assert unchanged_failed.finished_at is None
    assert db.query(FlowRunEvent).count() == 2
    assert len(events) == 2
    for event in events:
        assert event.event_type == "run_failed"
        assert event.node_id is None
        assert event.event_payload_json["run_id"] == str(event.run_id)
        assert event.event_payload_json["interrupted"] is True


def test_mark_stale_running_runs_failed_respects_recovery_cutoff(db):
    from api.db.models import FlowRun
    from api.services.run_recovery import mark_stale_running_runs_failed

    cutoff = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)
    active_after_startup = FlowRun(
        id="33333333-3333-4333-8333-333333333337",
        flow_version_id="44444444-4444-4444-8444-444444444444",
        status="executing",
        input_json={},
        updated_at=cutoff,
    )
    db.add(active_after_startup)
    db.commit()

    count = mark_stale_running_runs_failed(db, older_than=cutoff)

    db.expire_all()
    unchanged_run = db.get(FlowRun, active_after_startup.id)
    assert count == 0
    assert unchanged_run.status == "executing"
    assert unchanged_run.finished_at is None
