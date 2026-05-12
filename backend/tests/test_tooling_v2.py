from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import UniqueConstraint
from sqlalchemy.exc import IntegrityError

from crewai.tools import BaseTool

from api.db import models
from api.schemas.capabilities import (
    VersionSkillAttachmentReadResponse,
    VersionSkillAttachmentResponse,
    VersionToolAttachmentReadResponse,
    VersionToolAttachmentResponse,
)


class EchoToolForCatalogTest(BaseTool):
    name: str = "echo"
    description: str = "Echo for catalog tests."

    def _run(self, value: str = "") -> str:
        return value


@pytest.fixture
def seeded_agent_version_id(db) -> str:
    asset = models.Asset(asset_type="agent", name="agent-asset")
    version = models.AssetVersion(asset=asset, version_number=1, status="draft", metadata_json={})
    db.add_all([asset, version])
    db.commit()
    return version.id


@pytest.fixture
def seeded_tool_catalog_entry(monkeypatch):
    monkeypatch.setattr(
        "api.services.tooling.list_tool_catalog_entries",
        lambda db: [
            {
                "id": "tool.search_web",
                "tool_key": "tool.search_web",
                "name": "Search Web",
                "description": "Search the public web",
                "tool_type": "python_class",
                "module_path": "api.tools.search_web",
                "class_name": "SearchWebTool",
                "default_config_json": {"timeout_seconds": 30},
                "enabled": True,
                "created_at": "2026-04-22T00:00:00Z",
                "updated_at": "2026-04-22T00:00:00Z",
            }
        ],
    )


@pytest.fixture
def second_agent_version_id(db) -> str:
    asset = models.Asset(asset_type="agent", name="agent-asset-2")
    version = models.AssetVersion(asset=asset, version_number=1, status="draft", metadata_json={})
    db.add_all([asset, version])
    db.commit()
    return version.id


def test_catalog_endpoints_remain_compatibility_only(client):
    tool_catalog = client.get("/api/tool-catalog")
    skill_catalog = client.get("/api/skill-catalog")
    skill_create = client.post(
        "/api/skill-catalog",
        json={
            "skill_key": "summarize",
            "name": "Summarize",
            "description": "Summarization skill",
            "skill_source": "/tmp/summarize.md",
        },
    )

    assert tool_catalog.status_code == 200
    assert tool_catalog.json()[0]["tool_key"] == "crewai.directory_read"
    assert skill_catalog.status_code == 200
    assert skill_catalog.json() == []
    assert skill_create.status_code == 501
    assert skill_create.json()["detail"] == "Skill catalog creation is not available under the current schema."


def test_tool_catalog_includes_ten_supported_crewai_default_tools(db):
    from api.services.tooling import list_tool_catalog_entries

    entries = list_tool_catalog_entries(db)
    by_key = {entry["tool_key"]: entry for entry in entries}

    assert list(by_key)[:10] == [
        "crewai.directory_read",
        "crewai.file_read",
        "crewai.csv_search",
        "crewai.json_search",
        "crewai.pdf_search",
        "crewai.website_search",
        "crewai.scrape_website",
        "crewai.serper_dev",
        "crewai.github_search",
        "crewai.dalle",
    ]
    assert by_key["crewai.directory_read"]["module_path"] == "crewai_tools"
    assert by_key["crewai.directory_read"]["class_name"] == "DirectoryReadTool"
    assert by_key["crewai.dalle"]["module_path"] == "crewai_tools"
    assert by_key["crewai.dalle"]["class_name"] == "DallETool"
    assert all(entry["enabled"] is True for entry in by_key.values())


def test_tool_catalog_create_persists_custom_tool(client):
    response = client.post(
        "/api/tool-catalog",
        json={
            "tool_key": "custom.local_echo",
            "name": "Local Echo",
            "description": "Echo test input.",
            "tool_type": "python_class",
            "module_path": "tests.test_tooling_v2",
            "class_name": "EchoToolForCatalogTest",
            "default_config_json": {"prefix": "AX"},
        },
    )

    assert response.status_code == 201
    assert response.json()["tool_key"] == "custom.local_echo"

    catalog = client.get("/api/tool-catalog")
    assert catalog.status_code == 200
    assert "custom.local_echo" in {item["tool_key"] for item in catalog.json()}

    detail = client.get("/api/tool-catalog/custom.local_echo")
    assert detail.status_code == 200
    assert detail.json()["default_config_json"] == {"prefix": "AX"}


def test_tool_catalog_create_rejects_non_allowlisted_module(client):
    response = client.post(
        "/api/tool-catalog",
        json={
            "tool_key": "custom.os_tool",
            "name": "OS Tool",
            "description": "Should not be importable from arbitrary modules.",
            "tool_type": "python_class",
            "module_path": "os",
            "class_name": "PathLike",
            "default_config_json": {},
        },
    )

    assert response.status_code == 422
    assert "Tool module is not allowlisted" in response.json()["detail"]


def test_serper_default_tool_exposes_config_input_and_env_metadata(db):
    from api.services.tooling import list_tool_catalog_entries

    by_key = {entry["tool_key"]: entry for entry in list_tool_catalog_entries(db)}
    serper = by_key["crewai.serper_dev"]

    assert serper["config_schema_json"]["type"] == "object"
    assert serper["config_schema_json"]["properties"]["n_results"]["type"] == "integer"
    assert serper["config_schema_json"]["properties"]["search_type"]["enum"] == ["search", "news"]
    assert "search_query" in serper["input_schema_json"]["properties"]
    assert serper["input_schema_json"]["properties"]["search_query"]["type"] == "string"
    assert serper["required_env_vars"] == [
        {"name": "SERPER_API_KEY", "description": "API key for Serper", "required": True}
    ]
    assert serper["ui_schema_json"]["fields"]["search_type"]["widget"] == "select"


def test_default_tool_metadata_responses_do_not_share_nested_state(db):
    from api.services.tooling import list_tool_catalog_entries

    first_by_key = {entry["tool_key"]: entry for entry in list_tool_catalog_entries(db)}
    first_serper = first_by_key["crewai.serper_dev"]
    first_serper["config_schema_json"]["properties"]["n_results"]["type"] = "mutated"
    first_serper["input_schema_json"]["properties"]["search_query"]["type"] = "mutated"
    first_serper["ui_schema_json"]["fields"]["search_type"]["widget"] = "mutated"
    first_serper["required_env_vars"][0]["name"] = "MUTATED_API_KEY"

    second_by_key = {entry["tool_key"]: entry for entry in list_tool_catalog_entries(db)}
    second_serper = second_by_key["crewai.serper_dev"]

    assert second_serper["config_schema_json"]["properties"]["n_results"]["type"] == "integer"
    assert second_serper["input_schema_json"]["properties"]["search_query"]["type"] == "string"
    assert second_serper["ui_schema_json"]["fields"]["search_type"]["widget"] == "select"
    assert second_serper["required_env_vars"][0]["name"] == "SERPER_API_KEY"


def test_tool_catalog_create_persists_custom_tool_metadata(client):
    response = client.post(
        "/api/tool-catalog",
        json={
            "tool_key": "custom.echo_with_metadata",
            "name": "Echo With Metadata",
            "description": "Echo test input with schema metadata.",
            "tool_type": "python_class",
            "module_path": "tests.test_tooling_v2",
            "class_name": "EchoToolForCatalogTest",
            "default_config_json": {"prefix": "AX"},
            "config_schema_json": {
                "type": "object",
                "properties": {"prefix": {"type": "string"}},
                "additionalProperties": False,
            },
            "input_schema_json": {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
            },
            "ui_schema_json": {"fields": {"prefix": {"label": "Prefix"}}},
            "required_env_vars": [
                {"name": "ECHO_API_KEY", "description": "Echo API key", "required": False}
            ],
        },
    )

    assert response.status_code == 201
    assert response.json()["config_schema_json"]["properties"]["prefix"]["type"] == "string"
    assert response.json()["input_schema_json"]["required"] == ["value"]
    assert response.json()["ui_schema_json"]["fields"]["prefix"]["label"] == "Prefix"
    assert response.json()["required_env_vars"] == [
        {"name": "ECHO_API_KEY", "description": "Echo API key", "required": False}
    ]

    detail = client.get("/api/tool-catalog/custom.echo_with_metadata")
    assert detail.status_code == 200
    assert detail.json()["config_schema_json"]["properties"]["prefix"]["type"] == "string"
    assert detail.json()["required_env_vars"][0]["name"] == "ECHO_API_KEY"


def test_tool_catalog_create_persists_custom_tool_credential_requirements(client):
    response = client.post(
        "/api/tool-catalog",
        json={
            "tool_key": "custom.echo_with_credentials",
            "name": "Echo With Credentials",
            "description": "Echo test input with credential metadata.",
            "tool_type": "python_class",
            "module_path": "tests.test_tooling_v2",
            "class_name": "EchoToolForCatalogTest",
            "default_config_json": {},
            "credential_requirements": [
                {
                    "provider": " openai ",
                    "env_var": " OPENAI_API_KEY ",
                }
            ],
        },
    )

    assert response.status_code == 201
    assert response.json()["credential_requirements"] == [
        {"provider": "openai", "env_var": "OPENAI_API_KEY", "required": True, "injection": "env"}
    ]

    detail = client.get("/api/tool-catalog/custom.echo_with_credentials")
    assert detail.status_code == 200
    assert detail.json()["credential_requirements"] == [
        {"provider": "openai", "env_var": "OPENAI_API_KEY", "required": True, "injection": "env"}
    ]


@pytest.mark.parametrize(
    "credential_requirements",
    [
        [{"provider": "unknown", "env_var": "UNKNOWN_API_KEY", "required": True, "injection": "env"}],
        [{"provider": "openai", "env_var": "SERPER_API_KEY", "required": True, "injection": "env"}],
        [{"provider": "openai", "env_var": "OPENAI_API_KEY", "required": True, "injection": "header"}],
    ],
)
def test_tool_catalog_create_rejects_malformed_credential_requirements(client, credential_requirements):
    response = client.post(
        "/api/tool-catalog",
        json={
            "tool_key": "custom.echo_bad_credentials",
            "name": "Echo Bad Credentials",
            "description": "Echo test input with invalid credential metadata.",
            "tool_type": "python_class",
            "module_path": "tests.test_tooling_v2",
            "class_name": "EchoToolForCatalogTest",
            "default_config_json": {},
            "credential_requirements": credential_requirements,
        },
    )

    assert response.status_code == 422


def test_tool_catalog_create_duplicate_custom_key_returns_409(client):
    payload = {
        "tool_key": "custom.local_echo",
        "name": "Local Echo",
        "description": "Echo test input.",
        "tool_type": "python_class",
        "module_path": "tests.test_tooling_v2",
        "class_name": "EchoToolForCatalogTest",
        "default_config_json": {"prefix": "AX"},
    }

    first_response = client.post("/api/tool-catalog", json=payload)
    duplicate_response = client.post("/api/tool-catalog", json=payload)

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409


def test_tool_catalog_create_rejects_builtin_tool_key_overwrite(client):
    response = client.post(
        "/api/tool-catalog",
        json={
            "tool_key": "crewai.directory_read",
            "name": "Directory Override",
            "description": "Should not replace built-in.",
            "tool_type": "python_class",
            "module_path": "tests.test_tooling_v2",
            "class_name": "EchoToolForCatalogTest",
            "default_config_json": {},
        },
    )

    assert response.status_code == 409


@pytest.mark.parametrize(
    ("tool_key", "module_path", "class_name"),
    [
        ("custom.missing_module", "tests.missing_tooling_module", "EchoToolForCatalogTest"),
        ("custom.missing_class", "tests.test_tooling_v2", "MissingCatalogTool"),
    ],
)
def test_tool_catalog_create_invalid_module_or_class_returns_422(client, tool_key, module_path, class_name):
    response = client.post(
        "/api/tool-catalog",
        json={
            "tool_key": tool_key,
            "name": "Invalid Tool",
            "description": "Invalid catalog entry.",
            "tool_type": "python_class",
            "module_path": module_path,
            "class_name": class_name,
            "default_config_json": {},
        },
    )

    assert response.status_code == 422


def test_tool_catalog_list_preserves_builtin_when_registry_contains_same_key(db):
    from api.services.tooling import list_tool_catalog_entries

    db.add(
        models.ToolCatalog(
            id="crewai.directory_read",
            name="Bad Override",
            description="Inserted outside the API.",
            entrypoint="tests.test_tooling_v2:EchoToolForCatalogTest",
            schema_json={"tool_type": "python_class", "default_config_json": {"prefix": "bad"}},
            enabled=True,
        )
    )
    db.commit()

    by_key = {entry["tool_key"]: entry for entry in list_tool_catalog_entries(db)}

    assert by_key["crewai.directory_read"]["name"] != "Bad Override"
    assert by_key["crewai.directory_read"]["module_path"] == "crewai_tools"
    assert by_key["crewai.directory_read"]["class_name"] == "DirectoryReadTool"


def test_default_crewai_tool_classes_resolve_from_pinned_dependency(db):
    from api.runtime.tool_loader import load_tool_class
    from api.services.tooling import list_tool_catalog_entries

    for entry in list_tool_catalog_entries(db):
        if entry["tool_key"].startswith("crewai."):
            load_tool_class(entry["module_path"], entry["class_name"])


def test_split_entrypoint_rejects_extra_colon_segments():
    from api.services.tooling import _split_entrypoint

    for invalid_entrypoint in (
        "crewai_tools:DirectoryReadTool:Extra",
        ":DirectoryReadTool",
        "crewai_tools:",
    ):
        with pytest.raises(ValueError, match="module:Class"):
            _split_entrypoint(invalid_entrypoint)


def test_default_crewai_tool_response_copies_default_config():
    from api.services.default_crewai_tools import DefaultCrewAITool

    tool = DefaultCrewAITool(
        tool_key="crewai.example",
        name="Example",
        description="Example tool.",
        class_name="ExampleTool",
        default_config_json={"nested": {"value": 1}},
    )

    response = tool.to_response()
    response["default_config_json"]["changed"] = True

    assert tool.default_config_json == {"nested": {"value": 1}}


def test_default_tool_catalog_exposes_provider_credential_requirements(db):
    from api.services.tooling import list_tool_catalog_entries

    by_key = {entry["tool_key"]: entry for entry in list_tool_catalog_entries(db)}

    assert by_key["crewai.serper_dev"]["credential_requirements"] == [
        {"provider": "serper", "env_var": "SERPER_API_KEY", "required": True, "injection": "env"}
    ]
    assert by_key["crewai.dalle"]["credential_requirements"] == [
        {"provider": "openai", "env_var": "OPENAI_API_KEY", "required": True, "injection": "env"}
    ]
    assert by_key["crewai.vision"]["credential_requirements"] == [
        {"provider": "openai", "env_var": "OPENAI_API_KEY", "required": True, "injection": "env"}
    ]
    assert by_key["crewai.firecrawl_scrape_website"]["credential_requirements"] == [
        {"provider": "firecrawl", "env_var": "FIRECRAWL_API_KEY", "required": True, "injection": "env"}
    ]
    assert by_key["ax.google_sheets"]["credential_requirements"] == [
        {
            "provider": "google_workspace",
            "env_var": "AX_GOOGLE_WORKSPACE_OAUTH",
            "required": True,
            "injection": "runtime_context",
        }
    ]
    assert by_key["ax.instagram_publish_tool"]["credential_requirements"] == [
        {
            "provider": "meta_instagram",
            "env_var": "AX_META_INSTAGRAM_OAUTH",
            "required": True,
            "injection": "runtime_context",
        }
    ]


def test_google_sheets_default_tool_exposes_enabled_operation_defaults(client):
    from api.services.default_crewai_tools import DEFAULT_CREWAI_TOOL_BY_KEY

    expected_defaults = {
        "read_range_enabled": True,
        "append_rows_enabled": True,
        "update_values_enabled": True,
    }

    assert (
        DEFAULT_CREWAI_TOOL_BY_KEY["ax.google_sheets"].to_response()["default_config_json"]
        == expected_defaults
    )

    response = client.get("/api/tool-catalog")

    assert response.status_code == 200
    by_key = {entry["tool_key"]: entry for entry in response.json()}
    assert by_key["ax.google_sheets"]["default_config_json"] == expected_defaults


def test_nano_banana_default_tool_exposes_image_config_schema(client):
    response = client.get("/api/tool-catalog")

    assert response.status_code == 200
    by_key = {entry["tool_key"]: entry for entry in response.json()}
    nano_banana = by_key["ax.nano_banana_image"]
    assert nano_banana["default_config_json"] == {
        "model": "gemini-3.1-flash-image-preview",
        "aspect_ratio": "1:1",
        "image_size": "1K",
    }
    model_schema = nano_banana["config_schema_json"]["properties"]["model"]
    assert set(model_schema["enum"]) == {
        "gemini-2.5-flash-image",
        "gemini-3-pro-image-preview",
        "gemini-3.1-flash-image-preview",
    }
    assert model_schema["default"] == "gemini-3.1-flash-image-preview"
    assert nano_banana["config_schema_json"]["properties"]["aspect_ratio"]["enum"] == [
        "1:1",
        "9:16",
        "16:9",
    ]
    assert nano_banana["config_schema_json"]["properties"]["image_size"]["enum"] == [
        "1K",
        "2K",
        "4K",
    ]
    model_ui_schema = nano_banana["ui_schema_json"]["fields"]["model"]
    assert model_ui_schema["widget"] == "select"
    assert model_ui_schema["label"] == "Model"
    assert nano_banana["ui_schema_json"]["fields"]["aspect_ratio"]["label"] == "Output ratio"


def test_instagram_publish_default_tool_exposes_publish_mode_schema(client):
    response = client.get("/api/tool-catalog")

    assert response.status_code == 200
    by_key = {entry["tool_key"]: entry for entry in response.json()}
    instagram = by_key["ax.instagram_publish_tool"]
    assert instagram["module_path"] == "api.tools.instagram_publish_tool"
    assert instagram["class_name"] == "AXInstagramPublishTool"
    assert instagram["default_config_json"] == {
        "publish_mode": 3,
        "poll_timeout_seconds": 60,
        "poll_interval_seconds": 3,
    }
    assert instagram["config_schema_json"] == {
        "type": "object",
        "properties": {
            "publish_mode": {
                "type": "integer",
                "enum": [1, 3],
                "default": 3,
            },
            "poll_timeout_seconds": {
                "type": "integer",
                "minimum": 1,
                "maximum": 300,
                "default": 60,
                "description": "Maximum seconds to wait for Meta media processing before publishing.",
            },
            "poll_interval_seconds": {
                "type": "integer",
                "minimum": 1,
                "maximum": 60,
                "default": 3,
                "description": "Seconds between Meta container status checks.",
            },
        },
        "additionalProperties": False,
    }
    assert instagram["input_schema_json"]["required"] == ["artifact_ids", "caption"]
    assert instagram["input_schema_json"]["properties"]["artifact_ids"]["maxItems"] == 3
    assert instagram["ui_schema_json"]["fields"]["publish_mode"] == {
        "widget": "select",
        "label": "Publish preference",
        "help": "The tool publishes 1 unique artifact as a single post and 3 unique artifacts as a carousel.",
        "options": [1, 3],
    }
    assert instagram["ui_schema_json"]["fields"]["poll_timeout_seconds"] == {
        "widget": "number",
        "label": "Publish wait timeout",
        "help": "Maximum seconds to wait for Meta media processing before publishing.",
    }
    assert instagram["ui_schema_json"]["fields"]["poll_interval_seconds"] == {
        "widget": "number",
        "label": "Status check interval",
        "help": "Seconds between Meta container status checks.",
    }


def test_version_tooling_models_define_persistence_level_uniqueness():
    tool_constraints = [constraint for constraint in models.VersionTool.__table__.constraints if isinstance(constraint, UniqueConstraint)]
    skill_constraints = [constraint for constraint in models.VersionSkill.__table__.constraints if isinstance(constraint, UniqueConstraint)]

    assert any([column.name for column in constraint.columns] == ["version_id", "tool_key"] for constraint in tool_constraints)
    assert any([column.name for column in constraint.columns] == ["version_id", "skill_key"] for constraint in skill_constraints)


def test_version_attachment_reads_use_version_tables_directly(client, db, seeded_agent_version_id):
    db.add(
        models.VersionTool(
            version_id=seeded_agent_version_id,
            tool_key="calculator",
            tool_config_json={"precision": 2},
            sort_order=3,
        )
    )
    db.add(
        models.VersionSkill(
            version_id=seeded_agent_version_id,
            skill_key="summarize",
            skill_source="/tmp/summarize.md",
            sort_order=4,
        )
    )
    db.commit()

    tools_response = client.get(f"/api/versions/{seeded_agent_version_id}/tools")
    skills_response = client.get(f"/api/versions/{seeded_agent_version_id}/skills")

    assert tools_response.status_code == 200
    assert tools_response.json()[0]["version_id"] == seeded_agent_version_id
    assert tools_response.json()[0]["tool_key"] == "calculator"
    assert tools_response.json()[0]["tool_config_json"] == {"precision": 2}
    assert tools_response.json()[0]["sort_order"] == 3
    assert set(tools_response.json()[0]) == {
        "id",
        "version_id",
        "tool_key",
        "tool_config_json",
        "sort_order",
        "created_at",
    }

    assert skills_response.status_code == 200
    assert skills_response.json()[0]["version_id"] == seeded_agent_version_id
    assert skills_response.json()[0]["skill_key"] == "summarize"
    assert skills_response.json()[0]["skill_source"] == "/tmp/summarize.md"
    assert skills_response.json()[0]["sort_order"] == 4
    assert set(skills_response.json()[0]) == {
        "id",
        "version_id",
        "skill_key",
        "skill_source",
        "sort_order",
        "created_at",
    }


def test_hydrate_crew_graph_tools_preserves_attachment_config(db, seeded_agent_version_id):
    from api.services.crew_tool_hydration import hydrate_crew_graph_tools

    db.add(
        models.VersionTool(
            version_id=seeded_agent_version_id,
            tool_key="ax.nano_banana_image",
            tool_config_json={"model": "gemini-3-pro-image-preview", "aspect_ratio": "9:16", "image_size": "2K"},
            sort_order=4,
        )
    )
    db.commit()
    graph = {
        "nodes": [
            {
                "id": "agent:creative",
                "type": "agent",
                "data": {"assetId": "agent-asset", "versionId": seeded_agent_version_id},
            }
        ],
        "entities": {"tools": {}},
    }

    hydrated = hydrate_crew_graph_tools(db, graph)

    attachment = hydrated["entities"]["tools"]["ax.nano_banana_image"]["attachments"][0]
    assert attachment["version_id"] == seeded_agent_version_id
    assert attachment["tool_config_json"] == {
        "model": "gemini-3-pro-image-preview",
        "aspect_ratio": "9:16",
        "image_size": "2K",
    }
    assert attachment["sort_order"] == 4


def test_version_attachment_reads_missing_parent_version_return_404(client):
    missing_version_id = "00000000-0000-0000-0000-000000000000"

    tools_response = client.get(f"/api/versions/{missing_version_id}/tools")
    skills_response = client.get(f"/api/versions/{missing_version_id}/skills")

    assert tools_response.status_code == 404
    assert tools_response.json()["detail"] == f"Version not found: {missing_version_id}"
    assert skills_response.status_code == 404
    assert skills_response.json()["detail"] == f"Version not found: {missing_version_id}"


def test_version_capabilities_batches_requested_versions(client, db, seeded_agent_version_id, second_agent_version_id):
    db.add_all(
        [
            models.VersionTool(
                version_id=seeded_agent_version_id,
                tool_key="calculator",
                tool_config_json={},
            ),
            models.VersionTool(
                version_id=second_agent_version_id,
                tool_key="search",
                tool_config_json={"mode": "web"},
            ),
            models.VersionSkill(
                version_id=seeded_agent_version_id,
                skill_key="summarize",
                skill_source="/tmp/summarize.md",
            ),
        ]
    )
    db.commit()

    response = client.get(
        "/api/version-capabilities",
        params=[("version_ids", seeded_agent_version_id), ("version_ids", second_agent_version_id)],
    )

    assert response.status_code == 200
    assert {item["version_id"] for item in response.json()["tools"]} == {
        seeded_agent_version_id,
        second_agent_version_id,
    }
    assert {item["tool_key"] for item in response.json()["tools"]} == {"calculator", "search"}
    assert {item["version_id"] for item in response.json()["skills"]} == {seeded_agent_version_id}
    assert {item["skill_key"] for item in response.json()["skills"]} == {"summarize"}


def test_version_capabilities_returns_agent_and_task_tool_attachments(client, db):
    agent_asset = models.Asset(asset_type="agent", name="agent")
    task_asset = models.Asset(asset_type="task", name="task")
    agent_version = models.AssetVersion(
        asset=agent_asset,
        version_number=1,
        status="draft",
        metadata_json={},
    )
    task_version = models.AssetVersion(
        asset=task_asset,
        version_number=1,
        status="draft",
        metadata_json={},
    )
    db.add_all([agent_asset, task_asset, agent_version, task_version])
    db.commit()

    db.add(
        models.VersionTool(
            version_id=agent_version.id,
            tool_key="crewai.serper_dev",
            tool_config_json={"country": "kr"},
            sort_order=0,
        )
    )
    db.add(
        models.VersionTool(
            version_id=task_version.id,
            tool_key="crewai.dalle",
            tool_config_json={"style": "vivid"},
            sort_order=0,
        )
    )
    db.commit()

    response = client.get(
        "/api/version-capabilities",
        params=[("version_ids", agent_version.id), ("version_ids", task_version.id)],
    )

    assert response.status_code == 200
    tools = response.json()["tools"]
    assert {(tool["version_id"], tool["tool_key"]) for tool in tools} == {
        (agent_version.id, "crewai.serper_dev"),
        (task_version.id, "crewai.dalle"),
    }


def test_attach_tool_enforces_uniqueness_per_version(client, seeded_agent_version_id, second_agent_version_id):
    first_attach = client.post(
        f"/api/versions/{seeded_agent_version_id}/tools",
        json={"tool_key": "crewai.dalle"},
    )
    duplicate_attach = client.post(
        f"/api/versions/{seeded_agent_version_id}/tools",
        json={"tool_key": "crewai.dalle"},
    )
    other_version_attach = client.post(
        f"/api/versions/{second_agent_version_id}/tools",
        json={"tool_key": "crewai.dalle"},
    )

    assert first_attach.status_code == 201
    assert first_attach.json()["version_id"] == seeded_agent_version_id
    assert first_attach.json()["tool_key"] == "crewai.dalle"
    assert duplicate_attach.status_code == 409
    assert duplicate_attach.json()["detail"] == "Tool already attached to version."
    assert other_version_attach.status_code == 201
    assert other_version_attach.json()["version_id"] == second_agent_version_id


def test_attachment_responses_serialize_postgres_uuid_values():
    attachment_id = uuid4()
    version_id = uuid4()
    created_at = datetime.now(timezone.utc)

    tool_response = VersionToolAttachmentResponse(
        id=attachment_id,
        version_id=version_id,
        tool_key="crewai.dalle",
        tool_config_json={},
        sort_order=0,
        created_at=created_at,
    )
    tool_read_response = VersionToolAttachmentReadResponse(
        id=attachment_id,
        version_id=version_id,
        tool_key="crewai.dalle",
        tool_config_json={},
        sort_order=0,
        created_at=created_at,
    )
    skill_response = VersionSkillAttachmentResponse(
        id=attachment_id,
        version_id=version_id,
        skill_key="skill.research",
        skill_source=None,
        sort_order=0,
        created_at=created_at,
    )
    skill_read_response = VersionSkillAttachmentReadResponse(
        id=attachment_id,
        version_id=version_id,
        skill_key="skill.research",
        skill_source=None,
        sort_order=0,
        created_at=created_at,
    )

    assert tool_response.id == str(attachment_id)
    assert tool_response.version_id == str(version_id)
    assert tool_read_response.id == str(attachment_id)
    assert tool_read_response.version_id == str(version_id)
    assert skill_response.id == str(attachment_id)
    assert skill_response.version_id == str(version_id)
    assert skill_read_response.id == str(attachment_id)
    assert skill_read_response.version_id == str(version_id)


def test_list_version_tool_attachments_serializes_uuid_row_ids():
    from api.services.tooling import list_version_tool_attachments

    attachment_id = uuid4()
    version_id = uuid4()
    created_at = datetime.now(timezone.utc)
    row = SimpleNamespace(
        id=attachment_id,
        version_id=version_id,
        tool_key="crewai.dalle",
        tool_config_json={"style": "vivid"},
        sort_order=3,
        created_at=created_at,
    )

    class FakeQuery:
        def filter(self, *args):
            return self

        def order_by(self, *args):
            return self

        def all(self):
            return [row]

    class FakeDb:
        def query(self, *args):
            return FakeQuery()

    result = list_version_tool_attachments(FakeDb(), version_ids=[str(version_id)])

    assert result == [
        {
            "id": str(attachment_id),
            "version_id": str(version_id),
            "tool_key": "crewai.dalle",
            "tool_config_json": {"style": "vivid"},
            "sort_order": 3,
            "created_at": created_at,
        }
    ]


def test_attach_tool_rejects_unknown_tool_key(client, seeded_agent_version_id):
    response = client.post(
        f"/api/versions/{seeded_agent_version_id}/tools",
        json={"tool_key": "missing.tool"},
    )

    assert response.status_code == 404
    assert "Tool not found" in response.json()["detail"]


def test_attach_tool_accepts_custom_catalog_tool_key(client, seeded_agent_version_id):
    create_response = client.post(
        "/api/tool-catalog",
        json={
            "tool_key": "custom.local_echo",
            "name": "Local Echo",
            "description": "Echo test input.",
            "tool_type": "python_class",
            "module_path": "tests.test_tooling_v2",
            "class_name": "EchoToolForCatalogTest",
            "default_config_json": {"prefix": "AX"},
        },
    )

    response = client.post(
        f"/api/versions/{seeded_agent_version_id}/tools",
        json={"tool_key": "custom.local_echo"},
    )

    assert create_response.status_code == 201
    assert response.status_code == 201
    assert response.json()["tool_key"] == "custom.local_echo"


def test_validate_tool_config_rejects_enum_value():
    from api.runtime.tool_metadata import validate_tool_config

    with pytest.raises(
        ValueError,
        match="Invalid config field 'mode'.*custom.enum_tool.*version-1.*fast, safe",
    ):
        validate_tool_config(
            tool_key="custom.enum_tool",
            version_id="version-1",
            config={"mode": "turbo"},
            config_schema_json={
                "type": "object",
                "properties": {"mode": {"type": "string", "enum": ["fast", "safe"]}},
                "additionalProperties": False,
            },
        )


def test_attach_tool_accepts_and_persists_tool_config_json(client, seeded_agent_version_id):
    response = client.post(
        f"/api/versions/{seeded_agent_version_id}/tools",
        json={"tool_key": "crewai.serper_dev", "tool_config_json": {"n_results": 3}},
    )

    assert response.status_code == 201
    assert response.json()["tool_key"] == "crewai.serper_dev"
    assert response.json()["tool_config_json"] == {"n_results": 3}
    assert client.get(f"/api/versions/{seeded_agent_version_id}/tools").json()[0]["tool_config_json"] == {
        "n_results": 3
    }


def test_attach_tool_rejects_invalid_tool_config_type(client, seeded_agent_version_id):
    response = client.post(
        f"/api/versions/{seeded_agent_version_id}/tools",
        json={"tool_key": "crewai.serper_dev", "tool_config_json": {"n_results": "3"}},
    )

    assert response.status_code == 422
    assert "Invalid config field 'n_results'" in response.text
    assert "expected integer" in response.text


def test_attach_tool_rejects_unknown_tool_config_field(client, seeded_agent_version_id):
    response = client.post(
        f"/api/versions/{seeded_agent_version_id}/tools",
        json={"tool_key": "crewai.serper_dev", "tool_config_json": {"unexpected": True}},
    )

    assert response.status_code == 422
    assert "Unsupported config field 'unexpected'" in response.text


def test_patch_attached_tool_rejects_invalid_tool_config_type(client, seeded_agent_version_id):
    client.post(f"/api/versions/{seeded_agent_version_id}/tools", json={"tool_key": "crewai.serper_dev"})

    response = client.patch(
        f"/api/versions/{seeded_agent_version_id}/tools/crewai.serper_dev",
        json={"tool_config_json": {"n_results": "3"}},
    )

    assert response.status_code == 422
    assert "Invalid config field 'n_results'" in response.text


def test_get_tool_catalog_entry_by_key(client, seeded_tool_catalog_entry):
    response = client.get("/api/tool-catalog/tool.search_web")

    assert response.status_code == 200
    assert response.json()["tool_key"] == "tool.search_web"
    assert response.json()["default_config_json"] == {"timeout_seconds": 30}


def test_patch_attached_tool_updates_config_and_sort_order(client, seeded_agent_version_id):
    client.post(f"/api/versions/{seeded_agent_version_id}/tools", json={"tool_key": "crewai.serper_dev"})

    response = client.patch(
        f"/api/versions/{seeded_agent_version_id}/tools/crewai.serper_dev",
        json={"tool_config_json": {"n_results": 5}, "sort_order": 2},
    )

    assert response.status_code == 200
    assert response.json()["tool_config_json"] == {"n_results": 5}
    assert response.json()["sort_order"] == 2


def test_patch_attached_tool_preserves_config_when_sort_order_only(client, db, seeded_agent_version_id):
    db.add(
        models.VersionTool(
            version_id=seeded_agent_version_id,
            tool_key="tool.search_web",
            tool_config_json={"timeout_seconds": 30},
            sort_order=1,
        )
    )
    db.commit()

    response = client.patch(
        f"/api/versions/{seeded_agent_version_id}/tools/tool.search_web",
        json={"sort_order": 2},
    )

    assert response.status_code == 200
    assert response.json()["tool_config_json"] == {"timeout_seconds": 30}
    assert response.json()["sort_order"] == 2
    assert client.get(f"/api/versions/{seeded_agent_version_id}/tools").json()[0]["tool_config_json"] == {
        "timeout_seconds": 30
    }


def test_patch_attached_tool_rejects_explicit_null_tool_config_json(client, seeded_agent_version_id):
    client.post(f"/api/versions/{seeded_agent_version_id}/tools", json={"tool_key": "crewai.serper_dev"})

    response = client.patch(
        f"/api/versions/{seeded_agent_version_id}/tools/crewai.serper_dev",
        json={"tool_config_json": None},
    )

    assert response.status_code == 422
    assert "tool_config_json must not be null" in response.text


def test_patch_attached_tool_rejects_explicit_null_sort_order(client, seeded_agent_version_id):
    client.post(f"/api/versions/{seeded_agent_version_id}/tools", json={"tool_key": "crewai.serper_dev"})

    response = client.patch(
        f"/api/versions/{seeded_agent_version_id}/tools/crewai.serper_dev",
        json={"sort_order": None},
    )

    assert response.status_code == 422
    assert "sort_order must not be null" in response.text


def test_delete_attached_tool_removes_attachment(client, db, seeded_agent_version_id):
    db.add(
        models.VersionTool(
            version_id=seeded_agent_version_id,
            tool_key="tool.search_web",
            tool_config_json={"timeout_seconds": 30},
            sort_order=1,
        )
    )
    db.commit()

    response = client.delete(f"/api/versions/{seeded_agent_version_id}/tools/tool.search_web")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/api/versions/{seeded_agent_version_id}/tools").json() == []


def test_version_tool_attachment_uniqueness_is_enforced_by_database(db, seeded_agent_version_id):
    first = models.VersionTool(
        version_id=seeded_agent_version_id,
        tool_key="calculator",
        tool_config_json={},
    )
    duplicate = models.VersionTool(
        version_id=seeded_agent_version_id,
        tool_key="calculator",
        tool_config_json={},
    )

    db.add(first)
    db.commit()
    db.add(duplicate)

    with pytest.raises(IntegrityError):
        db.flush()


def test_attach_skill_enforces_uniqueness_per_version(client, seeded_agent_version_id, second_agent_version_id):
    first_attach = client.post(
        f"/api/versions/{seeded_agent_version_id}/skills",
        json={"skill_key": "summarize"},
    )
    duplicate_attach = client.post(
        f"/api/versions/{seeded_agent_version_id}/skills",
        json={"skill_key": "summarize"},
    )
    other_version_attach = client.post(
        f"/api/versions/{second_agent_version_id}/skills",
        json={"skill_key": "summarize"},
    )

    assert first_attach.status_code == 201
    assert first_attach.json()["version_id"] == seeded_agent_version_id
    assert first_attach.json()["skill_key"] == "summarize"
    assert duplicate_attach.status_code == 409
    assert duplicate_attach.json()["detail"] == "Skill already attached to version."
    assert other_version_attach.status_code == 201
    assert other_version_attach.json()["version_id"] == second_agent_version_id


def test_version_skill_attachment_uniqueness_is_enforced_by_database(db, seeded_agent_version_id):
    first = models.VersionSkill(
        version_id=seeded_agent_version_id,
        skill_key="summarize",
        skill_source=None,
    )
    duplicate = models.VersionSkill(
        version_id=seeded_agent_version_id,
        skill_key="summarize",
        skill_source=None,
    )

    db.add(first)
    db.commit()
    db.add(duplicate)

    with pytest.raises(IntegrityError):
        db.flush()
