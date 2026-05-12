import pytest

from api.runtime.knowledge_search_tool import AXKnowledgeSearchTool


@pytest.fixture(autouse=True)
def _deterministic_search_provider(monkeypatch):
    from api.services import knowledge
    from api.services.knowledge_embeddings import DeterministicEmbeddingProvider

    provider = DeterministicEmbeddingProvider(dimension=2)
    monkeypatch.setattr(knowledge, "get_default_embedding_provider", lambda: provider)
    return provider


def _create_knowledge_item(db, *, name="FAQ", storage_path="knowledge-item", chunk_count=1):
    from api.db import models

    item = models.KnowledgeItem(
        workspace_id="00000000-0000-0000-0000-000000000000",
        owner_user_id="00000000-0000-0000-0000-000000000000",
        name=name,
        status="ready",
        source_file_name=f"{storage_path}.txt",
        source_file_size=1,
        storage_bucket="knowledge",
        storage_path=storage_path,
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        chunk_count=chunk_count,
    )
    db.add(item)
    db.flush()
    return item


def test_knowledge_search_tool_scopes_to_bound_ids(monkeypatch):
    calls = []

    def fake_search(query, knowledge_item_ids, top_k):
        calls.append({"query": query, "knowledge_item_ids": knowledge_item_ids, "top_k": top_k})
        return [
            {
                "knowledge_item_id": "k1",
                "knowledge_name": "FAQ",
                "content": "Refunds in 30 days.",
                "score": 0.9,
                "metadata": {},
            }
        ]

    tool = AXKnowledgeSearchTool(knowledge_item_ids=["k1"], search_fn=fake_search)
    result = tool._run(query="refund policy")

    assert calls == [{"query": "refund policy", "knowledge_item_ids": ["k1"], "top_k": 5}]
    assert result["matches"][0]["knowledge_item_id"] == "k1"


def test_knowledge_search_tool_returns_controlled_error_when_search_fails():
    def failing_search(query, knowledge_item_ids, top_k):
        raise RuntimeError("provider unavailable")

    tool = AXKnowledgeSearchTool(knowledge_item_ids=["k1"], search_fn=failing_search)

    assert tool._run(query="refund policy") == {
        "matches": [],
        "error": "Knowledge search is unavailable.",
    }


def test_search_bound_knowledge_chunks_filters_to_bound_items(db):
    from api.db import models
    from api.services.knowledge import search_bound_knowledge_chunks

    k1 = _create_knowledge_item(db, name="FAQ", storage_path="k1")
    k2 = _create_knowledge_item(db, name="Private", storage_path="k2")
    db.add_all([k1, k2])
    db.flush()
    db.add(models.KnowledgeChunk(knowledge_item_id=k1.id, workspace_id=k1.workspace_id, chunk_index=0, content="Refund policy is 30 days.", content_hash="a", metadata_json={}, embedding_json=[1.0, 0.0]))
    db.add(models.KnowledgeChunk(knowledge_item_id=k2.id, workspace_id=k2.workspace_id, chunk_index=0, content="Secret roadmap.", content_hash="b", metadata_json={}, embedding_json=[1.0, 0.0]))
    db.commit()

    matches = search_bound_knowledge_chunks("refund", [str(k1.id)], top_k=5, db=db)

    assert [match["knowledge_item_id"] for match in matches] == [str(k1.id)]
    assert matches[0]["content"] == "Refund policy is 30 days."


def test_search_bound_knowledge_chunks_ranks_by_embedding_similarity(db, monkeypatch):
    from api.db import models
    from api.services import knowledge
    from api.services.knowledge_embeddings import DeterministicEmbeddingProvider

    provider = DeterministicEmbeddingProvider(dimension=3)
    monkeypatch.setattr(knowledge, "get_default_embedding_provider", lambda: provider)

    item = _create_knowledge_item(db, name="FAQ", storage_path="ranked")
    db.add(models.KnowledgeChunk(knowledge_item_id=item.id, workspace_id=item.workspace_id, chunk_index=0, content="Warranty lasts one year.", content_hash="rank-a", metadata_json={}, embedding_json=[0.0, 1.0, 0.0]))
    db.add(models.KnowledgeChunk(knowledge_item_id=item.id, workspace_id=item.workspace_id, chunk_index=1, content="Refund policy is 30 days.", content_hash="rank-b", metadata_json={}, embedding_json=provider.embed_texts(["refund policy"])[0]))
    db.commit()

    matches = knowledge.search_bound_knowledge_chunks("refund policy", [str(item.id)], top_k=2, db=db)

    assert matches[0]["content"] == "Refund policy is 30 days."


def test_search_bound_knowledge_chunks_pgvector_casts_ids_and_skips_null_embeddings():
    from api.services.knowledge import search_bound_knowledge_chunks_pgvector

    class FakeResult:
        def mappings(self):
            return [
                {
                    "knowledge_item_id": "00000000-0000-0000-0000-000000000001",
                    "knowledge_name": "FAQ",
                    "content": "Refund policy is 30 days.",
                    "metadata_json": {"page_start": 1},
                    "score": 0.87654321,
                }
            ]

    class FakeDb:
        def __init__(self):
            self.statement = None
            self.params = None

        def execute(self, statement, params):
            self.statement = str(statement)
            self.params = params
            return FakeResult()

    fake_db = FakeDb()

    matches = search_bound_knowledge_chunks_pgvector(
        "refund policy",
        ["00000000-0000-0000-0000-000000000001"],
        [0.1, 0.2, 0.3],
        top_k=50,
        db=fake_db,
    )

    assert "kc.knowledge_item_id = ANY(CAST(:knowledge_item_ids AS uuid[]))" in fake_db.statement
    assert "kc.embedding IS NOT NULL" in fake_db.statement
    assert fake_db.params["query_embedding"] == "[0.1,0.2,0.3]"
    assert fake_db.params["knowledge_item_ids"] == "{00000000-0000-0000-0000-000000000001}"
    assert fake_db.params["top_k"] == 20
    assert matches == [
        {
            "knowledge_item_id": "00000000-0000-0000-0000-000000000001",
            "knowledge_name": "FAQ",
            "content": "Refund policy is 30 days.",
            "score": 0.876543,
            "metadata": {"page_start": 1},
        }
    ]


def test_knowledge_search_tool_can_use_db_bound_fallback_search(db):
    from api.db import models
    from api.services.knowledge import search_bound_knowledge_chunks

    item = _create_knowledge_item(db, name="FAQ", storage_path="tool-k1")
    private_item = _create_knowledge_item(db, name="Private", storage_path="tool-k2")
    db.add(models.KnowledgeChunk(knowledge_item_id=item.id, workspace_id=item.workspace_id, chunk_index=0, content="Refund policy is 30 days.", content_hash="tool-a", metadata_json={}, embedding_json=[1.0, 0.0]))
    db.add(models.KnowledgeChunk(knowledge_item_id=private_item.id, workspace_id=private_item.workspace_id, chunk_index=0, content="Secret roadmap.", content_hash="tool-b", metadata_json={}, embedding_json=[1.0, 0.0]))
    db.commit()

    def db_bound_search(query, knowledge_item_ids, top_k):
        return search_bound_knowledge_chunks(query, knowledge_item_ids, top_k=top_k, db=db)

    tool = AXKnowledgeSearchTool(knowledge_item_ids=[str(item.id)], search_fn=db_bound_search)
    result = tool._run(query="refund policy")

    assert [match["knowledge_item_id"] for match in result["matches"]] == [str(item.id)]
    assert result["matches"][0]["content"] == "Refund policy is 30 days."


def test_search_bound_knowledge_chunks_returns_empty_for_blank_query(db):
    from api.db import models
    from api.services.knowledge import search_bound_knowledge_chunks

    item = _create_knowledge_item(db, storage_path="blank-query")
    db.add(models.KnowledgeChunk(knowledge_item_id=item.id, workspace_id=item.workspace_id, chunk_index=0, content="Refund policy is 30 days.", content_hash="blank-query", metadata_json={}, embedding_json=[1.0, 0.0]))
    db.commit()

    assert search_bound_knowledge_chunks("", [str(item.id)], db=db) == []
    assert search_bound_knowledge_chunks("   ", [str(item.id)], db=db) == []


def test_search_bound_knowledge_chunks_returns_empty_for_non_positive_top_k(db):
    from api.db import models
    from api.services.knowledge import search_bound_knowledge_chunks

    item = _create_knowledge_item(db, storage_path="non-positive-top-k")
    db.add(models.KnowledgeChunk(knowledge_item_id=item.id, workspace_id=item.workspace_id, chunk_index=0, content="Refund policy is 30 days.", content_hash="non-positive-top-k", metadata_json={}, embedding_json=[1.0, 0.0]))
    db.commit()

    assert search_bound_knowledge_chunks("refund", [str(item.id)], top_k=0, db=db) == []
    assert search_bound_knowledge_chunks("refund", [str(item.id)], top_k=-1, db=db) == []


def test_search_bound_knowledge_chunks_clamps_top_k(db):
    from api.db import models
    from api.services.knowledge import search_bound_knowledge_chunks

    item = _create_knowledge_item(db, storage_path="clamped-top-k", chunk_count=25)
    for index in range(25):
        db.add(
            models.KnowledgeChunk(
                knowledge_item_id=item.id,
                workspace_id=item.workspace_id,
                chunk_index=index,
                content=f"Refund chunk {index}",
                content_hash=f"clamp-{index}",
                metadata_json={},
                embedding_json=[1.0, 0.0],
            )
        )
    db.commit()

    matches = search_bound_knowledge_chunks("refund", [str(item.id)], top_k=100, db=db)

    assert len(matches) == 20
    assert matches[0]["content"] == "Refund chunk 0"
    assert matches[-1]["content"] == "Refund chunk 19"
