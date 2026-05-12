import pytest
from sqlalchemy import text

from api.db import models
from api.services.knowledge import delete_knowledge_item, replace_version_knowledge


def test_knowledge_item_chunks_and_version_binding_cascade(db):
    db.execute(text("PRAGMA foreign_keys=ON"))

    agent_asset = models.Asset(asset_type="agent", name="Research Agent")
    agent_version = models.AssetVersion(asset=agent_asset, version_number=1, status="draft", metadata_json={})
    item = models.KnowledgeItem(
        workspace_id="00000000-0000-0000-0000-000000000000",
        owner_user_id="00000000-0000-0000-0000-000000000000",
        name="Product FAQ",
        status="ready",
        source_file_name="faq.txt",
        source_file_size=128,
        source_mime_type="text/plain",
        storage_bucket="knowledge",
        storage_path="workspace/knowledge/faq.txt",
        parser="text",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        chunk_count=1,
    )
    chunk = models.KnowledgeChunk(
        knowledge_item=item,
        workspace_id=item.workspace_id,
        chunk_index=0,
        content="Refunds are available within 30 days.",
        content_hash="hash-1",
        token_count=7,
        metadata_json={"source": "faq.txt"},
        embedding_json=[0.1, 0.2, 0.3],
    )
    binding = models.VersionKnowledge(asset_version=agent_version, knowledge_item=item, sort_order=0)
    db.add_all([agent_asset, agent_version, item, chunk, binding])
    db.commit()

    assert db.query(models.KnowledgeItem).count() == 1
    assert db.query(models.KnowledgeChunk).count() == 1
    assert db.query(models.VersionKnowledge).count() == 1

    db.delete(item)
    db.commit()

    assert db.query(models.KnowledgeItem).count() == 0
    assert db.query(models.KnowledgeChunk).count() == 0
    assert db.query(models.VersionKnowledge).count() == 0


def test_knowledge_list_create_and_delete_metadata(client, db):
    create_response = client.post(
        "/api/knowledge",
        json={
            "name": "Product FAQ",
            "description": "Support answers",
            "source_file_name": "faq.txt",
            "source_file_size": 42,
            "source_mime_type": "text/plain",
            "content": "Refunds are available within 30 days.",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "Product FAQ"
    assert created["status"] == "ready"
    assert created["chunk_count"] == 1

    list_response = client.get("/api/knowledge")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [created["id"]]

    delete_response = client.delete(f"/api/knowledge/{created['id']}")
    assert delete_response.status_code == 204
    assert client.get("/api/knowledge").json() == []
    assert db.query(models.KnowledgeChunk).count() == 0


def test_delete_knowledge_removes_storage_object(monkeypatch, client, db):
    item = _seed_ready_knowledge(db, name="Stored PDF")
    item.parser = "pdf"
    item.storage_bucket = "knowledge-private"
    item.storage_path = "workspace/knowledge/item/demo.pdf"
    db.commit()

    calls = []

    def fake_delete(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("api.services.knowledge.delete_knowledge_pdf_object", fake_delete)

    response = client.delete(f"/api/knowledge/{item.id}")

    assert response.status_code == 204
    assert calls == [{"bucket": "knowledge-private", "object_path": "workspace/knowledge/item/demo.pdf"}]


def test_delete_knowledge_skips_storage_for_non_pdf_parser_even_with_pdf_metadata(monkeypatch, client, db):
    item = _seed_ready_knowledge(db, name="Legacy PDF Metadata")
    item.parser = "text"
    item.source_mime_type = "application/pdf"
    item.storage_bucket = "knowledge-private"
    item.storage_path = "workspace/knowledge/item/demo.pdf"
    db.commit()

    def fail_delete(**kwargs):
        raise AssertionError(f"storage cleanup should not be called: {kwargs}")

    monkeypatch.setattr("api.services.knowledge.delete_knowledge_pdf_object", fail_delete)

    response = client.delete(f"/api/knowledge/{item.id}")

    assert response.status_code == 204


def test_delete_knowledge_does_not_remove_storage_when_db_commit_fails(monkeypatch, db):
    agent_version = _seed_asset_version(db, "agent")
    item = _seed_ready_knowledge(db, name="Stored PDF")
    item.parser = "pdf"
    item.storage_bucket = "knowledge-private"
    item.storage_path = "workspace/knowledge/item/demo.pdf"
    db.add(models.VersionKnowledge(version_id=agent_version.id, knowledge_item_id=item.id, sort_order=0))
    db.commit()

    calls = []
    rollback_calls = 0
    original_rollback = db.rollback

    def fail_commit():
        raise RuntimeError("commit failed")

    def track_rollback():
        nonlocal rollback_calls
        rollback_calls += 1
        original_rollback()

    monkeypatch.setattr(db, "commit", fail_commit)
    monkeypatch.setattr(db, "rollback", track_rollback)
    monkeypatch.setattr("api.services.knowledge.delete_knowledge_pdf_object", lambda **kwargs: calls.append(kwargs))

    with pytest.raises(RuntimeError, match="commit failed"):
        delete_knowledge_item(db, knowledge_item_id=str(item.id))

    assert calls == []
    assert rollback_calls == 1
    assert db.get(models.KnowledgeItem, item.id) is not None
    assert db.query(models.VersionKnowledge).filter_by(knowledge_item_id=item.id).count() == 1


def _seed_asset_version(db, asset_type: str):
    asset = models.Asset(asset_type=asset_type, name=f"{asset_type} asset")
    version = models.AssetVersion(asset=asset, version_number=1, status="draft", metadata_json={})
    db.add_all([asset, version])
    db.commit()
    return version


def _seed_ready_knowledge(db, *, name: str = "FAQ", status: str = "ready"):
    item = models.KnowledgeItem(
        workspace_id="00000000-0000-0000-0000-000000000000",
        owner_user_id="00000000-0000-0000-0000-000000000000",
        name=name,
        status=status,
        source_file_name=f"{name.lower().replace(' ', '-')}.txt",
        source_file_size=12,
        storage_bucket="knowledge",
        storage_path=f"knowledge/{name.lower().replace(' ', '-')}.txt",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        chunk_count=0,
    )
    db.add(item)
    db.commit()
    return item


def test_replace_agent_version_knowledge_bindings(client, db):
    agent_version = _seed_asset_version(db, "agent")
    item = _seed_ready_knowledge(db)

    response = client.put(
        f"/api/versions/{agent_version.id}/knowledge",
        json={"knowledge_item_ids": [str(item.id)]},
    )

    assert response.status_code == 200
    assert response.json()[0]["knowledge_item_id"] == str(item.id)

    clear_response = client.put(f"/api/versions/{agent_version.id}/knowledge", json={"knowledge_item_ids": []})
    assert clear_response.status_code == 200
    assert clear_response.json() == []


def test_replace_agent_version_knowledge_dedupes_ids_and_preserves_first_order(client, db):
    agent_version = _seed_asset_version(db, "agent")
    first_item = _seed_ready_knowledge(db, name="First FAQ")
    second_item = _seed_ready_knowledge(db, name="Second FAQ")

    response = client.put(
        f"/api/versions/{agent_version.id}/knowledge",
        json={"knowledge_item_ids": [str(second_item.id), str(first_item.id), str(second_item.id)]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [row["knowledge_item_id"] for row in payload] == [str(second_item.id), str(first_item.id)]
    assert [row["sort_order"] for row in payload] == [0, 1]


def test_get_agent_version_knowledge_returns_summary_without_storage_path(client, db):
    agent_version = _seed_asset_version(db, "agent")
    item = _seed_ready_knowledge(db)
    client.put(
        f"/api/versions/{agent_version.id}/knowledge",
        json={"knowledge_item_ids": [str(item.id)]},
    )

    response = client.get(f"/api/versions/{agent_version.id}/knowledge")

    assert response.status_code == 200
    knowledge_summary = response.json()[0]["knowledge"]
    assert knowledge_summary == {
        "id": str(item.id),
        "name": item.name,
        "status": "ready",
        "source_file_name": item.source_file_name,
    }
    assert "storage_path" not in knowledge_summary


def test_replacing_with_missing_knowledge_preserves_existing_bindings(client, db):
    agent_version = _seed_asset_version(db, "agent")
    existing_item = _seed_ready_knowledge(db, name="Existing FAQ")
    missing_item_id = "11111111-1111-1111-1111-111111111111"
    seed_response = client.put(
        f"/api/versions/{agent_version.id}/knowledge",
        json={"knowledge_item_ids": [str(existing_item.id)]},
    )
    assert seed_response.status_code == 200

    response = client.put(
        f"/api/versions/{agent_version.id}/knowledge",
        json={"knowledge_item_ids": [missing_item_id]},
    )

    assert response.status_code == 404
    assert client.get(f"/api/versions/{agent_version.id}/knowledge").json()[0]["knowledge_item_id"] == str(
        existing_item.id
    )


def test_replacing_with_non_ready_knowledge_preserves_existing_bindings(client, db):
    agent_version = _seed_asset_version(db, "agent")
    existing_item = _seed_ready_knowledge(db, name="Existing FAQ")
    non_ready_item = _seed_ready_knowledge(db, name="Draft FAQ", status="uploaded")
    seed_response = client.put(
        f"/api/versions/{agent_version.id}/knowledge",
        json={"knowledge_item_ids": [str(existing_item.id)]},
    )
    assert seed_response.status_code == 200

    response = client.put(
        f"/api/versions/{agent_version.id}/knowledge",
        json={"knowledge_item_ids": [str(non_ready_item.id)]},
    )

    assert response.status_code == 422
    assert client.get(f"/api/versions/{agent_version.id}/knowledge").json()[0]["knowledge_item_id"] == str(
        existing_item.id
    )


def test_replace_agent_version_knowledge_rolls_back_when_commit_fails(monkeypatch, db):
    agent_version = _seed_asset_version(db, "agent")
    existing_item = _seed_ready_knowledge(db, name="Existing FAQ")
    replacement_item = _seed_ready_knowledge(db, name="Replacement FAQ")
    db.add(models.VersionKnowledge(version_id=agent_version.id, knowledge_item_id=existing_item.id, sort_order=0))
    db.commit()
    rollback_calls = 0
    original_rollback = db.rollback

    def fail_commit():
        raise RuntimeError("commit failed")

    def track_rollback():
        nonlocal rollback_calls
        rollback_calls += 1
        original_rollback()

    monkeypatch.setattr(db, "commit", fail_commit)
    monkeypatch.setattr(db, "rollback", track_rollback)

    with pytest.raises(RuntimeError, match="commit failed"):
        replace_version_knowledge(db, version_id=str(agent_version.id), knowledge_item_ids=[str(replacement_item.id)])

    assert rollback_calls == 1
    assert db.query(models.VersionKnowledge).one().knowledge_item_id == existing_item.id


def test_reject_binding_knowledge_to_task_version(client, db):
    task_version = _seed_asset_version(db, "task")
    item = _seed_ready_knowledge(db)

    response = client.put(
        f"/api/versions/{task_version.id}/knowledge",
        json={"knowledge_item_ids": [str(item.id)]},
    )

    assert response.status_code == 422
    assert "Knowledge can only be attached to Agent versions" in response.json()["detail"]
