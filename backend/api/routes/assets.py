from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_
from sqlalchemy.orm import Session

from api.core.database import get_db
from api.dependencies import get_current_user
from api.db.models import Asset, AssetVersion
from api.schemas.assets import (
    AssetCreate,
    AssetResponse,
    AssetRestoreResponse,
    AssetUpdate,
    AssetVersionResponse,
)
from api.services.assets import (
    AssetConflictError,
    create_asset,
    delete_asset as delete_asset_service,
    delete_asset_version,
    list_asset_versions,
    read_asset_version,
    read_asset_with_current_version,
    restore_asset_version as restore_asset_version_service,
    serialize_asset_version_payloads,
    update_asset,
)

router = APIRouter(prefix="/api/assets", tags=["assets"])
_ZERO_UUID = "00000000-0000-0000-0000-000000000000"


def _serialize_asset(asset: Asset, current_version: AssetVersion, *, payload: dict) -> AssetResponse:
    workspace_id = None if str(asset.workspace_id) == _ZERO_UUID else asset.workspace_id
    return AssetResponse(
        id=asset.id,
        type=asset.asset_type,
        name=asset.name,
        description=asset.description,
        workspace_id=workspace_id,
        current_version={
            "id": current_version.id,
            "version_no": current_version.version_number,
            "status": current_version.status,
            "payload": payload,
            "created_at": current_version.created_at,
            "updated_at": current_version.created_at,
        },
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


def _serialize_asset_version(asset_version: AssetVersion, *, payload: dict) -> AssetVersionResponse:
    return AssetVersionResponse(
        id=asset_version.id,
        asset_id=asset_version.asset_id,
        version_no=asset_version.version_number,
        status=asset_version.status,
        payload=payload,
        created_at=asset_version.created_at,
    )


@router.get("", response_model=list[AssetResponse])
def list_assets(
    type: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    query = db.query(Asset).filter(Asset.owner_user_id == current_user["id"])
    if type is not None:
        query = query.filter(Asset.asset_type == type)

    assets = query.order_by(Asset.created_at.asc(), Asset.id.asc()).all()
    asset_ids = [str(asset.id) for asset in assets]
    current_versions = (
        db.query(AssetVersion)
        .join(
            Asset,
            and_(
                Asset.id == AssetVersion.asset_id,
                Asset.owner_user_id == current_user["id"],
            ),
        )
        .filter(AssetVersion.asset_id.in_(asset_ids))
        .order_by(AssetVersion.asset_id.asc(), AssetVersion.version_number.desc(), AssetVersion.created_at.desc())
        .all()
    )
    current_versions_by_asset_id: dict[str, AssetVersion] = {}
    for version in current_versions:
        current_versions_by_asset_id.setdefault(str(version.asset_id), version)

    asset_type_by_version_id = {
        str(version.id): asset.asset_type
        for asset in assets
        if (version := current_versions_by_asset_id.get(str(asset.id))) is not None
    }
    payloads_by_version_id = serialize_asset_version_payloads(
        db,
        list(current_versions_by_asset_id.values()),
        asset_type_by_version_id=asset_type_by_version_id,
    )

    responses: list[AssetResponse] = []
    for asset in assets:
        current_version = current_versions_by_asset_id.get(str(asset.id))
        if current_version is None:
            continue

        responses.append(
            _serialize_asset(
                asset,
                current_version,
                payload=payloads_by_version_id.get(str(current_version.id), {}),
            )
        )

    return responses


@router.post("", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
def create_asset_route(
    payload: AssetCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        created = create_asset(db, payload, owner_user_id=current_user["id"])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    asset = created["asset"]
    asset_version = created["asset_version"]
    payload = serialize_asset_version_payloads(
        db,
        [asset_version],
        asset_type_by_version_id={str(asset_version.id): asset.asset_type},
    ).get(str(asset_version.id), {})
    return _serialize_asset(asset, asset_version, payload=payload)


@router.get("/{asset_id}", response_model=AssetResponse)
def get_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        asset_read_model = read_asset_with_current_version(
            db,
            asset_id=asset_id,
            owner_user_id=current_user["id"],
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    payload = serialize_asset_version_payloads(
        db,
        [asset_read_model.current_version],
        asset_type_by_version_id={str(asset_read_model.current_version.id): asset_read_model.asset.asset_type},
    ).get(str(asset_read_model.current_version.id), {})
    return _serialize_asset(asset_read_model.asset, asset_read_model.current_version, payload=payload)


@router.patch("/{asset_id}", response_model=AssetResponse)
def update_asset_route(
    asset_id: str,
    payload: AssetUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        updated_asset = update_asset(db, asset_id, payload, owner_user_id=current_user["id"])
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AssetConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    payload = serialize_asset_version_payloads(
        db,
        [updated_asset.current_version],
        asset_type_by_version_id={str(updated_asset.current_version.id): updated_asset.asset.asset_type},
    ).get(str(updated_asset.current_version.id), {})
    return _serialize_asset(updated_asset.asset, updated_asset.current_version, payload=payload)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        delete_asset_service(db, asset_id, owner_user_id=current_user["id"])
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AssetConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/{asset_id}/versions", response_model=list[AssetVersionResponse])
def list_asset_versions_route(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        versions = list_asset_versions(db, asset_id=asset_id, owner_user_id=current_user["id"])
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    payloads_by_version_id = serialize_asset_version_payloads(db, versions)
    return [
        _serialize_asset_version(version, payload=payloads_by_version_id.get(str(version.id), {}))
        for version in versions
    ]


@router.get("/{asset_id}/versions/{version_id}", response_model=AssetVersionResponse)
def get_asset_version(
    asset_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        asset_version = read_asset_version(
            db,
            asset_id=asset_id,
            version_id=version_id,
            owner_user_id=current_user["id"],
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    payload = serialize_asset_version_payloads(db, [asset_version]).get(str(asset_version.id), {})
    return _serialize_asset_version(asset_version, payload=payload)


@router.delete("/{asset_id}/versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset_version_route(
    asset_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        delete_asset_version(
            db,
            asset_id=asset_id,
            version_id=version_id,
            owner_user_id=current_user["id"],
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AssetConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{asset_id}/versions/{version_id}/restore", response_model=AssetRestoreResponse)
def restore_asset_version(
    asset_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        restored_asset = restore_asset_version_service(
            db,
            asset_id=asset_id,
            version_id=version_id,
            owner_user_id=current_user["id"],
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AssetConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    payload = serialize_asset_version_payloads(
        db,
        [restored_asset.current_version],
        asset_type_by_version_id={str(restored_asset.current_version.id): restored_asset.asset.asset_type},
    ).get(str(restored_asset.current_version.id), {})
    serialized = _serialize_asset(restored_asset.asset, restored_asset.current_version, payload=payload).model_dump()
    return AssetRestoreResponse(
        **serialized,
        restored_from_version_id=version_id,
    )
