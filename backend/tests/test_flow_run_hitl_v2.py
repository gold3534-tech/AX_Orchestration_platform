from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from sqlalchemy.orm import sessionmaker

from tests.test_flow_run_skeleton_v2 import _create_published_flow, _install_nano_context_spy


CREW_ASSET_ID = "99999999-9999-9999-9999-999999999999"
CREW_VERSION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VISUAL_CREW_ASSET_ID = "88888888-8888-8888-8888-888888888888"
VISUAL_CREW_VERSION_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _create_published_crew(db) -> None:
    from api.db.models import Asset, AssetRuntimeSnapshot, AssetVersion

    db.add(
        Asset(
            id=CREW_ASSET_ID,
            asset_type="crew",
            owner_user_id="test-user",
            name="Draft Crew",
        )
    )
    db.add(
        AssetVersion(
            id=CREW_VERSION_ID,
            asset_id=CREW_ASSET_ID,
            version_number=1,
            status="published",
            metadata_json={},
            created_by="test-user",
        )
    )
    db.add(
        AssetRuntimeSnapshot(
            version_id=CREW_VERSION_ID,
            runtime_snapshot_json={
                "runtime_crew": {"crew_name": "Draft Crew", "agent_version_ids": [], "task_version_ids": []},
                "runtime_agents": {},
                "runtime_tasks": {},
                "task_agent_links": {},
                "task_tool_links": {},
                "runtime_tools": {},
            },
        )
    )


def _create_published_visual_crew(db) -> None:
    from api.db.models import Asset, AssetRuntimeSnapshot, AssetVersion

    db.add(
        Asset(
            id=VISUAL_CREW_ASSET_ID,
            asset_type="crew",
            owner_user_id="test-user",
            name="Visual Crew",
        )
    )
    db.add(
        AssetVersion(
            id=VISUAL_CREW_VERSION_ID,
            asset_id=VISUAL_CREW_ASSET_ID,
            version_number=1,
            status="published",
            metadata_json={},
            created_by="test-user",
        )
    )
    db.add(
        AssetRuntimeSnapshot(
            version_id=VISUAL_CREW_VERSION_ID,
            runtime_snapshot_json={
                "runtime_crew": {"crew_name": "Visual Crew", "agent_version_ids": [], "task_version_ids": []},
                "runtime_agents": {},
                "runtime_tasks": {},
                "task_agent_links": {},
                "task_tool_links": {},
                "runtime_tools": {},
            },
        )
    )


def _hitl_snapshot(*, max_attempts: int = 3) -> dict:
    return {
        "schemaVersion": 1,
        "graph": {
            "nodes": [
                {"id": "input:main", "type": "input", "data": {}},
                {"id": "start:main", "type": "start", "data": {}},
                {
                    "id": "crew:draft",
                    "type": "crew",
                    "data": {"assetId": CREW_ASSET_ID, "versionId": CREW_VERSION_ID},
                },
                {
                    "id": "hitl:review",
                    "type": "hitl",
                    "data": {"prompt": "Approve the draft?", "maxAttempts": max_attempts},
                },
                {"id": "output:main", "type": "output", "data": {}},
            ],
            "edges": [
                {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
                {"id": "edge:start:crew", "source": "start:main", "target": "crew:draft", "type": "flow"},
                {"id": "edge:crew:hitl", "source": "crew:draft", "target": "hitl:review", "type": "flow"},
                {"id": "edge:hitl:output", "source": "hitl:review", "target": "output:main", "type": "flow"},
            ],
        },
        "crew_refs": [
            {
                "node_id": "crew:draft",
                "asset_id": CREW_ASSET_ID,
                "version_id": CREW_VERSION_ID,
                "latest_version_id": CREW_VERSION_ID,
                "status": "latest",
            }
        ],
        "crew_input_mappings": {
            "crew:draft": {"topic": {"source": "state", "path": "topic"}}
        },
        "hitl_contracts": {
            "hitl:review": {
                "prompt": "Approve the draft?",
                "allowedDecisions": ["approved", "needs_revision", "rejected"],
                "maxAttempts": max_attempts,
            }
        },
        "output_fields": [
            {"label": "Final answer", "source": "node", "nodeId": "crew:draft", "path": "output.final_answer"}
        ],
    }


def _hitl_to_downstream_crew_snapshot(
    *,
    feedback_propagation: str = "needs_revision_only",
    on_needs_revision: str = "continue_with_feedback",
) -> dict:
    snapshot = _hitl_snapshot()
    snapshot["graph"]["nodes"].insert(
        -1,
        {
            "id": "crew:visual",
            "type": "crew",
            "data": {"assetId": VISUAL_CREW_ASSET_ID, "versionId": VISUAL_CREW_VERSION_ID},
        },
    )
    snapshot["graph"]["edges"] = [
        {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
        {"id": "edge:start:crew", "source": "start:main", "target": "crew:draft", "type": "flow"},
        {"id": "edge:crew:hitl", "source": "crew:draft", "target": "hitl:review", "type": "flow"},
        {"id": "edge:hitl:visual", "source": "hitl:review", "target": "crew:visual", "type": "flow"},
        {"id": "edge:visual:output", "source": "crew:visual", "target": "output:main", "type": "flow"},
    ]
    snapshot["crew_refs"].append(
        {
            "node_id": "crew:visual",
            "asset_id": VISUAL_CREW_ASSET_ID,
            "version_id": VISUAL_CREW_VERSION_ID,
            "latest_version_id": VISUAL_CREW_VERSION_ID,
            "status": "latest",
        }
    )
    snapshot["crew_input_mappings"]["crew:visual"] = {"topic": {"source": "state", "path": "topic"}}
    snapshot["hitl_contracts"]["hitl:review"] = {
        "prompt": "Approve the draft?",
        "allowedDecisions": ["approved", "needs_revision", "rejected"],
        "onNeedsRevision": on_needs_revision,
        "feedbackPropagation": feedback_propagation,
        "maxAttempts": 3,
    }
    snapshot["output_fields"] = [
        {"label": "Final answer", "source": "node", "nodeId": "crew:visual", "path": "output.final_answer"}
    ]
    return snapshot


def _replace_flow_runtime_snapshot(db, flow: dict, runtime_snapshot_json: dict) -> None:
    from api.db.models import AssetRuntimeSnapshot

    existing = db.get(AssetRuntimeSnapshot, flow["current_version"]["id"])
    if existing is None:
        existing = AssetRuntimeSnapshot(
            version_id=flow["current_version"]["id"],
            runtime_snapshot_json=runtime_snapshot_json,
        )
    else:
        existing.runtime_snapshot_json = runtime_snapshot_json
    db.add(existing)
    db.commit()


def _execute_background_and_get_detail(client, db, auth_headers, run_body: dict) -> dict:
    from api.services.runs import execute_flow_run_background

    testing_session_local = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    with patch("api.services.runs.SessionLocal", testing_session_local):
        execute_flow_run_background(run_id=run_body["id"], owner_user_id="test-user")
    db.expire_all()
    return client.get(f"/api/flow-runs/{run_body['id']}", headers=auth_headers).json()


@pytest.fixture
def fake_crew(monkeypatch):
    from api.runtime import flow_snapshot_executor as executor_module

    calls = []

    class FakeCrew:
        def kickoff(self, inputs):
            calls.append(inputs)
            if "human_feedback" in inputs:
                return {"final_answer": f"revised {inputs['human_feedback']['feedback']}"}
            return {"final_answer": f"draft {inputs['topic']}"}

    def fake_build_crew(self, **kwargs):
        return FakeCrew()

    monkeypatch.setattr(executor_module.CrewAIFactory, "build_crew", fake_build_crew)
    return calls


def _create_hitl_run(
    client,
    db,
    auth_headers,
    fake_crew,
    *,
    capture_agent_execution_logs=None,
    inputs: dict | None = None,
    max_attempts: int = 3,
):
    _create_published_crew(db)
    flow = _create_published_flow(client, db, auth_headers, name="HITL Flow")
    _replace_flow_runtime_snapshot(db, flow, _hitl_snapshot(max_attempts=max_attempts))

    payload = {
        "flow_version_id": flow["current_version"]["id"],
        "inputs": inputs if inputs is not None else {"topic": "CrewAI"},
    }
    if capture_agent_execution_logs is not None:
        payload["capture_agent_execution_logs"] = capture_agent_execution_logs

    response = client.post("/api/flow-runs", json=payload, headers=auth_headers)
    assert response.status_code == 201
    return _execute_background_and_get_detail(client, db, auth_headers, response.json())


def test_flow_run_node_output_store_versions_outputs(db):
    from api.runtime.node_output_store import NodeOutputStore

    run_id = "11111111-1111-4111-8111-111111111111"
    store = NodeOutputStore(db)

    first_ref = store.store_output(run_id=run_id, node_id="crew:content", output={"draft": "v1"})
    second_ref = store.store_output(run_id=run_id, node_id="crew:content", output={"draft": "v2"})

    assert first_ref == {"node_id": "crew:content", "version": 1}
    assert second_ref == {"node_id": "crew:content", "version": 2}
    assert store.resolve_output(run_id=run_id, ref=first_ref) == {"draft": "v1"}
    assert store.resolve_output(run_id=run_id, ref=second_ref) == {"draft": "v2"}


def test_flow_run_node_output_store_resolve_output_returns_empty_for_invalid_refs(db):
    from api.runtime.node_output_store import NodeOutputStore

    store = NodeOutputStore(db)

    assert store.resolve_output(run_id="11111111-1111-4111-8111-111111111111", ref=None) == {}
    assert store.resolve_output(run_id="11111111-1111-4111-8111-111111111111", ref={}) == {}
    assert (
        store.resolve_output(
            run_id="11111111-1111-4111-8111-111111111111",
            ref={"node_id": "crew:content", "version": "bad"},
        )
        == {}
    )


def test_flow_run_node_output_store_updates_state_current_ref(db):
    from api.runtime.node_output_store import NodeOutputStore

    run_id = "22222222-2222-4222-8222-222222222222"
    state = {"node_outputs": {}, "node_output_versions": {}}
    store = NodeOutputStore(db)

    store.store_output(run_id=run_id, node_id="crew:content", output={"draft": "v1"}, state=state)
    store.store_output(run_id=run_id, node_id="crew:content", output={"draft": "v2"}, state=state)

    assert state["node_outputs"]["crew:content"] == {"draft": "v2"}
    assert state["node_output_refs"]["crew:content"] == {
        "current_version": 2,
        "output_ref": {"node_id": "crew:content", "version": 2},
    }
    assert state["node_output_versions"]["crew:content"] == [
        {"version": 1, "status": "superseded"},
        {"version": 2, "status": "current"},
    ]


def test_hitl_node_pauses_run_and_returns_pending_request(client, db, auth_headers, fake_crew):
    from api.db.models import FlowRunNodeOutput, FlowRunStateSnapshot, HumanFeedbackRequest

    run = _create_hitl_run(client, db, auth_headers, fake_crew)

    assert run["status"] == "waiting_for_human"
    request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()
    assert request.node_id == "hitl:review"
    assert request.status == "pending"
    assert request.attempt_number == 1
    assert request.prompt_json["preview_payload_ref"] == {"node_id": "crew:draft", "version": 1}
    assert "preview_payload" not in request.prompt_json

    output = db.query(FlowRunNodeOutput).filter(FlowRunNodeOutput.run_id == run["id"]).one()
    assert output.node_id == "crew:draft"
    assert output.version == 1
    assert output.output_json == {"final_answer": "draft CrewAI"}

    crew_snapshot_rows = (
        db.query(FlowRunStateSnapshot)
        .filter(FlowRunStateSnapshot.run_id == run["id"], FlowRunStateSnapshot.node_id == "crew:draft")
        .all()
    )
    assert crew_snapshot_rows[0].state_json["node_outputs"]["crew:draft"] == {"final_answer": "draft CrewAI"}
    assert crew_snapshot_rows[0].state_json["node_output_refs"]["crew:draft"] == {
        "current_version": 1,
        "output_ref": {"node_id": "crew:draft", "version": 1},
    }


def test_hitl_request_metadata_is_prompt_free(client, db, auth_headers, fake_crew):
    from api.db.models import HumanFeedbackRequest

    run = _create_hitl_run(client, db, auth_headers, fake_crew)
    request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    assert run["status"] == "waiting_for_human"
    assert request is not None
    assert request.prompt_json["message"] == "HITL이 실행되었습니다. 계속 진행하시겠습니까?"
    assert request.prompt_json["source_node_id"] == "crew:draft"
    assert request.prompt_json["next_node_id"] == "output:main"
    assert request.prompt_json["attempt_number"] == 1
    assert request.prompt_json["retry_count"] == 0
    assert request.prompt_json["max_attempts"] == 3
    assert request.prompt_json["remaining_retries"] == 3
    assert request.prompt_json["method_name"] == "hitl:hitl:review"
    assert "resume_path_index" in request.prompt_json
    assert "prompt" not in request.prompt_json
    assert "allowed_decisions" not in request.prompt_json
    assert "feedback_propagation" not in request.prompt_json
    assert "on_needs_revision" not in request.prompt_json


def test_hitl_request_stores_preview_by_reference(client, db, auth_headers, fake_crew):
    from api.db.models import HumanFeedbackRequest

    run = _create_hitl_run(client, db, auth_headers, fake_crew)
    request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    assert request.prompt_json["preview_payload_ref"] == {"node_id": "crew:draft", "version": 1}
    assert "preview_payload" not in request.prompt_json
    assert request.response_json == {}

    response = client.get(f"/api/flow-runs/{run['id']}", headers=auth_headers)
    assert response.status_code == 200
    prompt_json = response.json()["pending_human_feedback_request"]["prompt_json"]
    assert prompt_json["preview_payload"] == {"final_answer": "draft CrewAI"}


def test_hitl_requested_event_uses_realtime_payload_shape(client, db, auth_headers, fake_crew):
    from api.db.models import FlowRunEvent, HumanFeedbackRequest

    run = _create_hitl_run(client, db, auth_headers, fake_crew)
    request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    event = (
        db.query(FlowRunEvent)
        .filter(FlowRunEvent.run_id == run["id"], FlowRunEvent.event_type == "hitl_requested")
        .one()
    )

    assert event.node_id == "hitl:review"
    assert event.event_payload_json == {
        "type": "hitl_requested",
        "run_id": run["id"],
        "request_id": str(request.id),
        "node_id": "hitl:review",
        "source_node_id": "crew:draft",
        "next_node_id": "output:main",
        "message": "HITL이 실행되었습니다. 계속 진행하시겠습니까?",
        "preview_payload_ref": {"node_id": "crew:draft", "version": 1},
        "retry_count": 0,
        "max_attempts": 3,
        "remaining_retries": 3,
    }


def test_get_flow_run_detail_returns_pending_hitl_request(client, db, auth_headers, fake_crew):
    run = _create_hitl_run(client, db, auth_headers, fake_crew)

    response = client.get(f"/api/flow-runs/{run['id']}", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == run["id"]
    assert body["status"] == "waiting_for_human"
    assert body["input_json"] == {"topic": "CrewAI"}
    assert body["pending_human_feedback_request"]["node_id"] == "hitl:review"
    assert body["pending_human_feedback_request"]["attempt_number"] == 1
    assert body["pending_human_feedback_request"]["expires_at"] is None
    assert body["pending_human_feedback_request"]["resolved_by"] is None
    assert body["pending_human_feedback_request"]["idempotency_key"] is None
    prompt_json = body["pending_human_feedback_request"]["prompt_json"]
    assert prompt_json["preview_payload_ref"] == {"node_id": "crew:draft", "version": 1}
    assert prompt_json["preview_payload"] == {"final_answer": "draft CrewAI"}


def test_hitl_runtime_does_not_special_case_additional_details_token(client, db, auth_headers, fake_crew):
    run = _create_hitl_run(
        client,
        db,
        auth_headers,
        fake_crew,
        inputs={"topic": "CrewAI", "additional_details": "Use concrete launch examples"},
    )

    response = client.get(f"/api/flow-runs/{run['id']}", headers=auth_headers)

    assert response.status_code == 200
    prompt_json = response.json()["pending_human_feedback_request"]["prompt_json"]
    assert "additional_details" not in prompt_json
    assert "human_feedback" not in prompt_json


def test_approved_feedback_completes_run(client, db, auth_headers, fake_crew):
    from api.db.models import FlowRunEvent, FlowRunStateSnapshot, HumanFeedbackRequest

    run = _create_hitl_run(client, db, auth_headers, fake_crew)
    request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(request.id), "outcome": "approved", "feedback": "Looks good"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["output_json"] == {"Final answer": "draft CrewAI"}
    db.refresh(request)
    assert request.status == "resolved"
    assert request.response_json["outcome"] == "approved"
    assert request.response_json["previous_output_ref"] == {"node_id": "crew:draft", "version": 1}
    assert "output" not in request.response_json

    output_snapshot = (
        db.query(FlowRunStateSnapshot)
        .filter(FlowRunStateSnapshot.run_id == run["id"], FlowRunStateSnapshot.node_id == "output:main")
        .one()
    )
    assert output_snapshot.state_json["output"] == {"Final answer": "draft CrewAI"}

    run_completed_event = (
        db.query(FlowRunEvent)
        .filter(FlowRunEvent.run_id == run["id"], FlowRunEvent.event_type == "run_completed")
        .one()
    )
    assert run_completed_event.node_id == "output:main"
    assert run_completed_event.event_payload_json == {"output": {"Final answer": "draft CrewAI"}}


def test_hitl_request_ignores_legacy_allowed_decisions_metadata(client, db, auth_headers, fake_crew):
    from api.db.models import HumanFeedbackRequest

    _create_published_crew(db)
    flow = _create_published_flow(client, db, auth_headers, name="HITL Decision Flow")
    snapshot = _hitl_snapshot()
    snapshot["hitl_contracts"]["hitl:review"]["allowedDecisions"] = ["approved", "rejected"]
    _replace_flow_runtime_snapshot(db, flow, snapshot)

    run = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "CrewAI"}},
        headers=auth_headers,
    ).json()
    run = _execute_background_and_get_detail(client, db, auth_headers, run)
    request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()
    assert "allowed_decisions" not in request.prompt_json

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(request.id), "outcome": "needs_revision", "feedback": "Retry anyway"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "waiting_for_human"
    db.refresh(request)
    assert request.status == "resolved"
    assert request.response_json["outcome"] == "needs_revision"


def test_approve_without_feedback_continues_without_human_feedback(client, db, auth_headers, monkeypatch):
    from api.db import models
    from api.runtime import flow_snapshot_executor as executor_module

    seen_inputs = []

    class FakeCrew:
        def kickoff(self, inputs):
            seen_inputs.append(inputs)
            if len(seen_inputs) == 1:
                return {"final_answer": "draft CrewAI"}
            return {"final_answer": f"visual {inputs.get('topic')}"}

    monkeypatch.setattr(executor_module.CrewAIFactory, "build_crew", lambda self, **kwargs: FakeCrew())
    _create_published_crew(db)
    _create_published_visual_crew(db)
    flow = _create_published_flow(client, db, auth_headers, name="HITL Downstream Flow")
    _replace_flow_runtime_snapshot(
        db,
        flow,
        _hitl_to_downstream_crew_snapshot(feedback_propagation="needs_revision_only"),
    )
    run = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "CrewAI"}},
        headers=auth_headers,
    ).json()
    run = _execute_background_and_get_detail(client, db, auth_headers, run)
    request = db.query(models.HumanFeedbackRequest).filter_by(run_id=run["id"]).one()

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(request.id), "outcome": "approved", "feedback": ""},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["output_json"] == {"Final answer": "visual CrewAI"}
    assert "human_feedback" not in seen_inputs[-1]


def test_approved_feedback_downstream_crew_installs_nano_context(client, db, auth_headers, monkeypatch):
    from api.db import models
    from api.runtime import flow_snapshot_executor as executor_module

    _context_calls, active_contexts = _install_nano_context_spy(monkeypatch)
    observed_contexts = []

    class FakeCrew:
        def kickoff(self, inputs):
            observed_contexts.append(dict(active_contexts[-1]) if active_contexts else None)
            if len(observed_contexts) == 1:
                return {"final_answer": "draft CrewAI"}
            return {"final_answer": f"visual {inputs.get('topic')}"}

    monkeypatch.setattr(executor_module.CrewAIFactory, "build_crew", lambda self, **kwargs: FakeCrew())
    _create_published_crew(db)
    _create_published_visual_crew(db)
    flow = _create_published_flow(client, db, auth_headers, name="HITL Nano Context Flow")
    _replace_flow_runtime_snapshot(
        db,
        flow,
        _hitl_to_downstream_crew_snapshot(feedback_propagation="needs_revision_only"),
    )
    run = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "CrewAI"}},
        headers=auth_headers,
    ).json()
    run = _execute_background_and_get_detail(client, db, auth_headers, run)
    request = db.query(models.HumanFeedbackRequest).filter_by(run_id=run["id"]).one()

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(request.id), "outcome": "approved", "feedback": ""},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert [context["node_id"] for context in observed_contexts] == ["crew:draft", "crew:visual"]
    assert observed_contexts[-1]["db"] is not None
    assert {
        key: observed_contexts[-1][key]
        for key in ("owner_user_id", "run_id", "node_id")
    } == {
        "owner_user_id": "test-user",
        "run_id": run["id"],
        "node_id": "crew:visual",
    }


def test_hitl_approved_downstream_failure_marks_run_failed(client, db, auth_headers, monkeypatch):
    from api.db import models
    from api.runtime import flow_snapshot_executor as executor_module

    seen_inputs = []

    class FakeCrew:
        def kickoff(self, inputs):
            seen_inputs.append(inputs)
            if len(seen_inputs) == 1:
                return {"final_answer": "draft CrewAI"}
            raise RuntimeError("visual boom")

    monkeypatch.setattr(executor_module.CrewAIFactory, "build_crew", lambda self, **kwargs: FakeCrew())
    _create_published_crew(db)
    _create_published_visual_crew(db)
    flow = _create_published_flow(client, db, auth_headers, name="HITL Downstream Failure Flow")
    _replace_flow_runtime_snapshot(db, flow, _hitl_to_downstream_crew_snapshot())
    run = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "CrewAI"}},
        headers=auth_headers,
    ).json()
    run = _execute_background_and_get_detail(client, db, auth_headers, run)
    request = db.query(models.HumanFeedbackRequest).filter_by(run_id=run["id"]).one()

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(request.id), "outcome": "approved", "feedback": ""},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    db.refresh(request)
    assert request.status == "resolved"

    detail = client.get(f"/api/flow-runs/{run['id']}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["pending_human_feedback_request"] is None

    run_failed_event = (
        db.query(models.FlowRunEvent)
        .filter(models.FlowRunEvent.run_id == run["id"], models.FlowRunEvent.event_type == "run_failed")
        .one()
    )
    assert run_failed_event.node_id == "crew:visual"
    assert "visual boom" in run_failed_event.event_payload_json["error"]


def test_approve_with_feedback_injects_human_feedback_into_next_crew(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from api.db import models
    from api.runtime import flow_snapshot_executor as executor_module

    seen_inputs = []

    class FakeCrew:
        def kickoff(self, inputs):
            seen_inputs.append(inputs)
            if len(seen_inputs) == 1:
                return {"final_answer": "draft CrewAI"}
            return {"final_answer": f"visual {inputs['human_feedback']['feedback']}"}

    monkeypatch.setattr(executor_module.CrewAIFactory, "build_crew", lambda self, **kwargs: FakeCrew())
    _create_published_crew(db)
    _create_published_visual_crew(db)
    flow = _create_published_flow(client, db, auth_headers, name="HITL Continue Flow")
    _replace_flow_runtime_snapshot(
        db,
        flow,
        _hitl_to_downstream_crew_snapshot(),
    )
    run = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "CrewAI"}},
        headers=auth_headers,
    ).json()
    run = _execute_background_and_get_detail(client, db, auth_headers, run)
    request = db.query(models.HumanFeedbackRequest).filter_by(run_id=run["id"]).one()

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(request.id), "outcome": "approved", "feedback": "Looks good"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert len(seen_inputs) == 2
    feedback = seen_inputs[-1]["human_feedback"]
    assert feedback["outcome"] == "approved"
    assert feedback["feedback"] == "Looks good"
    assert feedback["previous_output_ref"] == {"node_id": "crew:draft", "version": 1}
    assert feedback["retry_count"] == 0
    assert feedback["remaining_retries"] == 3


def test_approve_with_feedback_downstream_failure_redacts_feedback_values(client, db, auth_headers, monkeypatch):
    from api.db import models
    from api.runtime import flow_snapshot_executor as executor_module

    seen_inputs = []

    class FakeCrew:
        def kickoff(self, inputs):
            seen_inputs.append(inputs)
            if len(seen_inputs) == 1:
                return {"final_answer": "draft CrewAI"}
            raise RuntimeError(f"visual fail {inputs['topic']} {inputs['human_feedback']['feedback']}")

    monkeypatch.setattr(executor_module.CrewAIFactory, "build_crew", lambda self, **kwargs: FakeCrew())
    _create_published_crew(db)
    _create_published_visual_crew(db)
    flow = _create_published_flow(client, db, auth_headers, name="HITL Continue Failure Flow")
    _replace_flow_runtime_snapshot(db, flow, _hitl_to_downstream_crew_snapshot())
    run = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "CrewAI"}},
        headers=auth_headers,
    ).json()
    run = _execute_background_and_get_detail(client, db, auth_headers, run)
    request = db.query(models.HumanFeedbackRequest).filter_by(run_id=run["id"]).one()

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(request.id), "outcome": "approved", "feedback": "Looks good"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"

    db.expire_all()
    failed_run = db.get(models.FlowRun, run["id"])
    assert failed_run.error_message is not None
    assert "[redacted]" in failed_run.error_message
    assert "CrewAI" not in failed_run.error_message
    assert "Looks good" not in failed_run.error_message

    run_failed_event = (
        db.query(models.FlowRunEvent)
        .filter(models.FlowRunEvent.run_id == run["id"], models.FlowRunEvent.event_type == "run_failed")
        .one()
    )
    event_error = run_failed_event.event_payload_json["error"]
    assert "[redacted]" in event_error
    assert "CrewAI" not in event_error
    assert "Looks good" not in event_error


def test_google_sheets_oauth_token_is_redacted_from_crew_failure_events(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from cryptography.fernet import Fernet

    from api.db import models
    from api.integrations.google_workspace import GOOGLE_SHEETS_SCOPE
    from api.runtime import flow_snapshot_executor as executor_module
    from api.runtime.credential_store import encrypt_secret_payload

    access_token = "sheets-access-token-secret"
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    openai_credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="openai",
        label="OpenAI",
        secret_ref="",
        scopes_json=[],
        status="active",
        metadata_json={},
    )
    db.add(openai_credential)
    db.flush()
    openai_credential.secret_ref = f"secret://db/credential/{openai_credential.id}"
    db.add(
        models.CredentialSecret(
            credential_id=openai_credential.id,
            encrypted_secret_json=encrypt_secret_payload({"api_key": "runtime-openai"}),
            encryption_key_version="v1",
        )
    )
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="google_workspace",
        auth_type="oauth2",
        label="Google Workspace",
        provider_account_id="google-account-1",
        provider_account_label="creator@example.com",
        scopes_json=[GOOGLE_SHEETS_SCOPE],
        status="active",
        metadata_json={},
        secret_ref="",
    )
    db.add(credential)
    db.flush()
    credential.secret_ref = f"secret://db/credential/{credential.id}"
    db.add(
        models.CredentialSecret(
            credential_id=credential.id,
            encrypted_secret_json=encrypt_secret_payload({"access_token": access_token}),
            encryption_key_version="v1",
        )
    )

    _create_published_crew(db)
    db.flush()
    crew_snapshot = (
        db.query(models.AssetRuntimeSnapshot)
        .filter(models.AssetRuntimeSnapshot.version_id == CREW_VERSION_ID)
        .one()
    )
    crew_snapshot.runtime_snapshot_json = {
        "runtime_crew": {
            "crew_name": "Sheets Crew",
            "agent_version_ids": ["agent:sheets"],
            "task_version_ids": ["task:sheets"],
        },
        "runtime_agents": {
            "agent:sheets": {
                "role": "Sheets operator",
                "goal": "Use Sheets.",
                "backstory": "Uses a connected account.",
            }
        },
        "runtime_tasks": {
            "task:sheets": {
                "description": "Use Sheets.",
                "expected_output": "A result.",
            }
        },
        "task_agent_links": {"task:sheets": "agent:sheets"},
        "agent_tool_links": {"agent:sheets": ["custom.sheets_alias"]},
        "task_tool_links": {},
        "runtime_tools": {
            "custom.sheets_alias": {
                "tool_key": "custom.sheets_alias",
                "module_path": "api.tools.google_sheets_tool",
                "class_name": "AXGoogleSheetsTool",
                "credential_requirements": [
                    {
                        "provider": "google_workspace",
                        "env_var": "AX_GOOGLE_WORKSPACE_OAUTH",
                        "required": True,
                        "injection": "runtime_context",
                    }
                ],
            }
        },
    }
    db.add(crew_snapshot)
    db.commit()

    class FakeCrew:
        def kickoff(self, inputs):
            raise RuntimeError(f"Sheets API failed with bearer {access_token}")

    monkeypatch.setattr(
        executor_module.CrewAIFactory,
        "build_crew",
        lambda self, **kwargs: FakeCrew(),
    )

    flow = _create_published_flow(client, db, auth_headers, name="Sheets Redaction Flow")
    _replace_flow_runtime_snapshot(db, flow, _hitl_snapshot())
    run = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "CrewAI"}},
        headers=auth_headers,
    ).json()
    detail = _execute_background_and_get_detail(client, db, auth_headers, run)

    assert detail["status"] == "failed"
    db.expire_all()
    failed_run = db.get(models.FlowRun, run["id"])
    assert failed_run.error_message is not None
    assert "[redacted]" in failed_run.error_message
    assert access_token not in failed_run.error_message

    events = (
        db.query(models.FlowRunEvent)
        .filter(models.FlowRunEvent.run_id == run["id"])
        .all()
    )
    serialized_events = str([event.event_payload_json for event in events])
    assert "[redacted]" in serialized_events
    assert access_token not in serialized_events


def test_approve_with_feedback_next_output_does_not_inject_into_any_crew(client, db, auth_headers, fake_crew):
    from api.db.models import HumanFeedbackRequest

    run = _create_hitl_run(client, db, auth_headers, fake_crew)
    request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(request.id), "outcome": "approved", "feedback": "Looks good"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert len(fake_crew) == 1
    assert "human_feedback" not in fake_crew[0]


def test_approve_with_feedback_ignores_legacy_feedback_propagation_policy(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from api.db import models
    from api.runtime import flow_snapshot_executor as executor_module

    seen_inputs = []

    class FakeCrew:
        def kickoff(self, inputs):
            seen_inputs.append(inputs)
            if len(seen_inputs) == 1:
                return {"final_answer": "draft CrewAI"}
            return {"final_answer": f"visual {inputs['human_feedback']['outcome']}"}

    monkeypatch.setattr(executor_module.CrewAIFactory, "build_crew", lambda self, **kwargs: FakeCrew())
    _create_published_crew(db)
    _create_published_visual_crew(db)
    flow = _create_published_flow(client, db, auth_headers, name="HITL Legacy Feedback Policy Flow")
    _replace_flow_runtime_snapshot(
        db,
        flow,
        _hitl_to_downstream_crew_snapshot(feedback_propagation="none"),
    )
    run = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "CrewAI"}},
        headers=auth_headers,
    ).json()
    run = _execute_background_and_get_detail(client, db, auth_headers, run)
    request = db.query(models.HumanFeedbackRequest).filter_by(run_id=run["id"]).one()

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(request.id), "outcome": "approved", "feedback": "Looks good"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert seen_inputs[-1]["human_feedback"]["outcome"] == "approved"
    assert seen_inputs[-1]["human_feedback"]["feedback"] == "Looks good"


def test_retry_reruns_previous_crew_and_creates_new_pending_request(client, db, auth_headers, fake_crew):
    from api.db.models import FlowRunEvent, FlowRunNodeOutput, HumanFeedbackRequest

    run = _create_hitl_run(client, db, auth_headers, fake_crew)
    first_request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(first_request.id), "outcome": "needs_revision", "feedback": "Make it sharper"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "waiting_for_human"
    db.refresh(first_request)
    assert first_request.response_json["previous_output_ref"] == {"node_id": "crew:draft", "version": 1}
    assert "output" not in first_request.response_json
    assert fake_crew[-1]["human_feedback"]["outcome"] == "needs_revision"
    assert fake_crew[-1]["human_feedback"]["feedback"] == "Make it sharper"
    assert fake_crew[-1]["human_feedback"]["previous_output_ref"] == {"node_id": "crew:draft", "version": 1}
    assert fake_crew[-1]["human_feedback"]["retry_count"] == 0
    assert fake_crew[-1]["human_feedback"]["remaining_retries"] == 3
    assert "previous_output" not in fake_crew[-1]["human_feedback"]

    retry_event = (
        db.query(FlowRunEvent)
        .filter(FlowRunEvent.run_id == run["id"], FlowRunEvent.event_type == "crew_retry_started")
        .one()
    )
    payload = retry_event.event_payload_json
    assert payload["inputs"]["topic"] == {"type": "text", "length": len("CrewAI")}
    assert payload["inputs"]["human_feedback"] == {
        "type": "object",
        "keys": [
            "feedback",
            "outcome",
            "previous_output_ref",
            "remaining_retries",
            "retry_count",
            "source_hitl_node_id",
            "source_node_id",
        ],
    }
    assert "Make it sharper" not in str(payload)
    assert "draft CrewAI" not in str(payload)

    requests = (
        db.query(HumanFeedbackRequest)
        .filter(HumanFeedbackRequest.run_id == run["id"])
        .order_by(HumanFeedbackRequest.created_at.asc(), HumanFeedbackRequest.id.asc())
        .all()
    )
    assert [request.prompt_json["attempt_number"] for request in requests] == [1, 2]
    assert [request.prompt_json["retry_count"] for request in requests] == [0, 1]
    assert [request.prompt_json["remaining_retries"] for request in requests] == [3, 2]
    assert requests[-1].prompt_json["preview_payload_ref"] == {"node_id": "crew:draft", "version": 2}
    assert "preview_payload" not in requests[-1].prompt_json

    output_rows = (
        db.query(FlowRunNodeOutput)
        .filter(FlowRunNodeOutput.run_id == run["id"], FlowRunNodeOutput.node_id == "crew:draft")
        .order_by(FlowRunNodeOutput.version.asc())
        .all()
    )
    assert [(row.version, row.status) for row in output_rows] == [(1, "superseded"), (2, "current")]


def test_needs_revision_retry_installs_nano_context(client, db, auth_headers, monkeypatch):
    from api.db.models import HumanFeedbackRequest
    from api.runtime import flow_snapshot_executor as executor_module

    _context_calls, active_contexts = _install_nano_context_spy(monkeypatch)
    observed_contexts = []

    class FakeCrew:
        def kickoff(self, inputs):
            observed_contexts.append(dict(active_contexts[-1]) if active_contexts else None)
            if "human_feedback" in inputs:
                return {"final_answer": f"revised {inputs['human_feedback']['feedback']}"}
            return {"final_answer": f"draft {inputs['topic']}"}

    monkeypatch.setattr(executor_module.CrewAIFactory, "build_crew", lambda self, **kwargs: FakeCrew())
    _create_published_crew(db)
    flow = _create_published_flow(client, db, auth_headers, name="HITL Retry Nano Context Flow")
    _replace_flow_runtime_snapshot(db, flow, _hitl_snapshot())
    run = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "CrewAI"}},
        headers=auth_headers,
    ).json()
    run = _execute_background_and_get_detail(client, db, auth_headers, run)
    first_request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(first_request.id), "outcome": "needs_revision", "feedback": "Make it sharper"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "waiting_for_human"
    assert [context["node_id"] for context in observed_contexts] == ["crew:draft", "crew:draft"]
    assert observed_contexts[-1]["db"] is not None
    assert {
        key: observed_contexts[-1][key]
        for key in ("owner_user_id", "run_id", "node_id")
    } == {
        "owner_user_id": "test-user",
        "run_id": run["id"],
        "node_id": "crew:draft",
    }


def test_retry_without_feedback_reruns_previous_crew_without_human_feedback(client, db, auth_headers, monkeypatch):
    from api.db.models import HumanFeedbackRequest
    from api.runtime import flow_snapshot_executor as executor_module

    seen_inputs = []

    class FakeCrew:
        def kickoff(self, inputs):
            seen_inputs.append(inputs)
            return {"final_answer": f"draft {inputs['topic']}"}

    monkeypatch.setattr(executor_module.CrewAIFactory, "build_crew", lambda self, **kwargs: FakeCrew())

    run = _create_hitl_run(client, db, auth_headers, fake_crew=None)
    first_request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(first_request.id), "outcome": "needs_revision", "feedback": "   "},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "waiting_for_human"
    assert len(seen_inputs) == 2
    assert "human_feedback" not in seen_inputs[-1]


def test_needs_revision_retry_failure_keeps_request_resolved_and_marks_run_failed(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from api.db.models import FlowRun, FlowRunEvent, FlowRunStateSnapshot, HumanFeedbackRequest
    from api.runtime import flow_snapshot_executor as executor_module

    class FakeCrew:
        def kickoff(self, inputs):
            if "human_feedback" in inputs:
                raise RuntimeError(f"retry failed {inputs['topic']} {inputs['human_feedback']['feedback']}")
            return {"final_answer": f"draft {inputs['topic']}"}

    monkeypatch.setattr(executor_module.CrewAIFactory, "build_crew", lambda self, **kwargs: FakeCrew())

    run = _create_hitl_run(client, db, auth_headers, fake_crew=None)
    first_request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(first_request.id), "outcome": "needs_revision", "feedback": "Make it sharper"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    db.expire_all()
    resolved_request = db.get(HumanFeedbackRequest, first_request.id)
    assert resolved_request.status == "resolved"
    assert resolved_request.response_json["outcome"] == "needs_revision"

    failed_run = db.get(FlowRun, run["id"])
    assert failed_run.status == "failed"
    assert failed_run.error_message is not None
    assert "[redacted]" in failed_run.error_message
    assert "CrewAI" not in failed_run.error_message
    assert "Make it sharper" not in failed_run.error_message

    detail = client.get(f"/api/flow-runs/{run['id']}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["pending_human_feedback_request"] is None

    failed_event = (
        db.query(FlowRunEvent)
        .filter(FlowRunEvent.run_id == run["id"], FlowRunEvent.event_type == "run_failed")
        .one()
    )
    assert failed_event.node_id == "crew:draft"
    assert "[redacted]" in failed_event.event_payload_json["error"]
    assert "CrewAI" not in failed_event.event_payload_json["error"]
    assert "Make it sharper" not in failed_event.event_payload_json["error"]

    failed_snapshot = (
        db.query(FlowRunStateSnapshot)
        .filter(FlowRunStateSnapshot.run_id == run["id"], FlowRunStateSnapshot.node_id == "crew:draft")
        .order_by(FlowRunStateSnapshot.created_at.desc(), FlowRunStateSnapshot.id.desc())
        .first()
    )
    assert failed_snapshot is not None
    assert "output" not in failed_snapshot.state_json["human_feedback_history"][-1]
    assert failed_snapshot.state_json["human_feedback_history"][-1]["feedback"] == "[redacted]"
    assert "Make it sharper" not in str(failed_snapshot.state_json)


def test_needs_revision_retry_versions_output_before_retry_snapshot_without_duplicate_rows(
    client,
    db,
    auth_headers,
    fake_crew,
):
    from api.db.models import FlowRunNodeOutput, FlowRunStateSnapshot, HumanFeedbackRequest

    run = _create_hitl_run(client, db, auth_headers, fake_crew)
    first_request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(first_request.id), "outcome": "needs_revision", "feedback": "Make it sharper"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    crew_snapshots = (
        db.query(FlowRunStateSnapshot)
        .filter(FlowRunStateSnapshot.run_id == run["id"], FlowRunStateSnapshot.node_id == "crew:draft")
        .order_by(FlowRunStateSnapshot.created_at.asc(), FlowRunStateSnapshot.id.asc())
        .all()
    )
    assert len(crew_snapshots) == 2
    retry_state = crew_snapshots[-1].state_json
    assert retry_state["node_outputs"]["crew:draft"] == {"final_answer": "revised Make it sharper"}
    assert retry_state["node_output_refs"]["crew:draft"] == {
        "current_version": 2,
        "output_ref": {"node_id": "crew:draft", "version": 2},
    }
    assert retry_state["node_output_versions"]["crew:draft"] == [
        {"version": 1, "status": "superseded"},
        {"version": 2, "status": "current"},
    ]

    output_rows = (
        db.query(FlowRunNodeOutput)
        .filter(FlowRunNodeOutput.run_id == run["id"], FlowRunNodeOutput.node_id == "crew:draft")
        .order_by(FlowRunNodeOutput.version.asc())
        .all()
    )
    assert [(row.version, row.output_json, row.status) for row in output_rows] == [
        (1, {"final_answer": "draft CrewAI"}, "superseded"),
        (2, {"final_answer": "revised Make it sharper"}, "current"),
    ]


def test_retry_budget_exhaustion_keeps_run_waiting_and_rejects_retry_action(
    client,
    db,
    auth_headers,
    fake_crew,
):
    from api.db.models import FlowRunNodeOutput, HumanFeedbackRequest

    run = _create_hitl_run(client, db, auth_headers, fake_crew, max_attempts=3)
    first_request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()
    assert first_request.prompt_json["retry_count"] == 0
    assert first_request.prompt_json["remaining_retries"] == 3

    current_request = first_request
    for retry_number in range(1, 4):
        accepted_revision = client.post(
            f"/api/flow-runs/{run['id']}/human-feedback",
            json={
                "request_id": str(current_request.id),
                "outcome": "needs_revision",
                "feedback": f"Revision {retry_number}",
            },
            headers=auth_headers,
        )
        assert accepted_revision.status_code == 200
        current_request = (
            db.query(HumanFeedbackRequest)
            .filter(HumanFeedbackRequest.run_id == run["id"], HumanFeedbackRequest.status == "pending")
            .one()
        )
        assert current_request.prompt_json["retry_count"] == retry_number
        assert current_request.prompt_json["remaining_retries"] == 3 - retry_number

    blocked_revision = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(current_request.id), "outcome": "needs_revision", "feedback": "One more"},
        headers=auth_headers,
    )

    assert blocked_revision.status_code == 422
    assert "Retry budget has been exhausted" in blocked_revision.json()["detail"]
    db.refresh(current_request)
    assert current_request.status == "pending"
    detail = client.get(f"/api/flow-runs/{run['id']}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["status"] == "waiting_for_human"
    assert detail.json()["pending_human_feedback_request"]["id"] == str(current_request.id)
    output_rows = (
        db.query(FlowRunNodeOutput)
        .filter(FlowRunNodeOutput.run_id == run["id"], FlowRunNodeOutput.node_id == "crew:draft")
        .order_by(FlowRunNodeOutput.version.asc())
        .all()
    )
    assert [row.version for row in output_rows] == [1, 2, 3, 4]


def test_stale_retry_on_resolved_exhausted_request_returns_conflict(client, db, auth_headers, fake_crew):
    from api.db.models import HumanFeedbackRequest

    run = _create_hitl_run(client, db, auth_headers, fake_crew, max_attempts=1)
    first_request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    accepted_revision = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(first_request.id), "outcome": "needs_revision", "feedback": "Revision"},
        headers=auth_headers,
    )
    assert accepted_revision.status_code == 200

    exhausted_request = (
        db.query(HumanFeedbackRequest)
        .filter(HumanFeedbackRequest.run_id == run["id"], HumanFeedbackRequest.status == "pending")
        .one()
    )
    assert exhausted_request.prompt_json["remaining_retries"] == 0

    resolved_response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(exhausted_request.id), "outcome": "approved", "feedback": ""},
        headers=auth_headers,
    )
    assert resolved_response.status_code == 200

    stale_retry = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(exhausted_request.id), "outcome": "needs_revision", "feedback": "Too late"},
        headers=auth_headers,
    )

    assert stale_retry.status_code == 409


def test_needs_revision_retry_captures_agent_execution_log_events(client, db, auth_headers, monkeypatch):
    from crewai.agents.parser import AgentAction
    from api.db.models import FlowRunEvent, HumanFeedbackRequest
    from api.runtime import flow_snapshot_executor as executor_module

    build_callbacks = []

    class FakeCrew:
        def __init__(self, callbacks):
            self.callbacks = callbacks

        def kickoff(self, inputs):
            if self.callbacks is not None:
                label = "retry" if "human_feedback" in inputs else "initial"
                self.callbacks["step_callback"](
                    AgentAction(
                        thought=f"{label} thought",
                        tool="revise_draft",
                        tool_input=label,
                        text=f"Thought: {label}",
                    )
                )
            if "human_feedback" in inputs:
                return {"final_answer": f"revised {inputs['human_feedback']['feedback']}"}
            return {"final_answer": f"draft {inputs['topic']}"}

    def fake_build_crew(self, **kwargs):
        build_callbacks.append(kwargs.get("instrumentation_callbacks"))
        return FakeCrew(kwargs.get("instrumentation_callbacks"))

    monkeypatch.setattr(executor_module.CrewAIFactory, "build_crew", fake_build_crew)

    run = _create_hitl_run(client, db, auth_headers, fake_crew=None)
    first_request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(first_request.id), "outcome": "needs_revision", "feedback": "Make it sharper"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert len(build_callbacks) == 2
    assert build_callbacks[1] is not None

    agent_events = (
        db.query(FlowRunEvent)
        .filter(FlowRunEvent.run_id == run["id"], FlowRunEvent.event_type == "agent_step")
        .order_by(FlowRunEvent.created_at.asc(), FlowRunEvent.id.asc())
        .all()
    )
    assert [event.event_payload_json["tool_input"] for event in agent_events] == ["initial", "retry"]
    assert all(event.node_id == "crew:draft" for event in agent_events)


def test_needs_revision_retry_redacts_feedback_values_from_callback_events(client, db, auth_headers, monkeypatch):
    from api.db.models import FlowRunEvent, HumanFeedbackRequest
    from api.runtime import flow_snapshot_executor as executor_module

    class FakeCrew:
        def __init__(self, callbacks):
            self.callbacks = callbacks

        def kickoff(self, inputs):
            if "human_feedback" in inputs:
                rendered = (
                    f"{inputs['topic']} / "
                    f"{inputs['human_feedback']['feedback']} / "
                    f"{inputs['human_feedback']['previous_output_ref'].get('node_id', '')}"
                )
                self.callbacks["step_callback"]({"output": rendered})
                return {"final_answer": f"revised {inputs['human_feedback']['feedback']}"}
            return {"final_answer": f"draft {inputs['topic']}"}

    def fake_build_crew(self, **kwargs):
        return FakeCrew(kwargs.get("instrumentation_callbacks"))

    monkeypatch.setattr(executor_module.CrewAIFactory, "build_crew", fake_build_crew)

    run = _create_hitl_run(client, db, auth_headers, fake_crew=None)
    first_request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(first_request.id), "outcome": "needs_revision", "feedback": "Make it sharper"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    callback_event = (
        db.query(FlowRunEvent)
        .filter(FlowRunEvent.run_id == run["id"], FlowRunEvent.event_type == "agent_finish")
        .one()
    )

    assert callback_event.event_payload_json["output"] == "[redacted] / [redacted] / [redacted]"
    assert "CrewAI" not in str(callback_event.event_payload_json)
    assert "Make it sharper" not in str(callback_event.event_payload_json)
    assert "draft CrewAI" not in str(callback_event.event_payload_json)


def test_needs_revision_retry_preserves_disabled_agent_execution_log_capture(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from api.db.models import HumanFeedbackRequest
    from api.runtime import flow_snapshot_executor as executor_module

    build_callbacks = []

    class FakeCrew:
        def kickoff(self, inputs):
            if "human_feedback" in inputs:
                return {"final_answer": f"revised {inputs['human_feedback']['feedback']}"}
            return {"final_answer": f"draft {inputs['topic']}"}

    def fake_build_crew(self, **kwargs):
        build_callbacks.append(kwargs.get("instrumentation_callbacks"))
        return FakeCrew()

    monkeypatch.setattr(executor_module.CrewAIFactory, "build_crew", fake_build_crew)

    run = _create_hitl_run(
        client,
        db,
        auth_headers,
        fake_crew=None,
        capture_agent_execution_logs=False,
    )
    first_request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(first_request.id), "outcome": "needs_revision", "feedback": "Make it sharper"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert build_callbacks == [None, None]


def test_needs_revision_retry_wraps_crew_run_with_resolved_credential_env(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from cryptography.fernet import Fernet

    from api.db import models
    from api.runtime import flow_snapshot_executor as executor_module
    from api.runtime.credential_store import encrypt_secret_payload

    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    for provider, api_key in (("openai", "runtime-openai"), ("serper", "serper-secret")):
        credential = models.Credential(
            owner_type="user",
            owner_user_id="test-user",
            workspace_id=None,
            provider=provider,
            label=f"{provider} key",
            secret_ref="",
            scopes_json=[],
            status="active",
        )
        db.add(credential)
        db.flush()
        credential.secret_ref = f"secret://db/credential/{credential.id}"
        db.add(
            models.CredentialSecret(
                credential_id=credential.id,
                encrypted_secret_json=encrypt_secret_payload({"api_key": api_key}),
                encryption_key_version="v1",
            )
        )

    _create_published_crew(db)
    db.flush()
    crew_snapshot = (
        db.query(models.AssetRuntimeSnapshot)
        .filter(models.AssetRuntimeSnapshot.version_id == CREW_VERSION_ID)
        .one()
    )
    crew_snapshot.runtime_snapshot_json = {
        "runtime_crew": {
            "crew_name": "Draft Crew",
            "agent_version_ids": ["agent:research"],
            "task_version_ids": ["task:draft"],
        },
        "runtime_agents": {
            "agent:research": {
                "role": "Researcher",
                "goal": "Draft",
                "backstory": "Uses search.",
                "llm": {"provider": "openai", "model": "gpt-4o-mini"},
            }
        },
        "runtime_tasks": {
            "task:draft": {
                "description": "Draft.",
                "expected_output": "Draft.",
            }
        },
        "task_agent_links": {"task:draft": "agent:research"},
        "agent_tool_links": {"agent:research": ["crewai.serper_dev"]},
        "task_tool_links": {},
        "runtime_tools": {
            "crewai.serper_dev": {
                "tool_key": "crewai.serper_dev",
                "credential_requirements": [
                    {
                        "provider": "serper",
                        "env_var": "SERPER_API_KEY",
                        "required": True,
                        "injection": "env",
                    }
                ],
            }
        },
    }
    db.add(crew_snapshot)
    db.commit()

    observed_env = []

    class FakeCrew:
        def kickoff(self, inputs):
            observed_env.append(
                {
                    "SERPER_API_KEY": os.environ.get("SERPER_API_KEY"),
                    "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
                    "is_retry": "human_feedback" in inputs,
                }
            )
            if "human_feedback" in inputs:
                return {"final_answer": f"revised {inputs['human_feedback']['feedback']}"}
            return {"final_answer": f"draft {inputs['topic']}"}

    def fake_build_crew(self, **kwargs):
        return FakeCrew()

    monkeypatch.setenv("OPENAI_API_KEY", "existing-openai")
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.setattr(executor_module.CrewAIFactory, "build_crew", fake_build_crew)

    flow = _create_published_flow(client, db, auth_headers, name="HITL Credential Flow")
    _replace_flow_runtime_snapshot(db, flow, _hitl_snapshot())
    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "CrewAI"}},
        headers=auth_headers,
    )
    assert response.status_code == 201
    run = response.json()
    run = _execute_background_and_get_detail(client, db, auth_headers, run)
    first_request = (
        db.query(models.HumanFeedbackRequest)
        .filter(models.HumanFeedbackRequest.run_id == run["id"])
        .one()
    )

    retry_response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={
            "request_id": str(first_request.id),
            "outcome": "needs_revision",
            "feedback": "Make it sharper",
        },
        headers=auth_headers,
    )

    assert retry_response.status_code == 200
    assert observed_env == [
        {
            "SERPER_API_KEY": "serper-secret",
            "OPENAI_API_KEY": "runtime-openai",
            "is_retry": False,
        },
        {
            "SERPER_API_KEY": "serper-secret",
            "OPENAI_API_KEY": "runtime-openai",
            "is_retry": True,
        },
    ]
    assert "SERPER_API_KEY" not in os.environ
    assert os.environ["OPENAI_API_KEY"] == "existing-openai"


def test_needs_revision_retry_missing_credential_returns_422(client, db, auth_headers, fake_crew):
    from api.db import models

    run = _create_hitl_run(client, db, auth_headers, fake_crew)
    first_request = (
        db.query(models.HumanFeedbackRequest)
        .filter(models.HumanFeedbackRequest.run_id == run["id"])
        .one()
    )
    crew_snapshot = (
        db.query(models.AssetRuntimeSnapshot)
        .filter(models.AssetRuntimeSnapshot.version_id == CREW_VERSION_ID)
        .one()
    )
    crew_snapshot.runtime_snapshot_json = {
        "runtime_crew": {
            "crew_name": "Draft Crew",
            "agent_version_ids": ["agent:research"],
            "task_version_ids": ["task:draft"],
        },
        "runtime_agents": {
            "agent:research": {
                "role": "Researcher",
                "goal": "Draft",
                "backstory": "Uses an LLM.",
                "llm": {"provider": "openai", "model": "gpt-4o-mini"},
            }
        },
        "runtime_tasks": {
            "task:draft": {
                "description": "Draft.",
                "expected_output": "Draft.",
            }
        },
        "task_agent_links": {"task:draft": "agent:research"},
        "agent_tool_links": {},
        "task_tool_links": {},
        "runtime_tools": {},
    }
    db.add(crew_snapshot)
    db.commit()

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={
            "request_id": str(first_request.id),
            "outcome": "needs_revision",
            "feedback": "Make it sharper",
        },
        headers=auth_headers,
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"] == (
        "OpenAI API key is not connected. Add it on the Credentials page."
    )


def test_reject_marks_run_rejected(client, db, auth_headers, fake_crew):
    from api.db.models import HumanFeedbackRequest

    run = _create_hitl_run(client, db, auth_headers, fake_crew)
    request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(request.id), "outcome": "rejected", "feedback": "Stop this run"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_hitl_rejection_records_run_rejected_event(client, db, auth_headers, fake_crew):
    from api.db.models import FlowRunEvent, HumanFeedbackRequest

    run = _create_hitl_run(client, db, auth_headers, fake_crew)
    request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={
            "request_id": str(request.id),
            "outcome": "rejected",
            "feedback": "Not acceptable",
            "idempotency_key": "reject-once",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    events = (
        db.query(FlowRunEvent)
        .filter(FlowRunEvent.run_id == run["id"])
        .order_by(FlowRunEvent.created_at.asc())
        .all()
    )
    payloads = [event.event_payload_json for event in events]
    assert {
        "type": "hitl_resolved",
        "run_id": run["id"],
        "node_id": request.node_id,
        "request_id": str(request.id),
        "outcome": "rejected",
        "feedback": "Not acceptable",
    } in payloads
    assert {
        "type": "run_rejected",
        "run_id": run["id"],
        "node_id": request.node_id,
        "request_id": str(request.id),
        "feedback": "Not acceptable",
    } in payloads


def test_duplicate_feedback_submission_returns_409(client, db, auth_headers, fake_crew):
    from api.db.models import HumanFeedbackRequest

    run = _create_hitl_run(client, db, auth_headers, fake_crew)
    request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    first = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(request.id), "outcome": "approved", "feedback": ""},
        headers=auth_headers,
    )
    second = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(request.id), "outcome": "approved", "feedback": ""},
        headers=auth_headers,
    )

    assert first.status_code == 200
    assert second.status_code == 409


def test_duplicate_feedback_submission_for_resolved_retry_request_returns_409(
    client,
    db,
    auth_headers,
    fake_crew,
):
    from api.db.models import HumanFeedbackRequest

    run = _create_hitl_run(client, db, auth_headers, fake_crew)
    first_request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    first = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(first_request.id), "outcome": "needs_revision", "feedback": "Make it sharper"},
        headers=auth_headers,
    )
    duplicate = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(first_request.id), "outcome": "approved", "feedback": ""},
        headers=auth_headers,
    )

    assert first.status_code == 200
    assert duplicate.status_code == 409
    pending_requests = (
        db.query(HumanFeedbackRequest)
        .filter(HumanFeedbackRequest.run_id == run["id"], HumanFeedbackRequest.status == "pending")
        .all()
    )
    assert len(pending_requests) == 1
    assert pending_requests[0].attempt_number == 2


def test_human_feedback_response_persists_idempotency_key_and_resolved_by(
    client,
    db,
    auth_headers,
    fake_crew,
):
    from api.db.models import HumanFeedbackRequest

    run = _create_hitl_run(client, db, auth_headers, fake_crew)
    request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={
            "request_id": str(request.id),
            "outcome": "approved",
            "feedback": "Looks good",
            "idempotency_key": "hitl-response-1",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    db.refresh(request)
    assert request.status == "resolved"
    assert request.idempotency_key == "hitl-response-1"
    assert request.resolved_by == "test-user"


def test_reused_idempotency_key_for_retry_request_returns_409_and_leaves_pending(
    client,
    db,
    auth_headers,
    fake_crew,
):
    from api.db.models import HumanFeedbackRequest

    run = _create_hitl_run(client, db, auth_headers, fake_crew)
    first_request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    first = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={
            "request_id": str(first_request.id),
            "outcome": "needs_revision",
            "feedback": "Make it sharper",
            "idempotency_key": "same-key",
        },
        headers=auth_headers,
    )
    assert first.status_code == 200

    second_request = (
        db.query(HumanFeedbackRequest)
        .filter(HumanFeedbackRequest.run_id == run["id"], HumanFeedbackRequest.status == "pending")
        .one()
    )
    second = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={
            "request_id": str(second_request.id),
            "outcome": "approved",
            "feedback": "",
            "idempotency_key": "same-key",
        },
        headers=auth_headers,
    )

    assert second.status_code == 409
    db.refresh(second_request)
    assert second_request.status == "pending"
    assert second_request.idempotency_key is None


def test_other_user_cannot_submit_feedback_for_pending_request(client, db, auth_headers, fake_crew):
    from api.db.models import Asset, AssetVersion, HumanFeedbackRequest

    run = _create_hitl_run(client, db, auth_headers, fake_crew)
    request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()
    asset_version = db.get(AssetVersion, run["flow_version_id"])
    asset = db.get(Asset, asset_version.asset_id)
    asset.owner_user_id = "other-user"
    db.add(asset)
    db.commit()

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(request.id), "outcome": "approved", "feedback": "Not mine"},
        headers=auth_headers,
    )

    assert response.status_code == 404
    db.refresh(request)
    assert request.status == "pending"


def test_needs_revision_runtime_snapshot_error_returns_422(client, db, auth_headers, fake_crew):
    from api.db.models import HumanFeedbackRequest

    run = _create_hitl_run(client, db, auth_headers, fake_crew)
    request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    snapshot = _hitl_snapshot()
    snapshot.pop("crew_refs")
    flow = {"current_version": {"id": run["flow_version_id"]}}
    _replace_flow_runtime_snapshot(db, flow, snapshot)

    response = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(request.id), "outcome": "needs_revision", "feedback": "Retry please"},
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"] == f"Crew runtime snapshot missing for version {CREW_VERSION_ID}."

    _replace_flow_runtime_snapshot(db, flow, _hitl_snapshot())
    retry_after_failure = client.post(
        f"/api/flow-runs/{run['id']}/human-feedback",
        json={"request_id": str(request.id), "outcome": "approved", "feedback": "Recovered"},
        headers=auth_headers,
    )

    assert retry_after_failure.status_code == 200
    assert retry_after_failure.json()["status"] == "completed"
