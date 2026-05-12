from __future__ import annotations

from dataclasses import dataclass
import os
import re
import unicodedata
import uuid

from api.supabase_client import get_supabase


@dataclass(frozen=True)
class KnowledgeStorageUpload:
    bucket: str
    object_path: str


def knowledge_storage_bucket() -> str:
    bucket = os.environ.get("AX_SUPABASE_KNOWLEDGE_BUCKET")
    if bucket is None or not bucket.strip():
        raise ValueError("Knowledge storage is not configured.")
    return bucket.strip()


def knowledge_storage_configured() -> bool:
    try:
        knowledge_storage_bucket()
    except ValueError:
        return False
    return get_supabase() is not None


def upload_knowledge_pdf_bytes(
    *,
    pdf_bytes: bytes,
    workspace_id: str,
    knowledge_item_id: str,
    original_filename: str,
    supabase_client=None,
) -> KnowledgeStorageUpload:
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes:
        raise ValueError("PDF file content is empty.")

    bucket = knowledge_storage_bucket()
    client = supabase_client if supabase_client is not None else get_supabase()
    if client is None:
        raise ValueError("Knowledge storage is not configured.")

    object_path = _object_path(
        workspace_id=workspace_id,
        knowledge_item_id=knowledge_item_id,
        original_filename=original_filename,
    )
    try:
        client.storage.from_(bucket).upload(
            object_path,
            pdf_bytes,
            file_options={
                "content-type": "application/pdf",
                "cache-control": "3600",
                "upsert": "false",
            },
        )
    except Exception as exc:
        raise ValueError("Knowledge file could not be uploaded.") from exc
    return KnowledgeStorageUpload(bucket=bucket, object_path=object_path)


def delete_knowledge_pdf_object(*, bucket: str, object_path: str, supabase_client=None) -> None:
    client = supabase_client if supabase_client is not None else get_supabase()
    if client is None:
        raise ValueError("Knowledge storage is not configured.")
    client.storage.from_(bucket).remove([object_path])


def _object_path(*, workspace_id: str, knowledge_item_id: str, original_filename: str) -> str:
    safe_workspace = _safe_segment(workspace_id)
    safe_item = _safe_segment(knowledge_item_id)
    safe_filename = _safe_filename(original_filename)
    return f"{safe_workspace}/knowledge/{safe_item}/{uuid.uuid4().hex}-{safe_filename}"


def _safe_segment(value: str) -> str:
    safe = "".join(
        character for character in str(value).strip() if character.isalnum() or character in {"-", "_"}
    )
    if not safe:
        raise ValueError("Storage path segment must not be empty.")
    return safe


def _safe_filename(value: str) -> str:
    name = str(value).split("/")[-1].split("\\")[-1].strip()
    stem = name[:-4] if name.lower().endswith(".pdf") else name
    normalized = unicodedata.normalize("NFKD", stem)
    ascii_stem = normalized.encode("ascii", "ignore").decode("ascii")
    safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", ascii_stem).strip("_-")
    if not safe_stem:
        safe_stem = "document"
    return f"{safe_stem}.pdf"
