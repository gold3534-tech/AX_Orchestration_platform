from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from tests.fixtures_api import auth_headers, client, db


def _create_flow(client, auth_headers):
    response = client.post(
        "/api/assets",
        json={
            "type": "flow",
            "name": "Launch Flow",
            "description": "Canvas-first Flow",
            "payload": {"entry_method": "run"},
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def _create_published_crew(client, db, auth_headers):
    from api.db.models import AssetRuntimeSnapshot, AssetVersion

    response = client.post(
        "/api/assets",
        json={
            "type": "crew",
            "name": "Research Crew",
            "description": "Published Crew",
            "payload": {
                "process": "sequential",
                "manager_llm": {},
                "manager_agent_asset_id": None,
                "function_calling_llm": {},
                "verbose": False,
                "planning": False,
                "memory": False,
            },
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    crew = response.json()
    asset_version = db.get(AssetVersion, crew["current_version"]["id"])
    asset_version.status = "published"
    runtime_snapshot = AssetRuntimeSnapshot(
        version_id=crew["current_version"]["id"],
        runtime_snapshot_json={
            "schemaVersion": 1,
            "required_inputs": ["topic"],
            "output_schema": {"type": "object", "properties": {"final_answer": {"type": "string"}}},
        },
    )
    db.add(asset_version)
    db.add(runtime_snapshot)
    db.commit()
    return crew


def _create_published_crew_with_required_tool_credential(client, db, auth_headers):
    from api.db.models import AssetRuntimeSnapshot, AssetVersion

    response = client.post(
        "/api/assets",
        json={
            "type": "crew",
            "name": "Tool Credential Crew",
            "description": "Published Crew",
            "payload": {
                "process": "sequential",
                "manager_llm": {},
                "manager_agent_asset_id": None,
                "function_calling_llm": {},
                "verbose": False,
                "planning": False,
                "memory": False,
            },
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    crew = response.json()
    asset_version = db.get(AssetVersion, crew["current_version"]["id"])
    asset_version.status = "published"
    runtime_snapshot = AssetRuntimeSnapshot(
        version_id=crew["current_version"]["id"],
        runtime_snapshot_json={
            "schemaVersion": 1,
            "required_inputs": ["topic"],
            "output_schema": {"type": "object", "properties": {"final_answer": {"type": "string"}}},
            "runtime_crew": {
                "agent_version_ids": ["agent-1"],
                "task_version_ids": ["task-1"],
            },
            "runtime_agents": {},
            "runtime_tasks": {},
            "task_agent_links": {"task-1": "agent-1"},
            "agent_tool_links": {"agent-1": ["search_docs"]},
            "task_tool_links": {},
            "runtime_tools": {
                "search_docs": {
                    "module_path": "api.tools.search_docs",
                    "class_name": "SearchDocsTool",
                    "config_schema_json": {"type": "object", "properties": {}, "additionalProperties": False},
                    "default_config_json": {},
                    "credential_requirements": [
                        {"provider": "serper", "env_var": "SERPER_API_KEY", "required": True, "injection": "env"}
                    ],
                }
            },
        },
    )
    db.add(asset_version)
    db.add(runtime_snapshot)
    db.commit()
    return crew


def _create_published_crew_with_google_sheets_runtime_context(client, db, auth_headers):
    from api.db.models import AssetRuntimeSnapshot, AssetVersion

    response = client.post(
        "/api/assets",
        json={
            "type": "crew",
            "name": "Sheets Credential Crew",
            "description": "Published Crew",
            "payload": {
                "process": "sequential",
                "manager_llm": {},
                "manager_agent_asset_id": None,
                "function_calling_llm": {},
                "verbose": False,
                "planning": False,
                "memory": False,
            },
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    crew = response.json()
    asset_version = db.get(AssetVersion, crew["current_version"]["id"])
    asset_version.status = "published"
    runtime_snapshot = AssetRuntimeSnapshot(
        version_id=crew["current_version"]["id"],
        runtime_snapshot_json={
            "schemaVersion": 1,
            "required_inputs": ["topic"],
            "output_schema": {"type": "object", "properties": {"final_answer": {"type": "string"}}},
            "runtime_crew": {
                "agent_version_ids": ["agent-1"],
                "task_version_ids": ["task-1"],
            },
            "runtime_agents": {},
            "runtime_tasks": {},
            "task_agent_links": {"task-1": "agent-1"},
            "agent_tool_links": {"agent-1": ["ax.google_sheets"]},
            "task_tool_links": {},
            "runtime_tools": {
                "ax.google_sheets": {
                    "module_path": "api.tools.google_sheets_tool",
                    "class_name": "AXGoogleSheetsTool",
                    "config_schema_json": {"type": "object", "properties": {}, "additionalProperties": True},
                    "default_config_json": {},
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
        },
    )
    db.add(asset_version)
    db.add(runtime_snapshot)
    db.commit()
    return crew


def _create_published_crew_with_optional_tool_env(client, db, auth_headers):
    from api.db.models import AssetRuntimeSnapshot, AssetVersion

    response = client.post(
        "/api/assets",
        json={
            "type": "crew",
            "name": "Optional Env Crew",
            "description": "Published Crew",
            "payload": {
                "process": "sequential",
                "manager_llm": {},
                "manager_agent_asset_id": None,
                "function_calling_llm": {},
                "verbose": False,
                "planning": False,
                "memory": False,
            },
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    crew = response.json()
    asset_version = db.get(AssetVersion, crew["current_version"]["id"])
    asset_version.status = "published"
    runtime_snapshot = AssetRuntimeSnapshot(
        version_id=crew["current_version"]["id"],
        runtime_snapshot_json={
            "schemaVersion": 1,
            "required_inputs": ["topic"],
            "output_schema": {"type": "object", "properties": {"final_answer": {"type": "string"}}},
            "runtime_crew": {"agent_version_ids": ["agent-1"], "task_version_ids": ["task-1"]},
            "runtime_agents": {},
            "runtime_tasks": {},
            "task_agent_links": {"task-1": "agent-1"},
            "agent_tool_links": {"agent-1": ["optional_search"]},
            "task_tool_links": {},
            "runtime_tools": {
                "optional_search": {
                    "module_path": "api.tools.optional_search",
                    "class_name": "OptionalSearchTool",
                    "config_schema_json": {"type": "object", "properties": {}, "additionalProperties": False},
                    "default_config_json": {},
                    "credential_requirements": [
                        {"provider": "serper", "env_var": "SERPER_API_KEY", "required": False, "injection": "env"}
                    ],
                    "required_env_vars": [
                        {"name": "OPTIONAL_TOOL_TOKEN", "description": "Optional token", "required": False}
                    ],
                }
            },
        },
    )
    db.add(asset_version)
    db.add(runtime_snapshot)
    db.commit()
    return crew


def _create_published_crew_with_manager_only_tool(client, db, auth_headers):
    from api.db.models import AssetRuntimeSnapshot, AssetVersion

    response = client.post(
        "/api/assets",
        json={
            "type": "crew",
            "name": "Manager Tool Crew",
            "description": "Published Crew",
            "payload": {
                "process": "hierarchical",
                "manager_llm": {"provider": "openai", "model": "gpt-4o-mini"},
                "manager_agent_asset_id": None,
                "function_calling_llm": {},
                "verbose": False,
                "planning": False,
                "memory": False,
            },
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    crew = response.json()
    asset_version = db.get(AssetVersion, crew["current_version"]["id"])
    asset_version.status = "published"
    runtime_snapshot = AssetRuntimeSnapshot(
        version_id=crew["current_version"]["id"],
        runtime_snapshot_json={
            "schemaVersion": 1,
            "required_inputs": ["topic"],
            "output_schema": {"type": "object", "properties": {"final_answer": {"type": "string"}}},
            "runtime_crew": {
                "agent_version_ids": [],
                "task_version_ids": ["task-1"],
                "manager_agent_version_id": "manager-agent-1",
            },
            "runtime_agents": {},
            "runtime_tasks": {},
            "task_agent_links": {},
            "agent_tool_links": {"manager-agent-1": ["manager_optional"]},
            "task_tool_links": {},
            "runtime_tools": {
                "manager_optional": {
                    "module_path": "api.tools.manager_optional",
                    "class_name": "ManagerOptionalTool",
                    "config_schema_json": {"type": "object", "properties": {}, "additionalProperties": False},
                    "default_config_json": {},
                    "credential_requirements": [
                        {"provider": "serper", "env_var": "SERPER_API_KEY", "required": False, "injection": "env"}
                    ],
                    "required_env_vars": [
                        {"name": "MANAGER_OPTIONAL_TOKEN", "description": "Optional token", "required": False}
                    ],
                }
            },
        },
    )
    db.add(asset_version)
    db.add(runtime_snapshot)
    db.commit()
    return crew


def _create_active_credential(db, *, provider: str, with_secret: bool, api_key: str = "secret-key"):
    from api.db import models

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
    if with_secret:
        from api.runtime.credential_store import encrypt_secret_payload

        db.add(
            models.CredentialSecret(
                credential_id=credential.id,
                encrypted_secret_json=encrypt_secret_payload({"api_key": api_key}),
                encryption_key_version="v1",
            )
        )
    db.commit()
    return credential


def _create_unlisted_crew(client, db, auth_headers, *, status: str, runtime_snapshot_json: dict):
    from api.db.models import AssetRuntimeSnapshot, AssetVersion

    response = client.post(
        "/api/assets",
        json={
            "type": "crew",
            "name": f"Unlisted {status}",
            "description": "Should not appear",
            "payload": {
                "process": "sequential",
                "manager_llm": {},
                "manager_agent_asset_id": None,
                "function_calling_llm": {},
                "verbose": False,
                "planning": False,
                "memory": False,
            },
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    crew = response.json()
    asset_version = db.get(AssetVersion, crew["current_version"]["id"])
    asset_version.status = status
    runtime_snapshot = AssetRuntimeSnapshot(
        version_id=crew["current_version"]["id"],
        runtime_snapshot_json=runtime_snapshot_json,
    )
    db.add(asset_version)
    db.add(runtime_snapshot)
    db.commit()
    return crew


def _flow_graph(crew_asset_id: str, crew_version_id: str) -> dict:
    return {
        "schemaVersion": 1,
        "nodes": [
            {
                "id": "input:main",
                "type": "input",
                "position": {"x": 0, "y": 0},
                "data": {"fields": [{"name": "topic", "type": "string", "required": True}]},
            },
            {"id": "start:main", "type": "start", "position": {"x": 160, "y": 0}, "data": {"triggerType": "manual"}},
            {
                "id": "crew:research",
                "type": "crew",
                "position": {"x": 320, "y": 0},
                "data": {
                    "assetId": crew_asset_id,
                    "versionId": crew_version_id,
                    "inputMappings": {"topic": {"source": "state", "path": "topic"}},
                },
            },
            {
                "id": "output:main",
                "type": "output",
                "position": {"x": 640, "y": 0},
                "data": {
                    "fields": [
                        {"label": "Answer", "source": "node", "nodeId": "crew:research", "path": "output.final_answer"}
                    ]
                },
            },
        ],
        "edges": [
            {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
            {"id": "edge:start:crew", "source": "start:main", "target": "crew:research", "type": "flow"},
            {"id": "edge:crew:output", "source": "crew:research", "target": "output:main", "type": "flow"},
        ],
    }


def test_flow_graph_draft_save_load_validate_and_publish(client, db, auth_headers):
    from api.db.models import AssetRuntimeSnapshot

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])

    save_response = client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers)
    assert save_response.status_code == 200
    assert save_response.json()["draft"]["graph"]["nodes"][0]["type"] == "input"

    load_response = client.get(f"/api/flow-graphs/{flow['id']}/draft", headers=auth_headers)
    assert load_response.status_code == 200
    assert load_response.json()["draft"]["graph"]["nodes"][2]["data"]["versionId"] == crew["current_version"]["id"]

    validate_response = client.post(f"/api/flow-graphs/{flow['id']}/validate", headers=auth_headers)
    assert validate_response.status_code == 200
    assert validate_response.json()["schemaVersion"] == 1

    publish_response = client.post(f"/api/flow-graphs/{flow['id']}/publish", headers=auth_headers)
    assert publish_response.status_code == 200
    body = publish_response.json()
    assert body["version"]["status"] == "published"
    assert body["version"]["runtime_snapshot_json"]["schemaVersion"] == 1
    assert body["version"]["runtime_snapshot_json"]["crew_refs"][0]["asset_id"] == crew["id"]
    assert "runtime_snapshot_json" not in body["version"]["payload"]

    published_snapshot = db.get(AssetRuntimeSnapshot, body["version"]["id"])
    assert published_snapshot is not None
    assert published_snapshot.runtime_snapshot_json["schemaVersion"] == 1
    assert published_snapshot.runtime_snapshot_json["crew_refs"][0]["asset_id"] == crew["id"]

    restore_response = client.post(
        f"/api/assets/{flow['id']}/versions/{body['version']['id']}/restore",
        headers=auth_headers,
    )
    assert restore_response.status_code == 200
    assert "runtime_snapshot_json" not in restore_response.json()["current_version"]["payload"]


def test_save_flow_draft_overwrites_existing_draft_version_row_when_current_is_draft(client, db, auth_headers):
    from api.db.models import AssetVersion, FlowVersionDraft

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])

    first_save = client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers)
    assert first_save.status_code == 200
    first_draft_id = first_save.json()["draft"]["id"]

    changed_graph = _flow_graph(crew["id"], crew["current_version"]["id"])
    changed_graph["nodes"][3]["data"]["fields"][0]["label"] = "Changed Answer"
    second_save = client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": changed_graph}, headers=auth_headers)
    assert second_save.status_code == 200

    versions = (
        db.query(AssetVersion)
        .filter(AssetVersion.asset_id == flow["id"])
        .order_by(AssetVersion.version_number.asc())
        .all()
    )
    assert [version.version_number for version in versions] == [1]
    assert [version.status for version in versions] == ["draft"]

    draft = db.query(FlowVersionDraft).filter(FlowVersionDraft.flow_asset_id == flow["id"]).one()
    assert str(draft.id) == first_draft_id
    assert str(draft.base_version_id) == flow["current_version"]["id"]
    assert draft.graph_json["nodes"][3]["data"]["fields"][0]["label"] == "Changed Answer"


def test_save_flow_draft_creates_new_draft_version_when_current_is_published(client, db, auth_headers):
    from api.db.models import AssetRuntimeSnapshot, AssetVersion, FlowVersionDraft

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])

    save_response = client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers)
    assert save_response.status_code == 200
    publish_response = client.post(f"/api/flow-graphs/{flow['id']}/publish", headers=auth_headers)
    assert publish_response.status_code == 200
    published_version_id = publish_response.json()["version"]["id"]

    changed_graph = _flow_graph(crew["id"], crew["current_version"]["id"])
    changed_graph["nodes"][3]["data"]["fields"][0]["label"] = "Edited From Published"
    second_save = client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": changed_graph}, headers=auth_headers)
    assert second_save.status_code == 200
    draft_body = second_save.json()["draft"]

    versions = (
        db.query(AssetVersion)
        .filter(AssetVersion.asset_id == flow["id"])
        .order_by(AssetVersion.version_number.asc())
        .all()
    )
    assert [version.version_number for version in versions] == [1, 2, 3]
    assert [version.status for version in versions] == ["draft", "published", "draft"]
    assert str(versions[2].base_version_id) == published_version_id
    assert versions[2].payload_json == {"entry_method": "run"}

    assert db.get(AssetRuntimeSnapshot, versions[2].id) is None

    draft = db.query(FlowVersionDraft).filter(FlowVersionDraft.flow_asset_id == flow["id"]).one()
    assert str(draft.base_version_id) == str(versions[2].id)
    assert draft_body["base_version_id"] == str(versions[2].id)
    assert draft.graph_json["nodes"][3]["data"]["fields"][0]["label"] == "Edited From Published"


def test_save_flow_draft_from_published_preserves_current_version_metadata(client, db, auth_headers):
    from api.db.models import AssetVersion

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])

    save_response = client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers)
    assert save_response.status_code == 200
    publish_response = client.post(f"/api/flow-graphs/{flow['id']}/publish", headers=auth_headers)
    assert publish_response.status_code == 200

    published_version = db.get(AssetVersion, publish_response.json()["version"]["id"])
    published_version.metadata_json = {
        **(published_version.metadata_json or {}),
        "review_marker": "kept across draft save",
        "external": {"ticket": "FLOW-123"},
    }
    db.add(published_version)
    db.commit()

    changed_graph = _flow_graph(crew["id"], crew["current_version"]["id"])
    changed_graph["nodes"][3]["data"]["fields"][0]["label"] = "Edited From Published"
    second_save = client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": changed_graph}, headers=auth_headers)
    assert second_save.status_code == 200

    versions = (
        db.query(AssetVersion)
        .filter(AssetVersion.asset_id == flow["id"])
        .order_by(AssetVersion.version_number.asc())
        .all()
    )
    assert versions[2].metadata_json["review_marker"] == "kept across draft save"
    assert versions[2].metadata_json["external"] == {"ticket": "FLOW-123"}
    assert versions[2].metadata_json["change_summary"] == "draft:flow_graph"


def test_publish_flow_draft_creates_new_version_when_snapshot_is_unchanged(client, db, auth_headers):
    from api.db.models import AssetRuntimeSnapshot, AssetVersion, FlowVersionDraft

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])

    save_response = client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers)
    assert save_response.status_code == 200

    first_publish = client.post(f"/api/flow-graphs/{flow['id']}/publish", headers=auth_headers)
    second_publish = client.post(f"/api/flow-graphs/{flow['id']}/publish", headers=auth_headers)

    assert first_publish.status_code == 200
    assert second_publish.status_code == 200
    assert first_publish.json()["already_published"] is False
    assert second_publish.json()["already_published"] is False
    assert second_publish.json()["version"]["id"] != first_publish.json()["version"]["id"]

    versions = (
        db.query(AssetVersion)
        .filter(AssetVersion.asset_id == flow["id"])
        .order_by(AssetVersion.version_number.asc())
        .all()
    )
    assert [version.version_number for version in versions] == [1, 2, 3]
    assert [version.status for version in versions] == ["draft", "archived", "published"]

    assert db.get(AssetRuntimeSnapshot, first_publish.json()["version"]["id"]) is not None
    assert db.get(AssetRuntimeSnapshot, second_publish.json()["version"]["id"]) is not None

    draft = db.query(FlowVersionDraft).filter(FlowVersionDraft.flow_asset_id == flow["id"]).one()
    assert str(draft.base_version_id) == second_publish.json()["version"]["id"]


def test_publish_flow_draft_archives_previous_published_version_when_changed(client, db, auth_headers):
    from api.db.models import AssetVersion

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])

    assert client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers).status_code == 200
    first_publish = client.post(f"/api/flow-graphs/{flow['id']}/publish", headers=auth_headers)
    assert first_publish.status_code == 200

    changed_graph = _flow_graph(crew["id"], crew["current_version"]["id"])
    changed_graph["nodes"][3]["data"]["fields"][0]["label"] = "Final Answer"
    assert client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": changed_graph}, headers=auth_headers).status_code == 200

    second_publish = client.post(f"/api/flow-graphs/{flow['id']}/publish", headers=auth_headers)

    assert second_publish.status_code == 200
    assert second_publish.json()["already_published"] is False
    assert second_publish.json()["version"]["id"] != first_publish.json()["version"]["id"]

    versions = (
        db.query(AssetVersion)
        .filter(AssetVersion.asset_id == flow["id"])
        .order_by(AssetVersion.version_number.asc())
        .all()
    )
    assert [version.version_number for version in versions] == [1, 2, 3, 4]
    assert [version.status for version in versions] == ["draft", "archived", "draft", "published"]


def test_flow_pinned_to_archived_crew_version_remains_valid_after_crew_republish(client, db, auth_headers):
    from api.db.models import AssetVersion
    from tests.test_crew_graph_routes_v2 import make_valid_publish_graph_for_asset

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew(client, db, auth_headers)
    pinned_crew_version_id = crew["current_version"]["id"]
    graph = _flow_graph(crew["id"], pinned_crew_version_id)

    save_response = client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers)
    assert save_response.status_code == 200

    crew_draft_response = client.put(
        f"/api/crew-graphs/{crew['id']}/draft",
        json={"graph": make_valid_publish_graph_for_asset(crew)},
        headers=auth_headers,
    )
    assert crew_draft_response.status_code == 200
    crew_publish_response = client.post(f"/api/crew-graphs/{crew['id']}/publish", headers=auth_headers)
    assert crew_publish_response.status_code == 200
    latest_crew_version_id = crew_publish_response.json()["version"]["id"]

    pinned_version = db.get(AssetVersion, pinned_crew_version_id)
    assert pinned_version.status == "archived"

    validate_response = client.post(f"/api/flow-graphs/{flow['id']}/validate", headers=auth_headers)
    assert validate_response.status_code == 200
    assert validate_response.json()["crew_refs"] == [
        {
            "node_id": "crew:research",
            "asset_id": crew["id"],
            "version_id": pinned_crew_version_id,
            "latest_version_id": latest_crew_version_id,
            "status": "new_version_available",
        }
    ]

    publish_response = client.post(f"/api/flow-graphs/{flow['id']}/publish", headers=auth_headers)
    assert publish_response.status_code == 200
    body = publish_response.json()
    assert "crew_refs" not in body["version"]["payload"]
    assert body["version"]["runtime_snapshot_json"]["crew_refs"] == [
        {
            "node_id": "crew:research",
            "asset_id": crew["id"],
            "version_id": pinned_crew_version_id,
            "latest_version_id": latest_crew_version_id,
            "status": "new_version_available",
        }
    ]


def test_get_flow_draft_returns_empty_envelope_when_missing(client, auth_headers):
    flow = _create_flow(client, auth_headers)

    response = client.get(f"/api/flow-graphs/{flow['id']}/draft", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["draft"] is None


def test_publish_flow_draft_rejects_stale_base_version_without_duplicate(client, db, auth_headers):
    from api.db.models import AssetVersion, FlowVersionDraft

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])

    save_response = client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers)
    assert save_response.status_code == 200
    original_base_version_id = save_response.json()["draft"]["base_version_id"]

    update_response = client.patch(
        f"/api/assets/{flow['id']}",
        json={
            "base_version_id": flow["current_version"]["id"],
            "name": "Launch Flow v2",
            "payload": {
                "entry_method": "run",
                "timeout_seconds": 180,
            },
        },
        headers=auth_headers,
    )
    assert update_response.status_code == 200

    publish_response = client.post(f"/api/flow-graphs/{flow['id']}/publish", headers=auth_headers)

    assert publish_response.status_code == 409
    assert publish_response.json()["detail"] == "Asset has a newer version. Refresh and retry from the latest version."

    versions = (
        db.query(AssetVersion)
        .filter(AssetVersion.asset_id == flow["id"])
        .order_by(AssetVersion.version_number.asc())
        .all()
    )
    assert [version.version_number for version in versions] == [1, 2]

    draft = db.query(FlowVersionDraft).filter(FlowVersionDraft.flow_asset_id == flow["id"]).one()
    assert str(draft.base_version_id) == original_base_version_id


def test_save_flow_draft_maps_asset_conflict_to_409(client, db, auth_headers):
    from api.services.assets import AssetConflictError

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])
    save_response = client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers)
    assert save_response.status_code == 200
    publish_response = client.post(f"/api/flow-graphs/{flow['id']}/publish", headers=auth_headers)
    assert publish_response.status_code == 200

    with patch(
        "api.routes.flow_graphs.save_flow_draft",
        side_effect=AssetConflictError("Asset has a newer version. Refresh and retry from the latest version."),
    ):
        response = client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "Asset has a newer version. Refresh and retry from the latest version."


def test_save_flow_draft_rolls_back_uncommitted_draft_version_on_exception(client, db, auth_headers, monkeypatch):
    from api.db.models import AssetVersion
    import api.services.flow_graphs as flow_graphs_service

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])
    assert client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers).status_code == 200
    publish_response = client.post(f"/api/flow-graphs/{flow['id']}/publish", headers=auth_headers)
    assert publish_response.status_code == 200

    original_create_next_flow_draft_version = flow_graphs_service.create_next_flow_draft_version

    def create_then_conflict(*args, **kwargs):
        original_create_next_flow_draft_version(*args, **kwargs)
        raise RuntimeError("unexpected failure after draft version flush")

    monkeypatch.setattr(flow_graphs_service, "create_next_flow_draft_version", create_then_conflict)

    with pytest.raises(RuntimeError, match="unexpected failure after draft version flush"):
        flow_graphs_service.save_flow_draft(
            db,
            flow_asset_id=flow["id"],
            owner_user_id="test-user",
            graph=graph,
        )

    versions = (
        db.query(AssetVersion)
        .filter(AssetVersion.asset_id == flow["id"])
        .order_by(AssetVersion.version_number.asc())
        .all()
    )
    assert [version.version_number for version in versions] == [1, 2]
    assert [version.status for version in versions] == ["draft", "published"]


def test_get_flow_draft_rejects_owned_non_flow_asset(client, auth_headers):
    crew = client.post(
        "/api/assets",
        json={
            "type": "crew",
            "name": "Research Crew",
            "description": "Not a flow",
            "payload": {
                "process": "sequential",
                "manager_llm": {},
                "manager_agent_asset_id": None,
                "function_calling_llm": {},
                "verbose": False,
                "planning": False,
                "memory": False,
            },
        },
        headers=auth_headers,
    ).json()

    response = client.get(f"/api/flow-graphs/{crew['id']}/draft", headers=auth_headers)

    assert response.status_code == 422
    assert response.json()["detail"] == f"Asset is not a flow asset: {crew['id']}"


def test_flow_graph_published_crews_picker_lists_only_published_runtime_crews(client, db, auth_headers):
    crew = _create_published_crew(client, db, auth_headers)
    _create_unlisted_crew(client, db, auth_headers, status="published", runtime_snapshot_json={})
    _create_unlisted_crew(
        client,
        db,
        auth_headers,
        status="draft",
        runtime_snapshot_json={"schemaVersion": 1},
    )

    response = client.get("/api/flow-graphs/published-crews", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["crews"] == [
        {
            "asset_id": crew["id"],
            "version_id": crew["current_version"]["id"],
            "version_no": 1,
            "name": "Research Crew",
            "description": "Published Crew",
            "status": "published",
            "runtime_snapshot_json": {
                "schemaVersion": 1,
                "required_inputs": ["topic"],
                "output_schema": {"type": "object", "properties": {"final_answer": {"type": "string"}}},
            },
        }
    ]


def test_flow_graph_published_flows_lists_runtime_backed_flows_for_run_page(client, db, auth_headers):
    from api.db.models import AssetRuntimeSnapshot

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])

    assert client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers).status_code == 200
    publish_response = client.post(f"/api/flow-graphs/{flow['id']}/publish", headers=auth_headers)
    assert publish_response.status_code == 200
    version = publish_response.json()["version"]

    snapshot = db.get(AssetRuntimeSnapshot, version["id"])
    assert snapshot is not None

    response = client.get("/api/flow-graphs/published-flows", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["flows"] == [
        {
            "asset_id": flow["id"],
            "version_id": version["id"],
            "version_no": version["version_no"],
            "name": "Launch Flow",
            "description": "Canvas-first Flow",
            "status": "published",
            "has_input_node": True,
        }
    ]


def test_flow_graph_compatibility_route_returns_diagnostics(client, db, auth_headers, monkeypatch):
    from api.services import flow_graphs

    monkeypatch.setattr(
        flow_graphs,
        "run_compatibility_diagnostics",
        lambda *, snapshot, inputs, **kwargs: {
            "mode": "compatibility",
            "status": "passed",
            "provider_calls": "blocked",
            "required_credentials": ["openai"],
            "crews": [{"node_id": "crew:research", "build_crew": "passed", "kickoff": "passed", "llm_call": "passed"}],
        },
    )

    flow = client.post(
        "/api/assets",
        json={"type": "flow", "name": "Diagnostic Flow", "description": "", "payload": {"entry_method": "run"}},
        headers=auth_headers,
    ).json()
    crew = _create_published_crew(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])
    assert client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers).status_code == 200
    response = client.post(
        f"/api/flow-graphs/{flow['id']}/diagnostics/compatibility",
        json={"inputs": {"topic": "MVP"}},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "compatibility"
    assert response.json()["provider_calls"] == "blocked"


def test_flow_graph_tool_mock_call_route_returns_diagnostics(client, db, auth_headers, monkeypatch):
    from api.services import flow_graphs

    monkeypatch.setattr(
        flow_graphs,
        "run_tool_mock_call_check",
        lambda *, snapshot, live_credential_providers, **kwargs: {
            "mode": "tool_mock_call",
            "status": "passed",
            "tools": [{"tool_key": "crewai.serper_dev", "external_call": "not_called"}],
        },
    )

    flow = client.post(
        "/api/assets",
        json={"type": "flow", "name": "Tool Diagnostic Flow", "description": "", "payload": {"entry_method": "run"}},
        headers=auth_headers,
    ).json()
    crew = _create_published_crew(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])
    assert client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers).status_code == 200
    response = client.post(
        f"/api/flow-graphs/{flow['id']}/diagnostics/tool-mock-call",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "tool_mock_call"
    assert response.json()["tools"][0]["external_call"] == "not_called"


def test_flow_graph_diagnostics_routes_return_404_without_draft(client, auth_headers):
    flow = client.post(
        "/api/assets",
        json={"type": "flow", "name": "No Draft Diagnostics", "description": "", "payload": {"entry_method": "run"}},
        headers=auth_headers,
    ).json()

    compatibility_response = client.post(
        f"/api/flow-graphs/{flow['id']}/diagnostics/compatibility",
        json={"inputs": {"topic": "MVP"}},
        headers=auth_headers,
    )
    tool_response = client.post(
        f"/api/flow-graphs/{flow['id']}/diagnostics/tool-mock-call",
        headers=auth_headers,
    )

    assert compatibility_response.status_code == 404
    assert compatibility_response.json()["detail"] == f"Flow draft not found: {flow['id']}"
    assert tool_response.status_code == 404
    assert tool_response.json()["detail"] == f"Flow draft not found: {flow['id']}"


def test_flow_graph_tool_mock_call_route_reports_required_credential_unavailable_without_active_credential(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from api.services import flow_graphs

    monkeypatch.setattr(
        flow_graphs,
        "run_tool_mock_call_check",
        lambda *, snapshot, live_credential_providers, **kwargs: {
            "mode": "tool_mock_call",
            "status": "passed",
            "tools": [
                {
                    "tool_key": "search_docs",
                    "credential_requirements": [
                        {
                            "provider": "serper",
                            "required": True,
                            "available_for_live_run": "serper" in live_credential_providers,
                        }
                    ],
                }
            ],
        },
    )

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew_with_required_tool_credential(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])
    assert client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers).status_code == 200

    response = client.post(f"/api/flow-graphs/{flow['id']}/diagnostics/tool-mock-call", headers=auth_headers)

    assert response.status_code == 200
    requirement = response.json()["tools"][0]["credential_requirements"][0]
    assert requirement["provider"] == "serper"
    assert requirement["available_for_live_run"] is False


def test_flow_graph_tool_mock_call_route_reports_required_credential_available_with_active_metadata(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from api.services import flow_graphs
    from cryptography.fernet import Fernet

    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setattr(
        flow_graphs,
        "run_tool_mock_call_check",
        lambda *, snapshot, live_credential_providers, **kwargs: {
            "mode": "tool_mock_call",
            "status": "passed",
            "tools": [
                {
                    "tool_key": "search_docs",
                    "credential_requirements": [
                        {
                            "provider": "serper",
                            "required": True,
                            "available_for_live_run": "serper" in live_credential_providers,
                        }
                    ],
                }
            ],
        },
    )
    _create_active_credential(db, provider="serper", with_secret=True, api_key="serper-secret")

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew_with_required_tool_credential(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])
    assert client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers).status_code == 200

    response = client.post(f"/api/flow-graphs/{flow['id']}/diagnostics/tool-mock-call", headers=auth_headers)

    assert response.status_code == 200
    requirement = response.json()["tools"][0]["credential_requirements"][0]
    assert requirement["provider"] == "serper"
    assert requirement["available_for_live_run"] is True


def test_flow_graph_tool_mock_call_route_reports_google_sheets_oauth_available_with_valid_token(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from api.db import models
    from api.integrations.google_workspace import GOOGLE_SHEETS_SCOPE
    from api.runtime.credential_store import encrypt_secret_payload
    from api.services import flow_graphs
    from cryptography.fernet import Fernet

    observed_live_providers = []

    def fake_tool_mock_call_check(*, snapshot, live_credential_providers, **kwargs):
        observed_live_providers.append(live_credential_providers)
        return {
            "mode": "tool_mock_call",
            "status": "passed",
            "tools": [
                {
                    "tool_key": "ax.google_sheets",
                    "credential_requirements": [
                        {
                            "provider": "google_workspace",
                            "required": True,
                            "available_for_live_run": "google_workspace" in live_credential_providers,
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr(flow_graphs, "run_tool_mock_call_check", fake_tool_mock_call_check)
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
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
            encrypted_secret_json=encrypt_secret_payload({"access_token": "sheets-access-token"}),
            encryption_key_version="v1",
        )
    )
    db.commit()

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew_with_google_sheets_runtime_context(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])
    assert client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers).status_code == 200

    response = client.post(f"/api/flow-graphs/{flow['id']}/diagnostics/tool-mock-call", headers=auth_headers)

    assert response.status_code == 200
    assert observed_live_providers == [["google_workspace"]]
    requirement = response.json()["tools"][0]["credential_requirements"][0]
    assert requirement["provider"] == "google_workspace"
    assert requirement["available_for_live_run"] is True


@pytest.mark.parametrize(
    "scopes,with_secret",
    [
        pytest.param(["https://www.googleapis.com/auth/spreadsheets"], False, id="missing-secret"),
        pytest.param([], True, id="missing-scope"),
    ],
)
def test_flow_graph_tool_mock_call_route_reports_google_sheets_oauth_unavailable_when_runtime_token_invalid(
    client,
    db,
    auth_headers,
    monkeypatch,
    scopes,
    with_secret,
):
    from api.db import models
    from api.runtime.credential_store import encrypt_secret_payload
    from api.services import flow_graphs
    from cryptography.fernet import Fernet

    observed_live_providers = []

    def fake_tool_mock_call_check(*, snapshot, live_credential_providers, **kwargs):
        observed_live_providers.append(live_credential_providers)
        return {
            "mode": "tool_mock_call",
            "status": "passed",
            "tools": [
                {
                    "tool_key": "ax.google_sheets",
                    "credential_requirements": [
                        {
                            "provider": "google_workspace",
                            "required": True,
                            "available_for_live_run": "google_workspace" in live_credential_providers,
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr(flow_graphs, "run_tool_mock_call_check", fake_tool_mock_call_check)
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="google_workspace",
        auth_type="oauth2",
        label="Google Workspace",
        provider_account_id="google-account-1",
        provider_account_label="creator@example.com",
        scopes_json=scopes,
        status="active",
        metadata_json={},
        secret_ref="",
    )
    db.add(credential)
    db.flush()
    credential.secret_ref = f"secret://db/credential/{credential.id}"
    if with_secret:
        db.add(
            models.CredentialSecret(
                credential_id=credential.id,
                encrypted_secret_json=encrypt_secret_payload({"access_token": "sheets-access-token"}),
                encryption_key_version="v1",
            )
        )
    db.commit()

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew_with_google_sheets_runtime_context(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])
    assert client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers).status_code == 200

    response = client.post(f"/api/flow-graphs/{flow['id']}/diagnostics/tool-mock-call", headers=auth_headers)

    assert response.status_code == 200
    assert observed_live_providers == [[]]
    requirement = response.json()["tools"][0]["credential_requirements"][0]
    assert requirement["provider"] == "google_workspace"
    assert requirement["available_for_live_run"] is False


def test_flow_graph_tool_mock_call_route_reports_optional_credential_available_with_active_secret(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from cryptography.fernet import Fernet
    from api.services import flow_graphs

    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setattr(
        flow_graphs,
        "run_tool_mock_call_check",
        lambda *, snapshot, live_credential_providers, **kwargs: {
            "mode": "tool_mock_call",
            "status": "passed",
            "tools": [
                {
                    "tool_key": "optional_search",
                    "credential_requirements": [
                        {
                            "provider": "serper",
                            "required": False,
                            "available_for_live_run": "serper" in live_credential_providers,
                        }
                    ],
                }
            ],
        },
    )
    _create_active_credential(db, provider="serper", with_secret=True, api_key="serper-secret")

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew_with_optional_tool_env(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])
    assert client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers).status_code == 200

    response = client.post(f"/api/flow-graphs/{flow['id']}/diagnostics/tool-mock-call", headers=auth_headers)

    assert response.status_code == 200
    requirement = response.json()["tools"][0]["credential_requirements"][0]
    assert requirement["provider"] == "serper"
    assert requirement["required"] is False
    assert requirement["available_for_live_run"] is True


def test_flow_graph_tool_mock_call_route_reports_required_credential_unavailable_without_secret(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from cryptography.fernet import Fernet
    from api.services import flow_graphs

    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setattr(
        flow_graphs,
        "run_tool_mock_call_check",
        lambda *, snapshot, live_credential_providers, **kwargs: {
            "mode": "tool_mock_call",
            "status": "passed",
            "tools": [
                {
                    "tool_key": "search_docs",
                    "credential_requirements": [
                        {
                            "provider": "serper",
                            "required": True,
                            "available_for_live_run": "serper" in live_credential_providers,
                        }
                    ],
                }
            ],
        },
    )
    _create_active_credential(db, provider="serper", with_secret=False)

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew_with_required_tool_credential(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])
    assert client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers).status_code == 200

    response = client.post(f"/api/flow-graphs/{flow['id']}/diagnostics/tool-mock-call", headers=auth_headers)

    assert response.status_code == 200
    requirement = response.json()["tools"][0]["credential_requirements"][0]
    assert requirement["provider"] == "serper"
    assert requirement["available_for_live_run"] is False


def test_flow_graph_compatibility_route_uses_resolved_credentials_for_required_tool_env(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from cryptography.fernet import Fernet
    from api.services import flow_graphs

    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    _create_active_credential(db, provider="serper", with_secret=True, api_key="serper-secret")
    seen_env: list[str | None] = []

    def fake_compatibility_diagnostics(*, snapshot, inputs, **kwargs):
        seen_env.append(os.environ.get("SERPER_API_KEY"))
        return {
            "mode": "compatibility",
            "status": "passed" if os.environ.get("SERPER_API_KEY") == "serper-secret" else "failed",
            "provider_calls": "blocked",
            "required_credentials": ["serper"],
            "crews": [{"node_id": "crew:research", "build_crew": "passed", "kickoff": "passed", "llm_call": "passed"}],
        }

    monkeypatch.setattr(flow_graphs, "run_compatibility_diagnostics", fake_compatibility_diagnostics)

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew_with_required_tool_credential(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])
    assert client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers).status_code == 200

    response = client.post(
        f"/api/flow-graphs/{flow['id']}/diagnostics/compatibility",
        json={"inputs": {"topic": "MVP"}},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "passed"
    assert seen_env == ["serper-secret"]
    assert "SERPER_API_KEY" not in os.environ


def test_flow_graph_compatibility_route_blocks_ambient_env_for_unresolved_credentials(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from cryptography.fernet import Fernet
    from api.services import flow_graphs

    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setenv("SERPER_API_KEY", "ambient-serper")
    seen_env: list[str | None] = []

    def fake_compatibility_diagnostics(*, snapshot, inputs, **kwargs):
        seen_env.append(os.environ.get("SERPER_API_KEY"))
        return {
            "mode": "compatibility",
            "status": "failed" if os.environ.get("SERPER_API_KEY") != "ambient-serper" else "passed",
            "provider_calls": "blocked",
            "required_credentials": ["serper"],
            "crews": [{"node_id": "crew:research", "build_crew": "failed", "kickoff": "failed", "llm_call": "failed"}],
        }

    monkeypatch.setattr(flow_graphs, "run_compatibility_diagnostics", fake_compatibility_diagnostics)

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew_with_required_tool_credential(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])
    assert client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers).status_code == 200

    response = client.post(
        f"/api/flow-graphs/{flow['id']}/diagnostics/compatibility",
        json={"inputs": {"topic": "MVP"}},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert seen_env == ["__AI_OH_MISSING_CREDENTIAL__"]
    assert os.environ["SERPER_API_KEY"] == "ambient-serper"


def test_flow_graph_compatibility_route_blocks_ambient_optional_tool_env(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from cryptography.fernet import Fernet
    from api.services import flow_graphs

    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setenv("SERPER_API_KEY", "ambient-serper")
    monkeypatch.setenv("OPTIONAL_TOOL_TOKEN", "ambient-optional")
    seen_env: list[tuple[str | None, str | None]] = []

    def fake_compatibility_diagnostics(*, snapshot, inputs, **kwargs):
        seen_env.append((os.environ.get("SERPER_API_KEY"), os.environ.get("OPTIONAL_TOOL_TOKEN")))
        ambient_leaked = "ambient-serper" in seen_env[-1] or "ambient-optional" in seen_env[-1]
        return {
            "mode": "compatibility",
            "status": "passed" if not ambient_leaked else "failed",
            "provider_calls": "blocked",
            "required_credentials": [],
            "crews": [{"node_id": "crew:research", "build_crew": "passed", "kickoff": "passed", "llm_call": "passed"}],
        }

    monkeypatch.setattr(flow_graphs, "run_compatibility_diagnostics", fake_compatibility_diagnostics)

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew_with_optional_tool_env(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])
    assert client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers).status_code == 200

    response = client.post(
        f"/api/flow-graphs/{flow['id']}/diagnostics/compatibility",
        json={"inputs": {"topic": "MVP"}},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "passed"
    assert seen_env == [("__AI_OH_MISSING_CREDENTIAL__", "__AI_OH_MISSING_CREDENTIAL__")]
    assert os.environ["SERPER_API_KEY"] == "ambient-serper"
    assert os.environ["OPTIONAL_TOOL_TOKEN"] == "ambient-optional"


def test_flow_graph_tool_mock_call_route_isolates_env_and_redacts_constructor_error(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from api.runtime import flow_diagnostics
    from crewai.tools import BaseTool

    monkeypatch.setenv("SERPER_API_KEY", "ambient-serper")

    class LeakyTool(BaseTool):
        name: str = "Leaky Tool"
        description: str = "Raises constructor error with env value."

        def __init__(self, **kwargs):
            raise RuntimeError(f"constructor saw {os.environ.get('SERPER_API_KEY')}")

        def _run(self, **kwargs):
            raise AssertionError("_run must not be called")

    monkeypatch.setattr(flow_diagnostics, "load_tool_class", lambda module_path, class_name: LeakyTool)

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew_with_optional_tool_env(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])
    assert client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers).status_code == 200

    response = client.post(f"/api/flow-graphs/{flow['id']}/diagnostics/tool-mock-call", headers=auth_headers)

    assert response.status_code == 200
    body_text = response.text
    assert "ambient-serper" not in body_text
    assert "__AI_OH_MISSING_CREDENTIAL__" not in body_text
    assert "[redacted]" in body_text
    assert os.environ["SERPER_API_KEY"] == "ambient-serper"


def test_flow_graph_manager_only_tool_is_isolated_and_diagnosed(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from api.runtime import flow_diagnostics
    from crewai.tools import BaseTool

    monkeypatch.setenv("SERPER_API_KEY", "ambient-serper")
    monkeypatch.setenv("MANAGER_OPTIONAL_TOKEN", "ambient-manager")
    seen_env: list[tuple[str | None, str | None]] = []

    def fake_compatibility_diagnostics(*, snapshot, inputs, **kwargs):
        seen_env.append((os.environ.get("SERPER_API_KEY"), os.environ.get("MANAGER_OPTIONAL_TOKEN")))
        return {
            "mode": "compatibility",
            "status": "passed",
            "provider_calls": "blocked",
            "required_credentials": [],
            "crews": [{"node_id": "crew:research", "build_crew": "passed", "kickoff": "passed", "llm_call": "passed"}],
        }

    class ManagerOptionalTool(BaseTool):
        name: str = "Manager Optional"
        description: str = "Manager-only optional tool."

        def _run(self, **kwargs):
            raise AssertionError("_run must not be called")

    monkeypatch.setattr(flow_diagnostics, "load_tool_class", lambda module_path, class_name: ManagerOptionalTool)
    monkeypatch.setattr("api.services.flow_graphs.run_compatibility_diagnostics", fake_compatibility_diagnostics)

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew_with_manager_only_tool(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])
    assert client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers).status_code == 200

    compatibility_response = client.post(
        f"/api/flow-graphs/{flow['id']}/diagnostics/compatibility",
        json={"inputs": {"topic": "MVP"}},
        headers=auth_headers,
    )
    tool_response = client.post(f"/api/flow-graphs/{flow['id']}/diagnostics/tool-mock-call", headers=auth_headers)

    assert compatibility_response.status_code == 200
    assert seen_env == [("__AI_OH_MISSING_CREDENTIAL__", "__AI_OH_MISSING_CREDENTIAL__")]
    assert tool_response.status_code == 200
    assert [tool["tool_key"] for tool in tool_response.json()["tools"]] == ["manager_optional"]
    assert os.environ["SERPER_API_KEY"] == "ambient-serper"
    assert os.environ["MANAGER_OPTIONAL_TOKEN"] == "ambient-manager"


def test_flow_graph_compatibility_route_redacts_resolved_credential_values(
    client,
    db,
    auth_headers,
    monkeypatch,
):
    from cryptography.fernet import Fernet
    from api.runtime import flow_diagnostics

    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    _create_active_credential(db, provider="serper", with_secret=True, api_key="serper-secret")

    class FakeFactory:
        def __init__(self, *, execution_mode="validation", llm_catalog=None):
            assert execution_mode == "validation"

        def build_crew(self, **kwargs):
            raise RuntimeError("failed with serper-secret")

    monkeypatch.setattr(flow_diagnostics, "CrewAIFactory", FakeFactory)

    flow = _create_flow(client, auth_headers)
    crew = _create_published_crew_with_required_tool_credential(client, db, auth_headers)
    graph = _flow_graph(crew["id"], crew["current_version"]["id"])
    assert client.put(f"/api/flow-graphs/{flow['id']}/draft", json={"graph": graph}, headers=auth_headers).status_code == 200

    response = client.post(
        f"/api/flow-graphs/{flow['id']}/diagnostics/compatibility",
        json={"inputs": {"topic": "MVP"}},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body_text = response.text
    assert "serper-secret" not in body_text
    assert "[redacted]" in body_text
