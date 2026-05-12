from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.db.models import AssetVersion, ToolCatalog, VersionSkill, VersionTool
from api.runtime.tool_loader import load_tool_class
from api.runtime.tool_metadata import validate_tool_config
from api.schemas.capabilities import SkillCatalogCreate, ToolCatalogCreate, VersionToolAttachmentUpdate
from api.services.default_crewai_tools import DEFAULT_CREWAI_TOOL_BY_KEY, DEFAULT_CREWAI_TOOLS


class ToolingConflictError(ValueError):
    pass


@dataclass(frozen=True)
class AttachedVersionTool:
    version_tool: VersionTool


@dataclass(frozen=True)
class AttachedVersionSkill:
    version_skill: VersionSkill


def list_tool_catalog_entries(db: Session) -> list[dict]:
    entries_by_key = {tool.tool_key: tool.to_response() for tool in DEFAULT_CREWAI_TOOLS}

    if _is_tool_catalog_mapped():
        for row in _list_tool_catalog_rows(db):
            response = _tool_catalog_row_to_response(row)
            if response["tool_key"] in DEFAULT_CREWAI_TOOL_BY_KEY:
                continue
            entries_by_key[response["tool_key"]] = response

    return list(entries_by_key.values())


def _is_tool_catalog_mapped() -> bool:
    try:
        inspect(ToolCatalog)
    except NoInspectionAvailable:
        return False
    return True


def _list_tool_catalog_rows(db: Session) -> list[ToolCatalog]:
    query = db.query(ToolCatalog)
    mapper = inspect(ToolCatalog)
    columns = mapper.columns
    order_by_columns = []
    if "created_at" in columns:
        order_by_columns.append(columns.created_at.asc())
    if "id" in columns:
        order_by_columns.append(columns.id.asc())
    if order_by_columns:
        query = query.order_by(*order_by_columns)
    return query.all()


def _split_entrypoint(entrypoint: str) -> tuple[str, str]:
    if entrypoint.count(":") != 1:
        raise ValueError("Tool catalog entrypoint must use module:Class format.")
    module_path, class_name = entrypoint.split(":", maxsplit=1)
    if not module_path.strip() or not class_name.strip():
        raise ValueError("Tool catalog entrypoint must use module:Class format.")
    return module_path.strip(), class_name.strip()


def _tool_catalog_row_to_response(row: ToolCatalog) -> dict:
    module_path, class_name = _split_entrypoint(row.entrypoint)
    schema_json = row.schema_json if isinstance(row.schema_json, dict) else {}
    return {
        "id": row.id,
        "tool_key": row.id,
        "name": row.name,
        "description": row.description or "",
        "tool_type": schema_json.get("tool_type", "python_class"),
        "module_path": module_path,
        "class_name": class_name,
        "default_config_json": schema_json.get("default_config_json", {}),
        "config_schema_json": schema_json.get("config_schema_json", {}),
        "input_schema_json": schema_json.get("input_schema_json", {}),
        "ui_schema_json": schema_json.get("ui_schema_json", {}),
        "required_env_vars": schema_json.get("required_env_vars", []),
        "credential_requirements": schema_json.get("credential_requirements", []),
        "enabled": row.enabled,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def get_tool_catalog_entry_by_key(db: Session, *, tool_key: str) -> dict:
    for entry in list_tool_catalog_entries(db):
        if entry.get("tool_key") == tool_key:
            return entry
    raise LookupError(f"Tool not found: {tool_key}")


def list_skill_catalog_entries(db: Session) -> list[dict]:
    return []


def ensure_version_exists(db: Session, *, version_id: str) -> AssetVersion:
    asset_version = db.get(AssetVersion, version_id)
    if asset_version is None:
        raise LookupError(f"Version not found: {version_id}")
    return asset_version


def list_version_tool_attachments(db: Session, *, version_ids: list[str]) -> list[dict]:
    if not version_ids:
        return []

    rows = (
        db.query(VersionTool)
        .filter(VersionTool.version_id.in_(version_ids))
        .order_by(VersionTool.created_at.asc(), VersionTool.id.asc())
        .all()
    )

    return [
        {
            "id": str(row.id),
            "version_id": str(row.version_id),
            "tool_key": row.tool_key,
            "tool_config_json": row.tool_config_json,
            "sort_order": row.sort_order,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def list_version_skill_attachments(db: Session, *, version_ids: list[str]) -> list[dict]:
    if not version_ids:
        return []

    rows = (
        db.query(VersionSkill)
        .filter(VersionSkill.version_id.in_(version_ids))
        .order_by(VersionSkill.created_at.asc(), VersionSkill.id.asc())
        .all()
    )

    return [
        {
            "id": str(row.id),
            "version_id": str(row.version_id),
            "skill_key": row.skill_key,
            "skill_source": row.skill_source,
            "sort_order": row.sort_order,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def validate_skill_source(skill_source: str) -> str:
    path = Path(skill_source).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"Skill source not found: {skill_source}") from exc
    except OSError as exc:
        raise ValueError(f"Skill source not readable: {skill_source}") from exc

    if not resolved.is_file() or not resolved.exists():
        raise ValueError(f"Skill source not found: {skill_source}")

    try:
        with resolved.open("rb"):
            pass
    except OSError as exc:
        raise ValueError(f"Skill source not readable: {skill_source}")

    return str(resolved)


def create_skill_catalog_entry(db: Session, payload: SkillCatalogCreate) -> dict:
    normalized_skill_source = validate_skill_source(payload.skill_source)
    now = datetime.now(timezone.utc)
    return {
        "id": payload.skill_key,
        "skill_key": payload.skill_key,
        "name": payload.name,
        "description": payload.description,
        "skill_source": normalized_skill_source,
        "enabled": True,
        "created_at": now,
        "updated_at": now,
    }


def create_tool_catalog_entry(db: Session, payload: ToolCatalogCreate) -> dict:
    if payload.tool_key in DEFAULT_CREWAI_TOOL_BY_KEY:
        raise ToolingConflictError("Built-in CrewAI tool keys cannot be overwritten.")

    load_tool_class(payload.module_path, payload.class_name)
    row = ToolCatalog(
        id=payload.tool_key,
        name=payload.name,
        description=payload.description,
        entrypoint=f"{payload.module_path}:{payload.class_name}",
        schema_json={
            "tool_type": payload.tool_type,
            "default_config_json": payload.default_config_json,
            "config_schema_json": payload.config_schema_json,
            "input_schema_json": payload.input_schema_json,
            "ui_schema_json": payload.ui_schema_json,
            "required_env_vars": payload.required_env_vars,
            "credential_requirements": [
                requirement.model_dump() for requirement in payload.credential_requirements
            ],
        },
        enabled=True,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ToolingConflictError("Tool already exists.") from exc
    db.refresh(row)
    return _tool_catalog_row_to_response(row)


def _validated_tool_catalog_for_attachment(
    db: Session,
    *,
    version_id: str,
    tool_key: str,
    tool_config_json: dict,
) -> dict[str, Any]:
    catalog = get_tool_catalog_entry_by_key(db, tool_key=tool_key)
    validate_tool_config(
        tool_key=tool_key,
        version_id=version_id,
        config=tool_config_json,
        config_schema_json=catalog.get("config_schema_json"),
    )
    return catalog


def attach_tool_to_version(
    db: Session,
    *,
    version_id: str,
    tool_key: str,
    tool_config_json: dict | None = None,
) -> AttachedVersionTool:
    asset_version = db.get(AssetVersion, version_id)
    if asset_version is None:
        raise LookupError(f"Version not found: {version_id}")

    config = dict(tool_config_json or {})
    _validated_tool_catalog_for_attachment(
        db,
        version_id=str(asset_version.id),
        tool_key=tool_key,
        tool_config_json=config,
    )

    existing = (
        db.query(VersionTool)
        .filter(
            VersionTool.version_id == asset_version.id,
            VersionTool.tool_key == tool_key,
        )
        .first()
    )
    if existing is not None:
        raise ToolingConflictError("Tool already attached to version.")

    version_tool = VersionTool(
        version_id=asset_version.id,
        tool_key=tool_key,
        tool_config_json=config,
    )
    db.add(version_tool)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ToolingConflictError("Tool already attached to version.") from exc
    db.refresh(version_tool)

    return AttachedVersionTool(version_tool=version_tool)


def update_tool_attachment(
    db: Session,
    *,
    version_id: str,
    tool_key: str,
    payload: VersionToolAttachmentUpdate,
) -> AttachedVersionTool:
    asset_version = ensure_version_exists(db, version_id=version_id)
    version_tool = (
        db.query(VersionTool)
        .filter(
            VersionTool.version_id == asset_version.id,
            VersionTool.tool_key == tool_key,
        )
        .one_or_none()
    )
    if version_tool is None:
        raise LookupError(f"Tool attachment not found: {version_id}/{tool_key}")

    if payload.tool_config_json is not None:
        next_config = dict(payload.tool_config_json)
        _validated_tool_catalog_for_attachment(
            db,
            version_id=str(asset_version.id),
            tool_key=tool_key,
            tool_config_json=next_config,
        )
        version_tool.tool_config_json = next_config
    if payload.sort_order is not None:
        version_tool.sort_order = payload.sort_order
    db.add(version_tool)
    db.commit()
    db.refresh(version_tool)
    return AttachedVersionTool(version_tool=version_tool)


def delete_tool_attachment(
    db: Session,
    *,
    version_id: str,
    tool_key: str,
) -> None:
    asset_version = ensure_version_exists(db, version_id=version_id)
    version_tool = (
        db.query(VersionTool)
        .filter(
            VersionTool.version_id == asset_version.id,
            VersionTool.tool_key == tool_key,
        )
        .one_or_none()
    )
    if version_tool is None:
        raise LookupError(f"Tool attachment not found: {version_id}/{tool_key}")

    db.delete(version_tool)
    db.commit()


def attach_skill_to_version(
    db: Session,
    *,
    version_id: str,
    skill_key: str,
) -> AttachedVersionSkill:
    asset_version = db.get(AssetVersion, version_id)
    if asset_version is None:
        raise LookupError(f"Version not found: {version_id}")

    existing = (
        db.query(VersionSkill)
        .filter(
            VersionSkill.version_id == asset_version.id,
            VersionSkill.skill_key == skill_key,
        )
        .first()
    )
    if existing is not None:
        raise ToolingConflictError("Skill already attached to version.")

    version_skill = VersionSkill(
        version_id=asset_version.id,
        skill_key=skill_key,
        skill_source=None,
    )
    db.add(version_skill)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ToolingConflictError("Skill already attached to version.") from exc
    db.refresh(version_skill)

    return AttachedVersionSkill(version_skill=version_skill)
