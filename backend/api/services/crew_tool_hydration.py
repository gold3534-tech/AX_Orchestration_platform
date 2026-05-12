from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from api.services.tooling import get_tool_catalog_entry_by_key, list_version_tool_attachments


def hydrate_crew_graph_tools(db: Session, graph: dict[str, Any]) -> dict[str, Any]:
    hydrated = deepcopy(graph)
    nodes = hydrated.get("nodes") if isinstance(hydrated.get("nodes"), list) else []
    version_ids = [
        node.get("data", {}).get("versionId")
        for node in nodes
        if isinstance(node, dict) and node.get("type") in {"agent", "task"}
    ]
    version_ids = [
        version_id
        for version_id in version_ids
        if isinstance(version_id, str) and version_id
    ]
    attachments = list_version_tool_attachments(db, version_ids=version_ids)
    current_version_ids = set(version_ids)

    entities = hydrated.setdefault("entities", {})
    tools = entities.setdefault("tools", {})
    db_tool_keys = {attachment["tool_key"] for attachment in attachments}
    for tool_key, tool_entity in list(tools.items()):
        existing_attachments = tool_entity.get("attachments")
        if not isinstance(existing_attachments, list):
            existing_attachments = []
        tool_entity["attachments"] = [
            item
            for item in existing_attachments
            if item.get("version_id") not in current_version_ids
        ]
        if not tool_entity["attachments"] and tool_key not in db_tool_keys:
            del tools[tool_key]

    for attachment in attachments:
        catalog = get_tool_catalog_entry_by_key(db, tool_key=attachment["tool_key"])
        tool_entity = tools.setdefault(
            attachment["tool_key"],
            {},
        )
        tool_entity.update(
            {
                "tool_key": catalog["tool_key"],
                "name": catalog["name"],
                "description": catalog["description"],
                "tool_type": catalog["tool_type"],
                "module_path": catalog["module_path"],
                "class_name": catalog["class_name"],
                "default_config_json": catalog["default_config_json"],
                "config_schema_json": catalog["config_schema_json"],
                "input_schema_json": catalog["input_schema_json"],
                "ui_schema_json": catalog["ui_schema_json"],
                "required_env_vars": catalog["required_env_vars"],
                "credential_requirements": catalog["credential_requirements"],
            }
        )
        existing_attachments = tool_entity.get("attachments")
        if not isinstance(existing_attachments, list):
            existing_attachments = []
        tool_entity["attachments"] = list(existing_attachments)
        tool_entity["attachments"].append(
            {
                "version_id": attachment["version_id"],
                "tool_config_json": attachment["tool_config_json"],
                "sort_order": attachment["sort_order"],
            }
        )

    return hydrated
