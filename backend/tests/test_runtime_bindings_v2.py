from datetime import datetime
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from api.db import models
from api.runtime.credential_store import decrypt_secret_payload
from api.schemas.runtime import CredentialProviderUpsert, ExecutionBindingResponse
from api.services.runtime import upsert_provider_credential


def _create_asset_version(db, asset_type: str, name: str) -> tuple[models.Asset, models.AssetVersion]:
    asset = models.Asset(asset_type=asset_type, name=name, owner_user_id="test-user")
    asset_version = models.AssetVersion(
        asset=asset,
        version_number=1,
        status="draft",
        metadata_json={"seed": name},
        created_by="test-user",
    )
    db.add_all([asset, asset_version])
    db.flush()
    return asset, asset_version


def test_list_credentials_filters_by_owner_and_status(client, db):
    owned_active = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="openai",
        label="Owned Active",
        secret_ref="secret://owned-active",
        scopes_json=[],
        status="active",
    )
    owned_inactive = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="anthropic",
        label="Owned Inactive",
        secret_ref="secret://owned-inactive",
        scopes_json=[],
        status="inactive",
    )
    owned_revoked = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="openai",
        label="Owned Revoked",
        secret_ref="secret://owned-revoked",
        scopes_json=[],
        status="revoked",
    )
    other_user = models.Credential(
        owner_type="user",
        owner_user_id="other-user",
        workspace_id=None,
        provider="openai",
        label="Other User",
        secret_ref="secret://other-user",
        scopes_json=[],
        status="active",
    )
    workspace_scoped = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id="00000000-0000-0000-0000-000000000001",
        provider="serper",
        label="Workspace Scoped",
        secret_ref="secret://workspace-scoped",
        scopes_json=[],
        status="active",
    )
    malformed_owner_type = models.Credential(
        owner_type="workspace",
        owner_user_id="test-user",
        workspace_id=None,
        provider="firecrawl",
        label="Malformed Owner Type",
        secret_ref="secret://malformed-owner-type",
        scopes_json=[],
        status="active",
    )
    db.add_all([owned_active, owned_inactive, owned_revoked, other_user, workspace_scoped, malformed_owner_type])
    db.commit()

    response = client.get("/api/credentials")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": owned_active.id,
            "label": "Owned Active",
            "provider": "openai",
            "enabled": True,
            "created_at": jsonable_encoder(owned_active.created_at),
            "updated_at": jsonable_encoder(owned_active.updated_at),
        },
    ]


@pytest.mark.parametrize(
    ("owner_user_id", "workspace_id", "status"),
    [
        ("other-user", None, "active"),
        ("test-user", None, "inactive"),
        ("test-user", "00000000-0000-0000-0000-000000000001", "active"),
    ],
)
def test_create_execution_binding_requires_owned_active_user_credentials(client, db, owner_user_id, workspace_id, status):
    _, version = _create_asset_version(db, "agent", "runtime-agent")
    credential = models.Credential(
        owner_type="user",
        owner_user_id=owner_user_id,
        workspace_id=workspace_id,
        provider="openai",
        label="Scoped Key",
        secret_ref="secret://scoped-key",
        scopes_json=[],
        status=status,
    )
    db.add(credential)
    db.commit()

    response = client.post(
        f"/api/versions/{version.id}/bindings",
        json={
            "binding_type": "llm",
            "binding_key": "openai",
            "credential_id": credential.id,
            "metadata_json": {"model": "gpt-4o-mini"},
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == f"Credential not found: {credential.id}"


def test_create_execution_binding_returns_canonical_subject_version_and_synthesized_metadata(client, db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    _, version = _create_asset_version(db, "agent", "runtime-agent")
    db.commit()

    credential_response = client.post(
        "/api/credentials",
        json={
            "label": "Primary OpenAI key",
            "provider": "openai",
            "secret_json": {"api_key": "sk-test-123"},
        },
    )

    assert credential_response.status_code == 201
    credential_body = credential_response.json()
    assert set(credential_body) == {"id", "label", "provider", "enabled", "created_at", "updated_at"}

    binding_response = client.post(
        f"/api/versions/{version.id}/bindings",
        json={
            "binding_type": "llm",
            "binding_key": "openai",
            "credential_id": credential_body["id"],
            "metadata_json": {"model": "gpt-4o-mini"},
        },
    )

    assert binding_response.status_code == 201
    binding_body = binding_response.json()
    assert binding_body == {
        "id": binding_body["id"],
        "subject_version_id": version.id,
        "binding_type": "llm",
        "binding_key": "openai",
        "credential_id": credential_body["id"],
        "metadata_json": {
            "binding_key": "openai",
            "credential_id": credential_body["id"],
            "model": "gpt-4o-mini",
        },
        "created_at": binding_body["created_at"],
    }
    assert "asset_id" not in binding_body
    assert "version_id" not in binding_body

    binding = db.query(models.ExecutionBinding).filter(models.ExecutionBinding.id == binding_body["id"]).one()
    assert binding.subject_version_id == version.id
    assert binding.credential_id == credential_body["id"]
    assert binding.binding_type == "llm"
    assert binding.binding_key == "openai"

    credential = db.query(models.Credential).filter(models.Credential.id == credential_body["id"]).one()
    assert credential.secret_ref == f"secret://db/credential/{credential.id}"
    assert "sk-test-123" not in credential.secret_ref
    secret = db.query(models.CredentialSecret).filter_by(credential_id=credential.id).one()
    assert secret.encrypted_secret_json["cipher"] == "fernet"
    assert "sk-test-123" not in str(secret.encrypted_secret_json)


def test_runtime_binding_round_trip_keeps_secrets_in_credentials_only(client, db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    _, version = _create_asset_version(db, "agent", "runtime-agent")
    db.commit()

    credential_response = client.post(
        "/api/credentials",
        json={
            "label": "Runtime secret",
            "provider": "openai",
            "secret_json": {"api_key": "sk-runtime-secret"},
        },
    )
    assert credential_response.status_code == 201
    credential_id = credential_response.json()["id"]

    binding_response = client.post(
        f"/api/versions/{version.id}/bindings",
        json={
            "binding_type": "llm",
            "binding_key": "openai",
            "credential_id": credential_id,
            "metadata_json": {"model": "gpt-4o-mini"},
        },
    )
    assert binding_response.status_code == 201
    binding_body = binding_response.json()
    assert binding_body["metadata_json"]["credential_id"] == credential_id
    assert binding_body["subject_version_id"] == version.id
    assert "sk-runtime-secret" not in str(binding_body)
    assert "secret_json" not in binding_body

    binding = db.query(models.ExecutionBinding).filter(models.ExecutionBinding.id == binding_body["id"]).one()
    assert binding.subject_version_id == version.id
    assert binding.credential_id == credential_id
    assert not hasattr(binding, "secret_json")


def test_execution_binding_response_requires_canonical_subject_version_id():
    with pytest.raises(ValidationError):
        ExecutionBindingResponse(
            id="binding-1",
            version_id="version-1",
            binding_type="llm",
            binding_key="openai",
            credential_id="credential-1",
            metadata_json={},
            created_at="2026-04-21T00:00:00Z",
        )


def test_execution_binding_schema_enforces_unique_binding_identity(db):
    _, version = _create_asset_version(db, "agent", "runtime-agent")
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="openai",
        label="Binding key",
        secret_ref="secret://binding-key",
        scopes_json=[],
        status="active",
    )
    db.add(credential)
    db.flush()
    db.add(
        models.ExecutionBinding(
            workspace_id="00000000-0000-0000-0000-000000000000",
            subject_version_id=version.id,
            binding_type="llm",
            binding_key="openai",
            credential_id=credential.id,
            created_by="test-user",
        )
    )
    db.commit()

    duplicate = models.ExecutionBinding(
        workspace_id="00000000-0000-0000-0000-000000000000",
        subject_version_id=version.id,
        binding_type="llm",
        binding_key="openai",
        credential_id=credential.id,
        created_by="test-user",
    )
    with db.begin_nested():
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.flush()


def test_credential_secret_model_stores_encrypted_payload_separately(db):
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="openai",
        label="OpenAI",
        secret_ref="secret://db/credential/credential-openai",
        scopes_json=[],
        status="active",
    )
    db.add(credential)
    db.flush()

    secret = models.CredentialSecret(
        credential_id=credential.id,
        encrypted_secret_json={
            "cipher": "fernet",
            "token": "encrypted-token",
            "key_version": "v1",
        },
        encryption_key_version="v1",
    )
    db.add(secret)
    db.commit()

    loaded = db.query(models.CredentialSecret).filter_by(credential_id=credential.id).one()
    assert loaded.credential_id == credential.id
    assert loaded.encrypted_secret_json["cipher"] == "fernet"
    assert loaded.encrypted_secret_json["token"] == "encrypted-token"
    assert loaded.encrypted_secret_json["key_version"] == "v1"
    assert loaded.encryption_key_version == "v1"
    assert loaded.credential.provider == "openai"


def test_credentials_define_active_provider_uniqueness_index():
    table = models.Credential.__table__
    indexes = {index.name: index for index in table.indexes}

    index = indexes["ix_credentials_active_user_provider"]
    assert [column.name for column in index.columns] == ["owner_user_id", "provider"]
    assert "owner_type = :owner_type_1" in str(index.dialect_options["sqlite"]["where"])
    assert "workspace_id IS NULL" in str(index.dialect_options["sqlite"]["where"])
    assert "status = :status_1" in str(index.dialect_options["sqlite"]["where"])


def test_user_credential_secrets_sql_scopes_active_provider_index_to_user_credentials():
    sql_path = Path(__file__).resolve().parents[1] / "sql" / "008_user_credential_secrets.sql"

    sql = sql_path.read_text()

    assert "PARTITION BY owner_user_id, provider" in sql
    assert "status = 'active'" in sql
    assert "owner_type = 'user'" in sql
    assert "workspace_id IS NULL" in sql
    assert "DROP INDEX IF EXISTS ix_credentials_active_user_provider" in sql
    assert "CREATE UNIQUE INDEX IF NOT EXISTS ix_credentials_active_user_provider" in sql
    assert "ON credentials(owner_user_id, provider)" in sql


def test_credentials_active_provider_uniqueness_index_behavior(db):
    active = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="openai",
        label="Active OpenAI",
        secret_ref="secret://active-openai",
        scopes_json=[],
        status="active",
    )
    db.add(active)
    db.commit()

    duplicate_active = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="openai",
        label="Duplicate Active OpenAI",
        secret_ref="secret://duplicate-active-openai",
        scopes_json=[],
        status="active",
    )
    with db.begin_nested():
        db.add(duplicate_active)
        with pytest.raises(IntegrityError):
            db.flush()

    db.add_all(
        [
            models.Credential(
                owner_type="user",
                owner_user_id="test-user",
                workspace_id="00000000-0000-0000-0000-000000000001",
                provider="openai",
                label="Workspace Scoped OpenAI",
                secret_ref="secret://workspace-scoped-openai",
                scopes_json=[],
                status="active",
            ),
            models.Credential(
                owner_type="user",
                owner_user_id="test-user",
                workspace_id=None,
                provider="openai",
                label="Revoked OpenAI",
                secret_ref="secret://revoked-openai",
                scopes_json=[],
                status="revoked",
            ),
            models.Credential(
                owner_type="user",
                owner_user_id="test-user",
                workspace_id=None,
                provider="openai",
                label="Inactive OpenAI",
                secret_ref="secret://inactive-openai",
                scopes_json=[],
                status="inactive",
            ),
            models.Credential(
                owner_type="user",
                owner_user_id="other-user",
                workspace_id=None,
                provider="openai",
                label="Other User OpenAI",
                secret_ref="secret://other-user-openai",
                scopes_json=[],
                status="active",
            ),
            models.Credential(
                owner_type="workspace",
                owner_user_id=None,
                workspace_id=None,
                provider="openai",
                label="Null Owner OpenAI",
                secret_ref="secret://null-owner-openai",
                scopes_json=[],
                status="active",
            ),
            models.Credential(
                owner_type="workspace",
                owner_user_id=None,
                workspace_id=None,
                provider="openai",
                label="Second Null Owner OpenAI",
                secret_ref="secret://second-null-owner-openai",
                scopes_json=[],
                status="active",
            ),
        ]
    )
    db.commit()


def test_put_provider_credential_encrypts_secret_and_returns_metadata_only(client, db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))

    response = client.put(
        "/api/credentials/openai",
        json={"api_key": "sk-openai-secret", "label": "Personal OpenAI"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "openai"
    assert body["label"] == "Personal OpenAI"
    assert body["enabled"] is True
    assert "sk-openai-secret" not in str(body)

    credential = db.query(models.Credential).filter_by(provider="openai", owner_user_id="test-user").one()
    assert credential.secret_ref == f"secret://db/credential/{credential.id}"
    assert "sk-openai-secret" not in str(credential.__dict__)

    secret = db.query(models.CredentialSecret).filter_by(credential_id=credential.id).one()
    assert secret.encrypted_secret_json["cipher"] == "fernet"
    assert "sk-openai-secret" not in str(secret.encrypted_secret_json)


def test_upsert_provider_credential_new_path_does_not_query_secret_with_pending_credential(db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    original_query = db.query

    def query_without_pending_secret_lookup(*entities, **kwargs):
        if models.CredentialSecret in entities and any(
            isinstance(instance, models.Credential) for instance in db.new
        ):
            raise AssertionError("new credential path must not query secrets before commit")
        return original_query(*entities, **kwargs)

    monkeypatch.setattr(db, "query", query_without_pending_secret_lookup)

    credential = upsert_provider_credential(
        db,
        provider="openai",
        payload=CredentialProviderUpsert(api_key="sk-openai-secret"),
        owner_user_id="test-user",
    )

    assert credential.provider == "openai"
    assert db.query(models.CredentialSecret).filter_by(credential_id=credential.id).count() == 1


def test_put_provider_credential_replaces_existing_secret_without_duplicate(client, db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))

    first = client.put("/api/credentials/serper", json={"api_key": "serper-one"})
    second = client.put("/api/credentials/serper", json={"api_key": "serper-two", "label": "Serper"})

    assert first.status_code == 200
    assert second.status_code == 200
    credentials = db.query(models.Credential).filter_by(provider="serper", owner_user_id="test-user").all()
    assert len(credentials) == 1
    assert credentials[0].label == "Serper"
    assert db.query(models.CredentialSecret).filter_by(credential_id=credentials[0].id).count() == 1


def test_put_provider_credential_replacement_updates_credential_timestamp(client, db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))

    first = client.put("/api/credentials/openai", json={"api_key": "sk-openai-one"})
    assert first.status_code == 200

    credential = db.query(models.Credential).filter_by(provider="openai", owner_user_id="test-user").one()
    stale_updated_at = datetime(2026, 1, 1)
    credential.updated_at = stale_updated_at
    db.commit()

    second = client.put("/api/credentials/openai", json={"api_key": "sk-openai-two"})

    assert second.status_code == 200
    db.refresh(credential)
    assert credential.updated_at > stale_updated_at
    assert second.json()["updated_at"] == jsonable_encoder(credential.updated_at)


def test_put_provider_credential_does_not_update_workspace_scoped_credential(client, db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    workspace_scoped = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id="00000000-0000-0000-0000-000000000001",
        provider="serper",
        label="Workspace Serper",
        secret_ref="secret://workspace-serper",
        scopes_json=[],
        status="active",
    )
    db.add(workspace_scoped)
    db.commit()

    response = client.put("/api/credentials/serper", json={"api_key": "serper-user", "label": "User Serper"})

    assert response.status_code == 200
    db.refresh(workspace_scoped)
    assert workspace_scoped.label == "Workspace Serper"
    assert workspace_scoped.secret_ref == "secret://workspace-serper"
    credentials = db.query(models.Credential).filter_by(provider="serper", owner_user_id="test-user").all()
    assert len(credentials) == 2
    assert {credential.workspace_id for credential in credentials} == {
        None,
        "00000000-0000-0000-0000-000000000001",
    }


def test_post_credential_disabled_creates_inactive_encrypted_credential(client, db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))

    response = client.post(
        "/api/credentials",
        json={
            "label": "Disabled OpenAI",
            "provider": "openai",
            "secret_json": {"api_key": "sk-disabled"},
            "enabled": False,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["enabled"] is False
    assert client.get("/api/credentials").json() == []
    credential = db.query(models.Credential).filter_by(id=body["id"]).one()
    assert credential.status == "inactive"
    secret = db.query(models.CredentialSecret).filter_by(credential_id=credential.id).one()
    assert decrypt_secret_payload(secret.encrypted_secret_json) == {"api_key": "sk-disabled"}


def test_post_credential_duplicate_replaces_active_secret(client, db, monkeypatch):
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", key)

    first = client.post(
        "/api/credentials",
        json={
            "label": "First OpenAI",
            "provider": "openai",
            "secret_json": {"api_key": "sk-first"},
        },
    )
    second = client.post(
        "/api/credentials",
        json={
            "label": "Second OpenAI",
            "provider": "openai",
            "secret_json": {"api_key": "sk-second"},
        },
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    credential = db.query(models.Credential).filter_by(provider="openai", owner_user_id="test-user").one()
    assert credential.label == "Second OpenAI"
    secret = db.query(models.CredentialSecret).filter_by(credential_id=credential.id).one()
    assert decrypt_secret_payload(secret.encrypted_secret_json) == {"api_key": "sk-second"}


def test_put_provider_credential_rejects_unknown_provider(client, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))

    response = client.put("/api/credentials/github", json={"api_key": "ghp-secret"})

    assert response.status_code == 422
    assert response.json()["detail"] == "Unsupported API key credential provider: github"


def test_put_provider_credential_rejects_oauth_only_provider(client, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))

    response = client.put("/api/credentials/google_workspace", json={"api_key": "oauth-secret"})

    assert response.status_code == 422
    assert response.json()["detail"] == "Unsupported API key credential provider: google_workspace"


def test_put_provider_credential_requires_encryption_key(client, monkeypatch):
    monkeypatch.delenv("CREDENTIAL_ENCRYPTION_KEY", raising=False)

    response = client.put("/api/credentials/openai", json={"api_key": "sk-openai-secret"})

    assert response.status_code == 422
    assert response.json()["detail"] == "Credential encryption is not configured."


def test_delete_provider_credential_revokes_metadata_and_removes_secret(client, db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    create_response = client.put("/api/credentials/firecrawl", json={"api_key": "fc-secret"})
    assert create_response.status_code == 200
    credential_id = create_response.json()["id"]

    delete_response = client.delete("/api/credentials/firecrawl")

    assert delete_response.status_code == 204
    credential = db.query(models.Credential).filter_by(id=credential_id).one()
    assert credential.status == "revoked"
    assert db.query(models.CredentialSecret).filter_by(credential_id=credential_id).count() == 0
    assert client.get("/api/credentials").json() == []


def test_delete_provider_credential_does_not_revoke_workspace_scoped_credential(client, db):
    workspace_scoped = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id="00000000-0000-0000-0000-000000000001",
        provider="firecrawl",
        label="Workspace Firecrawl",
        secret_ref="secret://workspace-firecrawl",
        scopes_json=[],
        status="active",
    )
    db.add(workspace_scoped)
    db.commit()

    response = client.delete("/api/credentials/firecrawl")

    assert response.status_code == 404
    db.refresh(workspace_scoped)
    assert workspace_scoped.status == "active"
