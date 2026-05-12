from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from api.core.database import SessionLocal
from api.db.models import Asset, AssetVersion, FlowRun, FlowRunEvent, FlowRunStateSnapshot, HumanFeedbackRequest, RunArtifact
from api.runtime.artifacts import staging_artifact_metadata
from api.runtime.flow_snapshot_executor import (
    FlowRuntimeSnapshotError,
    FlowSnapshotExecutor,
    HumanFeedbackConflictError,
    HumanFeedbackValidationError,
)
from api.runtime.node_output_store import NodeOutputStore


def create_flow_run(
    db,
    *,
    flow_version_id: str,
    owner_user_id: str,
    inputs: dict,
    capture_agent_execution_logs: bool = True,
) -> FlowRun:
    return FlowSnapshotExecutor(db).start_run(
        flow_version_id=flow_version_id,
        owner_user_id=owner_user_id,
        inputs=inputs,
        capture_agent_execution_logs=capture_agent_execution_logs,
    )


def create_flow_run_record(
    db,
    *,
    flow_version_id: str,
    owner_user_id: str,
    inputs: dict,
    capture_agent_execution_logs: bool = True,
) -> FlowRun:
    return FlowSnapshotExecutor(db).create_run_record(
        flow_version_id=flow_version_id,
        owner_user_id=owner_user_id,
        inputs=inputs,
        capture_agent_execution_logs=capture_agent_execution_logs,
    )


def _mark_owned_run_failed(db: Session, *, run_id: str, owner_user_id: str, error_message: str) -> None:
    run = (
        db.query(FlowRun)
        .join(AssetVersion, AssetVersion.id == FlowRun.flow_version_id)
        .join(Asset, Asset.id == AssetVersion.asset_id)
        .filter(FlowRun.id == run_id, Asset.owner_user_id == owner_user_id)
        .one_or_none()
    )
    if run is None:
        return

    run.status = "failed"
    run.error_message = error_message
    run.finished_at = datetime.now(UTC)
    db.add(
        FlowRunEvent(
            run_id=run_id,
            node_id=None,
            event_type="run_failed",
            event_payload_json={
                "type": "run_failed",
                "run_id": str(run_id),
                "node_id": None,
                "error_message": error_message,
                "error": error_message,
            },
        )
    )
    db.add(run)
    db.commit()


def execute_flow_run_background(*, run_id: str, owner_user_id: str) -> None:
    db = SessionLocal()
    try:
        executor = FlowSnapshotExecutor(db)
        execute_existing_run = getattr(executor, "execute_existing_run", None)
        if execute_existing_run is None:
            error_message = (
                "Flow run background execution is not available yet: "
                "FlowSnapshotExecutor.execute_existing_run is not implemented."
            )
            _mark_owned_run_failed(
                db,
                run_id=run_id,
                owner_user_id=owner_user_id,
                error_message=error_message,
            )
            return
        try:
            execute_existing_run(
                run_id=run_id,
                owner_user_id=owner_user_id,
            )
        except Exception as exc:
            db.rollback()
            _mark_owned_run_failed(
                db,
                run_id=run_id,
                owner_user_id=owner_user_id,
                error_message=str(exc),
            )
    finally:
        db.close()


def enqueue_flow_run_execution(
    background_tasks: BackgroundTasks,
    *,
    run_id: str,
    owner_user_id: str,
) -> None:
    background_tasks.add_task(
        execute_flow_run_background,
        run_id=run_id,
        owner_user_id=owner_user_id,
    )


def submit_human_feedback(
    db,
    *,
    run_id: str,
    owner_user_id: str,
    request_id: str,
    outcome: str,
    feedback: str,
    idempotency_key: str | None = None,
) -> FlowRun:
    return FlowSnapshotExecutor(db).resume_run(
        run_id=run_id,
        owner_user_id=owner_user_id,
        request_id=request_id,
        outcome=outcome,
        feedback=feedback,
        idempotency_key=idempotency_key,
    )


def resolve_human_feedback_prompt_json(db: Session, *, request: HumanFeedbackRequest) -> dict[str, Any]:
    prompt_json = dict(request.prompt_json or {})
    preview_payload_ref = prompt_json.get("preview_payload_ref")
    if isinstance(preview_payload_ref, dict):
        output = NodeOutputStore(db).resolve_output(
            run_id=str(request.run_id),
            ref=preview_payload_ref,
        )
        if output is not None:
            prompt_json["preview_payload"] = output
    return prompt_json


def get_flow_run_detail(db, *, run_id: str, owner_user_id: str) -> dict:
    run = FlowSnapshotExecutor(db)._owned_run(run_id=run_id, owner_user_id=owner_user_id)
    latest_snapshot = (
        db.query(FlowRunStateSnapshot)
        .filter(FlowRunStateSnapshot.run_id == run.id)
        .order_by(FlowRunStateSnapshot.created_at.desc(), FlowRunStateSnapshot.id.desc())
        .first()
    )
    pending_request = (
        db.query(HumanFeedbackRequest)
        .filter(HumanFeedbackRequest.run_id == run.id, HumanFeedbackRequest.status == "pending")
        .order_by(HumanFeedbackRequest.created_at.desc(), HumanFeedbackRequest.id.desc())
        .first()
    )
    artifacts = (
        db.query(RunArtifact)
        .filter(RunArtifact.run_id == run.id, RunArtifact.owner_user_id == owner_user_id)
        .order_by(RunArtifact.created_at.asc(), RunArtifact.id.asc())
        .all()
    )
    return {
        "run": run,
        "latest_state_snapshot": latest_snapshot,
        "pending_human_feedback_request": pending_request,
        "pending_human_feedback_prompt_json": (
            resolve_human_feedback_prompt_json(db, request=pending_request) if pending_request else None
        ),
        "artifacts": [staging_artifact_metadata(artifact) for artifact in artifacts],
    }


def list_flow_run_events(db, *, run_id: str, owner_user_id: str | None = None) -> list[FlowRunEvent]:
    query = db.query(FlowRunEvent).filter(FlowRunEvent.run_id == run_id)
    if owner_user_id is not None:
        query = (
            query.join(FlowRun, FlowRun.id == FlowRunEvent.run_id)
            .join(AssetVersion, AssetVersion.id == FlowRun.flow_version_id)
            .join(Asset, Asset.id == AssetVersion.asset_id)
            .filter(Asset.owner_user_id == owner_user_id)
        )
    return query.order_by(FlowRunEvent.created_at.asc(), FlowRunEvent.id.asc()).all()
