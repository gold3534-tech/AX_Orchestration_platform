from copy import deepcopy
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.db.models import AssetRuntimeSnapshot, AssetVersion, CrewVersionDraft
from api.runtime.loaders import CrewGraphLoader
from api.services.assets import (
    AssetConflictError,
    create_next_crew_version_with_snapshot,
    read_asset_with_current_version,
    snapshots_equal,
)
from api.services.crew_tool_hydration import hydrate_crew_graph_tools

_CREW_DRAFT_OWNER_UNIQUE_CONSTRAINT = "uq_crew_version_drafts_owner_asset"


def _read_owned_crew_asset(db: Session, *, crew_asset_id: str, owner_user_id: str):
    asset_read_model = read_asset_with_current_version(
        db,
        asset_id=crew_asset_id,
        owner_user_id=owner_user_id,
    )
    if asset_read_model.asset.asset_type != "crew":
        raise ValueError(f"Asset is not a crew asset: {crew_asset_id}")
    return asset_read_model


def _current_published_crew_version(
    db: Session, *, crew_asset_id: str, owner_user_id: str
) -> tuple[AssetVersion, AssetRuntimeSnapshot] | None:
    asset_version = (
        db.query(AssetVersion)
        .filter(
            AssetVersion.asset_id == crew_asset_id,
            AssetVersion.status == "published",
            AssetVersion.created_by == owner_user_id,
        )
        .order_by(AssetVersion.version_number.desc(), AssetVersion.created_at.desc())
        .first()
    )
    if asset_version is None:
        return None

    runtime_snapshot = db.get(AssetRuntimeSnapshot, asset_version.id)
    if runtime_snapshot is None:
        return None
    return asset_version, runtime_snapshot


def _is_crew_draft_owner_conflict(exc: IntegrityError) -> bool:
    orig = exc.orig
    diag = getattr(orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    if constraint_name == _CREW_DRAFT_OWNER_UNIQUE_CONSTRAINT:
        return True

    message = str(orig).lower()
    return (
        _CREW_DRAFT_OWNER_UNIQUE_CONSTRAINT in message
        or "unique constraint failed: crew_version_drafts.crew_asset_id, crew_version_drafts.owner_user_id" in message
        or (
            "duplicate key value violates unique constraint" in message
            and _CREW_DRAFT_OWNER_UNIQUE_CONSTRAINT in message
        )
    )


def _get_or_create_draft(
    db: Session,
    *,
    crew_asset_id: str,
    owner_user_id: str,
    asset_read_model: Any | None = None,
) -> CrewVersionDraft:
    if asset_read_model is None:
        asset_read_model = _read_owned_crew_asset(
            db,
            crew_asset_id=crew_asset_id,
            owner_user_id=owner_user_id,
        )
    draft = (
        db.query(CrewVersionDraft)
        .filter(
            CrewVersionDraft.crew_asset_id == crew_asset_id,
            CrewVersionDraft.owner_user_id == owner_user_id,
        )
        .one_or_none()
    )
    if draft is not None:
        # Drafts are tied to a crew version lineage. Normal crew version bumps (e.g. updating runtime settings)
        # should not strand the user with a permanently-stale base version.
        current_version_id = str(asset_read_model.current_version.id)
        if draft.base_version_id is None or str(draft.base_version_id) != current_version_id:
            draft.base_version_id = current_version_id
        return draft

    return CrewVersionDraft(
        crew_asset_id=asset_read_model.asset.id,
        base_version_id=asset_read_model.current_version.id,
        owner_user_id=owner_user_id,
        graph_json={},
        validation_json={},
        last_test_validation_json={},
    )


def _normalize_graph_route_crew(graph: dict[str, Any], asset_read_model: Any) -> dict[str, Any]:
    normalized = deepcopy(graph)
    route_asset_id = str(asset_read_model.asset.id)
    current_version_id = str(asset_read_model.current_version.id)
    nodes = normalized.get("nodes") if isinstance(normalized.get("nodes"), list) else []
    crew_nodes = [
        node
        for node in nodes
        if isinstance(node, dict) and node.get("type") == "crew"
    ]
    if len(crew_nodes) != 1:
        raise ValueError("Crew graph is invalid: exactly one Crew node is required.")

    crew_data = crew_nodes[0].get("data") if isinstance(crew_nodes[0].get("data"), dict) else {}
    crew_asset_id = crew_data.get("assetId")
    if crew_asset_id is not None and crew_asset_id != route_asset_id:
        raise ValueError("Crew graph Crew node must match route Crew asset.")
    crew_data["assetId"] = route_asset_id
    crew_data["versionId"] = current_version_id
    crew_nodes[0]["data"] = crew_data

    entities = normalized.get("entities") if isinstance(normalized.get("entities"), dict) else {}
    crew_entities = entities.get("crews") if isinstance(entities.get("crews"), dict) else {}
    if len(crew_entities) > 1:
        raise ValueError("Crew graph Crew entity must match route Crew asset.")

    if crew_entities:
        crew_entity = next(iter(crew_entities.values()))
        if not isinstance(crew_entity, dict):
            raise ValueError("Crew graph Crew entity must match route Crew asset.")
        entity_asset_id = crew_entity.get("asset_id")
        if entity_asset_id is not None and entity_asset_id != route_asset_id:
            raise ValueError("Crew graph Crew entity must match route Crew asset.")

    entities["crews"] = {
        current_version_id: {
            "version_id": current_version_id,
            "asset_id": route_asset_id,
            "version_no": asset_read_model.current_version.version_number,
            "name": asset_read_model.asset.name,
            "description": asset_read_model.asset.description,
            "status": asset_read_model.current_version.status,
            "payload": asset_read_model.current_version.payload_json or {},
        }
    }
    normalized["entities"] = entities
    return normalized


def _snapshots_equal_for_route_crew(left: dict | None, right: dict | None) -> bool:
    left_snapshot = deepcopy(left or {})
    right_snapshot = deepcopy(right or {})
    left_crew = left_snapshot.get("runtime_crew") if isinstance(left_snapshot, dict) else None
    right_crew = right_snapshot.get("runtime_crew") if isinstance(right_snapshot, dict) else None
    if (
        isinstance(left_crew, dict)
        and isinstance(right_crew, dict)
        and left_crew.get("asset_id") == right_crew.get("asset_id")
    ):
        left_crew["version_id"] = right_crew.get("version_id")
    return snapshots_equal(left_snapshot, right_snapshot)


def get_crew_draft(
    db: Session,
    *,
    crew_asset_id: str,
    owner_user_id: str,
) -> CrewVersionDraft:
    _read_owned_crew_asset(db, crew_asset_id=crew_asset_id, owner_user_id=owner_user_id)
    draft = (
        db.query(CrewVersionDraft)
        .filter(
            CrewVersionDraft.crew_asset_id == crew_asset_id,
            CrewVersionDraft.owner_user_id == owner_user_id,
        )
        .one_or_none()
    )
    if draft is None:
        raise LookupError(f"Crew draft not found: {crew_asset_id}")
    return draft


def _commit_and_refresh_draft(db: Session, draft: CrewVersionDraft) -> CrewVersionDraft:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(draft)
    return draft


def save_crew_draft(
    db: Session,
    *,
    crew_asset_id: str,
    owner_user_id: str,
    graph: dict[str, Any],
) -> CrewVersionDraft:
    asset_read_model = _read_owned_crew_asset(
        db,
        crew_asset_id=crew_asset_id,
        owner_user_id=owner_user_id,
    )
    graph = _normalize_graph_route_crew(graph, asset_read_model)
    CrewGraphLoader().validate_draft_graph(graph)
    draft = _get_or_create_draft(
        db,
        crew_asset_id=crew_asset_id,
        owner_user_id=owner_user_id,
        asset_read_model=asset_read_model,
    )
    draft.graph_json = graph
    draft.validation_json = {}
    draft.last_test_validation_json = {}
    db.add(draft)

    try:
        return _commit_and_refresh_draft(db, draft)
    except IntegrityError as exc:
        if not _is_crew_draft_owner_conflict(exc):
            raise

    draft = get_crew_draft(
        db,
        crew_asset_id=crew_asset_id,
        owner_user_id=owner_user_id,
    )
    draft.graph_json = graph
    draft.validation_json = {}
    draft.last_test_validation_json = {}
    db.add(draft)
    return _commit_and_refresh_draft(db, draft)


def validate_crew_draft(
    db: Session,
    *,
    crew_asset_id: str,
    owner_user_id: str,
) -> dict[str, Any]:
    draft = get_crew_draft(
        db,
        crew_asset_id=crew_asset_id,
        owner_user_id=owner_user_id,
    )
    asset_read_model = _read_owned_crew_asset(
        db,
        crew_asset_id=crew_asset_id,
        owner_user_id=owner_user_id,
    )
    graph = hydrate_crew_graph_tools(db, draft.graph_json)
    graph = _normalize_graph_route_crew(graph, asset_read_model)
    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)
    draft.last_test_validation_json = snapshot
    db.add(draft)
    _commit_and_refresh_draft(db, draft)
    return snapshot


def publish_crew_draft(
    db: Session,
    *,
    crew_asset_id: str,
    owner_user_id: str,
) -> dict[str, Any]:
    # We retry once to handle a narrow race where the crew version changes between syncing the draft
    # base_version_id and creating the next published version.
    for attempt in range(2):
        draft = get_crew_draft(
            db,
            crew_asset_id=crew_asset_id,
            owner_user_id=owner_user_id,
        )
        asset_read_model = _read_owned_crew_asset(
            db,
            crew_asset_id=crew_asset_id,
            owner_user_id=owner_user_id,
        )
        graph = hydrate_crew_graph_tools(db, draft.graph_json)
        graph = _normalize_graph_route_crew(graph, asset_read_model)
        snapshot = CrewGraphLoader().build_runtime_snapshot(graph)
        draft.validation_json = snapshot
        draft.last_test_validation_json = snapshot

        current_published = _current_published_crew_version(
            db,
            crew_asset_id=crew_asset_id,
            owner_user_id=owner_user_id,
        )
        if current_published is not None:
            published_asset_version, published_runtime_snapshot = current_published
            if _snapshots_equal_for_route_crew(published_runtime_snapshot.runtime_snapshot_json, snapshot):
                draft.validation_json = snapshot
                draft.last_test_validation_json = snapshot
                draft.base_version_id = published_asset_version.id
                db.add(draft)
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
                db.refresh(draft)
                db.refresh(published_asset_version)
                db.refresh(published_runtime_snapshot)
                return {
                    "asset": published_asset_version.asset,
                    "asset_version": published_asset_version,
                    "runtime_snapshot": published_runtime_snapshot,
                    "already_published": True,
                }

        current_version_id = str(asset_read_model.current_version.id)
        if draft.base_version_id is None or str(draft.base_version_id) != current_version_id:
            draft.base_version_id = current_version_id

        db.add(draft)

        try:
            published = create_next_crew_version_with_snapshot(
                db,
                crew_asset_id=crew_asset_id,
                owner_user_id=owner_user_id,
                runtime_snapshot_json=snapshot,
                base_version_id=str(draft.base_version_id) if draft.base_version_id is not None else None,
                commit=False,
            )
            draft.base_version_id = published["asset_version"].id
            db.add(draft)
            db.commit()
            break
        except AssetConflictError:
            db.rollback()
            if attempt == 0:
                continue
            raise
        except (IntegrityError, LookupError, ValueError):
            db.rollback()
            raise

    db.refresh(draft)
    db.refresh(published["asset"])
    db.refresh(published["asset_version"])
    db.refresh(published["runtime_snapshot"])
    published["already_published"] = False
    return published
