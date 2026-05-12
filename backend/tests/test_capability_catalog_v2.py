from contextlib import asynccontextmanager, contextmanager
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.core.database import get_db
from api.main import app
from api.schemas.capabilities import CapabilityCatalogResponse
from api.services.capabilities import CAPABILITY_TYPES


@asynccontextmanager
async def _test_lifespan(_app):
    yield


@contextmanager
def unauthenticated_test_client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    previous_overrides = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = override_get_db
    try:
        with patch.object(app.router, "lifespan_context", _test_lifespan):
            with TestClient(app, raise_server_exceptions=False) as test_client:
                yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


def _catalog_by_key(client) -> dict[str, dict]:
    response = client.get("/api/capabilities")

    assert response.status_code == 200
    return {item["key"]: item for item in response.json()}


def test_capability_catalog_separates_agent_tools_and_execution_actions(client):
    by_key = _catalog_by_key(client)

    assert by_key["ax.google_sheets"]["type"] == "agent_tool"
    assert by_key["crewai.firecrawl_scrape_website"]["type"] == "agent_tool"
    assert by_key["ax.coupang_product_scraper"]["type"] == "agent_tool"
    assert by_key["ax.nano_banana_image"]["type"] == "agent_tool"
    assert by_key["ax.instagram_publish_tool"]["type"] == "agent_tool"
    assert by_key["ax.google_drive_upload"]["type"] == "Execution_Action"
    assert by_key["ax.instagram_publish"]["type"] == "Execution_Action"


def test_capability_catalog_policy_uses_only_two_types(client):
    response = client.get("/api/capabilities")

    assert response.status_code == 200
    observed_types = {item["type"] for item in response.json()}
    assert CAPABILITY_TYPES == ("agent_tool", "Execution_Action")
    assert observed_types <= set(CAPABILITY_TYPES)
    assert "flow_action" not in observed_types
    assert "publish_action" not in observed_types


def test_capability_catalog_uses_frontend_contract_risk_levels(client):
    by_key = _catalog_by_key(client)
    allowed_risk_levels = {"read", "write", "upload", "publish"}

    assert {item["risk_level"] for item in by_key.values()} <= allowed_risk_levels
    assert by_key["ax.nano_banana_image"]["risk_level"] == "write"


def test_capability_catalog_response_rejects_invalid_risk_levels():
    try:
        CapabilityCatalogResponse.model_validate(
            {
                "key": "ax.invalid_risk",
                "type": "agent_tool",
                "label": "Invalid Risk",
                "description": "Invalid frontend risk contract value.",
                "risk_level": "create",
            }
        )
    except ValueError:
        pass
    else:
        raise AssertionError("create should not validate as a capability risk level")


def test_agent_tool_catalog_entries_preserve_policy_rationale(client):
    by_key = _catalog_by_key(client)

    firecrawl = by_key["crewai.firecrawl_scrape_website"]
    coupang = by_key["ax.coupang_product_scraper"]
    sheets = by_key["ax.google_sheets"]
    nano_banana = by_key["ax.nano_banana_image"]
    instagram_tool = by_key["ax.instagram_publish_tool"]

    assert firecrawl["provider"] == "firecrawl"
    assert firecrawl["auth_type"] == "api_key"
    assert firecrawl["implementation"] == "crewai_toolkit"
    assert "research" in firecrawl["policy_rationale"]
    assert coupang["provider"] == "firecrawl"
    assert coupang["auth_type"] == "api_key"
    assert coupang["implementation"] == "ax_tool"
    assert "flexible tools" in coupang["policy_rationale"]
    assert sheets["provider"] == "google_workspace"
    assert sheets["auth_type"] == "oauth2"
    assert sheets["required_scopes"] == ["https://www.googleapis.com/auth/spreadsheets"]
    assert "flexible tools" in sheets["policy_rationale"]
    assert nano_banana["provider"] == "google_gemini"
    assert nano_banana["auth_type"] == "api_key"
    assert "creative" in nano_banana["policy_rationale"]
    assert instagram_tool["provider"] == "meta_instagram"
    assert instagram_tool["auth_type"] == "oauth2"
    assert instagram_tool["required_scopes"] == ["instagram_basic", "instagram_content_publish"]
    assert instagram_tool["risk_level"] == "publish"


def test_catalog_marks_agent_tool_availability_from_tool_catalog(client):
    by_key = _catalog_by_key(client)

    firecrawl = by_key["crewai.firecrawl_scrape_website"]
    coupang = by_key["ax.coupang_product_scraper"]
    sheets = by_key["ax.google_sheets"]
    nano_banana = by_key["ax.nano_banana_image"]
    instagram_tool = by_key["ax.instagram_publish_tool"]

    assert firecrawl["implementation_status"] == "available"
    assert firecrawl["is_attachable"] is True
    assert firecrawl["is_runtime_available"] is True

    assert coupang["type"] == "agent_tool"
    assert coupang["implementation_status"] == "available"
    assert coupang["is_attachable"] is True
    assert coupang["is_runtime_available"] is True

    assert sheets["type"] == "agent_tool"
    assert sheets["implementation_status"] == "available"
    assert sheets["is_attachable"] is True
    assert sheets["is_runtime_available"] is True

    assert nano_banana["type"] == "agent_tool"
    assert nano_banana["implementation_status"] == "available"
    assert nano_banana["is_attachable"] is True
    assert nano_banana["is_runtime_available"] is True

    assert instagram_tool["type"] == "agent_tool"
    assert instagram_tool["implementation_status"] == "available"
    assert instagram_tool["is_attachable"] is True
    assert instagram_tool["is_runtime_available"] is True
    assert instagram_tool["risk_level"] == "publish"
    assert instagram_tool["supported_approval_modes"] == []
    assert instagram_tool["approval_policy"] == {}


def test_capability_catalog_exposes_coupang_product_scraper_schema(client):
    by_key = _catalog_by_key(client)
    coupang = by_key["ax.coupang_product_scraper"]

    assert coupang["implementation"] == "ax_tool"
    assert coupang["input_schema"] == {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Single Coupang product page URL.",
            }
        },
        "required": ["url"],
        "additionalProperties": False,
    }


def test_google_sheets_catalog_exposes_operation_toggles(client):
    by_key = _catalog_by_key(client)

    sheets = by_key["ax.google_sheets"]

    assert sheets["type"] == "agent_tool"
    assert sheets["config_schema"]["properties"]["read_range_enabled"]["type"] == "boolean"
    assert sheets["config_schema"]["properties"]["append_rows_enabled"]["type"] == "boolean"
    assert sheets["config_schema"]["properties"]["update_values_enabled"]["type"] == "boolean"
    assert sheets["required_scopes"] == ["https://www.googleapis.com/auth/spreadsheets"]
    assert sheets["risk_level"] == "write"


def test_capability_catalog_exposes_nano_banana_image_config(client):
    response = client.get("/api/capabilities")

    assert response.status_code == 200
    by_key = {entry["key"]: entry for entry in response.json()}
    nano_banana = by_key["ax.nano_banana_image"]
    assert nano_banana["config_schema"]["properties"]["aspect_ratio"]["enum"] == [
        "1:1",
        "9:16",
        "16:9",
    ]
    assert nano_banana["config_schema"]["properties"]["image_size"]["enum"] == ["1K", "2K", "4K"]
    input_schema = nano_banana["input_schema"]
    assert input_schema["additionalProperties"] is False
    assert input_schema["properties"]["prompt"]["type"] == "string"
    assert input_schema["properties"]["image_prompts"]["items"]["type"] == "string"
    assert input_schema["properties"]["delay_seconds"]["default"] in {10, 10.0}
    assert input_schema["oneOf"][0]["additionalProperties"] is False
    assert input_schema["oneOf"][1]["additionalProperties"] is False
    assert input_schema["oneOf"][0]["required"] == ["prompt"]
    assert input_schema["oneOf"][1]["required"] == ["image_prompts"]
    assert "image_prompts" not in input_schema["oneOf"][0]["properties"]
    assert "prompt" not in input_schema["oneOf"][1]["properties"]

    output_schema = nano_banana["output_schema"]
    batch_schema = next(
        branch for branch in output_schema["oneOf"] if "images" in branch["properties"]
    )
    assert batch_schema["required"] == ["images", "count"]
    assert batch_schema["properties"]["images"]["items"]["required"] == ["artifact_id"]
    assert batch_schema["properties"]["count"]["type"] == "integer"


def test_planned_agent_tool_becomes_attachable_when_tool_catalog_backed(monkeypatch, db):
    from api.services.capabilities import list_capabilities

    monkeypatch.setattr(
        "api.services.capabilities.list_tool_catalog_entries",
        lambda _db: [
            {
                "id": "ax.google_sheets",
                "tool_key": "ax.google_sheets",
                "name": "AX Google Sheets",
                "description": "Implemented Google Sheets tool.",
                "tool_type": "crewai_tool",
                "module_path": "api.tools.google_sheets_tool",
                "class_name": "AXGoogleSheetsTool",
                "default_config_json": {},
                "config_schema_json": {},
                "input_schema_json": {},
                "ui_schema_json": {},
                "credential_requirements": [
                    {
                        "provider": "google_workspace",
                        "env_var": "AX_GOOGLE_WORKSPACE_OAUTH",
                        "required": True,
                        "injection": "runtime_context",
                    }
                ],
                "enabled": True,
            }
        ],
    )

    by_key = {item["key"]: item for item in list_capabilities(db)}
    sheets = by_key["ax.google_sheets"]

    assert sheets["implementation_status"] == "available"
    assert sheets["is_attachable"] is True
    assert sheets["is_runtime_available"] is True
    assert sheets["type"] == "agent_tool"


def test_execution_action_catalog_exposes_conservative_node_approval_metadata(client):
    by_key = _catalog_by_key(client)

    drive = by_key["ax.google_drive_upload"]
    instagram = by_key["ax.instagram_publish"]

    for action in (drive, instagram):
        assert action["type"] == "Execution_Action"
        assert action["approval_policy"] == {
            "mode": "node-explicit",
            "node_level_toggle": True,
            "default_requires_approval": True,
            "default_approval_mode": "every_run",
        }
        assert action["supported_approval_modes"] == ["never", "every_run"]
        assert "external storage/publish" in action["policy_rationale"]
        assert action["implementation_status"] == "planned"
        assert action["is_attachable"] is False
        assert action["is_runtime_available"] is False

    assert drive["provider"] == "google_workspace"
    assert drive["auth_type"] == "oauth2"
    assert drive["required_scopes"] == ["https://www.googleapis.com/auth/drive.file"]
    assert drive["risk_level"] == "upload"
    assert drive["artifact_input_requirements"] == {"artifact_type": ["image", "file"]}

    assert instagram["provider"] == "meta_instagram"
    assert instagram["auth_type"] == "oauth2"
    assert instagram["required_scopes"] == ["instagram_basic", "instagram_content_publish"]
    assert instagram["risk_level"] == "publish"
    assert instagram["artifact_input_requirements"] == {"artifact_type": ["image"]}


def test_execution_actions_endpoint_returns_only_execution_actions(client):
    response = client.get("/api/execution-actions")

    assert response.status_code == 200
    payload = response.json()
    assert {item["key"] for item in payload} == {"ax.google_drive_upload", "ax.instagram_publish"}
    assert {item["type"] for item in payload} == {"Execution_Action"}


def test_capability_catalog_routes_require_bearer_without_auth_override(db):
    with unauthenticated_test_client(db) as no_auth_client:
        capabilities_response = no_auth_client.get("/api/capabilities")
        actions_response = no_auth_client.get("/api/execution-actions")

    assert capabilities_response.status_code == 403
    assert capabilities_response.json()["detail"] == "Not authenticated"
    assert actions_response.status_code == 403
    assert actions_response.json()["detail"] == "Not authenticated"


def test_capability_catalog_response_rejects_drifted_action_types():
    for drifted_type in ("flow_action", "publish_action", "execution_action"):
        try:
            CapabilityCatalogResponse.model_validate(
                {
                    "key": "ax.drifted",
                    "type": drifted_type,
                    "label": "Drifted",
                    "description": "Invalid drifted capability type.",
                }
            )
        except ValueError:
            pass
        else:
            raise AssertionError(f"{drifted_type} should not validate as a capability type")
