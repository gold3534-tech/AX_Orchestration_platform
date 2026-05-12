from __future__ import annotations

import os
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from sqlalchemy.orm import sessionmaker


@pytest.mark.parametrize("agent_tool_links", [pytest.param(None, id="null"), pytest.param({}, id="empty")])
def test_flow_executor_agent_tool_links_falls_back_to_legacy_when_empty(agent_tool_links):
    from api.runtime.flow_snapshot_executor import FlowSnapshotExecutor

    assert FlowSnapshotExecutor(db=None)._agent_tool_links_for_crew_snapshot(
        {
            "agent_tool_links": agent_tool_links,
            "tool_links": {"agent-version-1": ["legacy_search"]},
        }
    ) == {"agent-version-1": ["legacy_search"]}


def test_flow_executor_agent_tool_links_falls_back_to_legacy_when_missing():
    from api.runtime.flow_snapshot_executor import FlowSnapshotExecutor

    assert FlowSnapshotExecutor(db=None)._agent_tool_links_for_crew_snapshot(
        {"tool_links": {"agent-version-1": ["legacy_search"]}}
    ) == {"agent-version-1": ["legacy_search"]}


def _create_published_flow(client, db, auth_headers, *, name: str, runtime_snapshot_json: dict | None = None) -> dict:
    from api.db.models import AssetRuntimeSnapshot, AssetVersion

    flow = client.post(
        "/api/assets",
        json={
            "type": "flow",
            "name": name,
            "description": "Flow run skeleton",
            "payload": {
                "entry_method": "run",
            },
        },
        headers=auth_headers,
    ).json()
    asset_version = db.get(AssetVersion, flow["current_version"]["id"])
    asset_version.status = "published"
    snapshot = AssetRuntimeSnapshot(
        version_id=flow["current_version"]["id"],
        runtime_snapshot_json=runtime_snapshot_json if runtime_snapshot_json is not None else {
            "schemaVersion": 1,
            "graph": {
                "nodes": [
                    {"id": "input:main", "type": "input", "data": {}},
                    {"id": "start:main", "type": "start", "data": {}},
                    {"id": "output:main", "type": "output", "data": {}},
                ],
                "edges": [
                    {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
                    {"id": "edge:start:output", "source": "start:main", "target": "output:main", "type": "flow"},
                ],
            },
            "output_fields": [{"label": "Topic", "source": "state", "path": "topic"}],
        },
    )
    db.add(asset_version)
    db.add(snapshot)
    db.commit()
    return flow


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


def _create_published_crew_with_snapshot(client, db, auth_headers, *, runtime_snapshot_json: dict) -> dict:
    from api.db.models import AssetVersion, AssetRuntimeSnapshot

    crew = client.post(
        "/api/assets",
        json={
            "type": "crew",
            "name": "Runtime Crew",
            "description": "Crew used by flow run tests",
            "payload": {
                "process": "sequential",
                "manager_llm": {},
                "function_calling_llm": {},
                "verbose": False,
                "planning": False,
                "memory": False,
            },
        },
        headers=auth_headers,
    ).json()
    asset_version = db.get(AssetVersion, crew["current_version"]["id"])
    crew_version = AssetRuntimeSnapshot(
        version_id=crew["current_version"]["id"],
        runtime_snapshot_json=runtime_snapshot_json,
    )
    asset_version.status = "published"
    db.add(asset_version)
    db.add(crew_version)
    db.commit()
    return crew


def _add_active_credential(db, monkeypatch, *, provider: str, api_key: str) -> None:
    from cryptography.fernet import Fernet

    from api.db import models
    from api.runtime.credential_store import encrypt_secret_payload

    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider=provider,
        label=provider,
        secret_ref=f"secret://db/credential/test-{provider}",
        scopes_json=[],
        status="active",
    )
    db.add(credential)
    db.flush()
    db.add(
        models.CredentialSecret(
            credential_id=credential.id,
            encrypted_secret_json=encrypt_secret_payload({"api_key": api_key}),
            encryption_key_version="v1",
        )
    )
    db.commit()


def _install_nano_context_spy(monkeypatch):
    from api.runtime import flow_snapshot_executor as executor_module

    calls = []
    active_contexts = []

    @contextmanager
    def fake_nano_context(**kwargs):
        calls.append({"event": "enter", **kwargs})
        active_contexts.append(kwargs)
        try:
            yield
        finally:
            active_contexts.pop()
            calls.append({"event": "exit", **kwargs})

    monkeypatch.setattr(
        executor_module,
        "nano_banana_artifact_runtime_context",
        fake_nano_context,
        raising=False,
    )
    return calls, active_contexts


def _install_meta_instagram_context_spy(monkeypatch):
    from api.runtime import flow_snapshot_executor as executor_module

    calls = []
    active_contexts = []

    @contextmanager
    def fake_meta_instagram_context(**kwargs):
        calls.append({"event": "enter", **kwargs})
        active_contexts.append(kwargs)
        try:
            yield
        finally:
            active_contexts.pop()
            calls.append({"event": "exit", **kwargs})

    monkeypatch.setattr(
        executor_module,
        "meta_instagram_runtime_context",
        fake_meta_instagram_context,
        raising=False,
    )
    monkeypatch.setattr(
        executor_module,
        "resolve_meta_instagram_runtime_token_for_crew",
        lambda *_args, **_kwargs: None,
        raising=False,
    )
    return calls, active_contexts


def test_create_flow_run_passes_topic_input_to_crew_kickoff(client, db, auth_headers, monkeypatch):
    captured_inputs: dict[str, dict] = {}

    class FakeCrew:
        def kickoff(self, *, inputs):
            captured_inputs["crew"] = inputs
            return {"raw": f"topic={inputs['topic']}"}

    class FakeFactory:
        def __init__(self, *, execution_mode="validation", llm_catalog=None):
            self.execution_mode = execution_mode

        def build_crew(self, **kwargs):
            assert self.execution_mode == "live"
            return FakeCrew()

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
        name="Crew Input Flow",
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
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "CrewAI Inputs"}},
        headers=auth_headers,
    )

    assert response.status_code == 201
    detail = _execute_background_and_get_detail(client, db, auth_headers, response.json())
    assert captured_inputs["crew"] == {"topic": "CrewAI Inputs"}
    assert detail["output_json"] == {"Raw": "topic=CrewAI Inputs"}


def test_create_flow_run_executes_hierarchical_crew_node_with_manager_llm(client, db, auth_headers, monkeypatch):
    captured_build_kwargs: dict[str, dict] = {}
    captured_inputs: dict[str, dict] = {}

    class FakeCrew:
        def kickoff(self, *, inputs):
            captured_inputs["crew"] = inputs
            return {"raw": f"hierarchical topic={inputs['topic']}"}

    class FakeFactory:
        def __init__(self, *, execution_mode="validation", llm_catalog=None):
            self.execution_mode = execution_mode

        def build_crew(self, **kwargs):
            assert self.execution_mode == "live"
            captured_build_kwargs["crew"] = kwargs
            return FakeCrew()

    monkeypatch.setattr("api.runtime.flow_snapshot_executor.CrewAIFactory", FakeFactory)
    _add_active_credential(db, monkeypatch, provider="openai", api_key="runtime-openai")

    crew = _create_published_crew_with_snapshot(
        client,
        db,
        auth_headers,
        runtime_snapshot_json={
            "schemaVersion": 1,
            "required_inputs": ["topic"],
            "runtime_crew": {
                "crew_name": "Hierarchical Runtime Crew",
                "process": "hierarchical",
                "manager_llm": "gpt-4o-mini",
                "manager_agent_version_id": None,
                "agent_version_ids": ["agent-version-1"],
                "task_version_ids": ["task-version-1"],
            },
            "runtime_agents": {
                "agent-version-1": {
                    "version_id": "agent-version-1",
                    "asset_id": "agent-asset-1",
                    "role": "Researcher",
                    "goal": "Research assigned topics",
                    "backstory": "Handles delegated research.",
                }
            },
            "runtime_tasks": {
                "task-version-1": {
                    "version_id": "task-version-1",
                    "task_name": "Research Task",
                    "description": "Research the topic.",
                    "expected_output": "A concise answer.",
                }
            },
            "task_agent_links": {},
            "task_tool_links": {},
            "runtime_tools": {},
        },
    )
    flow = _create_published_flow(
        client,
        db,
        auth_headers,
        name="Hierarchical Crew Flow",
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
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "CrewAI Hierarchy"}},
        headers=auth_headers,
    )

    assert response.status_code == 201
    detail = _execute_background_and_get_detail(client, db, auth_headers, response.json())
    assert detail["status"] == "completed"
    assert captured_inputs["crew"] == {"topic": "CrewAI Hierarchy"}
    assert captured_build_kwargs["crew"]["runtime_crew"]["process"] == "hierarchical"
    assert captured_build_kwargs["crew"]["runtime_crew"]["manager_llm"] == "gpt-4o-mini"
    assert captured_build_kwargs["crew"]["task_agent_links"] == {}
    assert detail["output_json"] == {"Raw": "hierarchical topic=CrewAI Hierarchy"}


def test_live_crew_installs_nano_banana_artifact_context(client, db, auth_headers, monkeypatch):
    from api.runtime import flow_snapshot_executor as executor_module

    nano_context_calls, nano_active_contexts = _install_nano_context_spy(monkeypatch)
    meta_context_calls, meta_active_contexts = _install_meta_instagram_context_spy(monkeypatch)
    observed_contexts = []

    class FakeCrew:
        def kickoff(self, *, inputs):
            observed_contexts.append(
                {
                    "nano": dict(nano_active_contexts[-1]) if nano_active_contexts else None,
                    "meta": dict(meta_active_contexts[-1]) if meta_active_contexts else None,
                }
            )
            return {"raw": f"topic={inputs['topic']}"}

    class FakeFactory:
        def __init__(self, *, execution_mode="validation", llm_catalog=None):
            self.execution_mode = execution_mode

        def build_crew(self, **kwargs):
            assert self.execution_mode == "live"
            return FakeCrew()

    monkeypatch.setattr(executor_module, "CrewAIFactory", FakeFactory)

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
            "agent_tool_links": {"agent-1": ["ax.instagram_publish_tool"]},
            "runtime_tools": {
                "ax.instagram_publish_tool": {
                    "module_path": "api.tools.instagram_publish_tool",
                    "class_name": "AXInstagramPublishTool",
                    "credential_requirements": [
                        {
                            "provider": "meta_instagram",
                            "env_var": "AX_META_INSTAGRAM_OAUTH",
                            "required": True,
                            "injection": "runtime_context",
                        }
                    ],
                }
            },
        },
    )
    flow = _create_published_flow(
        client,
        db,
        auth_headers,
        name="Nano Context Flow",
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
    detail = _execute_background_and_get_detail(client, db, auth_headers, response.json())
    assert detail["status"] == "completed"
    assert observed_contexts[0]["nano"]["db"] is not None
    assert {
        key: observed_contexts[0]["nano"][key]
        for key in ("owner_user_id", "run_id", "node_id")
    } == {
        "owner_user_id": "test-user",
        "run_id": response.json()["id"],
        "node_id": "crew:research",
    }
    assert observed_contexts[0]["meta"]["db"] is not None
    assert {
        key: observed_contexts[0]["meta"][key]
        for key in ("owner_user_id", "run_id", "token")
    } == {
        "owner_user_id": "test-user",
        "run_id": response.json()["id"],
        "token": None,
    }
    assert [call["event"] for call in nano_context_calls] == ["enter", "exit"]
    assert [call["event"] for call in meta_context_calls] == ["enter", "exit"]


def test_start_run_records_crewai_bridge_events_without_immediate_event_writer(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from api.db.models import FlowRunEvent
    from api.runtime.flow_snapshot_executor import FlowSnapshotExecutor
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

    class RaisingFlowRunEventWriter:
        def __init__(self, **kwargs):
            del kwargs
            raise AssertionError("sync start_run must not construct FlowRunEventWriter")

    monkeypatch.setattr("api.runtime.flow_snapshot_executor.CrewAIFactory", FakeFactory)
    monkeypatch.setattr(
        "api.runtime.flow_snapshot_executor.FlowRunEventWriter",
        RaisingFlowRunEventWriter,
    )

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
        name="Sync Crew Bridge Flow",
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

    run = FlowSnapshotExecutor(db).start_run(
        flow_version_id=flow["current_version"]["id"],
        owner_user_id="test-user",
        inputs={"topic": "CrewAI"},
    )

    assert run.status == "completed"
    semantic_event = (
        db.query(FlowRunEvent)
        .filter(
            FlowRunEvent.run_id == str(run.id),
            FlowRunEvent.node_id == "crew:research",
            FlowRunEvent.event_type == "tool_execution_started",
        )
        .one()
    )
    assert semantic_event.event_payload_json["type"] == "tool_execution_started"
    assert semantic_event.event_payload_json["tool_args_preview"] == {"search_query": "[redacted]"}


def test_create_flow_run_builds_crews_in_live_mode(client, db, auth_headers, monkeypatch):
    captured_modes: list[str] = []

    class FakeCrew:
        def kickoff(self, *, inputs):
            return {"raw": "live-output"}

    class FakeFactory:
        def __init__(self, *, execution_mode="validation", llm_catalog=None):
            captured_modes.append(execution_mode)

        def build_crew(self, **kwargs):
            return FakeCrew()

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
            "agent_tool_links": {},
            "task_tool_links": {},
            "runtime_tools": {},
        },
    )
    flow = _create_published_flow(
        client,
        db,
        auth_headers,
        name="Live Mode Flow",
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
            "crew_input_mappings": {"crew:research": {"topic": {"source": "state", "path": "topic"}}},
            "output_fields": [{"label": "Raw", "source": "node", "nodeId": "crew:research", "path": "output.raw"}],
        },
    )

    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "Live mode"}},
        headers=auth_headers,
    )

    assert response.status_code == 201
    _execute_background_and_get_detail(client, db, auth_headers, response.json())
    assert captured_modes == ["live"]


def test_create_flow_run_missing_default_llm_credential_keeps_runtime_row_after_background_failure(
    client,
    db,
    auth_headers,
):
    from api.db import models

    crew = _create_published_crew_with_snapshot(
        client,
        db,
        auth_headers,
        runtime_snapshot_json={
            "schemaVersion": 1,
            "required_inputs": ["topic"],
            "runtime_crew": {"agent_version_ids": ["agent-default"], "task_version_ids": ["task-research"]},
            "runtime_agents": {"agent-default": {"role": "Researcher", "goal": "Research", "backstory": "Careful."}},
            "runtime_tasks": {"task-research": {"description": "Research {topic}.", "expected_output": "Summary."}},
            "task_agent_links": {"task-research": "agent-default"},
            "agent_tool_links": {},
            "task_tool_links": {},
            "runtime_tools": {},
        },
    )
    flow = _create_published_flow(
        client,
        db,
        auth_headers,
        name="Missing Default LLM Credential Rollback Flow",
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
            "crew_input_mappings": {"crew:research": {"topic": {"source": "state", "path": "topic"}}},
            "output_fields": [{"label": "Raw", "source": "node", "nodeId": "crew:research", "path": "output.raw"}],
        },
    )
    db.query(models.LLMModel).delete()
    db.query(models.LLMProvider).delete()
    db.commit()

    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "rollback"}},
        headers=auth_headers,
    )

    assert response.status_code == 201
    detail = _execute_background_and_get_detail(client, db, auth_headers, response.json())
    assert detail["status"] == "failed"
    assert detail["error_message"] == "OpenAI API key is not connected. Add it on the Credentials page."
    assert db.query(models.FlowRun).filter(models.FlowRun.flow_version_id == flow["current_version"]["id"]).count() == 1


def test_flow_snapshot_executor_raises_missing_credential_for_model_name_llm(client, db, auth_headers):
    from api.runtime.credential_resolver import CredentialResolutionError
    from api.runtime.flow_snapshot_executor import FlowSnapshotExecutor

    crew = _create_published_crew_with_snapshot(
        client,
        db,
        auth_headers,
        runtime_snapshot_json={
            "schemaVersion": 1,
            "required_inputs": ["topic"],
            "runtime_crew": {
                "agent_version_ids": ["agent-openai"],
                "task_version_ids": ["task-research"],
            },
            "runtime_agents": {
                "agent-openai": {
                    "role": "Researcher",
                    "goal": "Research",
                    "backstory": "Uses an OpenAI model.",
                    "llm": "gpt-4o-mini",
                }
            },
            "runtime_tasks": {
                "task-research": {
                    "description": "Research.",
                    "expected_output": "Summary.",
                }
            },
            "task_agent_links": {"task-research": "agent-openai"},
            "agent_tool_links": {},
            "task_tool_links": {},
            "runtime_tools": {},
        },
    )
    flow = _create_published_flow(
        client,
        db,
        auth_headers,
        name="Missing Credential Flow",
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
        },
    )

    with pytest.raises(CredentialResolutionError, match="OpenAI API key is not connected"):
        FlowSnapshotExecutor(db).start_run(
            flow_version_id=flow["current_version"]["id"],
            owner_user_id="test-user",
            inputs={"topic": "CrewAI Inputs"},
        )


def test_create_flow_run_missing_model_name_credential_returns_422(client, db, auth_headers):
    crew = _create_published_crew_with_snapshot(
        client,
        db,
        auth_headers,
        runtime_snapshot_json={
            "schemaVersion": 1,
            "runtime_crew": {
                "agent_version_ids": ["agent-openai"],
                "task_version_ids": ["task-research"],
            },
            "runtime_agents": {
                "agent-openai": {
                    "role": "Researcher",
                    "goal": "Research",
                    "backstory": "Uses an OpenAI model.",
                    "llm": "gpt-4o-mini",
                }
            },
            "runtime_tasks": {
                "task-research": {
                    "description": "Research.",
                    "expected_output": "Summary.",
                }
            },
            "task_agent_links": {"task-research": "agent-openai"},
            "agent_tool_links": {},
            "task_tool_links": {},
            "runtime_tools": {},
        },
    )
    flow = _create_published_flow(
        client,
        db,
        auth_headers,
        name="Missing Credential Route Flow",
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
        },
    )

    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "CrewAI Inputs"}},
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    detail = _execute_background_and_get_detail(client, db, auth_headers, response.json())
    assert detail["status"] == "failed"
    assert detail["error_message"] == (
        "OpenAI API key is not connected. Add it on the Credentials page."
    )


def test_create_flow_run_skeleton_requires_published_flow_version(client, auth_headers):
    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": "missing-version", "inputs": {"topic": "AI"}},
        headers=auth_headers,
    )

    assert response.status_code == 404


def test_flow_run_events_endpoint_returns_empty_event_list_for_created_run(client, db, auth_headers):
    from api.db.models import FlowRunStateSnapshot

    flow = _create_published_flow(client, db, auth_headers, name="Runnable Flow")

    run_response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "AI"}},
        headers=auth_headers,
    )
    assert run_response.status_code == 201
    run_body = run_response.json()
    detail = _execute_background_and_get_detail(client, db, auth_headers, run_body)
    run_id = run_body["id"]

    assert detail["status"] == "completed"
    snapshots = (
        db.query(FlowRunStateSnapshot)
        .filter(FlowRunStateSnapshot.run_id == run_id)
        .order_by(FlowRunStateSnapshot.created_at.asc(), FlowRunStateSnapshot.id.asc())
        .all()
    )
    assert snapshots[0].node_id is None
    assert snapshots[0].state_json["inputs"] == {"topic": "AI"}
    assert "output" not in snapshots[0].state_json
    assert snapshots[-1].node_id == "output:main"
    assert snapshots[-1].state_json["output"] == {"Topic": "AI"}

    events_response = client.get(f"/api/flow-runs/{run_id}/events", headers=auth_headers)

    assert events_response.status_code == 200
    assert [event["event_type"] for event in events_response.json()["events"]] == [
        "run_started",
        "run_completed",
    ]


def test_create_flow_run_skeleton_rejects_other_users_published_flow_version(client, db, auth_headers):
    from api.db.models import Asset, AssetVersion

    flow = client.post(
        "/api/assets",
        json={
            "type": "flow",
            "name": "Other User Flow",
            "description": "Not runnable by the current user",
            "payload": {"entry_method": "run"},
        },
        headers=auth_headers,
    ).json()
    asset = db.get(Asset, flow["id"])
    asset_version = db.get(AssetVersion, flow["current_version"]["id"])
    asset.owner_user_id = "other-user"
    asset_version.status = "published"
    db.add(asset)
    db.add(asset_version)
    db.commit()
    _replace_flow_runtime_snapshot(db, flow, {"schemaVersion": 1})

    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "AI"}},
        headers=auth_headers,
    )

    assert response.status_code == 404


def test_create_flow_run_rejects_published_flow_without_runtime_snapshot(client, db, auth_headers):
    from api.db.models import AssetVersion

    flow = client.post(
        "/api/assets",
        json={
            "type": "flow",
            "name": "Empty Snapshot Flow",
            "description": "Published but not executable",
            "payload": {
                "entry_method": "run",
            },
        },
        headers=auth_headers,
    ).json()
    asset_version = db.get(AssetVersion, flow["current_version"]["id"])
    asset_version.status = "published"
    db.add(asset_version)
    db.commit()

    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "AI"}},
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Published flow version is missing runtime_snapshot_json."


def test_create_flow_run_rejects_runtime_snapshot_without_schema_version(client, db, auth_headers):
    from api.db.models import AssetVersion

    flow = client.post(
        "/api/assets",
        json={
            "type": "flow",
            "name": "Malformed Snapshot Flow",
            "description": "Published but malformed",
            "payload": {"entry_method": "run"},
        },
        headers=auth_headers,
    ).json()
    asset_version = db.get(AssetVersion, flow["current_version"]["id"])
    asset_version.status = "published"
    db.add(asset_version)
    db.commit()
    _replace_flow_runtime_snapshot(db, flow, {"graph": {}})

    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "AI"}},
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Published flow runtime snapshot is missing schemaVersion."


@pytest.mark.parametrize(
    ("node_type", "expected_exception", "expected_error"),
    [
        ("crew", "UnsupportedGraphError", "Crew node crew:main is missing versionId."),
        ("hitl", "UnsupportedGraphError", "HITL node hitl:main must follow a Crew node."),
    ],
)
def test_create_flow_run_does_not_swallow_unsupported_execution_errors(
    client,
    db,
    auth_headers,
    node_type,
    expected_exception,
    expected_error,
):
    from api.db.models import FlowRun
    from api.runtime.linear_flow_runtime import UnsupportedGraphError
    from api.runtime.flow_snapshot_executor import HumanFeedbackValidationError
    from api.services.runs import create_flow_run

    flow = _create_published_flow(
        client,
        db,
        auth_headers,
        name=f"Unsupported {node_type} Flow",
        runtime_snapshot_json={
            "schemaVersion": 1,
            "graph": {
                "nodes": [
                    {"id": "input:main", "type": "input", "data": {}},
                    {"id": "start:main", "type": "start", "data": {}},
                    {"id": f"{node_type}:main", "type": node_type, "data": {}},
                    {"id": "output:main", "type": "output", "data": {}},
                ],
                "edges": [
                    {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
                    {
                        "id": f"edge:start:{node_type}",
                        "source": "start:main",
                        "target": f"{node_type}:main",
                        "type": "flow",
                    },
                    {
                        "id": f"edge:{node_type}:output",
                        "source": f"{node_type}:main",
                        "target": "output:main",
                        "type": "flow",
                    },
                ],
            },
            "output_fields": [{"label": "Topic", "source": "state", "path": "topic"}],
        },
    )

    exception_type = {
        "UnsupportedGraphError": UnsupportedGraphError,
        "HumanFeedbackValidationError": HumanFeedbackValidationError,
    }[expected_exception]

    with pytest.raises(exception_type, match=expected_error):
        create_flow_run(
            db,
            flow_version_id=flow["current_version"]["id"],
            owner_user_id="test-user",
            inputs={"topic": "AI"},
        )

    assert (
        db.query(FlowRun)
        .filter(FlowRun.flow_version_id == flow["current_version"]["id"])
        .count()
        == 0
    )


def test_create_flow_run_route_returns_201_then_background_failure_for_unsupported_execution(
    client, db, auth_headers
):
    flow = _create_published_flow(
        client,
        db,
        auth_headers,
        name="Unsupported Crew Route Flow",
        runtime_snapshot_json={
            "schemaVersion": 1,
            "graph": {
                "nodes": [
                    {"id": "input:main", "type": "input", "data": {}},
                    {"id": "start:main", "type": "start", "data": {}},
                    {"id": "crew:main", "type": "crew", "data": {}},
                    {"id": "output:main", "type": "output", "data": {}},
                ],
                "edges": [
                    {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
                    {"id": "edge:start:crew", "source": "start:main", "target": "crew:main", "type": "flow"},
                    {"id": "edge:crew:output", "source": "crew:main", "target": "output:main", "type": "flow"},
                ],
            },
            "output_fields": [{"label": "Topic", "source": "state", "path": "topic"}],
        },
    )

    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "AI"}},
        headers=auth_headers,
    )

    assert response.status_code == 201
    detail = _execute_background_and_get_detail(client, db, auth_headers, response.json())
    assert detail["status"] == "failed"
    assert detail["error_message"] == "Crew node crew:main is missing versionId."


def test_create_flow_run_rejects_unknown_node_type(client, db, auth_headers):
    from api.runtime.linear_flow_runtime import UnsupportedGraphError
    from api.services.runs import create_flow_run

    flow = _create_published_flow(
        client,
        db,
        auth_headers,
        name="Unknown Node Flow",
        runtime_snapshot_json={
            "schemaVersion": 1,
            "graph": {
                "nodes": [
                    {"id": "input:main", "type": "input", "data": {}},
                    {"id": "start:main", "type": "start", "data": {}},
                    {"id": "mystery:main", "type": "mystery", "data": {}},
                    {"id": "output:main", "type": "output", "data": {}},
                ],
                "edges": [
                    {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
                    {"id": "edge:start:mystery", "source": "start:main", "target": "mystery:main", "type": "flow"},
                    {"id": "edge:mystery:output", "source": "mystery:main", "target": "output:main", "type": "flow"},
                ],
            },
            "output_fields": [{"label": "Topic", "source": "state", "path": "topic"}],
        },
    )

    with pytest.raises(UnsupportedGraphError, match="Unsupported flow runtime node type: mystery"):
        create_flow_run(
            db,
            flow_version_id=flow["current_version"]["id"],
            owner_user_id="test-user",
            inputs={"topic": "AI"},
        )


def test_create_flow_run_executes_crew_node_with_inputs(client, db, auth_headers, monkeypatch):
    from api.db.models import Asset, AssetRuntimeSnapshot, AssetVersion
    from api.runtime import flow_snapshot_executor as executor_module

    crew_asset_id = "77777777-7777-7777-7777-777777777777"
    crew_version_id = "88888888-8888-8888-8888-888888888888"
    db.add(
        Asset(
            id=crew_asset_id,
            asset_type="crew",
            owner_user_id="test-user",
            name="Research Crew",
        )
    )
    db.add(
        AssetVersion(
            id=crew_version_id,
            asset_id=crew_asset_id,
            version_number=1,
            status="published",
            metadata_json={},
            created_by="test-user",
        )
    )
    db.add(
        AssetRuntimeSnapshot(version_id=crew_version_id,
            runtime_snapshot_json={
                "runtime_crew": {
                    "crew_name": "Research Crew",
                    "agent_version_ids": [],
                    "task_version_ids": [],
                },
                "runtime_agents": {},
                "runtime_tasks": {},
                "task_agent_links": {},
                "task_tool_links": {},
                "runtime_tools": {},
            },
        )
    )

    flow = _create_published_flow(client, db, auth_headers, name="Crew Runtime Flow")
    snapshot = {
        "schemaVersion": 1,
        "graph": {
            "nodes": [
                {"id": "input:main", "type": "input", "data": {}},
                {"id": "start:main", "type": "start", "data": {}},
                {
                    "id": "crew:research",
                    "type": "crew",
                    "data": {"assetId": crew_asset_id, "versionId": crew_version_id},
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
                "asset_id": crew_asset_id,
                "version_id": crew_version_id,
                "latest_version_id": crew_version_id,
                "status": "latest",
            }
        ],
        "crew_input_mappings": {
            "crew:research": {"topic": {"source": "state", "path": "topic"}}
        },
        "output_fields": [
            {"label": "Final answer", "source": "node", "nodeId": "crew:research", "path": "output.final_answer"}
        ],
    }
    _replace_flow_runtime_snapshot(db, flow, snapshot)

    class FakeCrew:
        def __init__(self):
            self.inputs = None

        def kickoff(self, inputs):
            self.inputs = inputs
            return {"final_answer": f"researched {inputs['topic']}"}

    fake_crew = FakeCrew()

    def fake_build_crew(self, **kwargs):
        return fake_crew

    monkeypatch.setattr(executor_module.CrewAIFactory, "build_crew", fake_build_crew)

    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "CrewAI"}},
        headers=auth_headers,
    )

    assert response.status_code == 201
    detail = _execute_background_and_get_detail(client, db, auth_headers, response.json())
    assert detail["status"] == "completed"
    assert fake_crew.inputs == {"topic": "CrewAI"}

    asset_version = db.get(AssetVersion, flow["current_version"]["id"])
    assert str(asset_version.id) == flow["current_version"]["id"]


def test_create_flow_run_executes_crew_node_from_crew_refs_fallback(client, db, auth_headers, monkeypatch):
    from api.db.models import Asset, AssetRuntimeSnapshot, AssetVersion, FlowRun, FlowRunEvent, FlowRunStateSnapshot
    from api.runtime import flow_snapshot_executor as executor_module

    crew_asset_id = "11111111-1111-1111-1111-111111111111"
    crew_version_id = "22222222-2222-2222-2222-222222222222"
    crew_snapshot = {
        "runtime_crew": {"crew_name": "Research Crew", "agent_version_ids": [], "task_version_ids": []},
        "runtime_agents": {},
        "runtime_tasks": {},
        "task_agent_links": {},
        "agent_tool_links": None,
        "tool_links": {"agent-version-1": ["legacy_search"]},
        "task_tool_links": {},
        "runtime_tools": {},
    }
    db.add(
        Asset(
            id=crew_asset_id,
            asset_type="crew",
            owner_user_id="test-user",
            name="Research Crew",
        )
    )
    db.add(
        AssetVersion(
            id=crew_version_id,
            asset_id=crew_asset_id,
            version_number=1,
            status="published",
            metadata_json={},
            created_by="test-user",
        )
    )
    db.add(AssetRuntimeSnapshot(version_id=crew_version_id, runtime_snapshot_json=crew_snapshot))

    flow = _create_published_flow(client, db, auth_headers, name="Crew Refs Runtime Flow")
    snapshot = {
        "schemaVersion": 1,
        "graph": {
            "nodes": [
                {"id": "input:main", "type": "input", "data": {}},
                {"id": "start:main", "type": "start", "data": {}},
                {
                    "id": "crew:research",
                    "type": "crew",
                    "data": {"assetId": crew_asset_id, "versionId": crew_version_id},
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
                "asset_id": crew_asset_id,
                "version_id": crew_version_id,
                "latest_version_id": crew_version_id,
                "status": "latest",
            }
        ],
        "crew_input_mappings": {
            "crew:research": {"topic": {"source": "state", "path": "topic"}}
        },
        "output_fields": [
            {"label": "Final answer", "source": "node", "nodeId": "crew:research", "path": "output.final_answer"}
        ],
    }
    _replace_flow_runtime_snapshot(db, flow, snapshot)

    class FakeCrew:
        def __init__(self):
            self.inputs = None

        def kickoff(self, inputs):
            self.inputs = inputs
            return {"final_answer": f"researched {inputs['topic']}"}

    fake_crew = FakeCrew()

    def fake_build_crew(self, **kwargs):
        assert kwargs["runtime_crew"]["crew_name"] == "Research Crew"
        assert kwargs["agent_tool_links"] == {"agent-version-1": ["legacy_search"]}
        return fake_crew

    monkeypatch.setattr(executor_module.CrewAIFactory, "build_crew", fake_build_crew)

    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "CrewAI"}},
        headers=auth_headers,
    )

    assert response.status_code == 201
    detail = _execute_background_and_get_detail(client, db, auth_headers, response.json())
    assert detail["status"] == "completed"
    assert detail["output_json"] == {"Final answer": "researched CrewAI"}
    assert fake_crew.inputs == {"topic": "CrewAI"}

    run = db.get(FlowRun, response.json()["id"])
    assert run.output_json == {"Final answer": "researched CrewAI"}

    events = (
        db.query(FlowRunEvent)
        .filter(FlowRunEvent.run_id == response.json()["id"])
        .order_by(FlowRunEvent.created_at.asc(), FlowRunEvent.id.asc())
        .all()
    )
    assert [event.event_type for event in events] == [
        "run_started",
        "crew_started",
        "crew_completed",
        "run_completed",
    ]
    assert events[1].node_id == "crew:research"
    assert events[1].event_payload_json == {
        "inputs": {"topic": {"type": "text", "length": len("CrewAI")}}
    }
    assert events[2].node_id == "crew:research"
    assert events[2].event_payload_json == {"output": {"final_answer": "researched CrewAI"}}

    snapshots = (
        db.query(FlowRunStateSnapshot)
        .filter(FlowRunStateSnapshot.run_id == response.json()["id"])
        .order_by(FlowRunStateSnapshot.created_at.asc(), FlowRunStateSnapshot.id.asc())
        .all()
    )
    crew_snapshot_rows = [snapshot for snapshot in snapshots if snapshot.node_id == "crew:research"]
    assert len(crew_snapshot_rows) == 1
    assert crew_snapshot_rows[0].state_json["node_outputs"]["crew:research"] == {
        "final_answer": "researched CrewAI"
    }


def test_create_flow_run_executes_flow_pinned_to_archived_crew_version(client, db, auth_headers, monkeypatch):
    from api.db.models import AssetVersion
    from api.runtime import flow_snapshot_executor as executor_module
    from tests.test_crew_graph_routes_v2 import make_valid_publish_graph_for_asset
    from tests.test_flow_graph_routes_v2 import _create_flow, _create_published_crew, _flow_graph

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew(client, db, auth_headers)
    pinned_crew_version_id = crew["current_version"]["id"]

    save_flow_response = client.put(
        f"/api/flow-graphs/{flow['id']}/draft",
        json={"graph": _flow_graph(crew["id"], pinned_crew_version_id)},
        headers=auth_headers,
    )
    assert save_flow_response.status_code == 200
    publish_flow_response = client.post(f"/api/flow-graphs/{flow['id']}/publish", headers=auth_headers)
    assert publish_flow_response.status_code == 200
    flow_version_id = publish_flow_response.json()["version"]["id"]

    save_crew_response = client.put(
        f"/api/crew-graphs/{crew['id']}/draft",
        json={"graph": make_valid_publish_graph_for_asset(crew)},
        headers=auth_headers,
    )
    assert save_crew_response.status_code == 200
    publish_crew_response = client.post(f"/api/crew-graphs/{crew['id']}/publish", headers=auth_headers)
    assert publish_crew_response.status_code == 200

    pinned_crew_version = db.get(AssetVersion, pinned_crew_version_id)
    assert pinned_crew_version.status == "archived"

    class FakeCrew:
        def kickoff(self, inputs):
            return {"final_answer": f"researched {inputs['topic']}"}

    def fake_build_crew(self, **kwargs):
        return FakeCrew()

    monkeypatch.setattr(executor_module.CrewAIFactory, "build_crew", fake_build_crew)

    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow_version_id, "inputs": {"topic": "CrewAI"}},
        headers=auth_headers,
    )

    assert response.status_code == 201
    detail = _execute_background_and_get_detail(client, db, auth_headers, response.json())
    assert detail["status"] == "completed"
    assert detail["output_json"] == {"Answer": "researched CrewAI"}


def test_create_flow_run_rejects_archived_flow_version_by_explicit_id(client, db, auth_headers):
    from api.db.models import AssetVersion
    from tests.test_flow_graph_routes_v2 import _create_flow, _create_published_crew, _flow_graph

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])

    save_flow_response = client.put(
        f"/api/flow-graphs/{flow['id']}/draft",
        json={"graph": graph},
        headers=auth_headers,
    )
    assert save_flow_response.status_code == 200
    first_publish_response = client.post(f"/api/flow-graphs/{flow['id']}/publish", headers=auth_headers)
    assert first_publish_response.status_code == 200
    archived_flow_version_id = first_publish_response.json()["version"]["id"]

    changed_graph = _flow_graph(crew["id"], crew["current_version"]["id"])
    changed_graph["nodes"][3]["data"]["fields"][0]["label"] = "Final Answer"
    assert (
        client.put(
            f"/api/flow-graphs/{flow['id']}/draft",
            json={"graph": changed_graph},
            headers=auth_headers,
        ).status_code
        == 200
    )
    second_publish_response = client.post(f"/api/flow-graphs/{flow['id']}/publish", headers=auth_headers)
    assert second_publish_response.status_code == 200

    archived_flow_version = db.get(AssetVersion, archived_flow_version_id)
    assert archived_flow_version.status == "archived"

    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": archived_flow_version_id, "inputs": {"topic": "CrewAI"}},
        headers=auth_headers,
    )

    assert response.status_code == 404


def test_create_flow_run_rejects_draft_flow_version_even_with_runtime_snapshot(client, db, auth_headers):
    from tests.test_flow_graph_routes_v2 import _create_flow

    flow = _create_flow(client, auth_headers)
    snapshot = {
        "schemaVersion": 1,
        "graph": {
            "nodes": [
                {"id": "input:main", "type": "input", "data": {}},
                {"id": "start:main", "type": "start", "data": {}},
                {"id": "output:main", "type": "output", "data": {}},
            ],
            "edges": [
                {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
                {"id": "edge:start:output", "source": "start:main", "target": "output:main", "type": "flow"},
            ],
        },
        "output_fields": [{"label": "Topic", "source": "state", "path": "topic"}],
    }
    _replace_flow_runtime_snapshot(db, flow, snapshot)

    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "AI"}},
        headers=auth_headers,
    )

    assert response.status_code == 404


def test_create_flow_run_ignores_tampered_embedded_crew_snapshot(client, db, auth_headers, monkeypatch):
    from api.db.models import Asset, AssetRuntimeSnapshot, AssetVersion
    from api.runtime import flow_snapshot_executor as executor_module

    crew_asset_id = "55555555-5555-5555-5555-555555555555"
    crew_version_id = "66666666-6666-6666-6666-666666666666"
    db_crew_snapshot = {
        "runtime_crew": {
            "crew_name": "DB Research Crew",
            "agent_version_ids": ["agent-version-db"],
            "task_version_ids": ["task-version-db"],
        },
        "runtime_agents": {"agent-version-db": {"name": "DB Agent"}},
        "runtime_tasks": {"task-version-db": {"description": "DB task"}},
        "task_agent_links": {"task-version-db": "agent-version-db"},
        "task_tool_links": {},
        "runtime_tools": {},
    }
    db.add(
        Asset(
            id=crew_asset_id,
            asset_type="crew",
            owner_user_id="test-user",
            name="DB Research Crew",
        )
    )
    db.add(
        AssetVersion(
            id=crew_version_id,
            asset_id=crew_asset_id,
            version_number=1,
            status="published",
            metadata_json={},
            created_by="test-user",
        )
    )
    db.add(AssetRuntimeSnapshot(version_id=crew_version_id, runtime_snapshot_json=db_crew_snapshot))

    flow = _create_published_flow(client, db, auth_headers, name="Tampered Embedded Crew Runtime Flow")
    snapshot = {
        "schemaVersion": 1,
        "graph": {
            "nodes": [
                {"id": "input:main", "type": "input", "data": {}},
                {"id": "start:main", "type": "start", "data": {}},
                {
                    "id": "crew:research",
                    "type": "crew",
                    "data": {"assetId": crew_asset_id, "versionId": crew_version_id},
                },
                {"id": "output:main", "type": "output", "data": {}},
            ],
            "edges": [
                {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
                {"id": "edge:start:crew", "source": "start:main", "target": "crew:research", "type": "flow"},
                {"id": "edge:crew:output", "source": "crew:research", "target": "output:main", "type": "flow"},
            ],
            "entities": {
                "crews": {
                    crew_version_id: {
                        "runtime_snapshot_json": {
                            "runtime_crew": {
                                "crew_name": "Tampered Embedded Crew",
                                "agent_version_ids": ["agent-version-tampered"],
                                "task_version_ids": ["task-version-tampered"],
                            },
                            "runtime_agents": {"agent-version-tampered": {"name": "Tampered Agent"}},
                            "runtime_tasks": {"task-version-tampered": {"description": "Tampered task"}},
                            "task_agent_links": {"task-version-tampered": "agent-version-tampered"},
                            "task_tool_links": {},
                            "runtime_tools": {},
                        }
                    }
                }
            },
        },
        "crew_refs": [
            {
                "node_id": "crew:research",
                "asset_id": crew_asset_id,
                "version_id": crew_version_id,
                "latest_version_id": crew_version_id,
                "status": "latest",
            }
        ],
        "crew_input_mappings": {
            "crew:research": {"topic": {"source": "state", "path": "topic"}}
        },
        "output_fields": [
            {"label": "Final answer", "source": "node", "nodeId": "crew:research", "path": "output.final_answer"}
        ],
    }
    _replace_flow_runtime_snapshot(db, flow, snapshot)
    _add_active_credential(db, monkeypatch, provider="openai", api_key="runtime-openai")

    observed_build_kwargs = {}

    class FakeCrew:
        def kickoff(self, inputs):
            return {"final_answer": f"researched {inputs['topic']}"}

    def fake_build_crew(self, **kwargs):
        observed_build_kwargs.update(kwargs)
        return FakeCrew()

    monkeypatch.setattr(executor_module.CrewAIFactory, "build_crew", fake_build_crew)

    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "CrewAI"}},
        headers=auth_headers,
    )

    assert response.status_code == 201
    _execute_background_and_get_detail(client, db, auth_headers, response.json())
    assert observed_build_kwargs["runtime_crew"]["crew_name"] == "DB Research Crew"
    assert observed_build_kwargs["runtime_crew"]["agent_version_ids"] == ["agent-version-db"]
    assert observed_build_kwargs["runtime_agents"] == {"agent-version-db": {"name": "DB Agent"}}
    assert observed_build_kwargs["runtime_tasks"] == {"task-version-db": {"description": "DB task"}}


@pytest.mark.parametrize(
    ("asset_type", "status", "owner_user_id"),
    [
        ("crew", "published", "other-user"),
        ("crew", "draft", "test-user"),
        ("flow", "published", "test-user"),
    ],
)
def test_create_flow_run_crew_refs_fallback_requires_published_owned_crew_boundary(
    client,
    db,
    auth_headers,
    monkeypatch,
    asset_type,
    status,
    owner_user_id,
):
    from api.db.models import Asset, AssetRuntimeSnapshot, AssetVersion, FlowRun
    from api.runtime import flow_snapshot_executor as executor_module

    crew_asset_id = "33333333-3333-3333-3333-333333333333"
    crew_version_id = "44444444-4444-4444-4444-444444444444"
    db.add(
        Asset(
            id=crew_asset_id,
            asset_type=asset_type,
            owner_user_id=owner_user_id,
            name="Boundary Crew",
        )
    )
    db.add(
        AssetVersion(
            id=crew_version_id,
            asset_id=crew_asset_id,
            version_number=1,
            status=status,
            metadata_json={},
            created_by=owner_user_id,
        )
    )
    db.add(
        AssetRuntimeSnapshot(version_id=crew_version_id,
            runtime_snapshot_json={
                "runtime_crew": {"crew_name": "Boundary Crew", "agent_version_ids": [], "task_version_ids": []},
                "runtime_agents": {},
                "runtime_tasks": {},
                "task_agent_links": {},
                "task_tool_links": {},
                "runtime_tools": {},
            },
        )
    )

    flow = _create_published_flow(client, db, auth_headers, name=f"Rejected Crew Ref {asset_type} {status}")
    snapshot = {
        "schemaVersion": 1,
        "graph": {
            "nodes": [
                {"id": "input:main", "type": "input", "data": {}},
                {"id": "start:main", "type": "start", "data": {}},
                {
                    "id": "crew:research",
                    "type": "crew",
                    "data": {"assetId": crew_asset_id, "versionId": crew_version_id},
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
                "asset_id": crew_asset_id,
                "version_id": crew_version_id,
                "latest_version_id": crew_version_id,
                "status": "latest",
            }
        ],
        "crew_input_mappings": {
            "crew:research": {"topic": {"source": "state", "path": "topic"}}
        },
        "output_fields": [
            {"label": "Final answer", "source": "node", "nodeId": "crew:research", "path": "output.final_answer"}
        ],
    }
    _replace_flow_runtime_snapshot(db, flow, snapshot)

    def fake_build_crew(self, **kwargs):
        raise AssertionError("CrewAIFactory should not be called for invalid crew boundary.")

    monkeypatch.setattr(executor_module.CrewAIFactory, "build_crew", fake_build_crew)

    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "CrewAI"}},
        headers=auth_headers,
    )

    assert response.status_code == 201
    detail = _execute_background_and_get_detail(client, db, auth_headers, response.json())
    assert detail["status"] == "failed"
    assert detail["error_message"] == f"Crew runtime snapshot missing for version {crew_version_id}."
    assert (
        db.query(FlowRun)
        .filter(FlowRun.flow_version_id == flow["current_version"]["id"])
        .count()
        == 1
    )


def test_create_flow_run_captures_agent_execution_log_events(client, db, auth_headers, monkeypatch):
    from crewai.agents.parser import AgentAction, AgentFinish
    from api.db.models import Asset, AssetRuntimeSnapshot, AssetVersion, FlowRunEvent
    from api.runtime import flow_snapshot_executor as executor_module

    crew_asset_id = "33333333-3333-3333-3333-333333333333"
    crew_version_id = "44444444-4444-4444-4444-444444444444"
    db.add(Asset(id=crew_asset_id, asset_type="crew", owner_user_id="test-user", name="Telemetry Crew"))
    db.add(
        AssetVersion(
            id=crew_version_id,
            asset_id=crew_asset_id,
            version_number=1,
            status="published",
            metadata_json={},
            created_by="test-user",
        )
    )
    db.add(
        AssetRuntimeSnapshot(version_id=crew_version_id,
            runtime_snapshot_json={
                "runtime_crew": {"crew_name": "Telemetry Crew", "agent_version_ids": [], "task_version_ids": []},
                "runtime_agents": {},
                "runtime_tasks": {},
                "task_agent_links": {},
                "agent_tool_links": {},
                "task_tool_links": {},
                "runtime_tools": {},
            },
        )
    )

    flow = _create_published_flow(client, db, auth_headers, name="Telemetry Flow")
    snapshot = {
        "schemaVersion": 1,
        "graph": {
            "nodes": [
                {"id": "input:main", "type": "input", "data": {}},
                {"id": "start:main", "type": "start", "data": {}},
                {
                    "id": "crew:telemetry",
                    "type": "crew",
                    "data": {"assetId": crew_asset_id, "versionId": crew_version_id},
                },
                {"id": "output:main", "type": "output", "data": {}},
            ],
            "edges": [
                {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
                {"id": "edge:start:crew", "source": "start:main", "target": "crew:telemetry", "type": "flow"},
                {"id": "edge:crew:output", "source": "crew:telemetry", "target": "output:main", "type": "flow"},
            ],
        },
        "crew_refs": [
            {
                "node_id": "crew:telemetry",
                "asset_id": crew_asset_id,
                "version_id": crew_version_id,
                "latest_version_id": crew_version_id,
                "status": "latest",
            }
        ],
        "output_fields": [{"label": "Final", "source": "node", "nodeId": "crew:telemetry", "path": "output.raw"}],
    }
    _replace_flow_runtime_snapshot(db, flow, snapshot)

    class FakeCrew:
        def __init__(self, callbacks):
            self.callbacks = callbacks

        def kickoff(self, inputs):
            self.callbacks["step_callback"](
                AgentAction(
                    thought="Need search",
                    tool="search_docs",
                    tool_input='{"query":"CrewAI"}',
                    text="Thought: Need search",
                )
            )
            self.callbacks["step_callback"](
                AgentFinish(
                    thought="Ready",
                    output="researched CrewAI",
                    text="Final Answer: researched CrewAI",
                )
            )
            return {"raw": "researched CrewAI"}

    def fake_build_crew(self, **kwargs):
        assert kwargs["instrumentation_callbacks"] is not None
        return FakeCrew(kwargs["instrumentation_callbacks"])

    monkeypatch.setattr(executor_module.CrewAIFactory, "build_crew", fake_build_crew)

    response = client.post(
        "/api/flow-runs",
        json={
            "flow_version_id": flow["current_version"]["id"],
            "inputs": {"topic": "CrewAI"},
            "capture_agent_execution_logs": True,
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    _execute_background_and_get_detail(client, db, auth_headers, response.json())
    events = (
        db.query(FlowRunEvent)
        .filter(FlowRunEvent.run_id == response.json()["id"])
        .order_by(FlowRunEvent.created_at.asc(), FlowRunEvent.id.asc())
        .all()
    )
    agent_events = [event for event in events if event.event_type in {"agent_step", "agent_finish"}]
    assert [event.event_type for event in agent_events] == ["agent_step", "agent_finish"]
    assert agent_events[0].node_id == "crew:telemetry"
    assert agent_events[0].event_payload_json["tool"] == "search_docs"
    assert agent_events[0].event_payload_json["tool_input"] == '{"query":"CrewAI"}'
    assert agent_events[1].event_payload_json["output"] == "researched CrewAI"


def test_create_flow_run_can_disable_agent_execution_log_capture(client, db, auth_headers, monkeypatch):
    from api.runtime import flow_snapshot_executor as executor_module

    flow = _create_published_flow(
        client,
        db,
        auth_headers,
        name="Telemetry Disabled Flow",
        runtime_snapshot_json={
            "schemaVersion": 1,
            "graph": {
                "nodes": [
                    {"id": "input:main", "type": "input", "data": {}},
                    {"id": "start:main", "type": "start", "data": {}},
                    {"id": "crew:main", "type": "crew", "data": {"assetId": "crew-a", "versionId": "crew-v"}},
                    {"id": "output:main", "type": "output", "data": {}},
                ],
                "edges": [
                    {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
                    {"id": "edge:start:crew", "source": "start:main", "target": "crew:main", "type": "flow"},
                    {"id": "edge:crew:output", "source": "crew:main", "target": "output:main", "type": "flow"},
                ],
            },
            "crew_refs": [
                {
                    "node_id": "crew:main",
                    "asset_id": "crew-a",
                    "version_id": "crew-v",
                    "latest_version_id": "crew-v",
                    "status": "latest",
                }
            ],
            "output_fields": [{"label": "Raw", "source": "node", "nodeId": "crew:main", "path": "output.raw"}],
        },
    )

    captured = {}

    class FakeCrew:
        def kickoff(self, inputs):
            return {"raw": "done"}

    def fake_crew_runtime_snapshot_for_node(self, *, snapshot, crew_node, owner_user_id):
        return {
            "runtime_crew": {"crew_name": "Crew", "agent_version_ids": [], "task_version_ids": []},
            "runtime_agents": {},
            "runtime_tasks": {},
            "task_agent_links": {},
            "agent_tool_links": {},
            "task_tool_links": {},
            "runtime_tools": {},
        }

    def fake_build_crew(self, **kwargs):
        captured["instrumentation_callbacks"] = kwargs.get("instrumentation_callbacks")
        return FakeCrew()

    monkeypatch.setattr(
        executor_module.FlowSnapshotExecutor,
        "_crew_runtime_snapshot_for_node",
        fake_crew_runtime_snapshot_for_node,
    )
    monkeypatch.setattr(executor_module.CrewAIFactory, "build_crew", fake_build_crew)

    response = client.post(
        "/api/flow-runs",
        json={
            "flow_version_id": flow["current_version"]["id"],
            "inputs": {},
            "capture_agent_execution_logs": False,
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    _execute_background_and_get_detail(client, db, auth_headers, response.json())
    assert captured["instrumentation_callbacks"] is None


def test_flow_executor_wraps_crew_run_with_resolved_credential_env(monkeypatch, db):
    from cryptography.fernet import Fernet

    from api.db import models
    from api.runtime.credential_store import encrypt_secret_payload
    from api.runtime.flow_snapshot_executor import FlowSnapshotExecutor

    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    openai_credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="openai",
        label="OpenAI",
        secret_ref="secret://db/credential/test-openai",
        scopes_json=[],
        status="active",
    )
    db.add(openai_credential)
    db.flush()
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
        provider="serper",
        label="Serper",
        secret_ref="secret://db/credential/test-serper",
        scopes_json=[],
        status="active",
    )
    db.add(credential)
    db.flush()
    db.add(
        models.CredentialSecret(
            credential_id=credential.id,
            encrypted_secret_json=encrypt_secret_payload({"api_key": "serper-secret"}),
            encryption_key_version="v1",
        )
    )

    flow_asset = models.Asset(asset_type="flow", name="Credential Flow", owner_user_id="test-user")
    flow_version = models.AssetVersion(
        asset=flow_asset,
        version_number=1,
        status="published",
        created_by="test-user",
    )
    db.add_all([flow_asset, flow_version])
    db.flush()
    db.add(
        models.AssetRuntimeSnapshot(
            version_id=flow_version.id,
            runtime_snapshot_json={
                "schemaVersion": 1,
                "graph": {
                    "nodes": [
                        {"id": "start-node", "type": "start", "data": {}},
                        {
                            "id": "crew-node",
                            "type": "crew",
                            "data": {
                                "assetId": "crew-asset-1",
                                "versionId": "crew-version-1",
                            },
                        },
                        {"id": "output-node", "type": "output", "data": {}},
                    ],
                    "edges": [
                        {
                            "id": "edge-1",
                            "source": "start-node",
                            "target": "crew-node",
                            "type": "flow",
                        },
                        {
                            "id": "edge-2",
                            "source": "crew-node",
                            "target": "output-node",
                            "type": "flow",
                        },
                    ],
                },
                "crew_refs": [
                    {
                        "node_id": "crew-node",
                        "asset_id": "crew-asset-1",
                        "version_id": "crew-version-1",
                        "latest_version_id": "crew-version-1",
                        "status": "latest",
                    }
                ],
                "input_mappings": {},
                "output_mappings": {},
            },
        )
    )
    db.commit()

    observed_env = {}

    class FakeCrew:
        def kickoff(self, inputs):
            import os

            observed_env["SERPER_API_KEY"] = os.environ.get("SERPER_API_KEY")
            return {"result": "ok"}

    def fake_build_crew(self, **kwargs):
        return FakeCrew()

    def fake_crew_runtime_snapshot_for_node(self, *, snapshot, crew_node, owner_user_id):
        return {
            "runtime_crew": {
                "version_id": "crew-version-1",
                "name": "Credential Crew",
                "process": "sequential",
                "agent_version_ids": ["agent-version-1"],
                "task_version_ids": ["task-version-1"],
            },
            "runtime_agents": {
                "agent-version-1": {
                    "version_id": "agent-version-1",
                    "role": "Researcher",
                    "goal": "Search",
                    "backstory": "Uses Serper.",
                    "llm": {"provider": "openai", "model": "gpt-4o-mini"},
                }
            },
            "runtime_tasks": {
                "task-version-1": {
                    "version_id": "task-version-1",
                    "task_name": "Search",
                    "description": "Search.",
                    "expected_output": "Summary.",
                }
            },
            "task_agent_links": {"task-version-1": "agent-version-1"},
            "agent_tool_links": {"agent-version-1": ["crewai.serper_dev"]},
            "task_tool_links": {},
            "runtime_tools": {
                "crewai.serper_dev": {
                    "tool_key": "crewai.serper_dev",
                    "module_path": "crewai_tools",
                    "class_name": "SerperDevTool",
                    "default_config_json": {},
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

    monkeypatch.setenv("OPENAI_API_KEY", "existing-openai")
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.setattr(
        FlowSnapshotExecutor,
        "_crew_runtime_snapshot_for_node",
        fake_crew_runtime_snapshot_for_node,
    )
    monkeypatch.setattr(
        "api.runtime.crewai_factory.CrewAIFactory.build_crew",
        fake_build_crew,
    )

    run = FlowSnapshotExecutor(db).start_run(
        flow_version_id=flow_version.id,
        owner_user_id="test-user",
        inputs={},
    )

    assert run.status == "completed"
    assert observed_env["SERPER_API_KEY"] == "serper-secret"
    assert "SERPER_API_KEY" not in os.environ
    assert os.environ["OPENAI_API_KEY"] == "existing-openai"


def test_create_flow_run_redacts_crew_started_input_payload(client, db, auth_headers, monkeypatch):
    from api.db.models import FlowRunEvent

    class FakeCrew:
        def kickoff(self, *, inputs):
            if "card_news_slides" in inputs:
                assert inputs["card_news_slides"].startswith("raw=Launch AI Ops")
                return {"raw": "visual prompt ready"}
            return {"raw": f"raw={inputs['topic']}"}

    class FakeFactory:
        def __init__(self, *, execution_mode="validation", llm_catalog=None):
            self.execution_mode = execution_mode

        def build_crew(self, **kwargs):
            assert self.execution_mode == "live"
            return FakeCrew()

    monkeypatch.setattr("api.runtime.flow_snapshot_executor.CrewAIFactory", FakeFactory)

    content_crew = _create_published_crew_with_snapshot(
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
    visual_crew = _create_published_crew_with_snapshot(
        client,
        db,
        auth_headers,
        runtime_snapshot_json={
            "schemaVersion": 1,
            "required_inputs": ["card_news_slides"],
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
        name="Transfer Event Flow",
        runtime_snapshot_json={
            "schemaVersion": 1,
            "graph": {
                "nodes": [
                    {"id": "input:main", "type": "input", "data": {}},
                    {"id": "start:main", "type": "start", "data": {}},
                    {"id": "crew:content", "type": "crew", "data": {"assetId": content_crew["id"], "versionId": content_crew["current_version"]["id"]}},
                    {"id": "crew:visual", "type": "crew", "data": {"assetId": visual_crew["id"], "versionId": visual_crew["current_version"]["id"]}},
                    {"id": "output:main", "type": "output", "data": {}},
                ],
                "edges": [
                    {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
                    {"id": "edge:start:content", "source": "start:main", "target": "crew:content", "type": "flow"},
                    {"id": "edge:content:visual", "source": "crew:content", "target": "crew:visual", "type": "flow"},
                    {"id": "edge:visual:output", "source": "crew:visual", "target": "output:main", "type": "flow"},
                ],
                "entities": {
                    "crews": {
                        content_crew["current_version"]["id"]: {"runtime_snapshot_json": {}},
                        visual_crew["current_version"]["id"]: {"runtime_snapshot_json": {}},
                    }
                },
            },
            "crew_refs": [
                {
                    "node_id": "crew:content",
                    "asset_id": content_crew["id"],
                    "version_id": content_crew["current_version"]["id"],
                    "latest_version_id": content_crew["current_version"]["id"],
                    "status": "latest",
                },
                {
                    "node_id": "crew:visual",
                    "asset_id": visual_crew["id"],
                    "version_id": visual_crew["current_version"]["id"],
                    "latest_version_id": visual_crew["current_version"]["id"],
                    "status": "latest",
                },
            ],
            "crew_input_mappings": {
                "crew:content": {"topic": {"source": "state", "path": "topic"}},
                "crew:visual": {
                    "card_news_slides": {
                        "source": "transform",
                        "inputType": "text",
                        "nodeId": "crew:content",
                        "paths": ["output.raw"],
                        "transform": "identity_v1",
                        "maxChars": 8000,
                        "overflow": "fail",
                    }
                },
            },
            "output_fields": [{"label": "Visual", "source": "node", "nodeId": "crew:visual", "path": "output.raw"}],
        },
    )

    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "Launch AI Ops"}},
        headers=auth_headers,
    )

    assert response.status_code == 201
    run_id = response.json()["id"]
    _execute_background_and_get_detail(client, db, auth_headers, response.json())
    events = (
        db.query(FlowRunEvent)
        .filter(FlowRunEvent.run_id == run_id, FlowRunEvent.event_type == "crew_started")
        .order_by(FlowRunEvent.created_at.asc(), FlowRunEvent.id.asc())
        .all()
    )
    visual_event = [event for event in events if event.node_id == "crew:visual"][0]
    payload = visual_event.event_payload_json

    assert payload["inputs"]["card_news_slides"]["type"] == "text"
    assert payload["inputs"]["card_news_slides"]["length"] == len("raw=Launch AI Ops")
    assert "raw=Launch AI Ops" not in str(payload)


def test_create_flow_run_redacts_transfer_values_from_callback_events(client, db, auth_headers, monkeypatch):
    from api.db.models import FlowRunEvent

    class FakeCrew:
        def __init__(self, callbacks):
            self.callbacks = callbacks

        def kickoff(self, *, inputs):
            if "card_news_slides" in inputs:
                transfer_text = inputs["card_news_slides"]
                self.callbacks["step_callback"]({"output": f"rendered prompt: {transfer_text}"})
                return {"raw": "visual prompt ready"}
            return {"raw": f"raw={inputs['topic']}"}

    class FakeFactory:
        def __init__(self, *, execution_mode="validation", llm_catalog=None):
            self.execution_mode = execution_mode

        def build_crew(self, **kwargs):
            assert self.execution_mode == "live"
            return FakeCrew(kwargs["instrumentation_callbacks"])

    monkeypatch.setattr("api.runtime.flow_snapshot_executor.CrewAIFactory", FakeFactory)

    content_crew = _create_published_crew_with_snapshot(
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
    visual_crew = _create_published_crew_with_snapshot(
        client,
        db,
        auth_headers,
        runtime_snapshot_json={
            "schemaVersion": 1,
            "required_inputs": ["card_news_slides"],
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
        name="Transfer Callback Redaction Flow",
        runtime_snapshot_json={
            "schemaVersion": 1,
            "graph": {
                "nodes": [
                    {"id": "input:main", "type": "input", "data": {}},
                    {"id": "start:main", "type": "start", "data": {}},
                    {"id": "crew:content", "type": "crew", "data": {"assetId": content_crew["id"], "versionId": content_crew["current_version"]["id"]}},
                    {"id": "crew:visual", "type": "crew", "data": {"assetId": visual_crew["id"], "versionId": visual_crew["current_version"]["id"]}},
                    {"id": "output:main", "type": "output", "data": {}},
                ],
                "edges": [
                    {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
                    {"id": "edge:start:content", "source": "start:main", "target": "crew:content", "type": "flow"},
                    {"id": "edge:content:visual", "source": "crew:content", "target": "crew:visual", "type": "flow"},
                    {"id": "edge:visual:output", "source": "crew:visual", "target": "output:main", "type": "flow"},
                ],
            },
            "crew_refs": [
                {
                    "node_id": "crew:content",
                    "asset_id": content_crew["id"],
                    "version_id": content_crew["current_version"]["id"],
                    "latest_version_id": content_crew["current_version"]["id"],
                    "status": "latest",
                },
                {
                    "node_id": "crew:visual",
                    "asset_id": visual_crew["id"],
                    "version_id": visual_crew["current_version"]["id"],
                    "latest_version_id": visual_crew["current_version"]["id"],
                    "status": "latest",
                },
            ],
            "crew_input_mappings": {
                "crew:content": {"topic": {"source": "state", "path": "topic"}},
                "crew:visual": {
                    "card_news_slides": {
                        "source": "transform",
                        "inputType": "text",
                        "nodeId": "crew:content",
                        "paths": ["output.raw"],
                        "transform": "identity_v1",
                    }
                },
            },
            "output_fields": [{"label": "Visual", "source": "node", "nodeId": "crew:visual", "path": "output.raw"}],
        },
    )

    response = client.post(
        "/api/flow-runs",
        json={"flow_version_id": flow["current_version"]["id"], "inputs": {"topic": "Launch AI Ops"}},
        headers=auth_headers,
    )

    assert response.status_code == 201
    _execute_background_and_get_detail(client, db, auth_headers, response.json())
    callback_event = (
        db.query(FlowRunEvent)
        .filter(
            FlowRunEvent.run_id == response.json()["id"],
            FlowRunEvent.node_id == "crew:visual",
            FlowRunEvent.event_type == "agent_finish",
        )
        .one()
    )

    assert callback_event.event_payload_json["output"] == "rendered prompt: [redacted]"
    assert "raw=Launch AI Ops" not in str(callback_event.event_payload_json)
