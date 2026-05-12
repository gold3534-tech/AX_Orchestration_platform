from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import uuid

from api.supabase_client import get_supabase

_MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


@dataclass(frozen=True)
class SupabaseArtifactUpload:
    bucket: str
    object_path: str
    public_url: str


def supabase_public_artifact_bucket() -> str:
    bucket = os.environ.get("AX_SUPABASE_ARTIFACT_BUCKET")
    if not isinstance(bucket, str) or not bucket.strip():
        raise ValueError("AX_SUPABASE_ARTIFACT_BUCKET is required for Supabase artifact storage.")
    return bucket.strip()


def supabase_public_artifact_storage_configured() -> bool:
    bucket = os.environ.get("AX_SUPABASE_ARTIFACT_BUCKET")
    return isinstance(bucket, str) and bool(bucket.strip()) and get_supabase() is not None


def upload_public_artifact_file(
    *,
    path: str | Path,
    media_type: str,
    owner_user_id: str,
    run_id: str,
    supabase_client=None,
) -> SupabaseArtifactUpload:
    artifact_path = Path(path).expanduser()
    try:
        resolved_path = artifact_path.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ValueError("Artifact file content is unavailable for Supabase upload.") from None
    if not resolved_path.is_file():
        raise ValueError("Artifact file content is unavailable for Supabase upload.")
    return upload_public_artifact_bytes(
        image_bytes=resolved_path.read_bytes(),
        media_type=media_type,
        owner_user_id=owner_user_id,
        run_id=run_id,
        object_suffix=_extension_for_media_type(media_type),
        supabase_client=supabase_client,
    )


def upload_public_artifact_bytes(
    *,
    image_bytes: bytes,
    media_type: str,
    owner_user_id: str,
    run_id: str,
    object_suffix: str,
    supabase_client=None,
) -> SupabaseArtifactUpload:
    if not isinstance(image_bytes, bytes) or not image_bytes:
        raise ValueError("image_bytes must not be empty")
    if not isinstance(media_type, str) or not media_type.strip():
        raise ValueError("media_type must not be empty")
    del owner_user_id
    normalized_media_type = media_type.strip().lower()
    safe_suffix = _validated_object_suffix(
        media_type=normalized_media_type,
        object_suffix=object_suffix,
    )
    client = supabase_client if supabase_client is not None else get_supabase()
    if client is None:
        raise ValueError("Supabase Storage is not configured for AX-managed artifacts.")

    bucket = supabase_public_artifact_bucket()
    object_path = _object_path(run_id=run_id, suffix=safe_suffix)
    bucket_client = client.storage.from_(bucket)
    bucket_client.upload(
        object_path,
        image_bytes,
        file_options={
            "content-type": normalized_media_type,
            "cache-control": "3600",
            "upsert": "false",
        },
    )
    public_url = bucket_client.get_public_url(object_path)
    if not isinstance(public_url, str) or not public_url.strip():
        raise ValueError("Supabase Storage did not return a public artifact URL.")
    return SupabaseArtifactUpload(
        bucket=bucket,
        object_path=object_path,
        public_url=public_url.strip(),
    )


def _object_path(*, run_id: str, suffix: str) -> str:
    safe_run_id = _safe_segment(run_id)
    return f"artifacts/{safe_run_id}/{uuid.uuid4().hex}{suffix}"


def _safe_segment(value: str) -> str:
    normalized = "".join(
        character
        for character in str(value).strip()
        if character.isalnum() or character in {"-", "_"}
    )
    if not normalized:
        raise ValueError("run_id must not be empty for Supabase artifact storage.")
    return normalized


def _extension_for_media_type(media_type: str) -> str:
    extension = _MIME_EXTENSIONS.get(media_type.strip().lower())
    if extension is None:
        raise ValueError(f"Unsupported image media type for Supabase artifact storage: {media_type}")
    return extension


def _validated_object_suffix(*, media_type: str, object_suffix: str) -> str:
    expected_suffix = _extension_for_media_type(media_type)
    if object_suffix != expected_suffix:
        raise ValueError("object_suffix must be a supported image extension for the media type.")
    return object_suffix
