import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from cryptography.fernet import Fernet

from api.db import models
from api.runtime.credential_store import encrypt_secret_payload


def test_knowledge_upload_real_rag_sql_declares_pgvector_schema():
    sql = Path("backend/sql/014_knowledge_upload_real_rag.sql").read_text()

    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "embedding vector(1536)" in sql
    assert "knowledge_chunks_embedding_idx" in sql
    assert "knowledge_chunks_workspace_item_idx" in sql


class FakeKnowledgeBucket:
    def __init__(self):
        self.upload_calls = []
        self.remove_calls = []
        self.upload_error = None

    def upload(self, path: str, file: bytes, file_options: dict[str, str]):
        if self.upload_error is not None:
            raise self.upload_error
        self.upload_calls.append({"path": path, "file": file, "file_options": file_options})
        return {"Key": path}

    def remove(self, paths: list[str]):
        self.remove_calls.append(paths)
        return [{"name": path} for path in paths]


class FakeKnowledgeStorage:
    def __init__(self):
        self.bucket = FakeKnowledgeBucket()

    def from_(self, bucket_name: str):
        assert bucket_name == "knowledge-private"
        return self.bucket


class FakeKnowledgeSupabase:
    def __init__(self):
        self.storage = FakeKnowledgeStorage()


def _add_credential(db, provider: str, api_key: str, owner_user_id: str = "test-user"):
    credential = models.Credential(
        owner_type="user",
        owner_user_id=owner_user_id,
        workspace_id=None,
        provider=provider,
        label=f"{provider} key",
        secret_ref="",
        scopes_json=[],
        status="active",
    )
    db.add(credential)
    db.flush()
    credential.secret_ref = f"secret://db/credential/{credential.id}"
    db.add(
        models.CredentialSecret(
            credential_id=credential.id,
            encrypted_secret_json=encrypt_secret_payload({"api_key": api_key}),
            encryption_key_version="v1",
        )
    )
    db.commit()
    return credential


def test_upload_knowledge_pdf_bytes_uses_private_bucket_and_safe_path(monkeypatch):
    from api.services import knowledge_storage

    fake_supabase = FakeKnowledgeSupabase()
    monkeypatch.setenv("AX_SUPABASE_KNOWLEDGE_BUCKET", "knowledge-private")
    monkeypatch.setattr(
        knowledge_storage.uuid,
        "uuid4",
        lambda: UUID("12345678-1234-4234-8234-123456789abc"),
    )

    uploaded = knowledge_storage.upload_knowledge_pdf_bytes(
        pdf_bytes=b"%PDF demo",
        workspace_id="workspace/../one",
        knowledge_item_id="item-1",
        original_filename="../Product FAQ.pdf",
        supabase_client=fake_supabase,
    )

    assert uploaded.bucket == "knowledge-private"
    assert uploaded.object_path == "workspaceone/knowledge/item-1/12345678123442348234123456789abc-Product_FAQ.pdf"
    assert fake_supabase.storage.bucket.upload_calls == [
        {
            "path": uploaded.object_path,
            "file": b"%PDF demo",
            "file_options": {
                "content-type": "application/pdf",
                "cache-control": "3600",
                "upsert": "false",
            },
        }
    ]


def test_upload_knowledge_pdf_bytes_uses_ascii_storage_key_for_korean_filename(monkeypatch):
    from api.services import knowledge_storage

    fake_supabase = FakeKnowledgeSupabase()
    monkeypatch.setenv("AX_SUPABASE_KNOWLEDGE_BUCKET", "knowledge-private")
    monkeypatch.setattr(
        knowledge_storage.uuid,
        "uuid4",
        lambda: UUID("12345678-1234-4234-8234-123456789abc"),
    )

    uploaded = knowledge_storage.upload_knowledge_pdf_bytes(
        pdf_bytes=b"%PDF demo",
        workspace_id="workspace",
        knowledge_item_id="item-1",
        original_filename="제안요청서.pdf",
        supabase_client=fake_supabase,
    )

    assert uploaded.object_path == "workspace/knowledge/item-1/12345678123442348234123456789abc-document.pdf"
    assert uploaded.object_path.isascii()


def test_upload_knowledge_pdf_bytes_wraps_storage_api_error(monkeypatch):
    from api.services import knowledge_storage

    fake_supabase = FakeKnowledgeSupabase()
    fake_supabase.storage.bucket.upload_error = RuntimeError("Invalid key")
    monkeypatch.setenv("AX_SUPABASE_KNOWLEDGE_BUCKET", "knowledge-private")

    with pytest.raises(ValueError, match="Knowledge file could not be uploaded"):
        knowledge_storage.upload_knowledge_pdf_bytes(
            pdf_bytes=b"%PDF demo",
            workspace_id="workspace",
            knowledge_item_id="item-1",
            original_filename="제안요청서.pdf",
            supabase_client=fake_supabase,
        )


def test_upload_knowledge_pdf_bytes_requires_storage_configuration(monkeypatch):
    from api.services.knowledge_storage import upload_knowledge_pdf_bytes

    monkeypatch.delenv("AX_SUPABASE_KNOWLEDGE_BUCKET", raising=False)

    with pytest.raises(ValueError, match="Knowledge storage is not configured"):
        upload_knowledge_pdf_bytes(
            pdf_bytes=b"%PDF demo",
            workspace_id="workspace",
            knowledge_item_id="item",
            original_filename="demo.pdf",
            supabase_client=None,
        )


def test_delete_knowledge_pdf_object_removes_storage_path(monkeypatch):
    from api.services.knowledge_storage import delete_knowledge_pdf_object

    fake_supabase = FakeKnowledgeSupabase()
    monkeypatch.setenv("AX_SUPABASE_KNOWLEDGE_BUCKET", "knowledge-private")

    delete_knowledge_pdf_object(
        bucket="knowledge-private",
        object_path="workspace/knowledge/item/demo.pdf",
        supabase_client=fake_supabase,
    )

    assert fake_supabase.storage.bucket.remove_calls == [["workspace/knowledge/item/demo.pdf"]]


def _minimal_pdf_with_text() -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_extract_pdf_text_rejects_empty_pdf_bytes():
    from api.services.knowledge_pdf import KnowledgePdfError, extract_pdf_text

    with pytest.raises(KnowledgePdfError, match="PDF file content is empty"):
        extract_pdf_text(b"")


def test_extract_pdf_text_rejects_blank_or_scanned_pdf():
    from api.services.knowledge_pdf import KnowledgePdfError, extract_pdf_text

    with pytest.raises(KnowledgePdfError, match="No readable text was found"):
        extract_pdf_text(_minimal_pdf_with_text())


def test_extract_pdf_text_returns_page_segments(monkeypatch):
    from api.services import knowledge_pdf

    class FakePage:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

    class FakeReader:
        pages = [FakePage("Refunds are available within 30 days."), FakePage("Warranty lasts one year.")]

    monkeypatch.setattr(knowledge_pdf, "PdfReader", lambda _buffer: FakeReader())

    result = knowledge_pdf.extract_pdf_text(b"%PDF fake")

    assert result.text == "Refunds are available within 30 days.\n\nWarranty lasts one year."
    assert result.pages == [
        {"page": 1, "text": "Refunds are available within 30 days."},
        {"page": 2, "text": "Warranty lasts one year."},
    ]


def test_extract_pdf_text_wraps_page_extraction_errors(monkeypatch):
    from api.services import knowledge_pdf

    class BrokenPage:
        def extract_text(self):
            raise RuntimeError("xref lookup failed")

    class FakeReader:
        # Narrow monkeypatch: avoids a heavyweight test-only PDF text generator while
        # exercising extraction-time parser failures after PdfReader construction.
        pages = [BrokenPage()]

    monkeypatch.setattr(knowledge_pdf, "PdfReader", lambda _buffer: FakeReader())

    with pytest.raises(knowledge_pdf.KnowledgePdfError, match="PDF file could not be parsed"):
        knowledge_pdf.extract_pdf_text(b"%PDF fake")


def test_deterministic_embedding_provider_returns_configured_dimension():
    from api.services.knowledge_embeddings import DeterministicEmbeddingProvider

    provider = DeterministicEmbeddingProvider(dimension=8)

    assert provider.embed_texts(["refund policy", "warranty"]) == [
        [0.909804, 0.819608, 0.376471, 0.580392, 0.066667, 0.745098, 0.372549, 0.611765],
        [0.607843, 0.647059, 0.85098, 0.341176, 0.94902, 0.513725, 0.45098, 0.031373],
    ]


def test_openai_embedding_provider_requires_api_key(monkeypatch):
    from api.services.knowledge_embeddings import KnowledgeEmbeddingError, OpenAIEmbeddingProvider

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(KnowledgeEmbeddingError, match="Embedding provider is not configured"):
        OpenAIEmbeddingProvider()


def test_openai_embedding_provider_rejects_non_default_dimension():
    from api.services.knowledge_embeddings import KnowledgeEmbeddingError, OpenAIEmbeddingProvider

    with pytest.raises(KnowledgeEmbeddingError, match="Only 1536-dimensional embeddings are supported for Knowledge"):
        OpenAIEmbeddingProvider(api_key="test-key", dimension=8)


def test_openai_embedding_provider_validates_returned_dimension(monkeypatch):
    from api.services.knowledge_embeddings import KnowledgeEmbeddingError, OpenAIEmbeddingProvider

    class FakeEmbedding:
        embedding = [0.1, 0.2]

    class FakeEmbeddingsClient:
        def create(self, model, input):
            assert model == "text-embedding-3-small"
            assert input == ["refund policy"]
            return SimpleNamespace(data=[FakeEmbedding()])

    class FakeOpenAI:
        def __init__(self, api_key):
            assert api_key == "test-key"
            self.embeddings = FakeEmbeddingsClient()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    provider = OpenAIEmbeddingProvider(api_key="test-key")

    with pytest.raises(KnowledgeEmbeddingError, match="Embedding provider returned an unexpected vector dimension"):
        provider.embed_texts([" refund policy "])


def test_get_default_embedding_provider_can_use_demo_fallback(monkeypatch):
    from api.services.knowledge_embeddings import DeterministicEmbeddingProvider, get_default_embedding_provider

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("AX_KNOWLEDGE_ALLOW_DEMO_EMBEDDINGS", "1")

    assert isinstance(get_default_embedding_provider(), DeterministicEmbeddingProvider)


def test_upload_knowledge_pdf_creates_ready_item(client, db, monkeypatch):
    from api.services import knowledge
    from api.services.knowledge_embeddings import DeterministicEmbeddingProvider
    from api.services.knowledge_pdf import ExtractedPdfText
    from api.services.knowledge_storage import KnowledgeStorageUpload

    vector_calls = []
    monkeypatch.setattr(
        knowledge,
        "upload_knowledge_pdf_bytes",
        lambda **_kwargs: KnowledgeStorageUpload(
            bucket="knowledge-private",
            object_path="workspace/knowledge/item/demo.pdf",
        ),
    )
    monkeypatch.setattr(
        knowledge,
        "extract_pdf_text",
        lambda _bytes: ExtractedPdfText(
            text="Refunds are available within 30 days.",
            pages=[{"page": 1, "text": "Refunds are available within 30 days."}],
        ),
    )
    monkeypatch.setattr(
        knowledge,
        "_embedding_provider_for_upload",
        lambda _db, owner_user_id: DeterministicEmbeddingProvider(dimension=8),
    )
    monkeypatch.setattr(
        knowledge,
        "_persist_chunk_vector",
        lambda db, chunk_id, embedding: vector_calls.append(
            {"db": db, "chunk_id": chunk_id, "embedding": embedding}
        ),
        raising=False,
    )

    response = client.post(
        "/api/knowledge/upload",
        data={"name": "Product FAQ", "description": "Support answers"},
        files={"file": ("faq.pdf", b"%PDF demo", "application/pdf")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "Product FAQ"
    assert payload["status"] == "ready"
    assert payload["source_file_name"] == "faq.pdf"
    assert payload["source_mime_type"] == "application/pdf"
    assert payload["chunk_count"] == 1
    chunk = db.query(models.KnowledgeChunk).one()
    assert chunk.metadata_json["source_file_name"] == "faq.pdf"
    assert chunk.metadata_json["page_start"] == 1
    assert chunk.metadata_json["page_end"] == 1
    assert vector_calls == [{"db": db, "chunk_id": chunk.id, "embedding": chunk.embedding_json}]


def test_upload_knowledge_pdf_rejects_non_pdf(client):
    response = client.post(
        "/api/knowledge/upload",
        data={"name": "Product FAQ"},
        files={"file": ("faq.txt", b"not a pdf", "text/plain")},
    )

    assert response.status_code == 422
    assert "Only PDF files are supported" in response.json()["detail"]


def test_upload_knowledge_pdf_returns_parser_error(client, monkeypatch):
    from api.services import knowledge
    from api.services.knowledge_embeddings import DeterministicEmbeddingProvider
    from api.services.knowledge_pdf import KnowledgePdfError
    from api.services.knowledge_storage import KnowledgeStorageUpload

    monkeypatch.setattr(
        knowledge,
        "_embedding_provider_for_upload",
        lambda _db, owner_user_id: DeterministicEmbeddingProvider(dimension=8),
    )
    monkeypatch.setattr(
        knowledge,
        "upload_knowledge_pdf_bytes",
        lambda **_kwargs: KnowledgeStorageUpload(
            bucket="knowledge-private",
            object_path="workspace/knowledge/item/demo.pdf",
        ),
    )

    def fail_extract(_bytes):
        raise KnowledgePdfError("No readable text was found in this PDF.")

    monkeypatch.setattr(knowledge, "extract_pdf_text", fail_extract)
    monkeypatch.setattr(knowledge, "delete_knowledge_pdf_object", lambda **_kwargs: None)

    response = client.post(
        "/api/knowledge/upload",
        data={"name": "Blank PDF"},
        files={"file": ("blank.pdf", b"%PDF blank", "application/pdf")},
    )

    assert response.status_code == 422
    assert "No readable text was found" in response.json()["detail"]


def test_upload_knowledge_pdf_returns_storage_config_error(client, monkeypatch):
    from api.services import knowledge
    from api.services.knowledge_embeddings import DeterministicEmbeddingProvider

    def fail_upload(**_kwargs):
        raise ValueError("Knowledge storage is not configured.")

    monkeypatch.setattr(
        knowledge,
        "_embedding_provider_for_upload",
        lambda _db, owner_user_id: DeterministicEmbeddingProvider(dimension=8),
    )
    monkeypatch.setattr(knowledge, "upload_knowledge_pdf_bytes", fail_upload)

    response = client.post(
        "/api/knowledge/upload",
        data={"name": "Product FAQ"},
        files={"file": ("faq.pdf", b"%PDF demo", "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Knowledge storage is not configured."


def test_upload_knowledge_pdf_returns_missing_openai_credential_error(client, monkeypatch):
    from api.services import knowledge

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))

    def fail_upload(**_kwargs):
        raise AssertionError("storage should not be touched when the OpenAI credential is missing")

    monkeypatch.setattr(knowledge, "upload_knowledge_pdf_bytes", fail_upload)

    response = client.post(
        "/api/knowledge/upload",
        data={"name": "Product FAQ"},
        files={"file": ("faq.pdf", b"%PDF demo", "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "OpenAI API key is not connected. Add it on the Credentials page."


def test_upload_knowledge_pdf_uses_current_user_openai_credential(client, db, monkeypatch):
    from api.services import knowledge
    from api.services.knowledge_embeddings import DeterministicEmbeddingProvider
    from api.services.knowledge_pdf import ExtractedPdfText
    from api.services.knowledge_storage import KnowledgeStorageUpload

    provider_api_keys = []

    class RecordingOpenAIEmbeddingProvider(DeterministicEmbeddingProvider):
        provider = "openai"
        model = "text-embedding-3-small"
        dimension = 8

        def __init__(self, api_key: str):
            provider_api_keys.append(api_key)

    monkeypatch.setenv("OPENAI_API_KEY", "env-key-that-must-not-be-used")
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    _add_credential(db, "openai", "sk-user-openai")
    _add_credential(db, "openai", "sk-other-openai", owner_user_id="other-user")
    monkeypatch.setattr(knowledge, "OpenAIEmbeddingProvider", RecordingOpenAIEmbeddingProvider)
    monkeypatch.setattr(
        knowledge,
        "upload_knowledge_pdf_bytes",
        lambda **_kwargs: KnowledgeStorageUpload(
            bucket="knowledge-private",
            object_path="workspace/knowledge/item/demo.pdf",
        ),
    )
    monkeypatch.setattr(
        knowledge,
        "extract_pdf_text",
        lambda _bytes: ExtractedPdfText(
            text="Refunds are available within 30 days.",
            pages=[{"page": 1, "text": "Refunds are available within 30 days."}],
        ),
    )
    monkeypatch.setattr(knowledge, "_persist_chunk_vector", lambda *_args, **_kwargs: None)

    response = client.post(
        "/api/knowledge/upload",
        data={"name": "Product FAQ"},
        files={"file": ("faq.pdf", b"%PDF demo", "application/pdf")},
    )

    assert response.status_code == 201
    assert provider_api_keys == ["sk-user-openai"]
    item = db.query(models.KnowledgeItem).one()
    assert str(item.owner_user_id) == "test-user"
