from unittest.mock import patch

from api.db.models import AssetRuntimeSnapshot, AssetVersion, CrewVersionDraft
from api.services.assets import AssetConflictError
from api.services.crew_graphs import save_crew_draft
from tests.fixtures_api import auth_headers, client, db


def _crew_payload() -> dict:
    return {
        "type": "crew",
        "name": "Operations Crew",
        "description": "Coordinates work",
        "workspace_id": "11111111-1111-1111-1111-111111111111",
        "payload": {
            "process": "sequential",
            "manager_llm": {"provider": "openai", "model": "gpt-4o-mini"},
            "manager_agent_asset_id": None,
            "function_calling_llm": {"provider": "openai", "model": "gpt-4o-mini"},
            "verbose": False,
            "planning": True,
            "memory": False,
        },
    }


def _agent_payload() -> dict:
    return {
        "type": "agent",
        "name": "Research Agent",
        "description": "Investigates topics",
        "workspace_id": "11111111-1111-1111-1111-111111111111",
        "payload": {
            "role": "Researcher",
            "goal": "Find facts",
            "backstory": "Careful analyst",
            "llm": {"provider": "openai", "model": "gpt-4o-mini"},
            "verbose": False,
        },
    }


def _task_payload() -> dict:
    return {
        "type": "task",
        "name": "Research Task",
        "description": "Collect and summarize facts",
        "workspace_id": "11111111-1111-1111-1111-111111111111",
        "payload": {
            "description": "Collect and summarize facts",
            "expected_output": "A concise summary",
            "async_execution": False,
            "human_input": False,
            "markdown": True,
        },
    }


def make_valid_draft_graph() -> dict:
    return {
        "schemaVersion": 1,
        "nodes": [
            {
                "id": "crew:1",
                "type": "crew",
                "position": {"x": 32, "y": 32},
                "data": {"assetId": "c1", "versionId": "cv1", "processType": "sequential"},
            },
            {
                "id": "agent:1",
                "type": "agent",
                "position": {"x": 96, "y": 96},
                "data": {"assetId": "a1", "versionId": "av1"},
            },
            {
                "id": "task:1",
                "type": "task",
                "position": {"x": 96, "y": 280},
                "data": {"assetId": "t1", "versionId": "tv1"},
            },
            {
                "id": "task:2",
                "type": "task",
                "position": {"x": 376, "y": 280},
                "data": {"assetId": "t2", "versionId": "tv2"},
            },
        ],
        "edges": [
            {"id": "assign:1", "source": "agent:1", "target": "task:1", "type": "agent_assignment"},
            {"id": "assign:2", "source": "agent:1", "target": "task:2", "type": "agent_assignment"},
            {"id": "sequence:1", "source": "task:1", "target": "task:2", "type": "task_sequence"},
        ],
        "entities": {
            "agents": {
                "av1": {
                    "version_id": "av1",
                    "asset_id": "a1",
                    "version_no": 1,
                    "name": "Researcher",
                    "status": "published",
                    "payload": {
                        "role": "Researcher",
                        "goal": "Investigate",
                        "backstory": "Handles research.",
                        "llm": {"provider": "openai", "model": "gpt-4o-mini"},
                    },
                }
            },
            "tasks": {
                "tv1": {
                    "version_id": "tv1",
                    "asset_id": "t1",
                    "version_no": 1,
                    "name": "Task 1",
                    "status": "published",
                    "payload": {
                        "description": "Task 1",
                        "expected_output": "Completed task 1",
                        "output_json_schema": None,
                    },
                },
                "tv2": {
                    "version_id": "tv2",
                    "asset_id": "t2",
                    "version_no": 1,
                    "name": "Task 2",
                    "status": "published",
                    "payload": {
                        "description": "Task 2",
                        "expected_output": "Completed task 2",
                        "output_json_schema": None,
                    },
                },
            },
            "crews": {
                "cv1": {
                    "version_id": "cv1",
                    "asset_id": "c1",
                    "version_no": 1,
                    "name": "Workflow Crew",
                    "status": "published",
                    "payload": {
                        "process": "sequential",
                        "manager_llm": {},
                        "payload_json": {},
                    },
                }
            },
            "tools": {},
        },
    }


def make_valid_publish_graph() -> dict:
    return make_valid_draft_graph()


def make_valid_draft_graph_for_asset(crew: dict) -> dict:
    graph = make_valid_draft_graph()
    crew_version = crew["current_version"]
    graph["nodes"][0]["id"] = f"crew:{crew['id']}"
    graph["nodes"][0]["data"] = {
        "assetId": crew["id"],
        "versionId": crew_version["id"],
        "processType": crew_version["payload"].get("process", "sequential"),
    }
    graph["entities"]["crews"] = {crew_version["id"]: _entity_from_asset(crew)}
    return graph


def make_valid_publish_graph_for_asset(crew: dict) -> dict:
    return make_valid_draft_graph_for_asset(crew)


def _seed_crew_asset(client, auth_headers) -> dict:
    response = client.post("/api/assets", json=_crew_payload(), headers=auth_headers)

    assert response.status_code == 201
    return response.json()


def _seed_asset(client, auth_headers, payload: dict) -> dict:
    response = client.post("/api/assets", json=payload, headers=auth_headers)

    assert response.status_code == 201
    return response.json()


def _entity_from_asset(asset: dict) -> dict:
    version = asset["current_version"]
    return {
        "version_id": version["id"],
        "asset_id": asset["id"],
        "version_no": version["version_no"],
        "name": asset["name"],
        "description": asset.get("description"),
        "status": version["status"],
        "payload": version["payload"],
    }


def _direct_graph_from_assets(crew: dict, agents: list[dict], tasks: list[dict], edges: list[dict]) -> dict:
    return {
        "schemaVersion": 1,
        "nodes": [
            {
                "id": f"crew:{crew['id']}",
                "type": "crew",
                "position": {"x": 32, "y": 32},
                "data": {
                    "assetId": crew["id"],
                    "versionId": crew["current_version"]["id"],
                    "processType": crew["current_version"]["payload"].get("process", "sequential"),
                },
            },
            *[
                {
                    "id": f"agent:{agent['id']}",
                    "type": "agent",
                    "position": {"x": 96 + index * 260, "y": 96},
                    "data": {"assetId": agent["id"], "versionId": agent["current_version"]["id"]},
                }
                for index, agent in enumerate(agents)
            ],
            *[
                {
                    "id": f"task:{task['id']}",
                    "type": "task",
                    "position": {"x": 96 + index * 280, "y": 280},
                    "data": {"assetId": task["id"], "versionId": task["current_version"]["id"]},
                }
                for index, task in enumerate(tasks)
            ],
        ],
        "edges": edges,
        "entities": {
            "agents": {agent["current_version"]["id"]: _entity_from_asset(agent) for agent in agents},
            "tasks": {task["current_version"]["id"]: _entity_from_asset(task) for task in tasks},
            "crews": {crew["current_version"]["id"]: _entity_from_asset(crew)},
            "tools": {},
        },
    }


def _direct_assigned_graph_from_assets(crew: dict, agents: list[dict], tasks: list[dict]) -> dict:
    return _direct_graph_from_assets(
        crew,
        agents=agents,
        tasks=tasks,
        edges=[
            {
                "id": f"assign:{index}",
                "source": f"agent:{agents[min(index - 1, len(agents) - 1)]['id']}",
                "target": f"task:{task['id']}",
                "type": "agent_assignment",
            }
            for index, task in enumerate(tasks, start=1)
        ],
    )


def test_save_crew_draft_persists_personal_graph(client, db, auth_headers):
    seeded_crew_asset = _seed_crew_asset(client, auth_headers)

    response = client.put(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/draft",
        json={"graph": make_valid_draft_graph_for_asset(seeded_crew_asset)},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["draft"]["graph"]["schemaVersion"] == 1

    draft = db.query(CrewVersionDraft).filter(CrewVersionDraft.crew_asset_id == seeded_crew_asset["id"]).one()
    assert draft.owner_user_id == "test-user"
    assert draft.base_version_id == seeded_crew_asset["current_version"]["id"]
    assert draft.graph_json["schemaVersion"] == 1


def test_save_crew_draft_accepts_saved_node_dimensions(client, db, auth_headers):
    seeded_crew_asset = _seed_crew_asset(client, auth_headers)
    graph = make_valid_draft_graph_for_asset(seeded_crew_asset)
    graph["nodes"][0]["style"] = {"width": 1440, "height": 820}

    response = client.put(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/draft",
        json={"graph": graph},
        headers=auth_headers,
    )

    assert response.status_code == 200

    draft = db.query(CrewVersionDraft).filter(CrewVersionDraft.crew_asset_id == seeded_crew_asset["id"]).one()
    assert draft.graph_json["nodes"][0]["style"] == {"width": 1440, "height": 820}


def test_save_crew_draft_normalizes_missing_crew_entity(client, db, auth_headers):
    seeded_crew_asset = _seed_crew_asset(client, auth_headers)
    graph = make_valid_draft_graph_for_asset(seeded_crew_asset)
    graph["entities"]["crews"] = {}

    response = client.put(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/draft",
        json={"graph": graph},
        headers=auth_headers,
    )

    assert response.status_code == 200

    draft = db.query(CrewVersionDraft).filter(CrewVersionDraft.crew_asset_id == seeded_crew_asset["id"]).one()
    current_version_id = seeded_crew_asset["current_version"]["id"]
    crew_entity = draft.graph_json["entities"]["crews"][current_version_id]
    assert crew_entity["asset_id"] == seeded_crew_asset["id"]
    assert crew_entity["version_id"] == current_version_id
    assert crew_entity["version_no"] == seeded_crew_asset["current_version"]["version_no"]
    assert crew_entity["name"] == seeded_crew_asset["name"]
    assert crew_entity["description"] == seeded_crew_asset["description"]
    assert crew_entity["status"] == seeded_crew_asset["current_version"]["status"]
    assert crew_entity["payload"] == seeded_crew_asset["current_version"]["payload"]


def test_save_crew_draft_rejects_mismatched_route_crew_identity(client, auth_headers):
    route_crew = _seed_crew_asset(client, auth_headers)
    other_crew = _seed_asset(client, auth_headers, {**_crew_payload(), "name": "Other Crew"})
    graph = make_valid_draft_graph_for_asset(other_crew)

    response = client.put(
        f"/api/crew-graphs/{route_crew['id']}/draft",
        json={"graph": graph},
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert "Crew graph Crew node must match route Crew asset" in response.json()["detail"]


def test_save_crew_draft_normalizes_stale_route_crew_version(client, db, auth_headers):
    route_crew = _seed_crew_asset(client, auth_headers)
    graph = make_valid_draft_graph_for_asset(route_crew)
    save_initial_response = client.put(
        f"/api/crew-graphs/{route_crew['id']}/draft",
        json={"graph": graph},
        headers=auth_headers,
    )
    publish_response = client.post(
        f"/api/crew-graphs/{route_crew['id']}/publish",
        headers=auth_headers,
    )
    current_version_id = publish_response.json()["version"]["id"]

    response = client.put(
        f"/api/crew-graphs/{route_crew['id']}/draft",
        json={"graph": graph},
        headers=auth_headers,
    )

    assert save_initial_response.status_code == 200
    assert publish_response.status_code == 200
    assert response.status_code == 200

    draft = db.query(CrewVersionDraft).filter(CrewVersionDraft.crew_asset_id == route_crew["id"]).one()
    assert draft.graph_json["nodes"][0]["data"]["assetId"] == route_crew["id"]
    assert draft.graph_json["nodes"][0]["data"]["versionId"] == current_version_id
    assert list(draft.graph_json["entities"]["crews"]) == [current_version_id]
    assert draft.graph_json["entities"]["crews"][current_version_id]["asset_id"] == route_crew["id"]
    assert draft.graph_json["entities"]["crews"][current_version_id]["version_id"] == current_version_id


def test_crew_graph_draft_save_allows_sequential_task_without_red(client, auth_headers):
    crew = _seed_asset(
        client,
        auth_headers,
        {**_crew_payload(), "name": "Seq Crew", "payload": {"process": "sequential"}},
    )
    task = _seed_asset(
        client,
        auth_headers,
        {
            **_task_payload(),
            "name": "Task",
            "payload": {"description": "Do it", "expected_output": "Done"},
        },
    )

    graph = _direct_graph_from_assets(crew, agents=[], tasks=[task], edges=[])

    response = client.put(f"/api/crew-graphs/{crew['id']}/draft", json={"graph": graph}, headers=auth_headers)

    assert response.status_code == 200


def test_crew_graph_validate_blocks_sequential_task_without_red(client, auth_headers):
    crew = _seed_asset(
        client,
        auth_headers,
        {**_crew_payload(), "name": "Seq Crew", "payload": {"process": "sequential"}},
    )
    task = _seed_asset(
        client,
        auth_headers,
        {
            **_task_payload(),
            "name": "Task",
            "payload": {"description": "Do it", "expected_output": "Done"},
        },
    )
    graph = _direct_graph_from_assets(crew, agents=[], tasks=[task], edges=[])

    save_response = client.put(f"/api/crew-graphs/{crew['id']}/draft", json={"graph": graph}, headers=auth_headers)
    assert save_response.status_code == 200

    validate_response = client.post(f"/api/crew-graphs/{crew['id']}/validate", headers=auth_headers)

    assert validate_response.status_code == 422
    assert "Sequential Crew must assign every Task" in validate_response.json()["detail"]


def test_crew_graph_draft_save_blocks_invalid_context_order(client, auth_headers):
    crew = _seed_asset(
        client,
        auth_headers,
        {**_crew_payload(), "name": "Seq Crew", "payload": {"process": "sequential"}},
    )
    agent = _seed_asset(
        client,
        auth_headers,
        {
            **_agent_payload(),
            "name": "Agent",
            "payload": {"role": "R", "goal": "G", "backstory": "B"},
        },
    )
    task1 = _seed_asset(
        client,
        auth_headers,
        {
            **_task_payload(),
            "name": "Task 1",
            "payload": {"description": "One", "expected_output": "One out"},
        },
    )
    task2 = _seed_asset(
        client,
        auth_headers,
        {
            **_task_payload(),
            "name": "Task 2",
            "payload": {"description": "Two", "expected_output": "Two out"},
        },
    )
    graph = _direct_graph_from_assets(
        crew,
        agents=[agent],
        tasks=[task1, task2],
        edges=[
            {
                "id": "assign:1",
                "source": f"agent:{agent['id']}",
                "target": f"task:{task1['id']}",
                "type": "agent_assignment",
            },
            {
                "id": "assign:2",
                "source": f"agent:{agent['id']}",
                "target": f"task:{task2['id']}",
                "type": "agent_assignment",
            },
            {
                "id": "context:bad",
                "source": f"task:{task2['id']}",
                "target": f"task:{task1['id']}",
                "type": "task_context",
            },
        ],
    )

    response = client.put(f"/api/crew-graphs/{crew['id']}/draft", json={"graph": graph}, headers=auth_headers)

    assert response.status_code == 422
    assert "task_context source must run before" in response.json()["detail"]


def test_get_crew_draft_returns_empty_envelope_when_missing(client, auth_headers):
    seeded_crew_asset = _seed_crew_asset(client, auth_headers)

    response = client.get(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/draft",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["draft"] is None


def test_get_crew_draft_returns_saved_draft(client, auth_headers):
    seeded_crew_asset = _seed_crew_asset(client, auth_headers)
    client.put(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/draft",
        json={"graph": make_valid_draft_graph_for_asset(seeded_crew_asset)},
        headers=auth_headers,
    )

    response = client.get(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/draft",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["draft"]["graph"]["schemaVersion"] == 1
    assert response.json()["draft"]["crew_asset_id"] == seeded_crew_asset["id"]


def test_save_crew_draft_retries_unique_conflict_by_reloading_existing_draft(client, db, auth_headers):
    seeded_crew_asset = _seed_crew_asset(client, auth_headers)
    existing_draft = CrewVersionDraft(
        crew_asset_id=seeded_crew_asset["id"],
        base_version_id=seeded_crew_asset["current_version"]["id"],
        owner_user_id="test-user",
        graph_json={"schemaVersion": 1, "nodes": [], "edges": [], "entities": {}},
        validation_json={"stale": True},
        last_test_validation_json={"stale": True},
    )
    db.add(existing_draft)
    db.commit()

    race_draft = CrewVersionDraft(
        crew_asset_id=seeded_crew_asset["id"],
        base_version_id=seeded_crew_asset["current_version"]["id"],
        owner_user_id="test-user",
        graph_json={},
        validation_json={},
        last_test_validation_json={},
    )

    with patch("api.services.crew_graphs._get_or_create_draft", return_value=race_draft):
        saved = save_crew_draft(
            db,
            crew_asset_id=seeded_crew_asset["id"],
            owner_user_id="test-user",
            graph=make_valid_draft_graph_for_asset(seeded_crew_asset),
        )

    db.refresh(existing_draft)

    assert str(saved.id) == str(existing_draft.id)
    assert existing_draft.graph_json["schemaVersion"] == 1
    assert existing_draft.validation_json == {}
    assert existing_draft.last_test_validation_json == {}
    assert (
        db.query(CrewVersionDraft)
        .filter(CrewVersionDraft.crew_asset_id == seeded_crew_asset["id"])
        .count()
        == 1
    )


def test_validate_crew_draft_returns_runtime_snapshot(client, auth_headers):
    seeded_crew_asset = _seed_crew_asset(client, auth_headers)
    client.put(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/draft",
        json={"graph": make_valid_publish_graph_for_asset(seeded_crew_asset)},
        headers=auth_headers,
    )

    response = client.post(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/validate",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["schemaVersion"] == 1
    assert response.json()["runtime_crew"]["name"] == "Operations Crew"


def test_validate_and_publish_reject_injected_mismatched_draft(client, db, auth_headers):
    route_crew = _seed_crew_asset(client, auth_headers)
    other_crew = _seed_asset(client, auth_headers, {**_crew_payload(), "name": "Other Crew"})
    injected_draft = CrewVersionDraft(
        crew_asset_id=route_crew["id"],
        base_version_id=route_crew["current_version"]["id"],
        owner_user_id="test-user",
        graph_json=make_valid_draft_graph_for_asset(other_crew),
        validation_json={},
        last_test_validation_json={},
    )
    db.add(injected_draft)
    db.commit()

    validate_response = client.post(f"/api/crew-graphs/{route_crew['id']}/validate", headers=auth_headers)
    publish_response = client.post(f"/api/crew-graphs/{route_crew['id']}/publish", headers=auth_headers)

    assert validate_response.status_code == 422
    assert "Crew graph Crew node must match route Crew asset" in validate_response.json()["detail"]
    assert publish_response.status_code == 422
    assert "Crew graph Crew node must match route Crew asset" in publish_response.json()["detail"]


def test_validate_crew_draft_hydrates_agent_and_task_tools_from_version_attachments(client, auth_headers):
    seeded_crew_asset = _seed_crew_asset(client, auth_headers)
    agent = _seed_asset(client, auth_headers, _agent_payload())
    task = _seed_asset(client, auth_headers, _task_payload())
    agent_version_id = agent["current_version"]["id"]
    asset_version_id = task["current_version"]["id"]

    agent_tool_response = client.post(
        f"/api/versions/{agent_version_id}/tools",
        json={"tool_key": "crewai.serper_dev"},
        headers=auth_headers,
    )
    task_tool_response = client.post(
        f"/api/versions/{asset_version_id}/tools",
        json={"tool_key": "crewai.dalle"},
        headers=auth_headers,
    )
    graph = _direct_assigned_graph_from_assets(seeded_crew_asset, [agent], [task])
    save_response = client.put(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/draft",
        json={"graph": graph},
        headers=auth_headers,
    )

    response = client.post(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/validate",
        headers=auth_headers,
    )

    assert agent_tool_response.status_code == 201
    assert task_tool_response.status_code == 201
    assert save_response.status_code == 200
    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["agent_tool_links"] == {agent_version_id: ["crewai.serper_dev"]}
    assert snapshot["task_tool_links"] == {asset_version_id: ["crewai.dalle"]}
    assert sorted(snapshot["runtime_tools"]) == ["crewai.dalle", "crewai.serper_dev"]


def test_validate_crew_draft_refreshes_stale_hydrated_tool_metadata_and_attachment(
    client,
    auth_headers,
):
    seeded_crew_asset = _seed_crew_asset(client, auth_headers)
    agent = _seed_asset(client, auth_headers, _agent_payload())
    task = _seed_asset(client, auth_headers, _task_payload())
    asset_version_id = task["current_version"]["id"]

    attach_response = client.post(
        f"/api/versions/{asset_version_id}/tools",
        json={"tool_key": "crewai.dalle"},
        headers=auth_headers,
    )
    patch_response = client.patch(
        f"/api/versions/{asset_version_id}/tools/crewai.dalle",
        json={"tool_config_json": {"style": "vivid"}, "sort_order": 7},
        headers=auth_headers,
    )
    graph = _direct_assigned_graph_from_assets(seeded_crew_asset, [agent], [task])
    graph["entities"]["tools"] = {
        "crewai.dalle": {
            "tool_key": "crewai.dalle",
            "name": "Stale DALL-E",
            "description": "Stale description.",
            "tool_type": "stale_type",
            "module_path": "stale.module",
            "class_name": "StaleTool",
            "default_config_json": {"stale": True},
            "attachments": [
                {
                    "version_id": asset_version_id,
                    "tool_config_json": {"style": "stale"},
                    "sort_order": 99,
                }
            ],
        }
    }
    save_response = client.put(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/draft",
        json={"graph": graph},
        headers=auth_headers,
    )

    response = client.post(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/validate",
        headers=auth_headers,
    )

    assert attach_response.status_code == 201
    assert patch_response.status_code == 200
    assert save_response.status_code == 200
    assert response.status_code == 200
    dalle_tool = response.json()["runtime_tools"]["crewai.dalle"]
    assert dalle_tool["name"] == "DALL-E Tool"
    assert dalle_tool["module_path"] == "crewai_tools"
    assert dalle_tool["class_name"] == "DallETool"
    assert dalle_tool["tool_type"] == "crewai_tool"
    assert dalle_tool["default_config_json"] == {}
    assert dalle_tool["attachments"] == [
        {
            "version_id": asset_version_id,
            "tool_config_json": {"style": "vivid"},
            "sort_order": 7,
        }
    ]


def test_validate_crew_draft_removes_stale_current_version_tool_attachments(
    client,
    auth_headers,
):
    seeded_crew_asset = _seed_crew_asset(client, auth_headers)
    agent = _seed_asset(client, auth_headers, _agent_payload())
    task = _seed_asset(client, auth_headers, _task_payload())
    agent_version_id = agent["current_version"]["id"]
    asset_version_id = task["current_version"]["id"]
    graph = _direct_assigned_graph_from_assets(seeded_crew_asset, [agent], [task])
    graph["entities"]["tools"] = {
        "crewai.serper_dev": {
            "tool_key": "crewai.serper_dev",
            "name": "Serper Dev Search",
            "description": "Search the web with Serper Dev.",
            "tool_type": "crewai_tool",
            "module_path": "crewai_tools",
            "class_name": "SerperDevTool",
            "default_config_json": {},
            "attachments": [
                {
                    "version_id": agent_version_id,
                    "tool_config_json": {"stale": True},
                    "sort_order": 3,
                }
            ],
        },
        "crewai.dalle": {
            "tool_key": "crewai.dalle",
            "name": "DALL-E Tool",
            "description": "Generate images from text prompts.",
            "tool_type": "crewai_tool",
            "module_path": "crewai_tools",
            "class_name": "DallETool",
            "default_config_json": {},
            "attachments": [
                {
                    "version_id": asset_version_id,
                    "tool_config_json": {"stale": True},
                    "sort_order": 4,
                }
            ],
        },
    }
    save_response = client.put(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/draft",
        json={"graph": graph},
        headers=auth_headers,
    )

    response = client.post(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/validate",
        headers=auth_headers,
    )

    assert save_response.status_code == 200
    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["agent_tool_links"] == {}
    assert snapshot["task_tool_links"] == {}
    assert snapshot["runtime_tools"] == {}


def test_validate_crew_draft_replaces_stale_tool_key_with_db_attachment(
    client,
    auth_headers,
):
    seeded_crew_asset = _seed_crew_asset(client, auth_headers)
    agent = _seed_asset(client, auth_headers, _agent_payload())
    task = _seed_asset(client, auth_headers, _task_payload())
    asset_version_id = task["current_version"]["id"]
    attach_response = client.post(
        f"/api/versions/{asset_version_id}/tools",
        json={"tool_key": "crewai.dalle"},
        headers=auth_headers,
    )
    graph = _direct_assigned_graph_from_assets(seeded_crew_asset, [agent], [task])
    graph["entities"]["tools"] = {
        "crewai.serper_dev": {
            "tool_key": "crewai.serper_dev",
            "name": "Serper Dev Search",
            "description": "Search the web with Serper Dev.",
            "tool_type": "crewai_tool",
            "module_path": "crewai_tools",
            "class_name": "SerperDevTool",
            "default_config_json": {},
            "attachments": [
                {
                    "version_id": asset_version_id,
                    "tool_config_json": {"old": True},
                    "sort_order": 0,
                }
            ],
        }
    }
    save_response = client.put(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/draft",
        json={"graph": graph},
        headers=auth_headers,
    )

    response = client.post(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/validate",
        headers=auth_headers,
    )

    assert attach_response.status_code == 201
    assert save_response.status_code == 200
    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["task_tool_links"] == {asset_version_id: ["crewai.dalle"]}
    assert sorted(snapshot["runtime_tools"]) == ["crewai.dalle"]


def test_validate_crew_draft_removes_stale_tool_edge_for_one_version_but_keeps_valid_edge(
    client,
    auth_headers,
):
    seeded_crew_asset = _seed_crew_asset(client, auth_headers)
    first_agent = _seed_asset(client, auth_headers, _agent_payload())
    second_agent = _seed_asset(client, auth_headers, _agent_payload())
    first_task = _seed_asset(client, auth_headers, _task_payload())
    second_task = _seed_asset(client, auth_headers, _task_payload())
    first_agent_version_id = first_agent["current_version"]["id"]
    second_agent_version_id = second_agent["current_version"]["id"]

    attach_response = client.post(
        f"/api/versions/{second_agent_version_id}/tools",
        json={"tool_key": "crewai.serper_dev"},
        headers=auth_headers,
    )
    graph = _direct_assigned_graph_from_assets(
        seeded_crew_asset,
        [first_agent, second_agent],
        [first_task, second_task],
    )
    graph["entities"]["tools"] = {
        "crewai.serper_dev": {
            "tool_key": "crewai.serper_dev",
            "name": "Serper Dev Search",
            "description": "Search the web with Serper Dev.",
            "tool_type": "crewai_tool",
            "module_path": "crewai_tools",
            "class_name": "SerperDevTool",
            "default_config_json": {},
            "attachments": [
                {
                    "version_id": first_agent_version_id,
                    "tool_config_json": {"stale": True},
                    "sort_order": 1,
                },
                {
                    "version_id": second_agent_version_id,
                    "tool_config_json": {},
                    "sort_order": 0,
                },
            ],
        }
    }
    save_response = client.put(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/draft",
        json={"graph": graph},
        headers=auth_headers,
    )

    response = client.post(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/validate",
        headers=auth_headers,
    )

    assert attach_response.status_code == 201
    assert save_response.status_code == 200
    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["agent_tool_links"] == {second_agent_version_id: ["crewai.serper_dev"]}
    assert first_agent_version_id not in snapshot["agent_tool_links"]
    assert sorted(snapshot["runtime_tools"]) == ["crewai.serper_dev"]


def test_publish_crew_draft_creates_new_version_with_runtime_snapshot(client, db, auth_headers):
    seeded_crew_asset = _seed_crew_asset(client, auth_headers)
    client.put(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/draft",
        json={"graph": make_valid_publish_graph_for_asset(seeded_crew_asset)},
        headers=auth_headers,
    )

    response = client.post(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/publish",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["version"]["runtime_snapshot_json"]["schemaVersion"] == 1
    assert response.json()["version"]["runtime_snapshot_json"]["runtime_crew"]["asset_id"] == seeded_crew_asset["id"]
    assert response.json()["version"]["status"] == "published"

    versions = (
        db.query(AssetVersion)
        .filter(AssetVersion.asset_id == seeded_crew_asset["id"])
        .order_by(AssetVersion.version_number.asc())
        .all()
    )
    assert [version.version_number for version in versions] == [1, 2]

    published_snapshot = db.get(AssetRuntimeSnapshot, versions[-1].id)
    assert published_snapshot.runtime_snapshot_json["schemaVersion"] == 1
    assert published_snapshot.runtime_snapshot_json["runtime_crew"]["asset_id"] == seeded_crew_asset["id"]


def test_crew_publish_hydrates_serper_tool_metadata(client, db, auth_headers):
    crew = _seed_crew_asset(client, auth_headers)
    agent = _seed_asset(client, auth_headers, _agent_payload())
    task = _seed_asset(client, auth_headers, _task_payload())
    agent_version_id = agent["current_version"]["id"]

    client.post(
        f"/api/versions/{agent_version_id}/tools",
        json={"tool_key": "crewai.serper_dev"},
        headers=auth_headers,
    )
    client.patch(
        f"/api/versions/{agent_version_id}/tools/crewai.serper_dev",
        json={"tool_config_json": {"n_results": 2}},
        headers=auth_headers,
    )

    graph = _direct_assigned_graph_from_assets(crew, [agent], [task])
    save_response = client.put(
        f"/api/crew-graphs/{crew['id']}/draft",
        json={"graph": graph},
        headers=auth_headers,
    )
    assert save_response.status_code == 200

    publish_response = client.post(f"/api/crew-graphs/{crew['id']}/publish", headers=auth_headers)
    assert publish_response.status_code == 200
    snapshot = publish_response.json()["version"]["runtime_snapshot_json"]
    serper = snapshot["runtime_tools"]["crewai.serper_dev"]

    assert serper["config_schema_json"]["properties"]["n_results"]["type"] == "integer"
    assert serper["input_schema_json"]["required"] == ["search_query"]
    assert serper["required_env_vars"][0]["name"] == "SERPER_API_KEY"
    assert serper["attachments"][0]["tool_config_json"] == {"n_results": 2}


def test_publish_crew_draft_is_idempotent_when_snapshot_is_unchanged(client, db, auth_headers):
    seeded_crew_asset = _seed_crew_asset(client, auth_headers)
    client.put(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/draft",
        json={"graph": make_valid_publish_graph_for_asset(seeded_crew_asset)},
        headers=auth_headers,
    )

    first_publish = client.post(f"/api/crew-graphs/{seeded_crew_asset['id']}/publish", headers=auth_headers)
    canvas_only_graph = make_valid_publish_graph_for_asset(seeded_crew_asset)
    canvas_only_graph["nodes"][0]["data"] = {
        **canvas_only_graph["nodes"][0].get("data", {}),
        "label": "Canvas-only Crew Label",
    }
    save_response = client.put(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/draft",
        json={"graph": canvas_only_graph},
        headers=auth_headers,
    )
    second_publish = client.post(f"/api/crew-graphs/{seeded_crew_asset['id']}/publish", headers=auth_headers)

    assert first_publish.status_code == 200
    assert save_response.status_code == 200
    assert second_publish.status_code == 200
    assert second_publish.json()["already_published"] is True
    assert second_publish.json()["version"]["id"] == first_publish.json()["version"]["id"]

    versions = (
        db.query(AssetVersion)
        .filter(AssetVersion.asset_id == seeded_crew_asset["id"])
        .order_by(AssetVersion.version_number.asc())
        .all()
    )
    assert [version.version_number for version in versions] == [1, 2]
    assert [version.status for version in versions] == ["draft", "published"]


def test_publish_crew_draft_archives_previous_published_version_when_changed(client, db, auth_headers):
    seeded_crew_asset = _seed_crew_asset(client, auth_headers)
    graph = make_valid_publish_graph_for_asset(seeded_crew_asset)
    client.put(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/draft",
        json={"graph": graph},
        headers=auth_headers,
    )
    first_publish = client.post(f"/api/crew-graphs/{seeded_crew_asset['id']}/publish", headers=auth_headers)
    assert first_publish.status_code == 200

    changed_graph = make_valid_publish_graph_for_asset(seeded_crew_asset)
    published_version_id = first_publish.json()["version"]["id"]
    changed_graph["nodes"][0]["data"]["versionId"] = published_version_id
    crew_entity = next(iter(changed_graph["entities"]["crews"].values()))
    crew_entity["version_id"] = published_version_id
    changed_graph["entities"]["crews"] = {published_version_id: crew_entity}
    changed_graph["entities"]["tasks"]["tv2"]["payload"]["expected_output"] = "Changed task 2 output"
    client.put(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/draft",
        json={"graph": changed_graph},
        headers=auth_headers,
    )

    second_publish = client.post(f"/api/crew-graphs/{seeded_crew_asset['id']}/publish", headers=auth_headers)

    assert second_publish.status_code == 200
    assert second_publish.json()["already_published"] is False
    assert second_publish.json()["version"]["id"] != first_publish.json()["version"]["id"]

    versions = (
        db.query(AssetVersion)
        .filter(AssetVersion.asset_id == seeded_crew_asset["id"])
        .order_by(AssetVersion.version_number.asc())
        .all()
    )
    assert [version.version_number for version in versions] == [1, 2, 3]
    assert [version.status for version in versions] == ["draft", "archived", "published"]


def test_publish_crew_draft_rebases_stale_base_version_and_publishes(client, db, auth_headers):
    seeded_crew_asset = _seed_crew_asset(client, auth_headers)
    client.put(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/draft",
        json={"graph": make_valid_publish_graph_for_asset(seeded_crew_asset)},
        headers=auth_headers,
    )

    update_response = client.patch(
        f"/api/assets/{seeded_crew_asset['id']}",
        json={
            "base_version_id": seeded_crew_asset["current_version"]["id"],
            "name": "Operations Crew v2",
            "payload": {
                "process": "sequential",
                "manager_llm": {"provider": "openai", "model": "gpt-4o-mini"},
                "manager_agent_asset_id": None,
                "function_calling_llm": {"provider": "openai", "model": "gpt-4o-mini"},
                "verbose": True,
                "planning": False,
                "memory": False,
            },
        },
        headers=auth_headers,
    )

    response = client.post(
        f"/api/crew-graphs/{seeded_crew_asset['id']}/publish",
        headers=auth_headers,
    )

    assert update_response.status_code == 200
    assert response.status_code == 200
    assert response.json()["version"]["status"] == "published"
    runtime_crew = response.json()["version"]["runtime_snapshot_json"]["runtime_crew"]
    assert runtime_crew["name"] == "Operations Crew v2"
    assert runtime_crew["verbose"] is True
    assert runtime_crew["planning"] is False

    versions = (
        db.query(AssetVersion)
        .filter(AssetVersion.asset_id == seeded_crew_asset["id"])
        .order_by(AssetVersion.version_number.asc())
        .all()
    )
    assert [version.version_number for version in versions] == [1, 2, 3]

    draft = db.query(CrewVersionDraft).filter(CrewVersionDraft.crew_asset_id == seeded_crew_asset["id"]).one()
    assert str(draft.base_version_id) == response.json()["version"]["id"]


def test_publish_crew_draft_maps_asset_conflict_to_409(client, auth_headers):
    seeded_crew_asset = _seed_crew_asset(client, auth_headers)

    with patch(
        "api.routes.crew_graphs.publish_crew_draft",
        side_effect=AssetConflictError("Asset has a newer version. Refresh and retry from the latest version."),
    ):
        response = client.post(
            f"/api/crew-graphs/{seeded_crew_asset['id']}/publish",
            headers=auth_headers,
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Asset has a newer version. Refresh and retry from the latest version."
