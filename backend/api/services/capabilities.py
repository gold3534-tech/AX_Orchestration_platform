from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from api.runtime.credential_providers import SUPPORTED_CREDENTIAL_PROVIDERS
from api.services.tooling import list_tool_catalog_entries


CAPABILITY_TYPES = ("agent_tool", "Execution_Action")
AVAILABILITY_FIELDS = {"implementation_status", "is_attachable", "is_runtime_available"}

AGENT_TOOL_POLICY_RATIONALE = (
    "creative and research flexible tools stay agent_tool so agents can decide how to use them."
)
EXECUTION_ACTION_POLICY_RATIONALE = (
    "external storage/publish and maintenance-special-care actions are explicit execution actions."
)
META_INSTAGRAM_PUBLISH_SCOPES = ["instagram_basic", "instagram_content_publish"]
CONSERVATIVE_NODE_APPROVAL_POLICY = {
    "mode": "node-explicit",
    "node_level_toggle": True,
    "default_requires_approval": True,
    "default_approval_mode": "every_run",
}

PLANNED_AGENT_TOOL_CAPABILITIES: tuple[dict[str, Any], ...] = (
    {
        "key": "ax.google_sheets",
        "type": "agent_tool",
        "label": "AX Google Sheets",
        "description": "Read and update Google Sheets through the connected user's Google Workspace account.",
        "implementation_status": "planned",
        "is_attachable": False,
        "is_runtime_available": False,
        "provider": "google_workspace",
        "auth_type": "oauth2",
        "required_scopes": ["https://www.googleapis.com/auth/spreadsheets"],
        "required_account_status": "active",
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["read_range", "append_rows", "update_values"],
                },
                "spreadsheet_id": {"type": "string"},
                "range_name": {"type": "string"},
                "values": {"type": "array"},
            },
            "required": ["operation", "spreadsheet_id", "range_name"],
            "additionalProperties": True,
        },
        "config_schema": {
            "type": "object",
            "properties": {
                "read_range_enabled": {"type": "boolean", "default": True},
                "append_rows_enabled": {"type": "boolean", "default": True},
                "update_values_enabled": {"type": "boolean", "default": True},
            },
            "additionalProperties": False,
        },
        "output_schema": {"type": "object"},
        "supported_approval_modes": [],
        "approval_policy": {},
        "risk_level": "write",
        "artifact_input_requirements": {},
        "implementation": "ax_tool",
        "policy_rationale": AGENT_TOOL_POLICY_RATIONALE,
    },
    {
        "key": "ax.nano_banana_image",
        "type": "agent_tool",
        "label": "Nano Banana 2 Image Generation",
        "description": "Generate image artifacts with Nano Banana 2 through the AX-managed image tool.",
        "implementation_status": "planned",
        "is_attachable": False,
        "is_runtime_available": False,
        "provider": "google_gemini",
        "auth_type": "api_key",
        "required_scopes": [],
        "required_account_status": "active",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Single image prompt."},
                "image_prompts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": "Batch image prompts. Use either prompt or image_prompts.",
                },
                "delay_seconds": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 30,
                    "default": 10,
                    "description": "Seconds to wait between batch image generations.",
                },
                "artifact_storage_mode": {
                    "type": "string",
                    "enum": ["temporary_only"],
                    "default": "temporary_only",
                },
            },
            "additionalProperties": False,
            "oneOf": [
                {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "artifact_storage_mode": {
                            "type": "string",
                            "enum": ["temporary_only"],
                            "default": "temporary_only",
                        },
                    },
                    "required": ["prompt"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {
                        "image_prompts": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                        },
                        "delay_seconds": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 30,
                            "default": 10,
                        },
                        "artifact_storage_mode": {
                            "type": "string",
                            "enum": ["temporary_only"],
                            "default": "temporary_only",
                        },
                    },
                    "required": ["image_prompts"],
                    "additionalProperties": False,
                },
            ],
        },
        "config_schema": {
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "enum": [
                        "gemini-3.1-flash-image-preview",
                        "gemini-3-pro-image-preview",
                        "gemini-2.5-flash-image",
                    ],
                    "default": "gemini-3.1-flash-image-preview",
                },
                "aspect_ratio": {
                    "type": "string",
                    "enum": ["1:1", "9:16", "16:9"],
                    "default": "1:1",
                },
                "image_size": {
                    "type": "string",
                    "enum": ["1K", "2K", "4K"],
                    "default": "1K",
                },
            },
            "additionalProperties": False,
        },
        "output_schema": {
            "oneOf": [
                {
                    "type": "object",
                    "properties": {
                        "artifact_id": {"type": "string"},
                        "preview_url": {"type": "string"},
                        "download_url": {"type": "string"},
                        "mime_type": {"type": "string"},
                    },
                    "required": ["artifact_id"],
                    "additionalProperties": True,
                },
                {
                    "type": "object",
                    "properties": {
                        "images": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "artifact_id": {"type": "string"},
                                    "preview_url": {"type": "string"},
                                    "download_url": {"type": "string"},
                                    "mime_type": {"type": "string"},
                                },
                                "required": ["artifact_id"],
                                "additionalProperties": True,
                            },
                        },
                        "count": {"type": "integer", "minimum": 0},
                    },
                    "required": ["images", "count"],
                    "additionalProperties": False,
                },
            ]
        },
        "supported_approval_modes": [],
        "approval_policy": {},
        "risk_level": "write",
        "artifact_input_requirements": {},
        "implementation": "ax_tool",
        "policy_rationale": AGENT_TOOL_POLICY_RATIONALE,
    },
    {
        "key": "ax.instagram_publish_tool",
        "type": "agent_tool",
        "label": "AX Instagram Publish",
        "description": "Publish 1 unique AX image artifact to Instagram as a single image post, or 3 unique artifacts as a carousel.",
        "implementation_status": "planned",
        "is_attachable": False,
        "is_runtime_available": False,
        "provider": "meta_instagram",
        "auth_type": "oauth2",
        "required_scopes": META_INSTAGRAM_PUBLISH_SCOPES,
        "required_account_status": "active",
        "input_schema": {
            "type": "object",
            "properties": {
                "artifact_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 3,
                },
                "caption": {"type": "string"},
            },
            "required": ["artifact_ids", "caption"],
            "additionalProperties": False,
        },
        "config_schema": {
            "type": "object",
            "properties": {
                "publish_mode": {
                    "type": "integer",
                    "enum": [1, 3],
                    "default": 3,
                }
            },
            "additionalProperties": False,
        },
        "output_schema": {"type": "object", "required": ["ig_media_id"]},
        "supported_approval_modes": [],
        "approval_policy": {},
        "risk_level": "publish",
        "artifact_input_requirements": {"artifact_type": ["image"]},
        "implementation": "ax_tool",
        "policy_rationale": AGENT_TOOL_POLICY_RATIONALE,
    },
)

EXECUTION_ACTIONS: tuple[dict[str, Any], ...] = (
    {
        "key": "ax.google_drive_upload",
        "type": "Execution_Action",
        "label": "Google Drive Upload",
        "description": "Upload an AX artifact or file URL to the connected user's Google Drive.",
        "implementation_status": "planned",
        "is_attachable": False,
        "is_runtime_available": False,
        "provider": "google_workspace",
        "auth_type": "oauth2",
        "required_scopes": ["https://www.googleapis.com/auth/drive.file"],
        "required_account_status": "active",
        "input_schema": {"type": "object", "required": ["artifact_id"]},
        "config_schema": {
            "type": "object",
            "properties": {
                "target_folder_id": {"type": "string"},
                "filename_template": {"type": "string"},
                "mime_type": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "output_schema": {"type": "object", "required": ["drive_file_id"]},
        "supported_approval_modes": ["never", "every_run"],
        "approval_policy": CONSERVATIVE_NODE_APPROVAL_POLICY,
        "risk_level": "upload",
        "artifact_input_requirements": {"artifact_type": ["image", "file"]},
        "implementation": "execution_action",
        "policy_rationale": EXECUTION_ACTION_POLICY_RATIONALE,
    },
    {
        "key": "ax.instagram_publish",
        "type": "Execution_Action",
        "label": "Instagram Publish",
        "description": "Publish an AX image artifact to a connected Instagram Professional account.",
        "implementation_status": "planned",
        "is_attachable": False,
        "is_runtime_available": False,
        "provider": "meta_instagram",
        "auth_type": "oauth2",
        "required_scopes": META_INSTAGRAM_PUBLISH_SCOPES,
        "required_account_status": "active",
        "input_schema": {"type": "object", "required": ["artifact_id", "caption"]},
        "config_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "output_schema": {"type": "object", "required": ["ig_media_id"]},
        "supported_approval_modes": ["never", "every_run"],
        "approval_policy": CONSERVATIVE_NODE_APPROVAL_POLICY,
        "risk_level": "publish",
        "artifact_input_requirements": {"artifact_type": ["image"]},
        "implementation": "execution_action",
        "policy_rationale": EXECUTION_ACTION_POLICY_RATIONALE,
    },
)


def list_capabilities(db: Session) -> list[dict[str, Any]]:
    capabilities_by_key: dict[str, dict[str, Any]] = {}

    for tool in list_tool_catalog_entries(db):
        capability = _agent_tool_capability_from_tool(tool)
        capabilities_by_key[capability["key"]] = capability

    for capability in PLANNED_AGENT_TOOL_CAPABILITIES:
        capabilities_by_key.setdefault(capability["key"], deepcopy(capability))

    return [*capabilities_by_key.values(), *list_execution_actions()]


def list_execution_actions() -> list[dict[str, Any]]:
    return [deepcopy(action) for action in EXECUTION_ACTIONS]


def _agent_tool_capability_from_tool(tool: dict[str, Any]) -> dict[str, Any]:
    key = tool["tool_key"]
    provider = _provider_for_tool(tool)
    provider_metadata = SUPPORTED_CREDENTIAL_PROVIDERS.get(provider) if provider else None
    override = _planned_agent_tool_by_key().get(key, {})

    capability = {
        "key": key,
        "type": "agent_tool",
        "label": tool["name"],
        "description": tool["description"],
        "implementation_status": "available",
        "is_attachable": True,
        "is_runtime_available": True,
        "provider": provider,
        "auth_type": provider_metadata.auth_type if provider_metadata else "none",
        "required_scopes": [],
        "required_account_status": "active",
        "input_schema": tool.get("input_schema_json") or {},
        "config_schema": tool.get("config_schema_json") or {},
        "output_schema": {},
        "supported_approval_modes": [],
        "approval_policy": {},
        "risk_level": "read",
        "artifact_input_requirements": {},
        "implementation": _implementation_for_tool(tool),
        "policy_rationale": AGENT_TOOL_POLICY_RATIONALE,
    }
    capability.update(
        {k: deepcopy(v) for k, v in override.items() if k not in {"key", *AVAILABILITY_FIELDS}}
    )
    return capability


def _provider_for_tool(tool: dict[str, Any]) -> str | None:
    credential_requirements = tool.get("credential_requirements") or []
    if credential_requirements:
        provider = credential_requirements[0].get("provider")
        if isinstance(provider, str):
            return provider

    tool_key = tool.get("tool_key")
    if tool_key == "crewai.firecrawl_scrape_website":
        return "firecrawl"
    if tool_key == "ax.google_sheets":
        return "google_workspace"
    if tool_key == "ax.nano_banana_image":
        return "google_gemini"
    return None


def _implementation_for_tool(tool: dict[str, Any]) -> str:
    if tool.get("module_path") == "crewai_tools":
        return "crewai_toolkit"
    if str(tool.get("tool_key", "")).startswith("ax."):
        return "ax_tool"
    return tool.get("tool_type") or "catalog"


def _planned_agent_tool_by_key() -> dict[str, dict[str, Any]]:
    return {capability["key"]: capability for capability in PLANNED_AGENT_TOOL_CAPABILITIES}
