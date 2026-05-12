import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

from api.db.models import (
    Asset,
    AssetRuntimeSnapshot,
    AssetVersion,
    ExecutionBinding,
    FlowRun,
    FlowRunExecution,
    TaskInputPresetBinding,
    VersionLink,
    VersionSkill,
    VersionTool,
    utcnow,
)
from api.schemas.assets import AssetCreate, AssetUpdate, normalize_asset_payload
from api.services.task_input_presets import (
    replace_task_input_preset_bindings,
)


class AssetConflictError(ValueError):
    pass


@dataclass(frozen=True)
class AssetReadModel:
    asset: Asset
    current_version: AssetVersion


_ASSET_VERSION_NO_UNIQUE_CONSTRAINT = "uq_asset_versions_asset_version_no"


def _is_asset_version_number_conflict(exc: IntegrityError) -> bool:
    orig = exc.orig
    diag = getattr(orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    if constraint_name == _ASSET_VERSION_NO_UNIQUE_CONSTRAINT:
        return True

    message = str(orig).lower()
    return (
        _ASSET_VERSION_NO_UNIQUE_CONSTRAINT in message
        or "unique constraint failed: asset_versions.asset_id, asset_versions.version_no" in message
        or (
            "duplicate key value violates unique constraint" in message
            and _ASSET_VERSION_NO_UNIQUE_CONSTRAINT in message
        )
    )


def canonical_json(value: Any) -> str:
    return json.dumps(value or {}, sort_keys=True, separators=(",", ":"), default=str)


def snapshots_equal(left: dict | None, right: dict | None) -> bool:
    return canonical_json(left or {}) == canonical_json(right or {})


def archive_published_versions_for_asset(db: Session, *, asset_id) -> None:
    (
        db.query(AssetVersion)
        .filter(AssetVersion.asset_id == asset_id, AssetVersion.status == "published")
        .update({AssetVersion.status: "archived"}, synchronize_session=False)
    )


def upsert_asset_runtime_snapshot(db: Session, *, version_id: str, runtime_snapshot_json: dict) -> AssetRuntimeSnapshot:
    snapshot = db.get(AssetRuntimeSnapshot, version_id)
    if snapshot is None:
        snapshot = AssetRuntimeSnapshot(
            version_id=version_id,
            runtime_snapshot_json=runtime_snapshot_json,
        )
    else:
        snapshot.runtime_snapshot_json = runtime_snapshot_json
        snapshot.updated_at = utcnow()
    db.add(snapshot)
    return snapshot


def _build_version_data_for_asset(asset: Asset, normalized_payload: dict, *, change_summary: str | None = None) -> dict:
    version_data = {
        "type": asset.asset_type,
        "name": asset.name,
        "description": asset.description,
        "workspace_id": str(asset.workspace_id),
    }
    if change_summary is not None:
        version_data["change_summary"] = change_summary
    return version_data


def _create_version_record(
    db: Session,
    *,
    asset: Asset,
    version_number: int,
    base_version_id: str | None,
    payload: dict,
    owner_user_id: str,
    change_summary: str | None = None,
    metadata_json: dict | None = None,
) -> AssetVersion:
    asset.updated_at = utcnow()
    asset_version = AssetVersion(
        asset_id=asset.id,
        version_number=version_number,
        status="draft",
        base_version_id=base_version_id,
        created_by=owner_user_id,
        metadata_json=(
            dict(metadata_json)
            if metadata_json is not None
            else _build_version_data_for_asset(asset, payload, change_summary=change_summary)
        ),
        payload_json=payload,
    )
    db.add(asset_version)
    db.flush()

    _sync_task_input_presets(db, asset_type=asset.asset_type, version_id=asset_version.id, payload=payload)
    return asset_version


def _sync_task_input_presets(db: Session, *, asset_type: str, version_id: str, payload: dict) -> None:
    if asset_type != "task":
        return
    replace_task_input_preset_bindings(
        db,
        asset_version_id=version_id,
        preset_keys=payload.get("input_presets", []),
    )


def serialize_asset_version_payloads(
    db: Session,
    asset_versions: list[AssetVersion],
    *,
    asset_type_by_version_id: dict[str, str] | None = None,
) -> dict[str, dict]:
    if not asset_versions:
        return {}

    payloads: dict[str, dict] = {}
    for asset_version in asset_versions:
        version_id = str(asset_version.id)
        version_payload = asset_version.payload_json or {}
        payloads[version_id] = dict(version_payload) if isinstance(version_payload, dict) else {}

    return payloads


def _restore_payload_for_version(db: Session, *, asset: Asset, source_version: AssetVersion) -> dict:
    return source_version.payload_json or {}


def _get_owned_asset(db: Session, *, asset_id: str, owner_user_id: str) -> Asset:
    asset = (
        db.query(Asset)
        .filter(Asset.id == asset_id, Asset.owner_user_id == owner_user_id)
        .first()
    )
    if asset is None:
        raise LookupError(f"Asset not found: {asset_id}")
    return asset


def _get_current_asset_version(db: Session, *, asset_id: str) -> AssetVersion:
    asset_version = (
        db.query(AssetVersion)
        .filter(AssetVersion.asset_id == asset_id)
        .order_by(AssetVersion.version_number.desc(), AssetVersion.created_at.desc())
        .first()
    )
    if asset_version is None:
        raise LookupError(f"Current asset version not found: {asset_id}")
    return asset_version


def _get_owned_asset_version(db: Session, *, asset_id: str, version_id: str, owner_user_id: str) -> tuple[Asset, AssetVersion]:
    asset = _get_owned_asset(db, asset_id=asset_id, owner_user_id=owner_user_id)
    asset_version = (
        db.query(AssetVersion)
        .filter(AssetVersion.id == version_id, AssetVersion.asset_id == asset.id)
        .first()
    )
    if asset_version is None:
        raise LookupError(f"Asset version not found: {version_id}")
    return asset, asset_version


def _version_delete_conflict_reason(db: Session, *, version_id: str) -> str | None:
    descendant_version = (
        db.query(AssetVersion.id)
        .filter(AssetVersion.base_version_id == version_id)
        .first()
    )
    if descendant_version is not None:
        return "Asset version is referenced by newer asset lineage."

    if db.query(ExecutionBinding.id).filter(ExecutionBinding.subject_version_id == version_id).first() is not None:
        return "Asset version is referenced by execution bindings."

    if db.query(FlowRun.id).filter(FlowRun.flow_version_id == version_id).first() is not None:
        return "Asset version is referenced by flow runs."

    flow_run_execution = (
        db.query(FlowRunExecution.id)
        .join(ExecutionBinding, FlowRunExecution.execution_binding_id == ExecutionBinding.id)
        .filter(ExecutionBinding.subject_version_id == version_id)
        .first()
    )
    if flow_run_execution is not None:
        return "Asset version is referenced by runtime executions."

    return None


def read_asset_with_current_version(db: Session, *, asset_id: str, owner_user_id: str) -> AssetReadModel:
    asset = _get_owned_asset(db, asset_id=asset_id, owner_user_id=owner_user_id)
    return AssetReadModel(asset=asset, current_version=_get_current_asset_version(db, asset_id=asset.id))


def list_asset_versions(db: Session, *, asset_id: str, owner_user_id: str) -> list[AssetVersion]:
    asset = _get_owned_asset(db, asset_id=asset_id, owner_user_id=owner_user_id)
    return (
        db.query(AssetVersion)
        .filter(AssetVersion.asset_id == asset.id)
        .order_by(AssetVersion.version_number.desc(), AssetVersion.created_at.desc())
        .all()
    )


def read_asset_version(db: Session, *, asset_id: str, version_id: str, owner_user_id: str) -> AssetVersion:
    _, asset_version = _get_owned_asset_version(
        db,
        asset_id=asset_id,
        version_id=version_id,
        owner_user_id=owner_user_id,
    )
    return asset_version


def update_asset(db: Session, asset_id: str, payload: AssetUpdate, *, owner_user_id: str) -> AssetReadModel:
    asset = _get_owned_asset(db, asset_id=asset_id, owner_user_id=owner_user_id)
    current_version = _get_current_asset_version(db, asset_id=asset.id)

    if str(current_version.id) != str(payload.base_version_id):
        raise AssetConflictError("Asset has a newer version. Refresh and retry from the latest version.")

    if payload.name is not None:
        asset.name = payload.name
    if payload.description is not None:
        asset.description = payload.description

    normalized_payload = normalize_asset_payload(asset.asset_type, payload.payload)
    try:
        _create_version_record(
            db,
            asset=asset,
            version_number=current_version.version_number + 1,
            base_version_id=str(payload.base_version_id),
            payload=normalized_payload,
            owner_user_id=owner_user_id,
            change_summary=payload.change_summary,
        )
        db.commit()
    except ValueError:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        if _is_asset_version_number_conflict(exc):
            raise AssetConflictError("Asset has a newer version. Refresh and retry from the latest version.") from exc
        raise
    return read_asset_with_current_version(db, asset_id=asset.id, owner_user_id=owner_user_id)


def restore_asset_version(db: Session, asset_id: str, version_id: str, *, owner_user_id: str) -> AssetReadModel:
    asset, source_version = _get_owned_asset_version(
        db,
        asset_id=asset_id,
        version_id=version_id,
        owner_user_id=owner_user_id,
    )
    current_version = _get_current_asset_version(db, asset_id=asset.id)
    source_data = source_version.metadata_json or {}
    asset.name = source_data.get("name", asset.name)
    asset.description = source_data.get("description", asset.description)
    restore_payload = source_version.payload_json or {}
    restore_metadata = dict(source_version.metadata_json or {})
    normalized_payload = normalize_asset_payload(asset.asset_type, restore_payload)
    try:
        _create_version_record(
            db,
            asset=asset,
            version_number=current_version.version_number + 1,
            base_version_id=source_version.id,
            payload=normalized_payload,
            owner_user_id=owner_user_id,
            metadata_json=restore_metadata,
        )
        db.commit()
    except ValueError:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        if _is_asset_version_number_conflict(exc):
            raise AssetConflictError("Asset has a newer version. Refresh and retry from the latest version.") from exc
        raise
    return read_asset_with_current_version(db, asset_id=asset.id, owner_user_id=owner_user_id)


def delete_asset_version(db: Session, asset_id: str, version_id: str, *, owner_user_id: str) -> None:
    asset, asset_version = _get_owned_asset_version(
        db,
        asset_id=asset_id,
        version_id=version_id,
        owner_user_id=owner_user_id,
    )
    current_version = _get_current_asset_version(db, asset_id=asset.id)
    if str(asset_version.id) == str(current_version.id):
        raise AssetConflictError("Cannot delete the current latest version of an asset.")

    version_count = db.query(AssetVersion).filter(AssetVersion.asset_id == asset.id).count()
    if version_count <= 1:
        raise AssetConflictError("Cannot delete the final remaining version of an asset.")

    conflict_reason = _version_delete_conflict_reason(db, version_id=asset_version.id)
    if conflict_reason is not None:
        raise AssetConflictError(conflict_reason)

    db.delete(asset_version)
    db.commit()


def _asset_delete_conflict_reason(db: Session, *, asset_id: str, version_ids: list[str]) -> str | None:
    row = db.execute(
        text(
            """
            SELECT reason
            FROM (
                SELECT 'Asset is referenced by version links.' AS reason
                WHERE EXISTS (
                    SELECT 1
                    FROM version_links
                    WHERE parent_version_id IN (SELECT id FROM asset_versions WHERE asset_id = :asset_id)
                       OR child_version_id IN (SELECT id FROM asset_versions WHERE asset_id = :asset_id)
                )
                UNION ALL
                SELECT 'Asset is referenced by execution bindings.' AS reason
                WHERE EXISTS (
                    SELECT 1
                    FROM execution_bindings
                    WHERE subject_version_id IN (SELECT id FROM asset_versions WHERE asset_id = :asset_id)
                )
                UNION ALL
                SELECT 'Asset is referenced by flow runs.' AS reason
                WHERE EXISTS (
                    SELECT 1
                    FROM flow_runs
                    WHERE flow_version_id IN (SELECT id FROM asset_versions WHERE asset_id = :asset_id)
                )
                UNION ALL
                SELECT 'Asset is referenced by runtime executions.' AS reason
                WHERE EXISTS (
                    SELECT 1
                    FROM flow_run_executions runtime_execution
                    JOIN execution_bindings binding
                      ON binding.id = runtime_execution.execution_binding_id
                    WHERE binding.subject_version_id IN (
                        SELECT id FROM asset_versions WHERE asset_id = :asset_id
                    )
                )
            ) conflicts
            LIMIT 1
            """
        ),
        {"asset_id": asset_id},
    ).first()
    return None if row is None else row[0]


def delete_asset(db: Session, asset_id: str, *, owner_user_id: str) -> None:
    asset = _get_owned_asset(db, asset_id=asset_id, owner_user_id=owner_user_id)
    conflict_reason = _asset_delete_conflict_reason(db, asset_id=str(asset.id), version_ids=[])
    if conflict_reason is not None:
        raise AssetConflictError(conflict_reason)

    db.execute(
        text(
            """
            DELETE FROM version_links
            WHERE parent_version_id IN (SELECT id FROM asset_versions WHERE asset_id = :asset_id)
               OR child_version_id IN (SELECT id FROM asset_versions WHERE asset_id = :asset_id)
            """
        ),
        {"asset_id": str(asset.id)},
    )
    db.execute(
        text(
            """
            DELETE FROM version_tools
            WHERE version_id IN (SELECT id FROM asset_versions WHERE asset_id = :asset_id)
            """
        ),
        {"asset_id": str(asset.id)},
    )
    db.execute(
        text(
            """
            DELETE FROM version_skills
            WHERE version_id IN (SELECT id FROM asset_versions WHERE asset_id = :asset_id)
            """
        ),
        {"asset_id": str(asset.id)},
    )
    if asset.asset_type == "task":
        db.execute(
            text(
                """
                DELETE FROM task_input_preset_bindings
                WHERE asset_version_id IN (SELECT id FROM asset_versions WHERE asset_id = :asset_id)
                """
            ),
            {"asset_id": str(asset.id)},
        )
    db.execute(
        text(
            """
            DELETE FROM asset_versions
            WHERE asset_id = :asset_id
            """
        ),
        {"asset_id": str(asset.id)},
    )
    db.execute(
        text(
            "DELETE FROM asset_shares "
            "WHERE asset_id = :asset_id"
        ),
        {"asset_id": str(asset.id)},
    )
    db.execute(
        text(
            "DELETE FROM asset_imports "
            "WHERE source_asset_id = :asset_id OR imported_asset_id = :asset_id"
        ),
        {"asset_id": str(asset.id)},
    )
    db.execute(
        text(
            "UPDATE assets "
            "SET source_asset_id = NULL "
            "WHERE source_asset_id = :asset_id"
        ),
        {"asset_id": str(asset.id)},
    )
    db.execute(
        text(
            "UPDATE assets "
            "SET root_asset_id = NULL "
            "WHERE root_asset_id = :asset_id"
        ),
        {"asset_id": str(asset.id)},
    )
    db.delete(asset)
    db.commit()


def create_asset(db: Session, payload: AssetCreate, *, owner_user_id: str) -> dict:
    workspace_id = payload.workspace_id or uuid.UUID("00000000-0000-0000-0000-000000000000")

    asset = Asset(
        asset_type=payload.type,
        workspace_id=str(workspace_id),
        owner_user_id=owner_user_id,
        name=payload.name,
        description=payload.description,
    )
    db.add(asset)
    db.flush()

    try:
        asset_version = _create_version_record(
            db,
            asset=asset,
            version_number=1,
            base_version_id=None,
            payload=payload.normalized_payload,
            owner_user_id=owner_user_id,
        )
        db.commit()
    except ValueError:
        db.rollback()
        raise
    db.refresh(asset)
    db.refresh(asset_version)

    return {
        "asset": asset,
        "asset_version": asset_version,
        "description": payload.description,
        "workspace_id": payload.workspace_id,
    }


def create_next_crew_version_with_snapshot(
    db: Session,
    *,
    crew_asset_id: str,
    owner_user_id: str,
    runtime_snapshot_json: dict,
    base_version_id: str | None = None,
    commit: bool = True,
) -> dict:
    asset = _get_owned_asset(db, asset_id=crew_asset_id, owner_user_id=owner_user_id)
    if asset.asset_type != "crew":
        raise ValueError(f"Asset is not a crew asset: {crew_asset_id}")

    current_version = _get_current_asset_version(db, asset_id=asset.id)
    if base_version_id is not None and str(base_version_id) != str(current_version.id):
        raise AssetConflictError("Asset has a newer version. Refresh and retry from the latest version.")

    normalized_payload = normalize_asset_payload(
        asset.asset_type,
        _restore_payload_for_version(db, asset=asset, source_version=current_version),
    )

    try:
        asset_version = _create_version_record(
            db,
            asset=asset,
            version_number=current_version.version_number + 1,
            base_version_id=base_version_id or current_version.id,
            payload=normalized_payload,
            owner_user_id=owner_user_id,
            change_summary="publish:crew_draft",
        )
        archive_published_versions_for_asset(db, asset_id=asset.id)
        asset_version.status = "published"
        runtime_snapshot = upsert_asset_runtime_snapshot(
            db,
            version_id=str(asset_version.id),
            runtime_snapshot_json=runtime_snapshot_json,
        )
        if commit:
            db.commit()
    except ValueError:
        if commit:
            db.rollback()
        raise
    except IntegrityError as exc:
        if commit:
            db.rollback()
        if _is_asset_version_number_conflict(exc):
            raise AssetConflictError("Asset has a newer version. Refresh and retry from the latest version.") from exc
        raise

    if commit:
        db.refresh(asset)
        db.refresh(asset_version)
        db.refresh(runtime_snapshot)
    return {
        "asset": asset,
        "asset_version": asset_version,
        "runtime_snapshot": runtime_snapshot,
    }


def create_next_flow_version_with_snapshot(
    db: Session,
    *,
    flow_asset_id: str,
    owner_user_id: str,
    runtime_snapshot_json: dict,
    base_version_id: str | None = None,
    commit: bool = True,
) -> dict:
    asset = _get_owned_asset(db, asset_id=flow_asset_id, owner_user_id=owner_user_id)
    if asset.asset_type != "flow":
        raise ValueError(f"Asset is not a flow asset: {flow_asset_id}")

    current_version = _get_current_asset_version(db, asset_id=asset.id)
    if base_version_id is not None and str(base_version_id) != str(current_version.id):
        raise AssetConflictError("Asset has a newer version. Refresh and retry from the latest version.")

    normalized_payload = normalize_asset_payload(
        asset.asset_type,
        _restore_payload_for_version(db, asset=asset, source_version=current_version),
    )

    try:
        asset_version = _create_version_record(
            db,
            asset=asset,
            version_number=current_version.version_number + 1,
            base_version_id=base_version_id or current_version.id,
            payload=normalized_payload,
            owner_user_id=owner_user_id,
            change_summary="publish:flow_draft",
        )
        archive_published_versions_for_asset(db, asset_id=asset.id)
        asset_version.status = "published"
        runtime_snapshot = upsert_asset_runtime_snapshot(
            db,
            version_id=str(asset_version.id),
            runtime_snapshot_json=runtime_snapshot_json,
        )
        if commit:
            db.commit()
    except ValueError:
        if commit:
            db.rollback()
        raise
    except IntegrityError as exc:
        if commit:
            db.rollback()
        if _is_asset_version_number_conflict(exc):
            raise AssetConflictError("Asset has a newer version. Refresh and retry from the latest version.") from exc
        raise

    if commit:
        db.refresh(asset)
        db.refresh(asset_version)
        db.refresh(runtime_snapshot)
    return {
        "asset": asset,
        "asset_version": asset_version,
        "runtime_snapshot": runtime_snapshot,
    }


def create_next_flow_draft_version(
    db: Session,
    *,
    flow_asset_id: str,
    owner_user_id: str,
    base_version_id: str,
    commit: bool = True,
) -> dict:
    asset = _get_owned_asset(db, asset_id=flow_asset_id, owner_user_id=owner_user_id)
    if asset.asset_type != "flow":
        raise ValueError(f"Asset is not a flow asset: {flow_asset_id}")

    current_version = _get_current_asset_version(db, asset_id=asset.id)
    if str(base_version_id) != str(current_version.id):
        raise AssetConflictError("Asset has a newer version. Refresh and retry from the latest version.")

    normalized_payload = normalize_asset_payload(
        asset.asset_type,
        _restore_payload_for_version(db, asset=asset, source_version=current_version),
    )
    metadata_json = dict(current_version.metadata_json or {})
    metadata_json["change_summary"] = "draft:flow_graph"

    try:
        asset_version = _create_version_record(
            db,
            asset=asset,
            version_number=current_version.version_number + 1,
            base_version_id=base_version_id,
            payload=normalized_payload,
            owner_user_id=owner_user_id,
            metadata_json=metadata_json,
        )
        if commit:
            db.commit()
    except ValueError:
        if commit:
            db.rollback()
        raise
    except IntegrityError as exc:
        if commit:
            db.rollback()
        if _is_asset_version_number_conflict(exc):
            raise AssetConflictError("Asset has a newer version. Refresh and retry from the latest version.") from exc
        raise

    if commit:
        db.refresh(asset)
        db.refresh(asset_version)
    return {"asset": asset, "asset_version": asset_version}
