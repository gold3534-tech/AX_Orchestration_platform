from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.core.database import get_db
from api.db.models import AssetRuntimeSnapshot, AssetVersion, FlowVersionDraft
from api.dependencies import get_current_user
from api.schemas.flow_graph import FlowGraphDocument
from api.schemas.runtime import AuthenticatedUser
from api.services.assets import AssetConflictError, serialize_asset_version_payloads
from api.services.flow_graphs import (
    get_flow_draft,
    list_published_crews_for_flow_builder,
    list_published_flows_for_run_page,
    publish_flow_draft,
    run_flow_compatibility_diagnostics,
    run_flow_tool_mock_call_diagnostics,
    save_flow_draft,
    validate_flow_draft,
)

router = APIRouter(prefix="/api/flow-graphs", tags=["flow-graphs"])


class FlowDraftSaveRequest(BaseModel):
    graph: FlowGraphDocument


class FlowCompatibilityDiagnosticRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


class FlowDraftResponseBody(BaseModel):
    id: str
    flow_asset_id: str
    base_version_id: str | None = None
    graph: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)
    last_test_validation: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class FlowDraftEnvelope(BaseModel):
    draft: FlowDraftResponseBody | None = None


class FlowPublishedVersionResponse(BaseModel):
    id: str
    asset_id: str
    version_no: int
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)
    runtime_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class FlowPublishResponse(BaseModel):
    version: FlowPublishedVersionResponse
    already_published: bool = False


class PublishedCrewPickerResponse(BaseModel):
    crews: list[dict[str, Any]] = Field(default_factory=list)


class PublishedFlowPickerResponse(BaseModel):
    flows: list[dict[str, Any]] = Field(default_factory=list)


def _serialize_draft(draft: FlowVersionDraft) -> FlowDraftEnvelope:
    return FlowDraftEnvelope(
        draft=FlowDraftResponseBody(
            id=str(draft.id),
            flow_asset_id=str(draft.flow_asset_id),
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
) -> FlowPublishResponse:
    payload = serialize_asset_version_payloads(
        db,
        [asset_version],
        asset_type_by_version_id={str(asset_version.id): "flow"},
    ).get(str(asset_version.id), {})
    return FlowPublishResponse(
        version=FlowPublishedVersionResponse(
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


@router.get("/published-crews", response_model=PublishedCrewPickerResponse)
def list_published_crews_route(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    return PublishedCrewPickerResponse(
        crews=list_published_crews_for_flow_builder(db, owner_user_id=current_user["id"])
    )


@router.get("/published-flows", response_model=PublishedFlowPickerResponse)
def list_published_flows_route(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    return PublishedFlowPickerResponse(
        flows=list_published_flows_for_run_page(db, owner_user_id=current_user["id"])
    )


@router.get("/{flow_asset_id}/draft", response_model=FlowDraftEnvelope)
def get_draft_route(
    flow_asset_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        draft = get_flow_draft(
            db,
            flow_asset_id=flow_asset_id,
            owner_user_id=current_user["id"],
        )
    except LookupError as exc:
        if str(exc).startswith("Flow draft not found:"):
            return FlowDraftEnvelope(draft=None)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    return _serialize_draft(draft)


@router.put("/{flow_asset_id}/draft", response_model=FlowDraftEnvelope)
def save_draft_route(
    flow_asset_id: str,
    payload: FlowDraftSaveRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        draft = save_flow_draft(
            db,
            flow_asset_id=flow_asset_id,
            owner_user_id=current_user["id"],
            graph=payload.graph.model_dump(mode="json"),
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AssetConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    return _serialize_draft(draft)


@router.post("/{flow_asset_id}/validate", response_model=dict[str, Any])
def validate_draft_route(
    flow_asset_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        return validate_flow_draft(
            db,
            flow_asset_id=flow_asset_id,
            owner_user_id=current_user["id"],
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.post("/{flow_asset_id}/diagnostics/compatibility", response_model=dict[str, Any])
def compatibility_diagnostics_route(
    flow_asset_id: str,
    payload: FlowCompatibilityDiagnosticRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        return run_flow_compatibility_diagnostics(
            db,
            flow_asset_id=flow_asset_id,
            owner_user_id=current_user["id"],
            inputs=payload.inputs,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.post("/{flow_asset_id}/diagnostics/tool-mock-call", response_model=dict[str, Any])
def tool_mock_call_diagnostics_route(
    flow_asset_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        return run_flow_tool_mock_call_diagnostics(
            db,
            flow_asset_id=flow_asset_id,
            owner_user_id=current_user["id"],
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.post("/{flow_asset_id}/publish", response_model=FlowPublishResponse)
def publish_draft_route(
    flow_asset_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        published = publish_flow_draft(
            db,
            flow_asset_id=flow_asset_id,
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
