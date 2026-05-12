import importlib
from pathlib import Path


LEGACY_ROUTE_MODULES = [
    "api.routes.agents",
    "api.routes.tasks",
    "api.routes.crews",
    "api.routes.flows",
    "api.routes.task_agents",
    "api.routes.flow_crews",
    "api.routes.skills",
    "api.routes.tools",
    "api.routes.input_presets",
    "api.routes.campaigns",
    "api.routes.workflow_graph",
]

LEGACY_ROUTE_FILES = [
    "agents.py",
    "tasks.py",
    "crews.py",
    "flows.py",
    "task_agents.py",
    "flow_crews.py",
    "skills.py",
    "tools.py",
    "input_presets.py",
    "campaigns.py",
    "workflow_graph.py",
]

LEGACY_OPENAPI_PATHS = [
    "/api/agents",
    "/api/agents/{agent_id}",
    "/api/tasks",
    "/api/tasks/{task_id}",
    "/api/crews",
    "/api/crews/{crew_id}",
    "/api/flows",
    "/api/flows/{flow_id}",
    "/api/task-agents",
    "/api/flow-crews",
    "/api/skills",
    "/api/skills/{skill_id}",
    "/api/tools",
    "/api/tools/{tool_id}",
    "/api/input-presets/{preset_id}",
    "/api/campaigns",
    "/api/campaigns/{campaign_id}",
    "/api/runs",
    "/api/flow-assemblies",
    "/api/workflows/{flow_id}/graph",
    "/api/workflows/{flow_id}/graph-view",
    "/api/workflows/{flow_id}/nodes",
    "/api/workflows/{flow_id}/nodes/{node_id}",
    "/api/workflows/{flow_id}/edges",
    "/api/workflows/{flow_id}/edges/{edge_id}",
    "/api/workflows/{flow_id}/validate",
    "/api/workflows/{flow_id}/migrations/preview",
    "/api/workflows/{flow_id}/migrations/apply",
]


def test_legacy_entity_routes_are_not_exposed_in_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]

    for legacy_path in LEGACY_OPENAPI_PATHS:
        assert legacy_path not in paths

    assert "/api/input-presets" in paths
    assert set(paths["/api/input-presets"]) == {"get"}


def test_legacy_route_modules_were_deleted_from_backend_surface():
    routes_dir = Path(__file__).resolve().parents[1] / "api" / "routes"

    for route_file in LEGACY_ROUTE_FILES:
        assert not (routes_dir / route_file).exists()

    for module_name in LEGACY_ROUTE_MODULES:
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        raise AssertionError(f"{module_name} should have been removed")
