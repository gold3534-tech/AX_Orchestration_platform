from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.core.database import get_db
from api.db.models import AssetRuntimeSnapshot, AssetVersion, CrewVersionDraft
from api.dependencies import get_current_user
from api.schemas.crew_graph import CrewGraphDocument
from api.schemas.runtime import AuthenticatedUser
from api.services.assets import AssetConflictError, serialize_asset_version_payloads
from api.services.crew_graphs import (
    get_crew_draft,
    publish_crew_draft,
    save_crew_draft,
    validate_crew_draft,
)

router = APIRouter(prefix="/api/crew-graphs", tags=["crew-graphs"])


class CrewDraftSaveRequest(BaseModel):
    graph: CrewGraphDocument


class CrewDraftResponseBody(BaseModel):
    id: str
    crew_asset_id: str
    base_version_id: str | None = None
    graph: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)
    last_test_validation: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CrewDraftEnvelope(BaseModel):
    draft: CrewDraftResponseBody | None = None


class CrewPublishedVersionResponse(BaseModel):
    id: str
    asset_id: str
    version_no: int
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)
    runtime_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class CrewPublishResponse(BaseModel):
    version: CrewPublishedVersionResponse
    already_published: bool = False


def _serialize_draft(draft: CrewVersionDraft) -> CrewDraftEnvelope:
    return CrewDraftEnvelope(
        draft=CrewDraftResponseBody(
            id=str(draft.id),
            crew_asset_id=str(draft.crew_asset_id),
            base_version_id=None if draft.base_version_id is None else str(draft.base_version_id),
            graph=draft.graph_json or {},
            validation=draft.validation_json or {},
            last_test_validation=draft.last_test_validation_json or {},
            created_at=draft.created_at,
            updated_at=draft.updated_at,
        )
    )


def _serialize_published_version(
    db: Session,
    *,
    asset_version: AssetVersion,
    runtime_snapshot: AssetRuntimeSnapshot,
    already_published: bool = False,
) -> CrewPublishResponse:
    payload = serialize_asset_version_payloads(
        db,
        [asset_version],
        asset_type_by_version_id={str(asset_version.id): "crew"},
    ).get(str(asset_version.id), {})
    return CrewPublishResponse(
        version=CrewPublishedVersionResponse(
            id=str(asset_version.id),
            asset_id=str(asset_version.asset_id),
            version_no=asset_version.version_number,
            status=asset_version.status,
            payload=payload,
            runtime_snapshot_json=runtime_snapshot.runtime_snapshot_json or {},
            created_at=asset_version.created_at,
        ),
        already_published=already_published,
    )


@router.get("/{crew_asset_id}/draft", response_model=CrewDraftEnvelope)
def get_draft_route(
    crew_asset_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        draft = get_crew_draft(
            db,
            crew_asset_id=crew_asset_id,
            owner_user_id=current_user["id"],
        )
    except LookupError as exc:
        if str(exc).startswith("Crew draft not found:"):
            return CrewDraftEnvelope(draft=None)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return _serialize_draft(draft)


@router.put("/{crew_asset_id}/draft", response_model=CrewDraftEnvelope)
def save_draft_route(
    crew_asset_id: str,
    payload: CrewDraftSaveRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        draft = save_crew_draft(
            db,
            crew_asset_id=crew_asset_id,
            owner_user_id=current_user["id"],
            graph=payload.graph.model_dump(mode="json"),
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    return _serialize_draft(draft)


@router.post("/{crew_asset_id}/validate", response_model=dict[str, Any])
def validate_draft_route(
    crew_asset_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        return validate_crew_draft(
            db,
            crew_asset_id=crew_asset_id,
            owner_user_id=current_user["id"],
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.post("/{crew_asset_id}/publish", response_model=CrewPublishResponse)
def publish_draft_route(
    crew_asset_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        published = publish_crew_draft(
            db,
            crew_asset_id=crew_asset_id,
            owner_user_id=current_user["id"],
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AssetConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    return _serialize_published_version(
        db,
        asset_version=published["asset_version"],
        runtime_snapshot=published["runtime_snapshot"],
        already_published=bool(published.get("already_published")),
    )
