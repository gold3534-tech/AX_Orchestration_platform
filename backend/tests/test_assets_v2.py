import importlib
import tempfile
import time
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError, ProgrammingError
from sqlalchemy.orm import Session, configure_mappers, sessionmaker

from api.core.database import get_db
from api.core.database import Base
from api.db import models
from api.db.models import (
    Asset,
    AssetRuntimeSnapshot,
    AssetVersion,
    CrewVersionDraft,
    FlowRun,
    FlowVersionDraft,
    TaskInputPresetBinding,
    VersionLink,
)
from api.dependencies import get_current_user
from api.main import app
from api.schemas.assets import AssetCreate, AssetUpdate
from api.services.assets import (
    _is_asset_version_number_conflict,
    create_asset,
    restore_asset_version as restore_asset_version_service,
    update_asset,
)
from api.services.task_input_presets import ensure_task_input_presets_seeded
from tests.fixtures_api import client, db


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


def _agent_update(created_asset: dict) -> dict:
    return {
        "base_version_id": created_asset["current_version"]["id"],
        "payload": {
            "role": "Senior Researcher",
            "goal": "Verify facts",
            "backstory": "Careful analyst",
            "llm": {"provider": "openai"},
            "verbose": True,
        },
        "change_summary": "promote role",
    }


def _isolated_session_factory():
    tempdir = tempfile.TemporaryDirectory()
    engine = create_engine(
        f"sqlite:///{tempdir.name}/assets-test.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        ensure_task_input_presets_seeded(session)
        session.execute(text("CREATE TABLE IF NOT EXISTS asset_shares (asset_id TEXT)"))
        session.execute(
            text(
                "CREATE TABLE IF NOT EXISTS asset_imports (source_asset_id TEXT, imported_asset_id TEXT)"
            )
        )
        session.commit()
    finally:
        session.close()
    return SessionLocal, engine, tempdir


def test_core_models_map_to_current_database_column_names():
    assert "asset_type" in Asset.__table__.c
    assert "workspace_id" in Asset.__table__.c
    assert "owner_user_id" in Asset.__table__.c
    assert "current_version_id" not in Asset.__table__.c

    assert "version_no" in AssetVersion.__table__.c
    assert "payload_json" in AssetVersion.__table__.c
    assert "version_number" not in AssetVersion.__table__.c
    assert "data_json" not in AssetVersion.__table__.c

    assert AssetRuntimeSnapshot.__tablename__ == "asset_runtime_snapshots"
    assert "version_id" in AssetRuntimeSnapshot.__table__.c
    assert "runtime_snapshot_json" in AssetRuntimeSnapshot.__table__.c
    assert "agent_versions" not in Base.metadata.tables
    assert "task_versions" not in Base.metadata.tables
    assert "crew_versions" not in Base.metadata.tables
    assert "flow_versions" not in Base.metadata.tables
    assert {
        fk.column.table.name
        for fk in CrewVersionDraft.__table__.c.base_version_id.foreign_keys
    } == {"asset_versions"}
    assert {
        fk.column.table.name
        for fk in FlowVersionDraft.__table__.c.base_version_id.foreign_keys
    } == {"asset_versions"}
    assert {
        fk.column.table.name
        for fk in FlowRun.__table__.c.flow_version_id.foreign_keys
    } == {"asset_versions"}


def test_unified_asset_payload_storage_sql_exists_for_postgres_schema_apply():
    sql_root = Path(__file__).resolve().parents[1] / "sql"
    sql_path = sql_root / "007_unify_asset_versions_payload_storage.sql"

    assert sql_path.exists()
    assert not (sql_root / "006_unify_asset_versions_payload_storage.sql").exists()

    sql = sql_path.read_text()

    assert "CREATE TABLE IF NOT EXISTS asset_runtime_snapshots" in sql
    assert "jsonb_build_object('role', av.role" in sql
    assert "jsonb_build_object('description', tv.description" in sql
    assert "jsonb_build_object('process', cv.process_type" in sql
    assert "|| COALESCE(av.payload_json, '{}'::jsonb)\n  || COALESCE(asset_version.payload_json, '{}'::jsonb)" in sql
    assert "|| COALESCE(tv.payload_json, '{}'::jsonb)\n  || COALESCE(asset_version.payload_json, '{}'::jsonb)" in sql
    assert "|| COALESCE(cv.payload_json, '{}'::jsonb)\n  || COALESCE(asset_version.payload_json, '{}'::jsonb)" in sql
    assert "RENAME COLUMN task_version_id TO asset_version_id" in sql
    assert "DROP TABLE IF EXISTS agent_versions CASCADE" in sql
    assert "DROP TABLE IF EXISTS task_versions CASCADE" in sql
    assert "DROP TABLE IF EXISTS crew_versions CASCADE" in sql
    assert "ALTER TABLE IF EXISTS flow_version_drafts" in sql
    assert "DROP CONSTRAINT IF EXISTS flow_version_drafts_base_version_id_fkey" in sql
    assert "ADD CONSTRAINT fk_flow_version_drafts_base_asset_version" in sql
    assert "FOREIGN KEY (base_version_id) REFERENCES asset_versions(id) ON DELETE SET NULL" in sql
    assert "ALTER TABLE IF EXISTS flow_runs" in sql
    assert "DROP CONSTRAINT IF EXISTS flow_runs_flow_version_id_fkey" in sql
    assert "ADD CONSTRAINT fk_flow_runs_flow_asset_version" in sql
    assert "FOREIGN KEY (flow_version_id) REFERENCES asset_versions(id) ON DELETE CASCADE" in sql
    assert "DROP TABLE IF EXISTS flow_versions CASCADE" in sql


def test_crew_draft_persistence_sql_exists_for_postgres_schema_apply():
    sql_path = Path(__file__).resolve().parents[1] / "sql" / "003_crew_draft_persistence.sql"

    assert sql_path.exists()

    sql = sql_path.read_text()

    assert "CREATE TABLE IF NOT EXISTS crew_version_drafts" in sql
    assert "base_version_id UUID REFERENCES asset_versions(id) ON DELETE SET NULL" in sql
    assert "crew_versions" not in sql


def test_flow_builder_persistence_sql_exists_for_postgres_schema_apply():
    sql_path = Path(__file__).resolve().parents[1] / "sql" / "004_flow_builder_persistence.sql"

    assert sql_path.exists()

    sql = sql_path.read_text()

    assert "ALTER TABLE flow_versions" not in sql
    assert "REFERENCES flow_versions" not in sql
    assert "CREATE TABLE IF NOT EXISTS flow_version_drafts" in sql
    assert "base_version_id UUID REFERENCES asset_versions(id) ON DELETE SET NULL" in sql
    assert "CREATE TABLE IF NOT EXISTS flow_run_state_snapshots" in sql
    assert "CREATE TABLE IF NOT EXISTS flow_run_events" in sql
    assert "CREATE TABLE IF NOT EXISTS human_feedback_requests" in sql


def test_flow_hitl_runtime_sql_includes_node_outputs_and_request_metadata():
    sql_path = Path(__file__).resolve().parents[1] / "sql" / "009_flow_hitl_review_gate_runtime.sql"

    assert sql_path.exists()

    sql = sql_path.read_text()
    assert "CREATE TABLE IF NOT EXISTS flow_run_node_outputs" in sql
    assert "id UUID PRIMARY KEY DEFAULT gen_random_uuid()" in sql
    assert "CONSTRAINT uq_flow_run_node_outputs_run_node_version UNIQUE (run_id, node_id, version)" in sql
    assert "ADD COLUMN IF NOT EXISTS attempt_number INTEGER" in sql
    assert "ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ" in sql
    assert "ADD COLUMN IF NOT EXISTS resolved_by UUID" in sql
    assert "ADD COLUMN IF NOT EXISTS idempotency_key TEXT" in sql


def test_flow_run_event_stream_index_sql_exists_for_postgres_schema_apply():
    sql_path = Path(__file__).resolve().parents[1] / "sql" / "010_flow_run_event_stream_index.sql"

    assert sql_path.exists()

    sql = sql_path.read_text()
    assert "CREATE INDEX IF NOT EXISTS ix_flow_run_events_run_created_id" in sql
    assert "ON flow_run_events (run_id, created_at, id)" in sql


def test_auth_profiles_restore_sql_keeps_new_google_users_insertable():
    sql_path = Path(__file__).resolve().parents[1] / "sql" / "013_restore_auth_profiles.sql"

    assert sql_path.exists()

    sql = sql_path.read_text()
    assert "CREATE TABLE IF NOT EXISTS profiles" in sql
    assert "REFERENCES auth.users(id) ON DELETE CASCADE" in sql
    assert "INSERT INTO profiles (id, email, created_at, updated_at)" in sql
    assert "CREATE OR REPLACE FUNCTION public.handle_new_user()" in sql
    assert "ON CONFLICT (id) DO UPDATE" in sql
    assert "SET search_path = public, auth" in sql
    assert "CREATE TRIGGER on_auth_user_created" in sql
    assert "AFTER INSERT ON auth.users" in sql


def test_asset_version_number_conflict_filter_is_specific():
    sqlite_version_conflict = IntegrityError(
        "INSERT",
        {},
        Exception("UNIQUE constraint failed: asset_versions.asset_id, asset_versions.version_no"),
    )
    postgres_version_conflict = IntegrityError(
        "INSERT",
        {},
        SimpleNamespace(
            diag=SimpleNamespace(constraint_name="uq_asset_versions_asset_version_no")
        ),
    )
    unrelated_integrity_error = IntegrityError(
        "INSERT",
        {},
        Exception("NOT NULL constraint failed: asset_versions.created_by"),
    )

    assert _is_asset_version_number_conflict(sqlite_version_conflict) is True
    assert _is_asset_version_number_conflict(postgres_version_conflict) is True
    assert _is_asset_version_number_conflict(unrelated_integrity_error) is False


def test_new_core_tables_exist(db):
    configure_mappers()
    asset = Asset(
        asset_type="agent",
        workspace_id="11111111-1111-1111-1111-111111111111",
        owner_user_id="22222222-2222-2222-2222-222222222222",
        name="test asset",
    )
    version = AssetVersion(asset=asset, version_number=1, status="draft", metadata_json={}, created_by="test-user")
    assert version.asset is asset
    assert version in asset.versions

    names = set(inspect(db.get_bind()).get_table_names())
    legacy_names = {
        "agent_definitions",
        "agent_skills",
        "agent_tools",
        "crew_agents",
        "crew_definitions",
        "crew_tasks",
        "flow_definitions",
        "run_logs",
        "skill_definitions",
        "task_agents",
        "task_definitions",
        "task_input_bindings",
    }

    assert "assets" in names
    assert "asset_versions" in names
    assert "version_links" in names
    assert "version_tools" in names
    assert "version_skills" in names
    assert "tool_registry" in names
    assert "credentials" in names
    assert "execution_bindings" in names
    assert "workflow_nodes" not in names
    assert "workflow_edges" not in names
    assert "flow_runs" in names
    assert names.isdisjoint(legacy_names)


def test_schema_includes_crew_version_drafts_table():
    from sqlalchemy import inspect

    _, engine, tempdir = _isolated_session_factory()
    try:
        names = inspect(engine).get_table_names()
    finally:
        engine.dispose()
        tempdir.cleanup()

    assert "crew_version_drafts" in names


def test_runtime_models_include_flow_builder_and_event_tables():
    from api.db.models import (
        FlowRunEvent,
        FlowRunNodeOutput,
        FlowRunStateSnapshot,
        FlowVersionDraft,
        HumanFeedbackRequest,
    )

    assert FlowVersionDraft.__tablename__ == "flow_version_drafts"
    assert "flow_versions" not in Base.metadata.tables
    assert "runtime_snapshot_json" in AssetRuntimeSnapshot.__table__.c
    assert FlowRunStateSnapshot.__tablename__ == "flow_run_state_snapshots"
    assert FlowRunEvent.__tablename__ == "flow_run_events"
    assert FlowRunNodeOutput.__tablename__ == "flow_run_node_outputs"
    assert HumanFeedbackRequest.__tablename__ == "human_feedback_requests"
    assert "attempt_number" in HumanFeedbackRequest.__table__.columns
    assert "idempotency_key" in HumanFeedbackRequest.__table__.columns
    event_index_by_name = {index.name: index for index in FlowRunEvent.__table__.indexes}
    assert "ix_flow_run_events_run_created_id" in event_index_by_name
    assert [column.name for column in event_index_by_name["ix_flow_run_events_run_created_id"].columns] == [
        "run_id",
        "created_at",
        "id",
    ]
    index_by_name = {index.name: index for index in HumanFeedbackRequest.__table__.indexes}
    assert "ix_human_feedback_requests_run_node_status" in index_by_name
    assert "uq_human_feedback_requests_idempotency" in index_by_name
    assert index_by_name["uq_human_feedback_requests_idempotency"].unique is True


def test_openapi_exposes_versioned_asset_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/assets" in paths
    assert set(paths["/api/assets"]) == {"get", "post"}
    assert "/api/assets/{asset_id}" in paths
    assert set(paths["/api/assets/{asset_id}"]) == {"get", "patch", "delete"}
    assert "/api/assets/{asset_id}/versions" in paths
    assert "/api/assets/{asset_id}/versions/{version_id}" in paths
    assert set(paths["/api/assets/{asset_id}/versions/{version_id}"]) == {"get", "delete"}
    assert "/api/assets/{asset_id}/versions/{version_id}/restore" in paths
    asset_create_schema = client.get("/openapi.json").json()["components"]["schemas"]["AssetCreate"]
    assert "payload" in asset_create_schema["properties"]
    assert "initial_payload" not in asset_create_schema["properties"]
    assert "/api/versions/{version_id}/links" not in paths
    assert "/api/versions/{version_id}/tools" in paths
    assert set(paths["/api/versions/{version_id}/tools"]) == {"get", "post"}
    assert "/api/versions/{version_id}/tools/{tool_key}" in paths
    assert set(paths["/api/versions/{version_id}/tools/{tool_key}"]) == {"patch", "delete"}
    assert "/api/versions/{version_id}/skills" in paths
    assert set(paths["/api/versions/{version_id}/skills"]) == {"get", "post"}
    assert "/api/version-capabilities" in paths
    assert set(paths["/api/version-capabilities"]) == {"get"}
    assert "/api/tool-catalog" in paths
    assert "/api/tool-catalog/{tool_key}" in paths
    assert "/api/skill-catalog" in paths
    assert "/api/credentials" in paths
    assert "/api/flow-assemblies" not in paths
    assert "/api/crew-graphs/{crew_asset_id}/draft" in paths
    assert set(paths["/api/crew-graphs/{crew_asset_id}/draft"]) == {"get", "put"}
    assert "/api/crew-graphs/{crew_asset_id}/validate" in paths
    assert set(paths["/api/crew-graphs/{crew_asset_id}/validate"]) == {"post"}
    assert "/api/crew-graphs/{crew_asset_id}/publish" in paths
    assert set(paths["/api/crew-graphs/{crew_asset_id}/publish"]) == {"post"}
    assert "/api/versions/{version_id}/bindings" in paths
    assert set(paths["/api/versions/{version_id}/bindings"]) == {"post"}
    assert "/api/input-presets" in paths
    assert set(paths["/api/input-presets"]) == {"get"}
    assert "/api/input-presets/{preset_id}" not in paths
    assert set(paths["/api/tool-catalog"]) == {"get", "post"}
    assert set(paths["/api/tool-catalog/{tool_key}"]) == {"get"}
    assert set(paths["/api/skill-catalog"]) == {"get", "post"}
    assert set(paths["/api/credentials"]) == {"get", "post"}
    assert "/api/agents" not in paths
    assert "/api/tasks" not in paths
    assert "/api/flows" not in paths


def test_legacy_modules_are_not_importable():
    for module_name in [
        "api.core.schema_sync",
        "api.routes.agents",
        "api.routes.composition",
        "api.routes.crews",
        "api.routes.flow_crews",
        "api.routes.flows",
        "api.routes.input_presets",
        "api.routes.skills",
        "api.routes.task_agents",
        "api.routes.tasks",
        "api.routes.tools",
        "api.repositories.agents",
        "api.repositories.crews",
        "api.repositories.flow_crews",
        "api.repositories.flows",
        "api.repositories.input_presets",
        "api.repositories.runs",
        "api.repositories.skills",
        "api.repositories.task_agents",
        "api.repositories.tasks",
        "api.repositories.tools",
        "api.runtime.crew_builder",
        "api.runtime.definition_loader",
        "api.runtime.executor",
        "api.runtime.input_contracts",
        "api.runtime.llm_resolver",
        "api.runtime.policy_resolver",
        "api.runtime.skill_loader",
        "api.runtime.tool_registry",
        "api.schemas.agent",
        "api.schemas.crew",
        "api.schemas.flow",
        "api.schemas.input_preset",
        "api.schemas.run",
        "api.schemas.skill",
        "api.schemas.task",
    ]:
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        raise AssertionError(f"{module_name} should have been removed")


def test_agent_asset_sparse_top_level_payload_preserves_explicit_optional_values(client, auth_headers):
    response = client.post(
        "/api/assets",
        json={
            "type": "agent",
            "name": "Sparse Agent",
            "description": "Agent sparse payload",
            "payload": {
                "role": "Researcher",
                "goal": "Find reliable facts",
                "backstory": "Careful analyst",
                "verbose": False,
                "cache": True,
                "reasoning": True,
                "max_reasoning_attempts": 3,
            },
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    payload = response.json()["current_version"]["payload"]
    assert payload["role"] == "Researcher"
    assert payload["goal"] == "Find reliable facts"
    assert payload["backstory"] == "Careful analyst"
    assert payload["verbose"] is False
    assert payload["cache"] is True
    assert payload["reasoning"] is True
    assert payload["max_reasoning_attempts"] == 3
    assert "max_iter" not in payload
    assert "respect_context_window" not in payload
    assert "date_format" not in payload
    assert "payload_json" not in payload


@pytest.mark.parametrize(
    "asset_payload",
    [
        {
            "type": "agent",
            "name": "Warning Free Agent",
            "payload": {
                "role": "Researcher",
                "goal": "Find reliable facts",
                "backstory": "Careful analyst",
                "cache": True,
            },
        },
        {
            "type": "task",
            "name": "Warning Free Task",
            "payload": {
                "description": "Write a structured result.",
                "expected_output": "A structured result.",
                "output_type": "Output JSON",
                "output_schema_fields": [{"name": "summary", "type": "str", "required": True}],
            },
        },
        {
            "type": "crew",
            "name": "Warning Free Crew",
            "payload": {
                "process": "sequential",
                "cache": False,
                "tracing": True,
                "checkpoint": True,
            },
        },
    ],
)
def test_asset_create_model_dump_does_not_warn_for_sparse_payloads(asset_payload):
    asset = AssetCreate.model_validate(asset_payload)

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        dumped = asset.model_dump(mode="json")

    unexpected_serialization_warnings = [
        warning
        for warning in captured
        if "PydanticSerializationUnexpectedValue" in str(warning.message)
    ]
    assert unexpected_serialization_warnings == []
    assert isinstance(dumped["payload"], dict)


def test_agent_asset_omits_unset_optional_values(client, auth_headers):
    response = client.post(
        "/api/assets",
        json={
            "type": "agent",
            "name": "Core Agent",
            "description": "Only required text fields",
            "payload": {
                "role": "Researcher",
                "goal": "Find reliable facts",
                "backstory": "Careful analyst",
            },
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    payload = response.json()["current_version"]["payload"]
    assert payload == {
        "role": "Researcher",
        "goal": "Find reliable facts",
        "backstory": "Careful analyst",
    }


def test_task_asset_sparse_top_level_output_schema_fields(client, auth_headers):
    response = client.post(
        "/api/assets",
        json={
            "type": "task",
            "name": "Structured Task",
            "description": "Task sparse payload",
            "payload": {
                "description": "Write a structured result.",
                "expected_output": "A structured result.",
                "human_input": True,
                "output_type": "Output JSON",
                "output_schema_fields": [
                    {
                        "name": "summary",
                        "type": "str",
                        "description": "Short summary",
                        "required": True,
                    },
                    {
                        "name": "metadata",
                        "type": "dict",
                        "description": "Flat metadata object",
                        "required": False,
                    },
                ],
            },
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    payload = response.json()["current_version"]["payload"]
    assert payload["description"] == "Write a structured result."
    assert payload["expected_output"] == "A structured result."
    assert payload["human_input"] is True
    assert payload["output_type"] == "Output JSON"
    assert payload["output_schema_fields"][0]["name"] == "summary"
    assert "async_execution" not in payload
    assert "markdown" not in payload
    assert "payload_json" not in payload


def test_task_asset_raw_output_omits_structured_output_fields(client, auth_headers):
    response = client.post(
        "/api/assets",
        json={
            "type": "task",
            "name": "Raw Task",
            "description": "Task with native raw output",
            "payload": {
                "description": "Write a plain result.",
                "expected_output": "A plain result.",
            },
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    payload = response.json()["current_version"]["payload"]
    assert payload["description"] == "Write a plain result."
    assert payload["expected_output"] == "A plain result."
    assert "output_type" not in payload
    assert "output_schema_fields" not in payload


def test_task_asset_preserves_explicit_false_optional_values(client, auth_headers):
    response = client.post(
        "/api/assets",
        json={
            "type": "task",
            "name": "Explicit False Task",
            "description": "Task with explicit false options",
            "payload": {
                "description": "Write a result.",
                "expected_output": "A result.",
                "async_execution": False,
                "markdown": False,
            },
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    payload = response.json()["current_version"]["payload"]
    assert payload["async_execution"] is False
    assert payload["markdown"] is False


def test_crew_asset_sparse_top_level_payload_preserves_explicit_optional_values(client, auth_headers):
    response = client.post(
        "/api/assets",
        json={
            "type": "crew",
            "name": "Sparse Crew",
            "description": "Crew sparse payload",
            "payload": {
                "process": "sequential",
                "verbose": False,
                "cache": True,
                "planning": True,
                "memory": True,
                "stream": False,
                "tracing": True,
                "checkpoint": True,
            },
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    payload = response.json()["current_version"]["payload"]
    assert payload["process"] == "sequential"
    assert payload["verbose"] is False
    assert payload["cache"] is True
    assert payload["planning"] is True
    assert payload["memory"] is True
    assert payload["stream"] is False
    assert payload["tracing"] is True
    assert payload["checkpoint"] is True
    assert "payload_json" not in payload


def test_crew_asset_omitted_process_persists_default_process(client, auth_headers):
    response = client.post(
        "/api/assets",
        json={
            "type": "crew",
            "name": "Default Process Crew",
            "description": "Crew default process payload",
            "payload": {},
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["current_version"]["payload"] == {"process": "sequential"}


def test_crew_asset_accepts_bool_output_log_file_and_dict_checkpoint(client, auth_headers):
    response = client.post(
        "/api/assets",
        json={
            "type": "crew",
            "name": "Logging Crew",
            "description": "Crew flexible logging payload",
            "payload": {
                "process": "sequential",
                "output_log_file": True,
                "checkpoint": {"enabled": True, "path": "checkpoints/run.json"},
            },
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    payload = response.json()["current_version"]["payload"]
    assert payload["output_log_file"] is True
    assert payload["checkpoint"] == {"enabled": True, "path": "checkpoints/run.json"}


def test_config_json_is_rejected_from_public_asset_payload(client, auth_headers):
    response = client.post(
        "/api/assets",
        json={
            "type": "agent",
            "name": "Config Agent",
            "description": "Config is not public payload storage",
            "payload": {
                "role": "Researcher",
                "goal": "Find facts",
                "backstory": "Careful analyst",
                "config_json": {"cache": False},
            },
        },
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert "config_json" in response.text


def test_task_asset_payload_rejects_crewai_trigger_context(client, auth_headers):
    response = client.post(
        "/api/assets",
        json={
            "type": "task",
            "name": "No Trigger Context",
            "description": "Task",
            "payload": {
                "description": "Do the task.",
                "expected_output": "Done.",
                "allow_crewai_trigger_context": True,
            },
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_create_agent_asset_and_initial_version(client, db):
    payload = {
        "type": "agent",
        "name": "Research Agent",
        "description": "Investigates topics",
        "workspace_id": "11111111-1111-1111-1111-111111111111",
        "initial_payload": {
            "role": "Researcher",
            "goal": "Find facts",
            "backstory": "Careful analyst",
            "llm": {"provider": "openai", "model": "gpt-4o-mini"},
            "verbose": True,
        },
    }

    response = client.post("/api/assets", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "agent"
    assert data["current_version"]["version_no"] == 1
    assert data["current_version"]["payload"]["role"] == "Researcher"

    asset = db.query(Asset).filter(Asset.id == data["id"]).one()
    assert asset.asset_type == "agent"

    asset_version = db.query(AssetVersion).filter(AssetVersion.asset_id == asset.id).one()
    assert asset_version.version_number == 1
    assert asset_version.metadata_json["description"] == payload["description"]
    assert asset_version.metadata_json["workspace_id"] == payload["workspace_id"]
    assert asset_version.payload_json == payload["initial_payload"]


def test_create_task_asset_and_initial_version(client, db):
    payload = {
        "type": "task",
        "name": "Research Task",
        "description": "Collect and summarize facts",
        "workspace_id": "11111111-1111-1111-1111-111111111111",
        "payload": {
            "description": "Collect and summarize facts",
            "expected_output": "A concise summary",
            "async_execution": True,
            "human_input": False,
            "markdown": True,
        },
    }

    response = client.post("/api/assets", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "task"
    assert data["current_version"]["version_no"] == 1
    assert data["current_version"]["payload"]["expected_output"] == "A concise summary"

    asset = db.query(Asset).filter(Asset.id == data["id"]).one()
    assert asset.asset_type == "task"

    asset_version = db.query(AssetVersion).filter(AssetVersion.asset_id == asset.id).one()
    assert asset_version.version_number == 1
    assert asset_version.payload_json == payload["payload"]


def test_task_asset_payload_omits_unsubmitted_config_json(client):
    response = client.post(
        "/api/assets",
        json={
            "type": "task",
            "name": "Minimal Task",
            "description": "Only required task fields",
            "payload": {
                "description": "Only required task fields",
                "expected_output": "A concise result",
            },
        },
    )

    assert response.status_code == 201
    assert "payload_json" not in response.json()["current_version"]["payload"]

    listed = client.get("/api/assets", params={"type": "task"})
    assert listed.status_code == 200
    assert "payload_json" not in listed.json()[0]["current_version"]["payload"]


def test_task_asset_payload_accepts_input_presets(client):
    response = client.post(
        "/api/assets",
        json={
            "type": "task",
            "name": "SEO Brief",
            "description": "Search intent analysis",
            "payload": {
                "description": "Search intent analysis",
                "expected_output": "SEO brief",
                "input_presets": ["website_url", "keyword"],
            },
        },
    )

    assert response.status_code == 201
    assert response.json()["current_version"]["payload"]["input_presets"] == ["website_url", "keyword"]


def test_create_task_asset_persists_preset_bindings(client, db):
    response = client.post(
        "/api/assets",
        json={
            "type": "task",
            "name": "SEO Brief",
            "description": "Search intent analysis",
            "payload": {
                "description": "Search intent analysis",
                "expected_output": "SEO brief",
                "input_presets": ["website_url", "keyword"],
            },
        },
    )

    assert response.status_code == 201
    asset_id = response.json()["id"]
    version_id = response.json()["current_version"]["id"]

    asset = db.query(Asset).filter(Asset.id == asset_id).one()
    bindings = (
        db.query(models.TaskInputPresetBinding)
        .filter(models.TaskInputPresetBinding.asset_version_id == version_id)
        .order_by(models.TaskInputPresetBinding.sort_order.asc())
        .all()
    )

    assert asset.name == "SEO Brief"
    assert [binding.preset_definition.key for binding in bindings] == ["website_url", "keyword"]


def test_create_task_asset_normalizes_duplicate_input_presets(client, db):
    response = client.post(
        "/api/assets",
        json={
            "type": "task",
            "name": "SEO Brief",
            "description": "Search intent analysis",
            "payload": {
                "description": "Search intent analysis",
                "expected_output": "SEO brief",
                "input_presets": ["website_url", "keyword", "website_url", "keyword"],
            },
        },
    )

    assert response.status_code == 201
    version_id = response.json()["current_version"]["id"]
    assert response.json()["current_version"]["payload"]["input_presets"] == ["website_url", "keyword"]

    asset_version = db.query(AssetVersion).filter(AssetVersion.id == version_id).one()
    bindings = (
        db.query(models.TaskInputPresetBinding)
        .filter(models.TaskInputPresetBinding.asset_version_id == version_id)
        .order_by(models.TaskInputPresetBinding.sort_order.asc())
        .all()
    )

    assert asset_version.payload_json["input_presets"] == ["website_url", "keyword"]
    assert [binding.preset_definition.key for binding in bindings] == ["website_url", "keyword"]


def test_create_task_asset_without_workspace_serializes_null_workspace_id(client, db):
    payload = {
        "type": "task",
        "name": "Workspace-less Task",
        "description": "Uses sentinel workspace internally",
        "payload": {
            "description": "Collect and summarize facts",
            "expected_output": "A concise summary",
        },
    }

    response = client.post("/api/assets", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["workspace_id"] is None

    asset = db.query(Asset).filter(Asset.id == data["id"]).one()
    assert str(asset.workspace_id) == "00000000-0000-0000-0000-000000000000"


def test_flow_asset_payload_stores_only_flow_level_settings(client, db, auth_headers):
    response = client.post(
        "/api/assets",
        json={
            "type": "flow",
            "name": "Lean Flow",
            "description": "No runtime graph in payload",
            "payload": {
                "entry_method": "run",
                "timeout_seconds": 120,
            },
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["current_version"]["payload"] == {
        "entry_method": "run",
        "timeout_seconds": 120,
    }

    asset_version = db.get(AssetVersion, data["current_version"]["id"])
    assert asset_version.payload_json == {
        "entry_method": "run",
        "timeout_seconds": 120,
    }


def test_flow_asset_payload_rejects_runtime_graph_fields(client, auth_headers):
    response = client.post(
        "/api/assets",
        json={
            "type": "flow",
            "name": "Invalid Flow",
            "description": "Runtime graph belongs in drafts and snapshots",
            "payload": {
                "entry_method": "run",
                "state_schema_json": {},
                "flow_definition_json": {},
                "crew_refs": [],
                "runtime_snapshot_json": {},
            },
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_patch_asset_accepts_task_name_and_description_changes(client):
    created = client.post(
        "/api/assets",
        json={
            "type": "task",
            "name": "SEO Brief",
            "description": "Search intent analysis",
            "payload": {
                "description": "Search intent analysis",
                "expected_output": "SEO brief",
                "input_presets": ["website_url"],
            },
        },
    ).json()

    updated = client.patch(
        f"/api/assets/{created['id']}",
        json={
            "base_version_id": created["current_version"]["id"],
            "name": "SEO Brief v2",
            "description": "Search intent and competitor analysis",
            "payload": {
                "description": "Search intent and competitor analysis",
                "expected_output": "Expanded SEO brief",
                "input_presets": ["website_url", "brand_name"],
            },
        },
    )

    assert updated.status_code == 200
    assert updated.json()["name"] == "SEO Brief v2"
    assert updated.json()["description"] == "Search intent and competitor analysis"


def test_update_task_asset_replaces_binding_set_for_new_version(client, db):
    created = client.post(
        "/api/assets",
        json={
            "type": "task",
            "name": "SEO Brief",
            "description": "Search intent analysis",
            "payload": {
                "description": "Search intent analysis",
                "expected_output": "SEO brief",
                "input_presets": ["website_url", "keyword"],
            },
        },
    ).json()

    updated = client.patch(
        f"/api/assets/{created['id']}",
        json={
            "base_version_id": created["current_version"]["id"],
            "name": "SEO Brief v2",
            "payload": {
                "description": "Competitor-aware SEO brief",
                "expected_output": "Expanded SEO brief",
                "input_presets": ["website_url", "brand_name"],
            },
        },
    )

    assert updated.status_code == 200
    assert updated.json()["current_version"]["payload"]["input_presets"] == ["website_url", "brand_name"]

    versions = (
        db.query(AssetVersion)
        .filter(AssetVersion.asset_id == created["id"])
        .order_by(AssetVersion.version_number.asc())
        .all()
    )
    original_bindings = (
        db.query(models.TaskInputPresetBinding)
        .filter(models.TaskInputPresetBinding.asset_version_id == versions[0].id)
        .order_by(models.TaskInputPresetBinding.sort_order.asc())
        .all()
    )
    new_bindings = (
        db.query(models.TaskInputPresetBinding)
        .filter(models.TaskInputPresetBinding.asset_version_id == versions[1].id)
        .order_by(models.TaskInputPresetBinding.sort_order.asc())
        .all()
    )

    assert [row.preset_definition.key for row in original_bindings] == ["website_url", "keyword"]
    assert [row.preset_definition.key for row in new_bindings] == ["website_url", "brand_name"]


def test_task_asset_rejects_unknown_or_inactive_preset_keys(client, db):
    ensure_task_input_presets_seeded(db)
    inactive = (
        db.query(models.InputPresetDefinition)
        .filter(models.InputPresetDefinition.key == "keyword")
        .one()
    )
    inactive.is_active = False
    db.commit()

    inactive_response = client.post(
        "/api/assets",
        json={
            "type": "task",
            "name": "Inactive Preset Task",
            "description": "Inactive preset key",
            "payload": {
                "description": "Inactive preset key",
                "expected_output": "Failure",
                "input_presets": ["keyword"],
            },
        },
    )
    unknown_response = client.post(
        "/api/assets",
        json={
            "type": "task",
            "name": "Bad Task",
            "description": "Invalid preset key",
            "payload": {
                "description": "Invalid preset key",
                "expected_output": "Failure",
                "input_presets": ["not_real"],
            },
        },
    )

    assert inactive_response.status_code == 422
    assert inactive_response.json()["detail"] == "Unknown or inactive task input preset keys: keyword"
    assert unknown_response.status_code == 422
    assert unknown_response.json()["detail"] == "Unknown or inactive task input preset keys: not_real"


def test_create_task_asset_invalid_preset_keys_do_not_persist_partial_rows(client, db):
    response = client.post(
        "/api/assets",
        json={
            "type": "task",
            "name": "Bad Task",
            "description": "Invalid preset key",
            "payload": {
                "description": "Invalid preset key",
                "expected_output": "Failure",
                "input_presets": ["not_real"],
            },
        },
    )

    assert response.status_code == 422
    assert db.query(Asset).count() == 0
    assert db.query(AssetVersion).count() == 0
    assert db.query(models.TaskInputPresetBinding).count() == 0


def test_update_task_asset_invalid_preset_keys_do_not_persist_partial_rows():
    SessionLocal, engine, tempdir = _isolated_session_factory()
    setup = SessionLocal()
    try:
        created = create_asset(
            setup,
            AssetCreate.model_validate(
                {
                    "type": "task",
                    "name": "SEO Brief",
                    "description": "Search intent analysis",
                    "payload": {
                        "description": "Search intent analysis",
                        "expected_output": "SEO brief",
                        "input_presets": ["website_url"],
                    },
                }
            ),
            owner_user_id="test-user",
        )
        created_asset_id = str(created["asset"].id)
        created_version_id = str(created["asset_version"].id)
    finally:
        setup.close()

    writer = SessionLocal()
    try:
        with pytest.raises(ValueError, match="Unknown or inactive task input preset keys: not_real"):
            update_asset(
                writer,
                created_asset_id,
                AssetUpdate.model_validate(
                    {
                        "base_version_id": created_version_id,
                        "name": "Broken Task",
                        "description": "Should roll back",
                        "payload": {
                            "description": "Broken payload",
                            "expected_output": "Failure",
                            "input_presets": ["not_real"],
                        },
                    }
                ),
                owner_user_id="test-user",
            )
    finally:
        writer.close()

    reader = SessionLocal()
    try:
        asset = reader.query(Asset).filter(Asset.id == created_asset_id).one()
        versions = (
            reader.query(AssetVersion)
            .filter(AssetVersion.asset_id == created_asset_id)
            .order_by(AssetVersion.version_number.asc())
            .all()
        )
        bindings = (
            reader.query(models.TaskInputPresetBinding)
            .filter(models.TaskInputPresetBinding.asset_version_id == created_version_id)
            .order_by(models.TaskInputPresetBinding.sort_order.asc())
            .all()
        )
        binding_keys = [binding.preset_definition.key for binding in bindings]
    finally:
        reader.close()

    assert asset.name == "SEO Brief"
    assert asset.description == "Search intent analysis"
    assert [version.version_number for version in versions] == [1]
    assert binding_keys == ["website_url"]
    engine.dispose()
    tempdir.cleanup()


def test_create_crew_asset_and_initial_version(client, db):
    payload = {
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

    response = client.post("/api/assets", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "crew"
    assert data["current_version"]["version_no"] == 1
    assert data["current_version"]["payload"]["process"] == "sequential"

    asset = db.query(Asset).filter(Asset.id == data["id"]).one()
    asset_version = db.query(AssetVersion).filter(AssetVersion.asset_id == asset.id).one()
    assert "manager_agent_asset_id" not in asset_version.payload_json


def test_create_hierarchical_crew_asset_requires_manager_llm(client):
    response = client.post(
        "/api/assets",
        json={
            "type": "crew",
            "name": "Invalid Hierarchical Crew",
            "description": "Manager agent alone is future support",
            "workspace_id": "11111111-1111-1111-1111-111111111111",
            "payload": {
                "process": "hierarchical",
                "manager_agent_asset_id": "22222222-2222-2222-2222-222222222222",
            },
        },
    )

    assert response.status_code == 422
    assert "hierarchical crew requires manager_llm" in response.text


@pytest.mark.parametrize(
    "manager_llm",
    [
        {},
        "   ",
        {"provider": "openai"},
        {"provider": "openai", "model": "   "},
        {"provider": "openai", "main_model": "   "},
        {"provider": "openai", "main_model": "   ", "model": "gpt-4o-mini"},
    ],
)
def test_create_hierarchical_crew_asset_rejects_empty_manager_llm(client, manager_llm):
    response = client.post(
        "/api/assets",
        json={
            "type": "crew",
            "name": "Empty Manager LLM Crew",
            "description": "Hierarchical crew needs a usable manager LLM",
            "workspace_id": "11111111-1111-1111-1111-111111111111",
            "payload": {
                "process": "hierarchical",
                "manager_llm": manager_llm,
            },
        },
    )

    assert response.status_code == 422
    assert "hierarchical crew requires manager_llm" in response.text


def test_create_hierarchical_crew_asset_accepts_manager_llm(client, db):
    response = client.post(
        "/api/assets",
        json={
            "type": "crew",
            "name": "Manager LLM Crew",
            "description": "Coordinates through CrewAI hierarchical process",
            "workspace_id": "11111111-1111-1111-1111-111111111111",
            "payload": {
                "process": "hierarchical",
                "manager_llm": {"provider": "openai", "model": "gpt-4o-mini"},
                "manager_agent_asset_id": "22222222-2222-2222-2222-222222222222",
            },
        },
    )

    assert response.status_code == 201
    data = response.json()
    payload = data["current_version"]["payload"]
    assert payload["process"] == "hierarchical"
    assert payload["manager_llm"] == {"provider": "openai", "model": "gpt-4o-mini"}
    assert payload["manager_agent_asset_id"] == "22222222-2222-2222-2222-222222222222"

    asset_version = db.query(AssetVersion).filter(AssetVersion.asset_id == data["id"]).one()
    assert asset_version.payload_json["process"] == "hierarchical"
    assert asset_version.payload_json["manager_llm"] == {"provider": "openai", "model": "gpt-4o-mini"}


@pytest.mark.parametrize(
    "manager_llm",
    [
        "gpt-4o-mini",
        {"provider": "openai", "main_model": "gpt-4o-mini"},
    ],
)
def test_create_hierarchical_crew_asset_accepts_usable_manager_llm(client, manager_llm):
    response = client.post(
        "/api/assets",
        json={
            "type": "crew",
            "name": "Usable Manager LLM Crew",
            "description": "Coordinates through a usable manager LLM",
            "workspace_id": "11111111-1111-1111-1111-111111111111",
            "payload": {
                "process": "hierarchical",
                "manager_llm": manager_llm,
            },
        },
    )

    assert response.status_code == 201
    assert response.json()["current_version"]["payload"]["manager_llm"] == manager_llm


def test_create_crew_asset_serializes_uuid_payload_values(client, db):
    payload = {
        "type": "crew",
        "name": "UUID Crew",
        "description": "Coordinates work",
        "workspace_id": "11111111-1111-1111-1111-111111111111",
        "payload": {
            "process": "sequential",
            "manager_llm": {"provider": "openai", "model": "gpt-4o-mini"},
            "manager_agent_asset_id": "22222222-2222-2222-2222-222222222222",
            "function_calling_llm": {"provider": "openai", "model": "gpt-4o-mini"},
            "verbose": False,
            "planning": True,
            "memory": False,
        },
    }

    response = client.post("/api/assets", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["current_version"]["payload"]["manager_agent_asset_id"] == "22222222-2222-2222-2222-222222222222"

    asset = db.query(Asset).filter(Asset.id == data["id"]).one()
    asset_version = db.query(AssetVersion).filter(AssetVersion.asset_id == asset.id).one()
    assert asset_version.payload_json["manager_agent_asset_id"] == "22222222-2222-2222-2222-222222222222"


def test_create_task_asset_rejects_unknown_payload_field(client):
    payload = {
        "type": "task",
        "name": "Invalid Task",
        "description": "Should fail",
        "workspace_id": "11111111-1111-1111-1111-111111111111",
        "payload": {
            "description": "Collect and summarize facts",
            "expected_output": "A concise summary",
            "async_execution": True,
            "human_input": False,
            "markdown": True,
            "typo_field": "not allowed",
        },
    }

    response = client.post("/api/assets", json=payload)

    assert response.status_code == 422


def test_create_asset_rejects_unknown_top_level_field(client):
    payload = {
        "type": "task",
        "name": "Invalid Asset",
        "description": "Should fail",
        "workspace_id": "11111111-1111-1111-1111-111111111111",
        "payload": {
            "description": "Collect and summarize facts",
            "expected_output": "A concise summary",
        },
        "extra_field": "not allowed",
    }

    response = client.post("/api/assets", json=payload)

    assert response.status_code == 422


def test_create_task_asset_coerces_string_payload_values(client, db):
    payload = {
        "type": "task",
        "name": "Coerced Task",
        "description": "Should normalize strings",
        "workspace_id": "11111111-1111-1111-1111-111111111111",
        "payload": {
            "description": "Collect and summarize facts",
            "expected_output": "A concise summary",
            "async_execution": "true",
            "human_input": "false",
            "markdown": "true",
            "guardrail_max_retries": "3",
        },
    }

    response = client.post("/api/assets", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["current_version"]["payload"]["async_execution"] is True
    assert data["current_version"]["payload"]["human_input"] is False
    assert data["current_version"]["payload"]["markdown"] is True
    assert data["current_version"]["payload"]["guardrail_max_retries"] == 3

    asset = db.query(Asset).filter(Asset.id == data["id"]).one()
    asset_version = db.query(AssetVersion).filter(AssetVersion.asset_id == asset.id).one()
    assert asset_version.payload_json["async_execution"] is True
    assert asset_version.payload_json["human_input"] is False
    assert asset_version.payload_json["markdown"] is True
    assert asset_version.payload_json["guardrail_max_retries"] == 3


def test_get_asset_returns_current_owned_asset(client):
    created = client.post("/api/assets", json=_agent_payload()).json()

    response = client.get(f"/api/assets/{created['id']}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == created["id"]
    assert data["type"] == "agent"
    assert data["current_version"]["id"] == created["current_version"]["id"]
    assert data["current_version"]["version_no"] == 1
    assert data["current_version"]["payload"]["role"] == "Researcher"


def test_get_asset_hides_other_users_asset(client, db):
    other_asset = Asset(
        asset_type="agent",
        workspace_id="11111111-1111-1111-1111-111111111111",
        owner_user_id="other-user",
        name="Hidden Agent",
        description="Should not leak",
    )
    db.add(other_asset)
    db.flush()
    db.add(
        AssetVersion(
            asset_id=other_asset.id,
            version_number=1,
            status="draft",
            created_by="other-user",
            payload_json=_agent_payload()["payload"],
        )
    )
    db.commit()

    response = client.get(f"/api/assets/{other_asset.id}")

    assert response.status_code == 404


def test_patch_asset_creates_new_version(client, db):
    created = client.post("/api/assets", json=_agent_payload()).json()

    response = client.patch(f"/api/assets/{created['id']}", json=_agent_update(created))

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == created["id"]
    assert data["current_version"]["version_no"] == 2
    assert data["current_version"]["payload"]["role"] == "Senior Researcher"
    assert data["current_version"]["payload"]["verbose"] is True

    versions = (
        db.query(AssetVersion)
        .filter(AssetVersion.asset_id == created["id"])
        .order_by(AssetVersion.version_number.asc())
        .all()
    )
    assert [version.version_number for version in versions] == [1, 2]
    assert str(versions[1].base_version_id) == created["current_version"]["id"]
    assert versions[1].metadata_json["change_summary"] == "promote role"


def test_list_asset_versions_returns_latest_first(client):
    created = client.post("/api/assets", json=_agent_payload()).json()
    updated = client.patch(f"/api/assets/{created['id']}", json=_agent_update(created)).json()

    response = client.get(f"/api/assets/{created['id']}/versions")

    assert response.status_code == 200
    data = response.json()
    assert [version["version_no"] for version in data] == [2, 1]
    assert data[0]["id"] == updated["current_version"]["id"]
    assert data[1]["id"] == created["current_version"]["id"]


def test_get_asset_version_returns_requested_snapshot(client):
    created = client.post("/api/assets", json=_agent_payload()).json()
    updated = client.patch(f"/api/assets/{created['id']}", json=_agent_update(created)).json()

    response = client.get(
        f"/api/assets/{created['id']}/versions/{created['current_version']['id']}"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == created["current_version"]["id"]
    assert data["asset_id"] == created["id"]
    assert data["version_no"] == 1
    assert data["payload"]["role"] == "Researcher"
    assert updated["current_version"]["payload"]["role"] == "Senior Researcher"


def test_restore_asset_version_creates_new_latest_version(client):
    created = client.post("/api/assets", json=_agent_payload()).json()
    updated = client.patch(f"/api/assets/{created['id']}", json=_agent_update(created)).json()

    response = client.post(
        f"/api/assets/{created['id']}/versions/{created['current_version']['id']}/restore"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == created["id"]
    assert data["current_version"]["version_no"] == 3
    assert data["current_version"]["payload"]["role"] == "Researcher"
    assert data["restored_from_version_id"] == created["current_version"]["id"]
    assert updated["current_version"]["payload"]["role"] == "Senior Researcher"


def test_restore_asset_version_copies_source_metadata_and_payload(client, db):
    created = client.post("/api/assets", json=_agent_payload()).json()
    updated = client.patch(f"/api/assets/{created['id']}", json=_agent_update(created)).json()
    source_version = db.get(AssetVersion, created["current_version"]["id"])
    source_version.metadata_json = {
        **(source_version.metadata_json or {}),
        "name": "Restored Metadata Name",
        "description": "Restored metadata description",
        "change_summary": "source-summary",
        "custom_marker": "preserve-me",
    }
    db.commit()

    response = client.post(
        f"/api/assets/{created['id']}/versions/{created['current_version']['id']}/restore"
    )

    assert response.status_code == 200
    restored_version = db.get(AssetVersion, response.json()["current_version"]["id"])
    assert restored_version.payload_json == source_version.payload_json
    assert restored_version.metadata_json["name"] == "Restored Metadata Name"
    assert restored_version.metadata_json["description"] == "Restored metadata description"
    assert restored_version.metadata_json["change_summary"] == "source-summary"
    assert restored_version.metadata_json["custom_marker"] == "preserve-me"
    assert updated["current_version"]["payload"]["role"] == "Senior Researcher"


def test_restore_task_asset_recreates_binding_set_for_restored_version(client, db):
    created = client.post(
        "/api/assets",
        json={
            "type": "task",
            "name": "SEO Brief",
            "description": "Search intent analysis",
            "payload": {
                "description": "Search intent analysis",
                "expected_output": "SEO brief",
                "input_presets": ["website_url", "keyword"],
            },
        },
    ).json()
    updated = client.patch(
        f"/api/assets/{created['id']}",
        json={
            "base_version_id": created["current_version"]["id"],
            "payload": {
                "description": "Competitor-aware SEO brief",
                "expected_output": "Expanded SEO brief",
                "input_presets": ["website_url", "brand_name"],
            },
        },
    ).json()

    restored = client.post(
        f"/api/assets/{created['id']}/versions/{created['current_version']['id']}/restore"
    )

    assert restored.status_code == 200
    assert restored.json()["current_version"]["payload"]["input_presets"] == ["website_url", "keyword"]

    restored_bindings = (
        db.query(models.TaskInputPresetBinding)
        .filter(models.TaskInputPresetBinding.asset_version_id == restored.json()["current_version"]["id"])
        .order_by(models.TaskInputPresetBinding.sort_order.asc())
        .all()
    )

    assert updated["current_version"]["payload"]["input_presets"] == ["website_url", "brand_name"]
    assert [row.preset_definition.key for row in restored_bindings] == ["website_url", "keyword"]


def test_task_read_paths_ignore_stale_asset_version_input_presets(client, db):
    created = client.post(
        "/api/assets",
        json={
            "type": "task",
            "name": "SEO Brief",
            "description": "Search intent analysis",
            "payload": {
                "description": "Search intent analysis",
                "expected_output": "SEO brief",
                "input_presets": ["website_url", "keyword"],
            },
        },
    ).json()

    version = db.query(AssetVersion).filter(AssetVersion.id == created["current_version"]["id"]).one()
    version.payload_json = {
        **version.payload_json,
        "input_presets": ["brand_name"],
    }
    db.commit()

    current = client.get(f"/api/assets/{created['id']}")
    listed = client.get("/api/assets", params={"type": "task"})
    versions = client.get(f"/api/assets/{created['id']}/versions")
    single_version = client.get(
        f"/api/assets/{created['id']}/versions/{created['current_version']['id']}"
    )
    restored = client.post(
        f"/api/assets/{created['id']}/versions/{created['current_version']['id']}/restore"
    )

    assert current.json()["current_version"]["payload"]["input_presets"] == ["brand_name"]
    assert listed.json()[0]["current_version"]["payload"]["input_presets"] == ["brand_name"]
    assert versions.json()[0]["payload"]["input_presets"] == ["brand_name"]
    assert single_version.json()["payload"]["input_presets"] == ["brand_name"]
    assert restored.json()["current_version"]["payload"]["input_presets"] == ["brand_name"]


def test_task_read_paths_use_asset_version_payload_when_version_type_metadata_missing(client, db):
    created = client.post(
        "/api/assets",
        json={
            "type": "task",
            "name": "SEO Brief",
            "description": "Search intent analysis",
            "payload": {
                "description": "Search intent analysis",
                "expected_output": "SEO brief",
                "input_presets": ["website_url", "keyword"],
            },
        },
    ).json()

    version = db.query(AssetVersion).filter(AssetVersion.id == created["current_version"]["id"]).one()
    version.payload_json = {
        **version.payload_json,
        "input_presets": ["brand_name"],
    }
    version.metadata_json.pop("type", None)
    db.commit()

    versions = client.get(f"/api/assets/{created['id']}/versions")
    single_version = client.get(
        f"/api/assets/{created['id']}/versions/{created['current_version']['id']}"
    )

    assert versions.json()[0]["payload"]["input_presets"] == ["brand_name"]
    assert single_version.json()["payload"]["input_presets"] == ["brand_name"]


def test_task_read_paths_use_asset_version_payload_without_typed_rows(client, db):
    created = client.post(
        "/api/assets",
        json={
            "type": "task",
            "name": "SEO Brief",
            "description": "Search intent analysis",
            "payload": {
                "description": "Search intent analysis",
                "expected_output": "SEO brief",
                "input_presets": ["website_url", "keyword"],
            },
        },
    ).json()

    current = client.get(f"/api/assets/{created['id']}")
    listed = client.get("/api/assets", params={"type": "task"})
    versions = client.get(f"/api/assets/{created['id']}/versions")
    single_version = client.get(
        f"/api/assets/{created['id']}/versions/{created['current_version']['id']}"
    )
    restored = client.post(
        f"/api/assets/{created['id']}/versions/{created['current_version']['id']}/restore"
    )

    expected_payload = {
        "description": "Search intent analysis",
        "expected_output": "SEO brief",
        "input_presets": ["website_url", "keyword"],
    }
    assert current.json()["current_version"]["payload"] == expected_payload
    assert listed.json()[0]["current_version"]["payload"] == expected_payload
    assert versions.json()[0]["payload"] == expected_payload
    assert single_version.json()["payload"] == expected_payload
    assert restored.json()["current_version"]["payload"]["input_presets"] == ["website_url", "keyword"]


def test_restore_asset_version_reapplies_versioned_name_and_description(client, db):
    created = client.post(
        "/api/assets",
        json={
            "type": "task",
            "name": "SEO Brief",
            "description": "Search intent analysis",
            "payload": {
                "description": "Search intent analysis",
                "expected_output": "SEO brief",
                "input_presets": ["website_url"],
            },
        },
    ).json()
    updated = client.patch(
        f"/api/assets/{created['id']}",
        json={
            "base_version_id": created["current_version"]["id"],
            "name": "SEO Brief v2",
            "description": "Competitor analysis",
            "payload": {
                "description": "Competitor-aware SEO brief",
                "expected_output": "Expanded SEO brief",
                "input_presets": ["brand_name"],
            },
        },
    ).json()

    restored = client.post(
        f"/api/assets/{created['id']}/versions/{created['current_version']['id']}/restore"
    )

    assert restored.status_code == 200
    assert updated["name"] == "SEO Brief v2"
    assert updated["description"] == "Competitor analysis"
    assert restored.json()["name"] == "SEO Brief"
    assert restored.json()["description"] == "Search intent analysis"

    asset = db.query(Asset).filter(Asset.id == created["id"]).one()
    restored_version = db.query(AssetVersion).filter(AssetVersion.id == restored.json()["current_version"]["id"]).one()

    assert asset.name == "SEO Brief"
    assert asset.description == "Search intent analysis"
    assert restored_version.metadata_json["name"] == "SEO Brief"
    assert restored_version.metadata_json["description"] == "Search intent analysis"


def test_restore_task_asset_invalid_preset_keys_do_not_persist_partial_rows():
    SessionLocal, engine, tempdir = _isolated_session_factory()
    setup = SessionLocal()
    try:
        created = create_asset(
            setup,
            AssetCreate.model_validate(
                {
                    "type": "task",
                    "name": "SEO Brief",
                    "description": "Search intent analysis",
                    "payload": {
                        "description": "Search intent analysis",
                        "expected_output": "SEO brief",
                        "input_presets": ["website_url", "keyword"],
                    },
                }
            ),
            owner_user_id="test-user",
        )
        created_asset_id = str(created["asset"].id)
        source_version_id = str(created["asset_version"].id)

        updated = update_asset(
            setup,
            created_asset_id,
            AssetUpdate.model_validate(
                {
                    "base_version_id": source_version_id,
                    "payload": {
                        "description": "Competitor-aware SEO brief",
                        "expected_output": "Expanded SEO brief",
                        "input_presets": ["brand_name"],
                    },
                }
            ),
            owner_user_id="test-user",
        )
        latest_version_id = str(updated.current_version.id)
    finally:
        setup.close()

    deactivator = SessionLocal()
    try:
        keyword = (
            deactivator.query(models.InputPresetDefinition)
            .filter(models.InputPresetDefinition.key == "keyword")
            .one()
        )
        keyword.is_active = False
        deactivator.commit()
    finally:
        deactivator.close()

    writer = SessionLocal()
    try:
        with pytest.raises(ValueError, match="Unknown or inactive task input preset keys: keyword"):
            restore_asset_version_service(
                writer,
                created_asset_id,
                source_version_id,
                owner_user_id="test-user",
            )
    finally:
        writer.close()

    reader = SessionLocal()
    try:
        asset = reader.query(Asset).filter(Asset.id == created_asset_id).one()
        versions = (
            reader.query(AssetVersion)
            .filter(AssetVersion.asset_id == created_asset_id)
            .order_by(AssetVersion.version_number.asc())
            .all()
        )
        latest_bindings = (
            reader.query(models.TaskInputPresetBinding)
            .filter(models.TaskInputPresetBinding.asset_version_id == latest_version_id)
            .order_by(models.TaskInputPresetBinding.sort_order.asc())
            .all()
        )
        latest_binding_keys = [binding.preset_definition.key for binding in latest_bindings]
    finally:
        reader.close()

    assert asset.name == "SEO Brief"
    assert asset.description == "Search intent analysis"
    assert [version.version_number for version in versions] == [1, 2]
    assert latest_binding_keys == ["brand_name"]
    engine.dispose()
    tempdir.cleanup()


def test_delete_asset_version_rejects_last_remaining_version(client):
    created = client.post("/api/assets", json=_agent_payload()).json()

    response = client.delete(
        f"/api/assets/{created['id']}/versions/{created['current_version']['id']}"
    )

    assert response.status_code == 409


def test_delete_asset_version_rejects_referenced_version(client, db):
    task_response = client.post(
        "/api/assets",
        json={
            "type": "task",
            "name": "Research Task",
            "description": "Collect facts",
            "payload": {
                "description": "Collect facts",
                "expected_output": "A concise summary",
            },
        },
    )
    agent_response = client.post("/api/assets", json=_agent_payload())
    task_created = task_response.json()
    agent_created = agent_response.json()
    db.add(
        VersionLink(
            source_version_id=task_created["current_version"]["id"],
            target_version_id=agent_created["current_version"]["id"],
            link_type="task.agent",
        )
    )
    db.commit()

    response = client.delete(
        f"/api/assets/{agent_created['id']}/versions/{agent_created['current_version']['id']}"
    )

    assert response.status_code == 409


def test_delete_asset_version_rejects_current_latest_version(client, db):
    created = client.post("/api/assets", json=_agent_payload()).json()
    updated = client.patch(f"/api/assets/{created['id']}", json=_agent_update(created)).json()

    response = client.delete(
        f"/api/assets/{created['id']}/versions/{updated['current_version']['id']}"
    )

    assert response.status_code == 409

    versions = (
        db.query(AssetVersion)
        .filter(AssetVersion.asset_id == created["id"])
        .order_by(AssetVersion.version_number.asc())
        .all()
    )
    assert [version.version_number for version in versions] == [1, 2]


def test_delete_asset_version_removes_unreferenced_historical_version(client, db):
    created = client.post("/api/assets", json=_agent_payload()).json()
    updated = client.patch(f"/api/assets/{created['id']}", json=_agent_update(created)).json()
    restored = client.post(
        f"/api/assets/{created['id']}/versions/{created['current_version']['id']}/restore"
    ).json()

    response = client.delete(
        f"/api/assets/{created['id']}/versions/{updated['current_version']['id']}"
    )

    assert response.status_code == 204
    assert restored["current_version"]["version_no"] == 3

    versions = (
        db.query(AssetVersion)
        .filter(AssetVersion.asset_id == created["id"])
        .order_by(AssetVersion.version_number.asc())
        .all()
    )
    assert [version.version_number for version in versions] == [1, 3]
    assert [version.id for version in versions] == [
        created["current_version"]["id"],
        restored["current_version"]["id"],
    ]


def test_delete_asset_removes_owned_asset_and_all_versions(client, db):
    created = client.post(
        "/api/assets",
        json={
            "type": "task",
            "name": "SEO Brief",
            "description": "Search intent analysis",
            "payload": {
                "description": "Collect search intent",
                "expected_output": "Ranked intent buckets",
                "input_presets": ["website_url", "keyword"],
            },
        },
    ).json()
    updated = client.patch(
        f"/api/assets/{created['id']}",
        json={
            "base_version_id": created["current_version"]["id"],
            "name": "SEO Brief v2",
            "description": "Updated search intent analysis",
            "payload": {
                "description": "Collect and cluster search intent",
                "expected_output": "Clustered intent buckets",
                "input_presets": ["brand_name"],
            },
        },
    ).json()

    response = client.delete(f"/api/assets/{created['id']}")

    assert response.status_code == 204
    assert db.query(Asset).filter(Asset.id == created["id"]).count() == 0
    assert db.query(AssetVersion).filter(AssetVersion.asset_id == created["id"]).count() == 0
    assert (
        db.query(TaskInputPresetBinding)
        .filter(
            TaskInputPresetBinding.asset_version_id.in_(
                [created["current_version"]["id"], updated["current_version"]["id"]]
            )
        )
        .count()
        == 0
    )


def test_delete_asset_returns_404_for_other_users_asset(client, db):
    other_asset = Asset(
        asset_type="agent",
        workspace_id="11111111-1111-1111-1111-111111111111",
        owner_user_id="other-user",
        name="Other Agent",
        description="Hidden asset",
    )
    other_version = AssetVersion(
        asset=other_asset,
        version_number=1,
        status="draft",
        created_by="other-user",
        metadata_json={
            "type": "agent",
            "name": "Other Agent",
            "description": "Hidden asset",
            "workspace_id": "11111111-1111-1111-1111-111111111111",
        },
        payload_json={
            "role": "Researcher",
            "goal": "Find facts",
            "backstory": "Careful analyst",
        },
    )
    db.add_all(
        [
            other_asset,
            other_version,
        ]
    )
    db.commit()

    response = client.delete(f"/api/assets/{other_asset.id}")

    assert response.status_code == 404
    assert db.query(Asset).filter(Asset.id == other_asset.id).count() == 1


def test_delete_asset_returns_503_when_database_schema_is_unavailable(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    def override_get_current_user():
        return {"id": "test-user", "email": "test@example.com"}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    @asynccontextmanager
    async def _test_lifespan(_app):
        yield

    try:
        with patch.object(app.router, "lifespan_context", _test_lifespan):
            with patch(
                "api.routes.assets.delete_asset_service",
                side_effect=ProgrammingError("SELECT 1", {}, Exception('relation "asset_shares" does not exist')),
            ):
                with TestClient(app, raise_server_exceptions=False) as client:
                    response = client.delete("/api/assets/11111111-1111-1111-1111-111111111111")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "시스템 점검 중입니다. 잠시 후 다시 시도해주세요."}


def test_delete_asset_returns_422_for_invalid_database_request(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    def override_get_current_user():
        return {"id": "test-user", "email": "test@example.com"}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    @asynccontextmanager
    async def _test_lifespan(_app):
        yield

    try:
        with patch.object(app.router, "lifespan_context", _test_lifespan):
            with patch(
                "api.routes.assets.delete_asset_service",
                side_effect=DataError("SELECT 1", {}, Exception("invalid input syntax for type uuid")),
            ):
                with TestClient(app, raise_server_exceptions=False) as client:
                    response = client.delete("/api/assets/not-a-uuid")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json() == {"detail": "유효하지 않은 요청입니다."}


def test_delete_asset_version_rejects_version_referenced_by_newer_lineage(client):
    created = client.post("/api/assets", json=_agent_payload()).json()
    updated = client.patch(f"/api/assets/{created['id']}", json=_agent_update(created)).json()
    restored = client.post(
        f"/api/assets/{created['id']}/versions/{created['current_version']['id']}/restore"
    ).json()

    response = client.delete(
        f"/api/assets/{created['id']}/versions/{created['current_version']['id']}"
    )

    assert updated["current_version"]["version_no"] == 2
    assert restored["current_version"]["version_no"] == 3
    assert response.status_code == 409


def test_asset_updated_at_bumps_when_new_version_is_created(client, db):
    created = client.post("/api/assets", json=_agent_payload()).json()
    asset = db.query(Asset).filter(Asset.id == created["id"]).one()
    created_updated_at = asset.updated_at

    time.sleep(0.01)
    updated = client.patch(f"/api/assets/{created['id']}", json=_agent_update(created)).json()
    db.refresh(asset)
    patched_updated_at = asset.updated_at

    time.sleep(0.01)
    restored = client.post(
        f"/api/assets/{created['id']}/versions/{created['current_version']['id']}/restore"
    ).json()
    db.refresh(asset)
    restored_updated_at = asset.updated_at

    assert updated["current_version"]["version_no"] == 2
    assert restored["current_version"]["version_no"] == 3
    assert patched_updated_at > created_updated_at
    assert restored_updated_at > patched_updated_at


def test_list_assets_only_returns_current_users_assets(client, db):
    payload = {
        "type": "agent",
        "name": "Owned Agent",
        "description": "Visible to current user",
        "initial_payload": {
            "role": "Researcher",
            "goal": "Find facts",
            "backstory": "Careful analyst",
            "llm": {"provider": "openai", "model": "gpt-4o-mini"},
            "verbose": False,
        },
    }

    create_response = client.post("/api/assets", json=payload)
    assert create_response.status_code == 201
    owned_id = create_response.json()["id"]

    other_asset = Asset(
        asset_type="agent",
        workspace_id="11111111-1111-1111-1111-111111111111",
        owner_user_id="other-user",
        name="Hidden Agent",
        description="Should not leak",
    )
    db.add(other_asset)
    db.flush()
    db.add(
        AssetVersion(
            asset_id=other_asset.id,
            version_number=1,
            status="draft",
            created_by="other-user",
            payload_json=payload["initial_payload"],
        )
    )
    db.flush()
    db.commit()

    list_response = client.get("/api/assets")

    assert list_response.status_code == 200
    data = list_response.json()
    assert len(data) == 1
    assert data[0]["id"] == owned_id
    assert data[0]["name"] == "Owned Agent"


def test_list_assets_returns_persisted_agent_assets(client, db):
    payload = {
        "type": "agent",
        "name": "Listed Agent",
        "description": "Visible from collection list",
        "workspace_id": "11111111-1111-1111-1111-111111111111",
        "initial_payload": {
            "role": "Researcher",
            "goal": "Find facts",
            "backstory": "Careful analyst",
            "llm": {"provider": "openai", "main_model": "gpt-4o-mini"},
            "verbose": False,
        },
    }

    create_response = client.post("/api/assets", json=payload)
    assert create_response.status_code == 201

    list_response = client.get("/api/assets")
    assert list_response.status_code == 200

    data = list_response.json()
    assert len(data) == 1
    asset = data[0]
    assert asset["type"] == "agent"
    assert asset["name"] == "Listed Agent"
    assert asset["description"] == payload["description"]
    assert asset["workspace_id"] == payload["workspace_id"]
    assert asset["current_version"]["version_no"] == 1
    assert asset["current_version"]["status"] == "draft"
    assert asset["current_version"]["payload"] == payload["initial_payload"]


def test_agent_asset_payload_round_trips_crewai_runtime_attributes(client, auth_headers):
    response = client.post(
        "/api/assets",
        json={
            "type": "agent",
            "name": "Runtime Agent",
            "description": "Agent with CrewAI settings",
            "payload": {
                "role": "Researcher",
                "goal": "Find reliable details",
                "backstory": "A careful analyst.",
                "llm": {"provider": "openai", "model": "gpt-4o-mini"},
                "function_calling_llm": {"provider": "openai", "model": "gpt-4o-mini-tools"},
                "max_iter": 7,
                "max_rpm": 12,
                "max_execution_time": 90,
                "verbose": True,
                "allow_delegation": True,
                "reasoning": True,
                "max_reasoning_attempts": 3,
                "system_template": "System: {role}",
                "prompt_template": "Prompt: {input}",
                "response_template": "Response: {output}",
                "cache": False,
                "respect_context_window": True,
                "max_retry_limit": 4,
                "inject_date": True,
                "date_format": "%Y-%m-%d",
            },
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    payload = response.json()["current_version"]["payload"]
    assert payload["function_calling_llm"] == {"provider": "openai", "model": "gpt-4o-mini-tools"}
    assert payload["max_iter"] == 7
    assert payload["max_rpm"] == 12
    assert payload["max_execution_time"] == 90
    assert payload["verbose"] is True
    assert payload["allow_delegation"] is True
    assert payload["reasoning"] is True
    assert payload["max_reasoning_attempts"] == 3
    assert payload["system_template"] == "System: {role}"
    assert payload["prompt_template"] == "Prompt: {input}"
    assert payload["response_template"] == "Response: {output}"
    assert payload["cache"] is False
    assert payload["respect_context_window"] is True
    assert payload["max_retry_limit"] == 4
    assert payload["inject_date"] is True
    assert payload["date_format"] == "%Y-%m-%d"


def test_task_asset_payload_round_trips_structured_output_fields(client, auth_headers):
    response = client.post(
        "/api/assets",
        json={
            "type": "task",
            "name": "Runtime Task",
            "description": "Task with config",
            "payload": {
                "description": "Write a compact result.",
                "expected_output": "A compact result.",
                "async_execution": False,
                "human_input": True,
                "markdown": True,
                "guardrail_max_retries": 2,
                "output_file": "reports/result.md",
                "create_directory": False,
                "output_type": "Output JSON",
                "output_schema_fields": [{"name": "answer", "type": "str", "required": True}],
            },
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    payload = response.json()["current_version"]["payload"]
    assert payload["human_input"] is True
    assert payload["markdown"] is True
    assert payload["create_directory"] is False
    assert payload["output_type"] == "Output JSON"
    assert payload["output_schema_fields"] == [{"name": "answer", "type": "str", "required": True}]


def test_crew_asset_payload_round_trips_top_level_runtime_fields(client, auth_headers):
    response = client.post(
        "/api/assets",
        json={
            "type": "crew",
            "name": "Runtime Crew",
            "description": "Crew with runtime settings",
            "payload": {
                "process": "sequential",
                "manager_llm": {"provider": "openai", "model": "gpt-4o"},
                "function_calling_llm": {"provider": "openai", "model": "gpt-4o-mini-tools"},
                "verbose": True,
                "planning": True,
                "memory": True,
                "cache": False,
                "max_rpm": 20,
                "stream": False,
                "tracing": True,
                "checkpoint": True,
            },
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    payload = response.json()["current_version"]["payload"]
    assert payload["function_calling_llm"] == {"provider": "openai", "model": "gpt-4o-mini-tools"}
    assert payload["verbose"] is True
    assert payload["planning"] is True
    assert payload["memory"] is True
    assert payload["cache"] is False
    assert payload["max_rpm"] == 20
    assert payload["stream"] is False
    assert payload["tracing"] is True
    assert payload["checkpoint"] is True
