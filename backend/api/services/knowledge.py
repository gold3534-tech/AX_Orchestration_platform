from __future__ import annotations

import hashlib
import math
import os
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from api.db import models
from api.runtime.credential_resolver import CredentialResolutionError, resolve_credential_env
from api.schemas.knowledge import KnowledgeCreate
from api.services.knowledge_embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_PROVIDER,
    DeterministicEmbeddingProvider,
    EmbeddingProvider,
    KnowledgeEmbeddingError,
    OpenAIEmbeddingProvider,
    get_default_embedding_provider,
)
from api.services.knowledge_pdf import KnowledgePdfError, extract_pdf_text
from api.services.knowledge_storage import delete_knowledge_pdf_object, upload_knowledge_pdf_bytes

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000000"
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000000"
DEFAULT_BUCKET = "knowledge"


class KnowledgeValidationError(ValueError):
    pass


@dataclass(frozen=True)
class TextChunk:
    index: int
    content: str
    metadata: dict


def _chunk_text(
    content: str,
    *,
    max_chars: int = 3200,
    overlap_chars: int = 400,
) -> list[TextChunk]:
    text = content.strip()
    if not text:
        raise KnowledgeValidationError("Knowledge content must not be empty.")
    chunks: list[TextChunk] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunk_content = text[start:end].strip()
        if chunk_content:
            chunks.append(
                TextChunk(
                    index=len(chunks),
                    content=chunk_content,
                    metadata={"start": start, "end": end},
                )
            )
        if end == len(text):
            break
        start = max(0, end - overlap_chars)
    return chunks


def _fake_embedding_for_test(content: str) -> list[float]:
    digest = hashlib.sha256(content.encode("utf-8")).digest()
    return [round(byte / 255, 6) for byte in digest[:16]]


def _knowledge_to_response(db: Session, item: models.KnowledgeItem) -> dict:
    attached_agent_count = (
        db.query(models.VersionKnowledge)
        .join(models.AssetVersion, models.AssetVersion.id == models.VersionKnowledge.version_id)
        .join(models.Asset, models.Asset.id == models.AssetVersion.asset_id)
        .filter(
            models.VersionKnowledge.knowledge_item_id == item.id,
            models.Asset.asset_type == "agent",
        )
        .count()
    )
    return {
        "id": str(item.id),
        "name": item.name,
        "description": item.description,
        "status": item.status,
        "source_file_name": item.source_file_name,
        "source_file_size": item.source_file_size,
        "source_mime_type": item.source_mime_type,
        "embedding_provider": item.embedding_provider,
        "embedding_model": item.embedding_model,
        "chunk_count": item.chunk_count,
        "attached_agent_count": attached_agent_count,
        "error_message": item.error_message,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _require_agent_version(db: Session, *, version_id: str) -> models.AssetVersion:
    version = db.get(models.AssetVersion, version_id)
    if version is None:
        raise LookupError(f"Version not found: {version_id}")
    if version.asset is None or version.asset.asset_type != "agent":
        raise KnowledgeValidationError("Knowledge can only be attached to Agent versions.")
    return version


def _version_knowledge_to_response(row: models.VersionKnowledge) -> dict:
    return {
        "id": str(row.id),
        "version_id": str(row.version_id),
        "knowledge_item_id": str(row.knowledge_item_id),
        "sort_order": row.sort_order,
        "knowledge": {
            "id": str(row.knowledge_item.id),
            "name": row.knowledge_item.name,
            "status": row.knowledge_item.status,
            "source_file_name": row.knowledge_item.source_file_name,
        },
        "created_at": row.created_at,
    }


def list_knowledge_items(db: Session) -> list[dict]:
    rows = (
        db.query(models.KnowledgeItem)
        .order_by(models.KnowledgeItem.created_at.asc(), models.KnowledgeItem.id.asc())
        .all()
    )
    return [_knowledge_to_response(db, row) for row in rows]


def list_version_knowledge(db: Session, *, version_id: str) -> list[dict]:
    _require_agent_version(db, version_id=version_id)
    rows = (
        db.query(models.VersionKnowledge)
        .filter(models.VersionKnowledge.version_id == version_id)
        .order_by(models.VersionKnowledge.sort_order.asc(), models.VersionKnowledge.created_at.asc())
        .all()
    )
    return [_version_knowledge_to_response(row) for row in rows]


def create_knowledge_item(db: Session, payload: KnowledgeCreate) -> dict:
    chunks = _chunk_text(payload.content)
    item = models.KnowledgeItem(
        workspace_id=DEFAULT_WORKSPACE_ID,
        owner_user_id=DEFAULT_USER_ID,
        name=payload.name.strip(),
        description=payload.description,
        status="ready",
        source_mime_type=payload.source_mime_type,
        source_file_name=payload.source_file_name,
        source_file_size=payload.source_file_size,
        storage_bucket=DEFAULT_BUCKET,
        storage_path=f"{DEFAULT_WORKSPACE_ID}/knowledge/{payload.source_file_name}",
        parser="text",
        embedding_provider=DEFAULT_EMBEDDING_PROVIDER,
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        chunk_count=len(chunks),
    )
    db.add(item)
    db.flush()
    for chunk in chunks:
        db.add(
            models.KnowledgeChunk(
                knowledge_item_id=item.id,
                workspace_id=item.workspace_id,
                chunk_index=chunk.index,
                content=chunk.content,
                content_hash=hashlib.sha256(chunk.content.encode("utf-8")).hexdigest(),
                token_count=max(1, len(chunk.content.split())),
                metadata_json=chunk.metadata,
                embedding_json=_fake_embedding_for_test(chunk.content),
            )
        )
    db.commit()
    db.refresh(item)
    return _knowledge_to_response(db, item)


def create_knowledge_item_from_pdf_upload(
    db: Session,
    *,
    file_bytes: bytes,
    source_file_name: str,
    source_file_size: int,
    source_mime_type: str,
    name: str | None = None,
    description: str | None = None,
    owner_user_id: str = DEFAULT_USER_ID,
) -> dict:
    if not _is_pdf_upload(source_file_name=source_file_name, source_mime_type=source_mime_type):
        raise KnowledgeValidationError("Only PDF files are supported for Knowledge upload in this MVP.")
    if not isinstance(file_bytes, bytes) or not file_bytes:
        raise KnowledgeValidationError("PDF file content is empty.")

    provider = _embedding_provider_for_upload(db, owner_user_id=owner_user_id)
    item_id = str(uuid.uuid4())
    display_name = (name or "").strip() or _default_name_from_filename(source_file_name)
    item = models.KnowledgeItem(
        id=item_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        owner_user_id=owner_user_id,
        name=display_name,
        description=description,
        status="processing",
        source_mime_type="application/pdf",
        source_file_name=source_file_name,
        source_file_size=source_file_size,
        storage_bucket=DEFAULT_BUCKET,
        storage_path=f"{DEFAULT_WORKSPACE_ID}/knowledge/{item_id}/{source_file_name}",
        parser="pdf",
        embedding_provider=DEFAULT_EMBEDDING_PROVIDER,
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        chunk_count=0,
    )
    uploaded = None

    try:
        db.add(item)
        db.flush()

        uploaded = upload_knowledge_pdf_bytes(
            pdf_bytes=file_bytes,
            workspace_id=str(item.workspace_id),
            knowledge_item_id=str(item.id),
            original_filename=source_file_name,
        )
        item.storage_bucket = uploaded.bucket
        item.storage_path = uploaded.object_path

        extracted = extract_pdf_text(file_bytes)
        page_spans = _page_spans(extracted.pages)
        chunks = _chunk_text(extracted.text)
        embeddings = provider.embed_texts([chunk.content for chunk in chunks])
        if len(embeddings) != len(chunks):
            raise KnowledgeValidationError("Embedding provider returned an unexpected number of vectors.")

        item.embedding_provider = provider.provider
        item.embedding_model = provider.model
        item.chunk_count = len(chunks)
        item.status = "ready"
        item.error_message = None

        for chunk, embedding in zip(chunks, embeddings, strict=True):
            chunk_metadata = {
                **chunk.metadata,
                **_page_range_for_chunk(chunk.metadata["start"], chunk.metadata["end"], page_spans),
                "source_file_name": source_file_name,
            }
            chunk_row = models.KnowledgeChunk(
                knowledge_item_id=item.id,
                workspace_id=item.workspace_id,
                chunk_index=chunk.index,
                content=chunk.content,
                content_hash=hashlib.sha256(chunk.content.encode("utf-8")).hexdigest(),
                token_count=max(1, len(chunk.content.split())),
                metadata_json=chunk_metadata,
                embedding_json=embedding,
            )
            db.add(chunk_row)
            db.flush()
            _persist_chunk_vector(db, chunk_row.id, embedding)

        db.commit()
        db.refresh(item)
    except KnowledgePdfError as exc:
        _delete_uploaded_pdf_after_failure(uploaded)
        db.rollback()
        raise KnowledgeValidationError(str(exc)) from exc
    except KnowledgeValidationError:
        _delete_uploaded_pdf_after_failure(uploaded)
        db.rollback()
        raise
    except (KnowledgeEmbeddingError, ValueError) as exc:
        _delete_uploaded_pdf_after_failure(uploaded)
        db.rollback()
        raise KnowledgeValidationError(str(exc)) from exc
    except Exception:
        _delete_uploaded_pdf_after_failure(uploaded)
        db.rollback()
        raise

    return _knowledge_to_response(db, item)


def _embedding_provider_for_upload(db: Session, *, owner_user_id: str) -> EmbeddingProvider:
    if os.environ.get("AX_KNOWLEDGE_ALLOW_DEMO_EMBEDDINGS") == "1":
        return DeterministicEmbeddingProvider()

    try:
        credential_env = resolve_credential_env(db, owner_user_id=owner_user_id, providers=["openai"])
    except CredentialResolutionError as exc:
        raise KnowledgeValidationError(str(exc)) from exc

    api_key = credential_env.get("OPENAI_API_KEY")
    if not api_key:
        raise KnowledgeValidationError("OpenAI API key is not connected. Add it on the Credentials page.")
    return OpenAIEmbeddingProvider(api_key=api_key)


def _is_pdf_upload(*, source_file_name: str, source_mime_type: str | None) -> bool:
    mime_type = (source_mime_type or "").split(";")[0].strip().lower()
    file_name = (source_file_name or "").strip().lower()
    return mime_type == "application/pdf" or file_name.endswith(".pdf")


def _default_name_from_filename(source_file_name: str) -> str:
    base_name = (source_file_name or "Knowledge PDF").split("/")[-1].split("\\")[-1].strip()
    if base_name.lower().endswith(".pdf"):
        base_name = base_name[:-4]
    return base_name.strip() or "Knowledge PDF"


def _page_spans(pages: list[dict[str, object]]) -> list[dict[str, int]]:
    spans: list[dict[str, int]] = []
    cursor = 0
    for page in pages:
        page_number = int(page["page"])
        page_text = str(page["text"])
        start = cursor
        end = start + len(page_text)
        spans.append({"page": page_number, "start": start, "end": end})
        cursor = end + 2
    return spans


def _page_range_for_chunk(start: int, end: int, spans: list[dict[str, int]]) -> dict[str, int]:
    pages = [
        span["page"]
        for span in spans
        if span["end"] > start and span["start"] < end
    ]
    if not pages:
        return {}
    return {"page_start": min(pages), "page_end": max(pages)}


def _persist_chunk_vector(db: Session, chunk_id: str, embedding: list[float]) -> None:
    if db.bind is None or db.bind.dialect.name == "sqlite":
        return
    vector = "[" + ",".join(str(value) for value in embedding) + "]"
    db.execute(
        text("UPDATE knowledge_chunks SET embedding = CAST(:embedding AS vector) WHERE id = :chunk_id"),
        {"embedding": vector, "chunk_id": str(chunk_id)},
    )


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot_product = sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))
    left_magnitude = math.sqrt(sum(value * value for value in left))
    right_magnitude = math.sqrt(sum(value * value for value in right))
    if left_magnitude == 0 or right_magnitude == 0:
        return 0.0
    return dot_product / (left_magnitude * right_magnitude)


def _delete_uploaded_pdf_after_failure(uploaded) -> None:
    if uploaded is None:
        return
    try:
        delete_knowledge_pdf_object(bucket=uploaded.bucket, object_path=uploaded.object_path)
    except Exception:
        # DB rollback remains the source of truth if best-effort storage cleanup fails.
        pass


def _should_delete_knowledge_storage_object(item: models.KnowledgeItem) -> bool:
    if not item.storage_bucket or not item.storage_path:
        return False
    return item.parser == "pdf"


def replace_version_knowledge(db: Session, *, version_id: str, knowledge_item_ids: list[str]) -> list[dict]:
    version = _require_agent_version(db, version_id=version_id)
    unique_ids = list(dict.fromkeys(knowledge_item_ids))
    items = []
    for item_id in unique_ids:
        item = db.get(models.KnowledgeItem, item_id)
        if item is None:
            raise LookupError(f"Knowledge item not found: {item_id}")
        if item.status != "ready":
            raise KnowledgeValidationError("Only ready knowledge items can be attached to Agent versions.")
        items.append(item)

    try:
        db.query(models.VersionKnowledge).filter(models.VersionKnowledge.version_id == version.id).delete()
        for index, item in enumerate(items):
            db.add(models.VersionKnowledge(version_id=version.id, knowledge_item_id=item.id, sort_order=index))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return list_version_knowledge(db, version_id=version_id)


def delete_knowledge_item(db: Session, *, knowledge_item_id: str) -> None:
    item = db.get(models.KnowledgeItem, knowledge_item_id)
    if item is None:
        raise LookupError(f"Knowledge item not found: {knowledge_item_id}")
    should_delete_storage_object = _should_delete_knowledge_storage_object(item)
    storage_bucket = item.storage_bucket
    storage_path = item.storage_path
    try:
        db.query(models.KnowledgeChunk).filter(
            models.KnowledgeChunk.knowledge_item_id == item.id
        ).delete(synchronize_session=False)
        db.query(models.VersionKnowledge).filter(
            models.VersionKnowledge.knowledge_item_id == item.id
        ).delete(synchronize_session=False)
        db.delete(item)
        db.commit()
    except Exception:
        db.rollback()
        raise
    if should_delete_storage_object:
        delete_knowledge_pdf_object(bucket=storage_bucket, object_path=storage_path)


def search_bound_knowledge_chunks(
    query: str,
    knowledge_item_ids: list[str],
    top_k: int = 5,
    db: Session | None = None,
) -> list[dict]:
    clean_query = query.strip()
    if not clean_query or not knowledge_item_ids or top_k <= 0 or db is None:
        return []
    top_k = min(top_k, 20)
    query_embedding = get_default_embedding_provider().embed_texts([clean_query])[0]
    rows = (
        db.query(models.KnowledgeChunk, models.KnowledgeItem)
        .join(models.KnowledgeItem, models.KnowledgeItem.id == models.KnowledgeChunk.knowledge_item_id)
        .filter(models.KnowledgeChunk.knowledge_item_id.in_(knowledge_item_ids))
        .all()
    )

    ranked_rows = sorted(
        (
            (_cosine_similarity(query_embedding, chunk.embedding_json or []), chunk, item)
            for chunk, item in rows
        ),
        key=lambda row: (-row[0], row[1].chunk_index),
    )[:top_k]

    return [
        {
            "knowledge_item_id": str(item.id),
            "knowledge_name": item.name,
            "content": chunk.content,
            "score": round(score, 6),
            "metadata": chunk.metadata_json or {},
        }
        for score, chunk, item in ranked_rows
    ]


def search_bound_knowledge_chunks_pgvector(
    query: str,
    knowledge_item_ids: list[str],
    query_embedding: list[float],
    top_k: int = 5,
    db: Session | None = None,
) -> list[dict]:
    if not query.strip() or not knowledge_item_ids or not query_embedding or top_k <= 0 or db is None:
        return []

    top_k = min(top_k, 20)
    vector = "[" + ",".join(str(value) for value in query_embedding) + "]"
    knowledge_item_id_array = "{" + ",".join(str(item_id) for item_id in knowledge_item_ids) + "}"
    rows = db.execute(
        text(
            """
            SELECT kc.knowledge_item_id, ki.name AS knowledge_name, kc.content, kc.metadata_json,
                   1 - (kc.embedding <=> CAST(:query_embedding AS vector)) AS score
            FROM knowledge_chunks kc
            JOIN knowledge_items ki ON ki.id = kc.knowledge_item_id
            WHERE kc.knowledge_item_id = ANY(CAST(:knowledge_item_ids AS uuid[]))
              AND kc.embedding IS NOT NULL
            ORDER BY kc.embedding <=> CAST(:query_embedding AS vector)
            LIMIT :top_k
            """
        ),
        {
            "query_embedding": vector,
            "knowledge_item_ids": knowledge_item_id_array,
            "top_k": top_k,
        },
    ).mappings()

    return [
        {
            "knowledge_item_id": str(row["knowledge_item_id"]),
            "knowledge_name": row["knowledge_name"],
            "content": row["content"],
            "score": round(float(row["score"]), 6),
            "metadata": row["metadata_json"] or {},
        }
        for row in rows
    ]
