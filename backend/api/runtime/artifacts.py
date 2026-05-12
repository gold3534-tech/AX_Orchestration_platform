from __future__ import annotations

from datetime import UTC, datetime, timedelta
import re
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

from sqlalchemy.orm import Session

from api.db.models import Asset, AssetVersion, FlowRun, RunArtifact

MVP_RETENTION_DAYS = 7
_RETENTION_PLAN_DAYS = {"free": MVP_RETENTION_DAYS}
_ZERO_UUID = "00000000-0000-0000-0000-000000000000"
ALLOWED_ARTIFACT_TYPES = frozenset({"image", "file"})
ALLOWED_STORAGE_BACKENDS = frozenset({"ax_managed", "temporary", "google_drive"})
ALLOWED_STATUSES = frozenset({"available", "expired", "failed"})
ALLOWED_RETENTION_MODES = frozenset({"temporary", "ax_managed"})
ALLOWED_STORAGE_OUTCOMES = frozenset({"temporary_only", "uploaded_to_google_drive", "ax_managed"})
_PUBLIC_URL_METADATA_KEYS = frozenset({"preview_url", "download_url", "external_resource_url"})
_OMIT_METADATA = object()
_SECRET_METADATA_FRAGMENTS = (
    "api_key",
    "access_token",
    "authorization",
    "credential",
    "password",
    "refresh_token",
    "secret",
    "token",
)


def retention_days_for_plan_tier(plan_tier: str = "free") -> int:
    normalized_plan_tier = (plan_tier or "free").strip().lower()
    if normalized_plan_tier in _RETENTION_PLAN_DAYS:
        return _RETENTION_PLAN_DAYS[normalized_plan_tier]
    raise NotImplementedError("Paid artifact retention tiers are not available in the MVP.")


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _apply_utc_datetimes(artifact: RunArtifact) -> RunArtifact:
    artifact.retention_expires_at = _utc(artifact.retention_expires_at)
    artifact.created_at = _utc(artifact.created_at)
    artifact.updated_at = _utc(artifact.updated_at)
    return artifact


def _validate_required_text(field_name: str, value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    return value


def _validate_enum(field_name: str, value: str, allowed_values: frozenset[str]) -> str:
    value = _validate_required_text(field_name, value)
    if value not in allowed_values:
        raise ValueError(f"{field_name} must be one of: {', '.join(sorted(allowed_values))}")
    return value


def _default_retention_mode_for_storage_backend(storage_backend: str) -> str:
    if storage_backend == "ax_managed":
        return "ax_managed"
    return "temporary"


def _validate_storage_combination(
    *,
    storage_backend: str,
    retention_mode: str,
) -> None:
    expected_retention_mode = _default_retention_mode_for_storage_backend(storage_backend)
    if retention_mode != expected_retention_mode:
        raise ValueError(
            f'storage_backend "{storage_backend}" requires retention_mode "{expected_retention_mode}"'
        )


def _validate_required_runtime_id(field_name: str, value: str | None) -> str:
    if value is None:
        raise ValueError(f"{field_name} must not be empty")
    value = _validate_required_text(field_name, value)
    if value == _ZERO_UUID:
        raise ValueError(f"{field_name} must not be the zero UUID")
    return value


def _metadata_secret_key(key: object) -> str | None:
    normalized_key = _bounded_unquote(str(key)).lower()
    for fragment in _SECRET_METADATA_FRAGMENTS:
        if fragment in normalized_key:
            return str(key)
    return None


def _validate_non_secret_metadata(value: Any, *, path: str = "metadata_json") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            secret_key = _metadata_secret_key(key)
            if secret_key is not None:
                raise ValueError(f"metadata_json must not include secret-like key: {secret_key}")
            _validate_non_secret_metadata(item, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_non_secret_metadata(item, path=f"{path}[{index}]")
        return
    if isinstance(value, str):
        normalized_value = value.lower()
        if any(fragment in normalized_value for fragment in _SECRET_METADATA_FRAGMENTS):
            raise ValueError(f"{path} must not include secret-like value")


def _require_owned_run(db: Session, *, run_id: str, owner_user_id: str) -> FlowRun:
    flow_run = (
        db.query(FlowRun)
        .join(AssetVersion, AssetVersion.id == FlowRun.flow_version_id)
        .join(Asset, Asset.id == AssetVersion.asset_id)
        .filter(FlowRun.id == run_id, Asset.owner_user_id == owner_user_id)
        .one_or_none()
    )
    if flow_run is None:
        raise LookupError(f"Flow run not found: {run_id}")
    return flow_run


def _contains_secret_fragment(value: str) -> bool:
    normalized_value = value.lower()
    return any(fragment in normalized_value for fragment in _SECRET_METADATA_FRAGMENTS)


def _bounded_unquote(value: str, *, max_rounds: int = 8) -> str:
    decoded = value
    for _ in range(max_rounds):
        next_decoded = unquote(decoded)
        if next_decoded == decoded:
            break
        decoded = next_decoded
    return decoded


def _safe_public_url(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if re.fullmatch(r"/api/run-artifacts/[0-9A-Fa-f-]+/content", value):
        return value
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.username or parsed.password:
        return None
    if _contains_secret_fragment(_bounded_unquote(parsed.netloc)):
        return None
    if parsed.hostname and _contains_secret_fragment(_bounded_unquote(parsed.hostname)):
        return None
    if _contains_secret_fragment(_bounded_unquote(parsed.path)) or _contains_secret_fragment(
        _bounded_unquote(parsed.fragment)
    ):
        return None
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        if _contains_secret_fragment(_bounded_unquote(key)) or _contains_secret_fragment(
            _bounded_unquote(item)
        ):
            return None
    return value


def _safe_public_label(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    sanitized_value = _safe_metadata(value.strip())
    return sanitized_value if isinstance(sanitized_value, str) else None


def _looks_like_http_url(value: str) -> bool:
    parsed = urlsplit(value.strip())
    return parsed.scheme in {"http", "https"}


def _retention_expiry(
    *,
    storage_backend: str,
    retention_expires_at: datetime | None,
    plan_tier: str,
) -> datetime | None:
    max_expires_at = datetime.now(UTC) + timedelta(days=retention_days_for_plan_tier(plan_tier))
    if retention_expires_at is not None:
        explicit_expires_at = _utc(retention_expires_at)
        if explicit_expires_at is not None and explicit_expires_at > max_expires_at:
            raise ValueError("retention_expires_at cannot exceed the 7 day MVP retention cap")
        return explicit_expires_at
    if storage_backend == "google_drive":
        return None
    return max_expires_at


def _public_retention_expires_at(artifact: RunArtifact) -> datetime | None:
    retention_expires_at = _utc(artifact.retention_expires_at)
    created_at = _utc(artifact.created_at)
    if retention_expires_at is not None and created_at is not None:
        max_expires_at = created_at + timedelta(days=MVP_RETENTION_DAYS)
        if retention_expires_at > max_expires_at:
            raise ValueError("retention_expires_at cannot exceed the 7 day MVP retention cap")
    return retention_expires_at


def _validate_non_negative_size(size_bytes: int | None) -> int:
    if size_bytes is None:
        return 0
    if size_bytes < 0:
        raise ValueError("size_bytes must be non-negative")
    return size_bytes


def _storage_reference(
    *,
    storage_reference: str | None,
    storage_bucket: str | None,
    storage_path: str | None,
) -> str:
    if storage_reference is not None:
        return _validate_required_text("storage_reference", storage_reference)
    if storage_path is None:
        raise ValueError("storage_reference must not be empty")
    return _validate_required_text("storage_path", storage_path)


def create_artifact_metadata(
    db: Session,
    *,
    owner_user_id: str,
    run_id: str,
    node_id: str | None = None,
    artifact_type: str = "",
    storage_backend: str | None = None,
    storage_reference: str | None = None,
    source_tool: str | None = None,
    source_capability: str | None = None,
    media_type: str | None = None,
    mime_type: str | None = None,
    sha256: str | None = None,
    size_bytes: int = 0,
    storage_bucket: str | None = None,
    storage_path: str | None = None,
    retention_mode: str | None = None,
    retention_expires_at: datetime | None = None,
    plan_tier: str = "free",
    status: str = "available",
    metadata_json: dict[str, Any] | None = None,
) -> RunArtifact:
    resolved_media_type = media_type or mime_type
    if resolved_media_type is None:
        raise ValueError("media_type must not be empty")

    validated_storage_backend = _validate_enum(
        "storage_backend",
        "temporary" if storage_backend is None else storage_backend,
        ALLOWED_STORAGE_BACKENDS,
    )
    resolved_retention_mode = (
        _default_retention_mode_for_storage_backend(validated_storage_backend)
        if retention_mode is None
        else retention_mode
    )
    validated_retention_mode = _validate_enum(
        "retention_mode",
        resolved_retention_mode,
        ALLOWED_RETENTION_MODES,
    )
    validated_status = _validate_enum("status", status, ALLOWED_STATUSES)
    _validate_storage_combination(
        storage_backend=validated_storage_backend,
        retention_mode=validated_retention_mode,
    )
    resolved_storage_reference = _storage_reference(
        storage_reference=storage_reference,
        storage_bucket=storage_bucket,
        storage_path=storage_path,
    )
    validated_owner_user_id = _validate_required_runtime_id("owner_user_id", owner_user_id)
    validated_run_id = _validate_required_runtime_id("run_id", run_id)
    _require_owned_run(db, run_id=validated_run_id, owner_user_id=validated_owner_user_id)
    validated_metadata_json = dict(metadata_json or {})
    _validate_non_secret_metadata(validated_metadata_json)
    artifact = RunArtifact(
        owner_user_id=validated_owner_user_id,
        run_id=validated_run_id,
        node_id=node_id,
        artifact_type=_validate_enum("artifact_type", artifact_type, ALLOWED_ARTIFACT_TYPES),
        media_type=_validate_required_text("media_type", resolved_media_type),
        sha256=sha256,
        size_bytes=_validate_non_negative_size(size_bytes),
        storage_backend=validated_storage_backend,
        storage_reference=resolved_storage_reference,
        storage_bucket=storage_bucket,
        storage_path=storage_path,
        source_tool=source_tool.strip() if isinstance(source_tool, str) and source_tool.strip() else None,
        source_capability=(
            source_capability.strip()
            if isinstance(source_capability, str) and source_capability.strip()
            else None
        ),
        retention_mode=validated_retention_mode,
        retention_expires_at=_retention_expiry(
            storage_backend=validated_storage_backend,
            retention_expires_at=retention_expires_at,
            plan_tier=plan_tier,
        ),
        status=validated_status,
        metadata_json=validated_metadata_json,
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return _apply_utc_datetimes(artifact)


def list_artifact_metadata(
    db: Session,
    *,
    owner_user_id: str,
    run_id: str | None = None,
) -> list[RunArtifact]:
    query = db.query(RunArtifact).filter(RunArtifact.owner_user_id == owner_user_id)
    if run_id is not None:
        query = query.filter(RunArtifact.run_id == run_id)
    artifacts = query.order_by(RunArtifact.created_at.asc(), RunArtifact.id.asc()).all()
    return [_apply_utc_datetimes(artifact) for artifact in artifacts]


def get_artifact_metadata(
    db: Session,
    *,
    artifact_id: str,
    owner_user_id: str,
) -> RunArtifact:
    artifact = (
        db.query(RunArtifact)
        .filter(
            RunArtifact.id == artifact_id,
            RunArtifact.owner_user_id == owner_user_id,
        )
        .one_or_none()
    )
    if artifact is None:
        raise LookupError(f"Artifact not found: {artifact_id}")
    return _apply_utc_datetimes(artifact)


def list_staging_artifacts(
    db: Session,
    *,
    owner_user_id: str,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    return [
        staging_artifact_metadata(artifact)
        for artifact in list_artifact_metadata(
            db,
            owner_user_id=owner_user_id,
            run_id=run_id,
        )
    ]


def get_staging_artifact(
    db: Session,
    *,
    artifact_id: str,
    owner_user_id: str,
) -> dict[str, Any]:
    return staging_artifact_metadata(
        get_artifact_metadata(
            db,
            artifact_id=artifact_id,
            owner_user_id=owner_user_id,
        )
    )


def _safe_metadata(value: Any, *, key: str | None = None) -> Any:
    if key in _PUBLIC_URL_METADATA_KEYS:
        safe_url = _safe_public_url(value)
        return safe_url if safe_url is not None else _OMIT_METADATA
    if isinstance(value, dict):
        safe_value = {}
        for key, item in value.items():
            normalized_key = _bounded_unquote(str(key)).lower()
            if _metadata_secret_key(key) is not None:
                continue
            sanitized_item = _safe_metadata(item, key=normalized_key)
            if sanitized_item is _OMIT_METADATA:
                continue
            safe_value[key] = sanitized_item
        return safe_value
    if isinstance(value, list):
        return [
            None if (sanitized_item := _safe_metadata(item)) is _OMIT_METADATA else sanitized_item
            for item in value
        ]
    if isinstance(value, str):
        if _looks_like_http_url(value):
            safe_url = _safe_public_url(value)
            return safe_url if safe_url is not None else _OMIT_METADATA
        if _contains_secret_fragment(_bounded_unquote(value)):
            return _OMIT_METADATA
    return value


def staging_artifact_metadata(artifact: RunArtifact) -> dict[str, Any]:
    retention_expires_at = _public_retention_expires_at(artifact)
    created_at = _utc(artifact.created_at)
    updated_at = _utc(artifact.updated_at)
    size_bytes = _validate_non_negative_size(artifact.size_bytes)
    metadata_json = artifact.metadata_json if isinstance(artifact.metadata_json, dict) else {}
    preview_url = _safe_public_url(metadata_json.get("preview_url"))
    download_url = _safe_public_url(metadata_json.get("download_url"))
    return {
        "id": str(artifact.id),
        "run_id": str(artifact.run_id),
        "node_id": artifact.node_id,
        "artifact_type": artifact.artifact_type,
        "mime_type": artifact.media_type,
        "media_type": artifact.media_type,
        "sha256": artifact.sha256,
        "size_bytes": size_bytes,
        "storage_backend": artifact.storage_backend,
        "source_tool": artifact.source_tool,
        "source_capability": artifact.source_capability,
        "retention_mode": artifact.retention_mode,
        "expires_at": retention_expires_at.isoformat() if retention_expires_at else None,
        "retention_expires_at": retention_expires_at.isoformat() if retention_expires_at else None,
        "preview_url": preview_url,
        "download_url": download_url,
        "status": artifact.status,
        "metadata_json": _safe_metadata(metadata_json),
        "self_delete_supported": False,
        "created_at": created_at.isoformat() if created_at else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


def storage_outcome_for_artifact(artifact: RunArtifact) -> dict[str, Any]:
    metadata_json = artifact.metadata_json if isinstance(artifact.metadata_json, dict) else {}
    storage_backend = artifact.storage_backend
    retention_mode = artifact.retention_mode
    status = artifact.status
    retention_expires_at = _public_retention_expires_at(artifact)
    _validate_enum("storage_backend", storage_backend, ALLOWED_STORAGE_BACKENDS)
    _validate_enum("retention_mode", retention_mode, ALLOWED_RETENTION_MODES)
    _validate_enum("status", status, ALLOWED_STATUSES)
    _validate_storage_combination(storage_backend=storage_backend, retention_mode=retention_mode)
    if status != "available":
        raise ValueError("storage_outcome requires artifact status available")
    if storage_backend == "google_drive":
        storage_outcome = "uploaded_to_google_drive"
        external_resource_url = _safe_public_url(metadata_json.get("external_resource_url"))
        if external_resource_url is None:
            raise ValueError("google_drive storage_outcome requires a safe external_resource_url")
    elif storage_backend == "ax_managed":
        storage_outcome = "ax_managed"
        external_resource_url = _safe_public_url(metadata_json.get("external_resource_url"))
    else:
        storage_outcome = "temporary_only"
        external_resource_url = _safe_public_url(metadata_json.get("external_resource_url"))
    if storage_outcome not in ALLOWED_STORAGE_OUTCOMES:
        raise ValueError(f"storage_outcome must be one of: {', '.join(sorted(ALLOWED_STORAGE_OUTCOMES))}")
    return {
        "storage_outcome": storage_outcome,
        "external_resource_url": external_resource_url,
        "external_resource_label": _safe_public_label(metadata_json.get("external_resource_label")),
        "retention_expires_at": retention_expires_at.isoformat() if retention_expires_at else None,
        "expires_at": retention_expires_at.isoformat() if retention_expires_at else None,
        "self_delete_supported": False,
    }
