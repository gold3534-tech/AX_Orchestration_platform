from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

import httpx
from sqlalchemy.orm import Session

from api.db.models import ExecutionActionRun, HumanFeedbackRequest, RunArtifact
from api.integrations.google_workspace import build_drive_client_from_runtime
from api.integrations.meta_instagram import build_meta_instagram_client_from_runtime
from api.runtime.provider_media_urls import (
    absolute_http_provider_media_url,
    provider_media_url_for_artifact,
)


@dataclass(frozen=True)
class ExecutionActionRequest:
    run_id: str
    node_id: str
    action_key: str
    owner_user_id: str
    inputs: dict[str, Any]
    config: dict[str, Any]
    approval_mode: str
    artifact_ids: list[str] = field(default_factory=list)
    credential_id: str | None = None
    approved: bool = False
    db: Session | None = field(default=None, repr=False, compare=False)


ActionExecutor = Callable[[ExecutionActionRequest], dict[str, Any]]
_ACTION_REGISTRY: dict[str, ActionExecutor] = {}
MAX_PROVIDER_ARTIFACT_BYTES = 25 * 1024 * 1024


def register_execution_action(action_key: str, executor: ActionExecutor) -> None:
    _ACTION_REGISTRY[action_key] = executor


def load_artifact_bytes(
    *,
    artifact_id: str,
    owner_user_id: str,
    run_id: str | None = None,
    db: Session | None = None,
) -> bytes:
    if db is None:
        raise ValueError("Database session is required to load artifact bytes.")
    artifact = _owned_artifact(
        db,
        artifact_id=artifact_id,
        owner_user_id=owner_user_id,
        run_id=run_id,
    )
    if artifact.status != "available":
        raise ValueError("Artifact bytes are unavailable for non-available artifacts.")
    if artifact.storage_backend not in {"temporary", "ax_managed"}:
        raise ValueError(f"Artifact byte loading does not support {artifact.storage_backend} storage.")

    if artifact.storage_backend == "ax_managed":
        public_url = _artifact_public_url_from_metadata(artifact)
        if public_url is not None:
            return _load_artifact_bytes_from_public_url(public_url)

    artifact_path = _artifact_file_path(artifact)
    try:
        return artifact_path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("Artifact file is unavailable.") from exc
    except OSError as exc:
        raise ValueError("Artifact file could not be read.") from exc


def build_google_drive_client(*, owner_user_id: str, db: Session | None = None):
    return build_drive_client_from_runtime(db=db, owner_user_id=owner_user_id)


def build_meta_instagram_client(*, owner_user_id: str, db: Session | None = None):
    return build_meta_instagram_client_from_runtime(db=db, owner_user_id=owner_user_id)


def google_drive_upload_executor(request: ExecutionActionRequest) -> dict[str, Any]:
    artifact_id = _required_string(
        request.inputs.get("artifact_id"),
        "artifact_id",
        action_label="Google Drive upload",
    )
    content_bytes = load_artifact_bytes(
        artifact_id=artifact_id,
        owner_user_id=request.owner_user_id,
        run_id=request.run_id,
        db=request.db,
    )
    client = build_google_drive_client(owner_user_id=request.owner_user_id, db=request.db)
    result = client.upload_file(
        filename=_optional_string(request.config.get("filename_template")) or "ax-artifact",
        mime_type=_optional_string(request.config.get("mime_type")) or "application/octet-stream",
        content_bytes=content_bytes,
        target_folder_id=_optional_string(request.config.get("target_folder_id")),
    )
    output = {
        "drive_file_id": result.get("drive_file_id"),
        "web_view_link": result.get("web_view_link"),
        "web_content_link": result.get("web_content_link"),
        "mime_type": result.get("mime_type"),
    }
    _record_google_drive_upload(
        db=request.db,
        owner_user_id=request.owner_user_id,
        run_id=request.run_id,
        artifact_id=artifact_id,
        drive_result=output,
    )
    return output


def instagram_publish_executor(request: ExecutionActionRequest) -> dict[str, Any]:
    artifact_id = _required_string(
        request.inputs.get("artifact_id"),
        "artifact_id",
        action_label="Instagram publish",
    )
    caption = str(request.inputs.get("caption") or "")
    image_url = provider_media_url_for_artifact(
        artifact_id=artifact_id,
        owner_user_id=request.owner_user_id,
        run_id=request.run_id,
        db=request.db,
    )
    client = build_meta_instagram_client(owner_user_id=request.owner_user_id, db=request.db)
    result = client.publish_image(image_url=image_url, caption=caption)
    return {
        "ig_container_id": result.get("ig_container_id"),
        "ig_media_id": result.get("ig_media_id"),
        "status": result.get("status"),
    }


def execute_execution_action(db: Session, request: ExecutionActionRequest) -> ExecutionActionRun:
    if request.db is None:
        request = ExecutionActionRequest(
            run_id=request.run_id,
            node_id=request.node_id,
            action_key=request.action_key,
            owner_user_id=request.owner_user_id,
            inputs=request.inputs,
            config=request.config,
            approval_mode=request.approval_mode,
            artifact_ids=request.artifact_ids,
            credential_id=request.credential_id,
            approved=request.approved,
            db=db,
        )
    idempotency_key = _idempotency_key(request)
    existing = (
        db.query(ExecutionActionRun)
        .filter(
            ExecutionActionRun.run_id == request.run_id,
            ExecutionActionRun.node_id == request.node_id,
            ExecutionActionRun.action_key == request.action_key,
            ExecutionActionRun.idempotency_key == idempotency_key,
        )
        .one_or_none()
    )
    if existing is not None and (existing.status == "succeeded" or not request.approved):
        return existing

    action_run = existing or ExecutionActionRun(
        run_id=request.run_id,
        node_id=request.node_id,
        action_key=request.action_key,
        owner_user_id=request.owner_user_id,
        credential_id=request.credential_id,
        idempotency_key=idempotency_key,
        status="pending",
        input_json={
            "inputs": request.inputs,
            "config": request.config,
            "artifact_ids": request.artifact_ids,
        },
        output_json={},
    )
    if existing is None:
        db.add(action_run)
        db.flush()

    if request.approval_mode == "every_run" and not request.approved:
        action_run.status = "pending_approval"
        if _pending_approval_request(db, request=request, idempotency_key=idempotency_key) is None:
            db.add(
                HumanFeedbackRequest(
                    run_id=request.run_id,
                    node_id=request.node_id,
                    status="pending",
                    prompt_json={
                        "approval_type": "execution_action",
                        "action_key": request.action_key,
                        "external_effect_summary": request.action_key,
                        "input_summary": request.inputs,
                        "artifact_ids": request.artifact_ids,
                        "approval_mode": request.approval_mode,
                        "idempotency_key": idempotency_key,
                    },
                    response_json={},
                    idempotency_key=idempotency_key,
                )
            )
        db.flush()
        db.refresh(action_run)
        return action_run

    if request.approval_mode not in {"never", "every_run"}:
        action_run.status = "failed"
        action_run.error_code = "unsupported_approval_mode"
        action_run.error_message = f"Unsupported approval mode: {request.approval_mode}"
        db.flush()
        db.refresh(action_run)
        return action_run

    executor = _ACTION_REGISTRY.get(request.action_key)
    if executor is None:
        action_run.status = "failed"
        action_run.error_code = "action_unavailable"
        action_run.error_message = f"Execution action is not registered: {request.action_key}"
        db.flush()
        db.refresh(action_run)
        return action_run

    action_run.output_json = executor(request)
    action_run.status = "succeeded"
    db.flush()
    db.refresh(action_run)
    return action_run


def _pending_approval_request(
    db: Session,
    *,
    request: ExecutionActionRequest,
    idempotency_key: str,
) -> HumanFeedbackRequest | None:
    return (
        db.query(HumanFeedbackRequest)
        .filter(
            HumanFeedbackRequest.run_id == request.run_id,
            HumanFeedbackRequest.node_id == request.node_id,
            HumanFeedbackRequest.idempotency_key == idempotency_key,
        )
        .one_or_none()
    )


def _idempotency_key(request: ExecutionActionRequest) -> str:
    payload = json.dumps(
        {
            "run_id": request.run_id,
            "node_id": request.node_id,
            "action_key": request.action_key,
            "inputs": request.inputs,
            "config": request.config,
            "artifact_ids": request.artifact_ids,
            "credential_id": request.credential_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _required_string(value: object, field_name: str, *, action_label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required for {action_label}.")
    return value.strip()


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _owned_artifact(
    db: Session,
    *,
    artifact_id: str,
    owner_user_id: str,
    run_id: str | None,
) -> RunArtifact:
    query = db.query(RunArtifact).filter(
        RunArtifact.id == artifact_id,
        RunArtifact.owner_user_id == owner_user_id,
    )
    if run_id:
        query = query.filter(RunArtifact.run_id == run_id)
    artifact = query.one_or_none()
    if artifact is None:
        raise LookupError(f"Artifact not found: {artifact_id}")
    return artifact


def _record_google_drive_upload(
    *,
    db: Session | None,
    owner_user_id: str,
    run_id: str,
    artifact_id: str,
    drive_result: dict[str, Any],
) -> None:
    if db is None:
        return
    try:
        artifact = _owned_artifact(
            db,
            artifact_id=artifact_id,
            owner_user_id=owner_user_id,
            run_id=run_id,
        )
    except LookupError:
        return
    drive_file_id = _optional_string(drive_result.get("drive_file_id"))
    if drive_file_id is None:
        return
    provider_media_url = _provider_media_url_from_drive_result(drive_result)
    if provider_media_url is None:
        return
    metadata_json = artifact.metadata_json if isinstance(artifact.metadata_json, dict) else {}
    next_metadata = dict(metadata_json)
    next_metadata.update(
        {
            "drive_file_id": drive_file_id,
            "external_resource_label": "Google Drive file",
        }
    )
    next_metadata.update(
        {
            "external_resource_url": provider_media_url,
            "provider_media_url": provider_media_url,
            "preview_url": provider_media_url,
            "download_url": provider_media_url,
        }
    )
    artifact.storage_backend = "google_drive"
    artifact.retention_mode = "temporary"
    artifact.storage_reference = f"drive://file/{drive_file_id}"
    artifact.metadata_json = next_metadata
    db.add(artifact)
    db.flush()


def _provider_media_url_from_drive_result(drive_result: dict[str, Any]) -> str | None:
    for key in ("web_content_link", "web_view_link"):
        value = _optional_string(drive_result.get(key))
        if value is None:
            continue
        try:
            return absolute_http_provider_media_url(value)
        except ValueError:
            continue
    return None


def _artifact_public_url_from_metadata(artifact: RunArtifact) -> str | None:
    metadata_json = artifact.metadata_json if isinstance(artifact.metadata_json, dict) else {}
    for key in ("provider_media_url", "download_url", "external_resource_url", "preview_url"):
        value = _optional_string(metadata_json.get(key))
        if value is None:
            continue
        try:
            return absolute_http_provider_media_url(value)
        except ValueError:
            continue
    return None


def _load_artifact_bytes_from_public_url(public_url: str) -> bytes:
    try:
        chunks: list[bytes] = []
        total_bytes = 0
        with httpx.stream("GET", public_url, timeout=10.0, follow_redirects=False) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                total_bytes += len(chunk)
                if total_bytes > MAX_PROVIDER_ARTIFACT_BYTES:
                    raise ValueError("Artifact file is too large to fetch.")
                chunks.append(chunk)
    except httpx.HTTPError as exc:
        raise ValueError("Artifact file could not be fetched.") from exc
    return b"".join(chunks)


def _artifact_file_path(artifact: RunArtifact) -> Path:
    reference = artifact.storage_path or artifact.storage_reference
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError("Artifact storage path is unavailable.")
    reference = reference.strip()
    parsed = urlparse(reference)
    if parsed.scheme and parsed.scheme != "file":
        raise ValueError(f"Artifact byte loading does not support {parsed.scheme} storage references.")
    if parsed.scheme == "file":
        if parsed.netloc:
            raise ValueError("Artifact file URLs with a host are unsupported.")
        raw_path = unquote(parsed.path)
    else:
        raw_path = reference

    candidate = Path(raw_path)
    if not candidate.is_absolute():
        storage_root = _configured_artifact_storage_root()
        if storage_root is None:
            raise ValueError("Relative artifact paths require AX_ARTIFACT_STORAGE_ROOT.")
        candidate = storage_root / candidate
        resolved = candidate.resolve(strict=False)
        if not _is_path_within_root(resolved, storage_root):
            raise ValueError("Artifact storage path is outside an allowed artifact storage root.")
    else:
        resolved = candidate.resolve(strict=False)
        if not _is_allowed_artifact_path(resolved):
            raise ValueError("Artifact storage path is outside an allowed artifact storage root.")
    if not resolved.is_file():
        raise ValueError("Artifact file is unavailable.")
    return resolved


def _configured_artifact_storage_root() -> Path | None:
    configured = os.environ.get("AX_ARTIFACT_STORAGE_ROOT")
    if not isinstance(configured, str) or not configured.strip():
        return None
    return Path(configured).expanduser().resolve(strict=False)


def _allowed_artifact_storage_roots() -> list[Path]:
    roots: list[Path] = [Path(tempfile.gettempdir()).resolve(strict=False)]
    configured = _configured_artifact_storage_root()
    if configured is not None:
        roots.append(configured)
    return roots


def _is_allowed_artifact_path(path: Path) -> bool:
    return any(path == root or root in path.parents for root in _allowed_artifact_storage_roots())


def _is_path_within_root(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


register_execution_action("ax.google_drive_upload", google_drive_upload_executor)
register_execution_action("ax.instagram_publish", instagram_publish_executor)
