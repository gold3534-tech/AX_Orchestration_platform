import asyncio
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from api.core.database import get_db
from api.db.models import FlowRunEvent, RunArtifact
from api.dependencies import authenticate_access_token, get_current_user
from api.runtime.credential_resolver import CredentialResolutionError
from api.runtime.linear_flow_runtime import UnsupportedGraphError
from api.runtime.provider_media_urls import absolute_http_provider_media_url
from api.schemas.runtime import AuthenticatedUser
from api.services.runs import (
    FlowRuntimeSnapshotError,
    HumanFeedbackConflictError,
    HumanFeedbackValidationError,
    create_flow_run_record,
    enqueue_flow_run_execution,
    get_flow_run_detail,
    list_flow_run_events,
    submit_human_feedback,
)
from api.runtime.flow_snapshot_executor import FlowSnapshotExecutor

router = APIRouter(tags=["runs"])
STREAM_EVENT_OVERLAP = timedelta(seconds=5)


class FlowRunCreateRequest(BaseModel):
    flow_version_id: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    capture_agent_execution_logs: bool = True

    @field_validator("flow_version_id")
    @classmethod
    def flow_version_id_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("flow_version_id must not be empty")
        return value


class FlowRunResponse(BaseModel):
    id: str
    flow_version_id: str
    status: str
    output_json: dict[str, Any] | None = None


class HumanFeedbackRequestResponse(BaseModel):
    id: str
    run_id: str
    node_id: str
    status: str
    prompt_json: dict[str, Any]
    response_json: dict[str, Any]
    created_at: str
    responded_at: str | None = None
    attempt_number: int | None = None
    expires_at: str | None = None
    resolved_by: str | None = None
    idempotency_key: str | None = None


class FlowRunStateSnapshotResponse(BaseModel):
    id: str
    run_id: str
    node_id: str | None
    state_json: dict[str, Any]
    created_at: str


class FlowRunDetailResponse(BaseModel):
    id: str
    flow_version_id: str
    status: str
    input_json: dict[str, Any]
    output_json: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    error_message: str | None = None
    latest_state_snapshot: FlowRunStateSnapshotResponse | None = None
    pending_human_feedback_request: HumanFeedbackRequestResponse | None = None


class HumanFeedbackSubmitRequest(BaseModel):
    request_id: str
    outcome: Literal["approved", "needs_revision", "rejected"]
    feedback: str = ""
    idempotency_key: str | None = None

    @field_validator("idempotency_key")
    @classmethod
    def empty_idempotency_key_as_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class FlowRunEventsResponse(BaseModel):
    events: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/api/flow-runs", response_model=FlowRunResponse, status_code=status.HTTP_201_CREATED)
def create_flow_run_route(
    payload: FlowRunCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        run = create_flow_run_record(
            db,
            flow_version_id=payload.flow_version_id,
            owner_user_id=current_user["id"],
            inputs=payload.inputs,
            capture_agent_execution_logs=payload.capture_agent_execution_logs,
        )
        enqueue_flow_run_execution(
            background_tasks,
            run_id=str(run.id),
            owner_user_id=current_user["id"],
        )
    except FlowRuntimeSnapshotError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except HumanFeedbackValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except CredentialResolutionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except UnsupportedGraphError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return FlowRunResponse(
        id=str(run.id),
        flow_version_id=str(run.flow_version_id),
        status=run.status,
        output_json=run.output_json,
    )


@router.get("/api/flow-runs/{run_id}", response_model=FlowRunDetailResponse)
def get_flow_run_detail_route(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        detail = get_flow_run_detail(db, run_id=run_id, owner_user_id=current_user["id"])
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    run = detail["run"]
    snapshot = detail["latest_state_snapshot"]
    request = detail["pending_human_feedback_request"]
    return FlowRunDetailResponse(
        id=str(run.id),
        flow_version_id=str(run.flow_version_id),
        status=run.status,
        input_json=run.input_json or {},
        output_json=run.output_json,
        artifacts=detail.get("artifacts") or [],
        error_message=run.error_message,
        latest_state_snapshot=None
        if snapshot is None
        else FlowRunStateSnapshotResponse(
            id=str(snapshot.id),
            run_id=str(snapshot.run_id),
            node_id=snapshot.node_id,
            state_json=snapshot.state_json or {},
            created_at=snapshot.created_at.isoformat(),
        ),
        pending_human_feedback_request=None
        if request is None
        else HumanFeedbackRequestResponse(
            id=str(request.id),
            run_id=str(request.run_id),
            node_id=request.node_id,
            status=request.status,
            prompt_json=(
                detail.get("pending_human_feedback_prompt_json")
                or request.prompt_json
                or {}
            ),
            response_json=request.response_json or {},
            created_at=request.created_at.isoformat(),
            responded_at=request.responded_at.isoformat() if request.responded_at else None,
            attempt_number=request.attempt_number,
            expires_at=request.expires_at.isoformat() if request.expires_at else None,
            resolved_by=str(request.resolved_by) if request.resolved_by else None,
            idempotency_key=request.idempotency_key,
        ),
    )


@router.post("/api/flow-runs/{run_id}/human-feedback", response_model=FlowRunResponse)
def submit_human_feedback_route(
    run_id: str,
    payload: HumanFeedbackSubmitRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        run = submit_human_feedback(
            db,
            run_id=run_id,
            owner_user_id=current_user["id"],
            request_id=payload.request_id,
            outcome=payload.outcome,
            feedback=payload.feedback,
            idempotency_key=payload.idempotency_key,
        )
    except HumanFeedbackConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except HumanFeedbackValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except CredentialResolutionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except UnsupportedGraphError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return FlowRunResponse(
        id=str(run.id),
        flow_version_id=str(run.flow_version_id),
        status=run.status,
        output_json=run.output_json,
    )


@router.get("/api/flow-runs/{run_id}/events", response_model=FlowRunEventsResponse)
def list_flow_run_events_route(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    # Validate ownership and attempt to load the published runtime snapshot
    try:
        detail = get_flow_run_detail(db, run_id=run_id, owner_user_id=current_user["id"])
        run = detail["run"]
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    try:
        published_snapshot = FlowSnapshotExecutor(db).load_published_snapshot(
            flow_version_id=str(run.flow_version_id), owner_user_id=current_user["id"]
        )
    except Exception:
        published_snapshot = None

    events = list_flow_run_events(db, run_id=run_id, owner_user_id=current_user["id"])

    def _resolve_agent_info(snapshot: dict[str, Any] | None, agent_version_id: str | None):
        if not snapshot or not agent_version_id:
            return None
        entities = snapshot.get("entities") if isinstance(snapshot, dict) else None
        if not isinstance(entities, dict):
            return None
        crews = entities.get("crews")
        if not isinstance(crews, dict):
            return None
        for crew in crews.values():
            try:
                runtime = crew.get("runtime_snapshot_json") if isinstance(crew, dict) else None
                runtime_agents = runtime.get("runtime_agents") if isinstance(runtime, dict) else None
                if isinstance(runtime_agents, dict) and agent_version_id in runtime_agents:
                    agent = runtime_agents[agent_version_id]
                    if isinstance(agent, dict):
                        name = agent.get("agent_name") or agent.get("name")
                        role = agent.get("role")
                        return {"agent_name": name, "agent_role": role}
            except Exception:
                continue
        return None

    out_events: list[dict[str, Any]] = []
    for event in events:
        payload = dict(event.event_payload_json or {})
        agent_ver = None
        if isinstance(payload.get("agent_id"), str):
            agent_ver = payload.get("agent_id")
        elif isinstance(payload.get("agent_version_id"), str):
            agent_ver = payload.get("agent_version_id")

        info = _resolve_agent_info(published_snapshot, agent_ver)
        if info:
            # don't overwrite existing keys if present
            payload.setdefault("agent_name", info.get("agent_name"))
            payload.setdefault("agent_role", info.get("agent_role"))

        out_events.append(
            {
                "id": str(event.id),
                "node_id": event.node_id,
                "event_type": event.event_type,
                "event_payload_json": payload,
                "created_at": event.created_at.isoformat(),
            }
        )

    return FlowRunEventsResponse(events=out_events)


@router.get("/api/run-artifacts/{artifact_id}/content")
def get_run_artifact_content_route(
    artifact_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    artifact = (
        db.query(RunArtifact)
        .filter(
            RunArtifact.id == artifact_id,
            RunArtifact.owner_user_id == current_user["id"],
            RunArtifact.status == "available",
        )
        .one_or_none()
    )
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    return _run_artifact_file_response(artifact, allow_external_redirect=True)


@router.get("/api/public/run-artifacts/{artifact_id}/content")
def get_public_run_artifact_content_route(
    artifact_id: str,
    db: Session = Depends(get_db),
):
    artifact = (
        db.query(RunArtifact)
        .filter(
            RunArtifact.id == artifact_id,
            RunArtifact.status == "available",
        )
        .one_or_none()
    )
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    if not _is_public_artifact_content_enabled(artifact):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact content not available")
    return _run_artifact_file_response(artifact)


def _is_public_artifact_content_enabled(artifact: RunArtifact) -> bool:
    if artifact.artifact_type != "image":
        return False
    metadata_json = artifact.metadata_json if isinstance(artifact.metadata_json, dict) else {}
    expected_path = f"/api/run-artifacts/{artifact.id}/content"
    return metadata_json.get("preview_url") == expected_path or metadata_json.get("download_url") == expected_path


def _run_artifact_file_response(
    artifact: RunArtifact,
    *,
    allow_external_redirect: bool = False,
) -> FileResponse | RedirectResponse:
    if allow_external_redirect and artifact.storage_backend == "ax_managed":
        public_url = _artifact_public_url_from_metadata(artifact)
        if public_url is not None:
            return RedirectResponse(public_url)

    if artifact.storage_backend not in {"temporary", "ax_managed"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact content not available")

    path_value = artifact.storage_path or artifact.storage_reference
    try:
        artifact_path = Path(path_value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact content not found") from None
    if not artifact_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact content not found")

    return FileResponse(
        artifact_path,
        media_type=artifact.media_type,
        filename=artifact_path.name,
    )


def _artifact_public_url_from_metadata(artifact: RunArtifact) -> str | None:
    metadata_json = artifact.metadata_json if isinstance(artifact.metadata_json, dict) else {}
    for key in ("provider_media_url", "download_url", "external_resource_url", "preview_url"):
        value = metadata_json.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            return absolute_http_provider_media_url(value)
        except ValueError:
            continue
    return None


@router.websocket("/api/flow-runs/{run_id}/stream")
async def stream_flow_run_events_route(
    websocket: WebSocket,
    run_id: str,
    access_token: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    await websocket.accept()

    if access_token is None:
        try:
            message = await asyncio.wait_for(websocket.receive_json(), timeout=1)
        except WebSocketDisconnect:
            return
        except Exception:
            await websocket.close(code=1008)
            return
        if isinstance(message, dict) and message.get("type") == "authenticate":
            access_token_value = message.get("access_token")
            access_token = access_token_value if isinstance(access_token_value, str) else None
        if access_token is None:
            await websocket.close(code=1008)
            return

    try:
        current_user = await authenticate_access_token(access_token)
    except HTTPException:
        await websocket.close(code=1008)
        return

    try:
        detail = get_flow_run_detail(db, run_id=run_id, owner_user_id=current_user["id"])
        run = detail["run"]
    except LookupError:
        db.rollback()
        await websocket.close(code=1008)
        return
    db.rollback()

    try:
        published_snapshot = FlowSnapshotExecutor(db).load_published_snapshot(
            flow_version_id=str(run.flow_version_id), owner_user_id=current_user["id"]
        )
    except Exception:
        published_snapshot = None

    def _resolve_agent_info_local(snapshot: dict[str, Any] | None, payload: dict[str, Any] | None):
        if not snapshot or not isinstance(payload, dict):
            return None
        agent_ver = payload.get("agent_id") or payload.get("agent_version_id")
        if not isinstance(agent_ver, str):
            return None
        entities = snapshot.get("entities") if isinstance(snapshot, dict) else None
        if not isinstance(entities, dict):
            return None
        crews = entities.get("crews")
        if not isinstance(crews, dict):
            return None
        for crew in crews.values():
            try:
                runtime = crew.get("runtime_snapshot_json") if isinstance(crew, dict) else None
                runtime_agents = runtime.get("runtime_agents") if isinstance(runtime, dict) else None
                if isinstance(runtime_agents, dict) and agent_ver in runtime_agents:
                    agent = runtime_agents[agent_ver]
                    if isinstance(agent, dict):
                        return {"agent_name": agent.get("agent_name") or agent.get("name"), "agent_role": agent.get("role")}
            except Exception:
                continue
        return None

    last_created_at = None
    last_event_id: str | None = None
    sent_event_ids: set[str] = set()
    pending_pong = False

    try:
        while True:
            sent_any = False
            while True:
                db.expire_all()
                query = db.query(FlowRunEvent).filter(FlowRunEvent.run_id == run_id)
                if last_created_at is not None and last_event_id is not None:
                    query = query.filter(
                        or_(
                            FlowRunEvent.created_at > last_created_at,
                            and_(
                                FlowRunEvent.created_at == last_created_at,
                                FlowRunEvent.id > last_event_id,
                            ),
                        )
                    )
                events = (
                    query.order_by(FlowRunEvent.created_at.asc(), FlowRunEvent.id.asc())
                    .limit(100)
                    .all()
                )
                if not events:
                    db.rollback()
                    if last_created_at is not None:
                        overlap_start = last_created_at - STREAM_EVENT_OVERLAP
                        overlap_created_at = overlap_start
                        overlap_event_id: str | None = None
                        while True:
                            overlap_query = db.query(FlowRunEvent).filter(
                                FlowRunEvent.run_id == run_id,
                                FlowRunEvent.created_at >= overlap_start,
                                FlowRunEvent.created_at <= last_created_at,
                            )
                            if overlap_event_id is not None:
                                overlap_query = overlap_query.filter(
                                    or_(
                                        FlowRunEvent.created_at > overlap_created_at,
                                        and_(
                                            FlowRunEvent.created_at == overlap_created_at,
                                            FlowRunEvent.id > overlap_event_id,
                                        ),
                                    )
                                )
                            overlap_events = (
                                overlap_query.order_by(
                                    FlowRunEvent.created_at.asc(),
                                    FlowRunEvent.id.asc(),
                                )
                                .limit(100)
                                .all()
                            )
                            if not overlap_events:
                                db.rollback()
                                break

                            for event in overlap_events:
                                event_id = str(event.id)
                                overlap_created_at = event.created_at
                                overlap_event_id = event_id
                                if event_id in sent_event_ids:
                                    continue
                                sent_event_ids.add(event_id)
                                payload = dict(event.event_payload_json or {})
                                payload.setdefault("type", event.event_type)
                                payload.setdefault("run_id", run_id)
                                payload.setdefault("node_id", event.node_id)
                                payload.setdefault("event_id", event_id)
                                payload.setdefault("created_at", event.created_at.isoformat())
                                info = _resolve_agent_info_local(published_snapshot, payload)
                                if info:
                                    payload.setdefault("agent_name", info.get("agent_name"))
                                    payload.setdefault("agent_role", info.get("agent_role"))
                                await websocket.send_json(payload)
                                sent_any = True
                            db.rollback()
                            if len(overlap_events) < 100:
                                break
                    break

                for event in events:
                    event_id = str(event.id)
                    if event_id in sent_event_ids:
                        last_created_at = event.created_at
                        last_event_id = event_id
                        continue
                    sent_event_ids.add(event_id)
                    payload = dict(event.event_payload_json or {})
                    payload.setdefault("type", event.event_type)
                    payload.setdefault("run_id", run_id)
                    payload.setdefault("node_id", event.node_id)
                    payload.setdefault("event_id", event_id)
                    payload.setdefault("created_at", event.created_at.isoformat())
                    info = _resolve_agent_info_local(published_snapshot, payload)
                    if info:
                        payload.setdefault("agent_name", info.get("agent_name"))
                        payload.setdefault("agent_role", info.get("agent_role"))
                    await websocket.send_json(payload)
                    last_created_at = event.created_at
                    last_event_id = event_id
                    sent_any = True
                db.rollback()

            if pending_pong and not sent_any:
                await websocket.send_json({"type": "pong"})
                pending_pong = False

            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
                if message == "ping":
                    pending_pong = True
            except asyncio.TimeoutError:
                continue
    except WebSocketDisconnect:
        return
