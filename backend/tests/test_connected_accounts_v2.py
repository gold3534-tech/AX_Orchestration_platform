from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime, timedelta
from threading import Barrier, BrokenBarrierError, Lock, Thread
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.core.database import Base, get_db
from api.db import models
from api.db.models.runtime import OAuthState
from api.main import app
from api.services import connected_accounts as connected_accounts_service
from api.services.connected_accounts import OAuthStateError, complete_oauth_callback
from api.runtime.credential_providers import provider_response_payload
from api.runtime.credential_resolver import CredentialResolutionError, resolve_credential_env
from api.runtime.credential_store import decrypt_secret_payload, encrypt_secret_payload
from api.runtime.oauth_clients import resolve_oauth_token_payload
from api.schemas.runtime import OAuthStartPathRequest


@asynccontextmanager
async def _test_lifespan(_app):
    yield


@contextmanager
def unauthenticated_test_client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    previous_overrides = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = override_get_db
    try:
        with patch.object(app.router, "lifespan_context", _test_lifespan):
            with TestClient(app, raise_server_exceptions=False) as test_client:
                yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


class FakeMetaOAuthResponse:
    def __init__(self, payload, *, ok=True, json_error=None):
        self._payload = payload
        self.ok = ok
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise AssertionError("Unexpected Meta Graph error response")


class FakeGoogleOAuthResponse:
    def __init__(self, payload, *, ok=True, json_error=None):
        self._payload = payload
        self.ok = ok
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise AssertionError("Unexpected Google OAuth error response")


def configure_meta_oauth_env(monkeypatch):
    monkeypatch.setenv("META_INSTAGRAM_APP_ID", "meta-app-id")
    monkeypatch.setenv("META_INSTAGRAM_APP_SECRET", "meta-app-secret")
    monkeypatch.setenv(
        "META_INSTAGRAM_REDIRECT_URI",
        "http://localhost:8000/api/connected-accounts/oauth/callback?provider=meta_instagram",
    )
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v24.0")


def configure_google_oauth_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLIENT_ID", "google-client-id")
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLIENT_SECRET", "google-client-secret")
    monkeypatch.setenv(
        "GOOGLE_WORKSPACE_REDIRECT_URI",
        "http://localhost:8000/api/connected-accounts/oauth/callback?provider=google_workspace",
    )


def mock_meta_graph(monkeypatch, *, page_payloads, token_payload=None):
    calls = []
    token_payload = token_payload or {
        "access_token": "meta-user-access-token",
        "token_type": "bearer",
        "expires_in": 3600,
    }

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "params": params or {}, "headers": headers or {}, "timeout": timeout})
        if url.endswith("/oauth/access_token"):
            assert params["client_id"] == "meta-app-id"
            assert params["client_secret"] == "meta-app-secret"
            assert (
                params["redirect_uri"]
                == "http://localhost:8000/api/connected-accounts/oauth/callback?provider=meta_instagram"
            )
            assert params["code"] == "meta-code"
            return FakeMetaOAuthResponse(token_payload)
        if url.endswith("/me/accounts"):
            assert params["fields"] == "id,name,access_token,tasks"
            assert headers == {"Authorization": "Bearer meta-user-access-token"}
            return FakeMetaOAuthResponse(
                {
                    "data": [
                        {
                            "id": item["page_id"],
                            "name": item["page_name"],
                            "access_token": item["page_access_token"],
                            "tasks": ["CREATE_CONTENT", "MANAGE"],
                        }
                        for item in page_payloads
                    ]
                }
            )
        for item in page_payloads:
            if url.endswith(f"/{item['page_id']}"):
                assert params["fields"] == "instagram_business_account"
                assert headers == {"Authorization": f"Bearer {item['page_access_token']}"}
                payload = {"id": item["page_id"]}
                if item.get("ig_user_id"):
                    payload["instagram_business_account"] = {"id": item["ig_user_id"]}
                return FakeMetaOAuthResponse(payload)
        raise AssertionError(f"Unexpected Meta Graph URL: {url}")

    import api.integrations.meta_oauth as meta_oauth

    if hasattr(meta_oauth, "requests"):
        monkeypatch.setattr(meta_oauth.requests, "get", fake_get)
    else:
        monkeypatch.setattr(meta_oauth, "requests", SimpleNamespace(get=fake_get), raising=False)
    return calls


def mock_google_oauth(monkeypatch, *, token_payload=None):
    calls = []
    token_payload = token_payload or {
        "access_token": "google-access-token",
        "refresh_token": "google-refresh-token",
        "expires_in": 3600,
        "scope": "https://www.googleapis.com/auth/spreadsheets",
        "token_type": "Bearer",
    }

    def fake_post(url, data=None, timeout=None):
        calls.append({"url": url, "data": data or {}, "timeout": timeout})
        assert url == "https://oauth2.googleapis.com/token"
        assert data["client_id"] == "google-client-id"
        assert data["client_secret"] == "google-client-secret"
        assert (
            data["redirect_uri"]
            == "http://localhost:8000/api/connected-accounts/oauth/callback?provider=google_workspace"
        )
        assert data["grant_type"] == "authorization_code"
        assert data["code"] == "google-code"
        return FakeGoogleOAuthResponse(token_payload)

    import api.integrations.google_oauth as google_oauth

    monkeypatch.setattr(google_oauth.requests, "post", fake_post)
    return calls


def test_oauth_state_is_exported_from_models_package():
    assert models.OAuthState is OAuthState


def test_supported_oauth_providers_expose_non_secret_metadata():
    google = provider_response_payload("google_workspace")
    instagram = provider_response_payload("meta_instagram")

    assert google == {
        "provider": "google_workspace",
        "label": "Google Workspace",
        "env_var": "AX_GOOGLE_WORKSPACE_OAUTH",
        "capabilities": ["sheets", "drive", "oauth2"],
        "auth_type": "oauth2",
    }
    assert instagram["provider"] == "meta_instagram"
    assert instagram["auth_type"] == "oauth2"
    assert "instagram_publish" in instagram["capabilities"]


def test_oauth_credential_secret_round_trips_without_frontend_fields(db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="google_workspace",
        auth_type="oauth2",
        label="Google Workspace",
        provider_account_id="google-account-1",
        provider_account_label="creator@example.com",
        scopes_json=["https://www.googleapis.com/auth/spreadsheets"],
        status="active",
        metadata_json={"picture": "https://example.com/avatar.png"},
        expires_at=expires_at,
        secret_ref="secret://db/credential/google",
    )
    db.add(credential)
    db.flush()
    db.add(
        models.CredentialSecret(
            credential_id=credential.id,
            encrypted_secret_json=encrypt_secret_payload(
                {
                    "access_token": "access-token",
                    "refresh_token": "refresh-token",
                    "expires_at": expires_at.isoformat(),
                }
            ),
            encryption_key_version="v1",
        )
    )
    db.commit()

    stored = db.get(models.Credential, credential.id)
    assert stored.auth_type == "oauth2"
    assert stored.provider_account_label == "creator@example.com"
    assert decrypt_secret_payload(stored.secret.encrypted_secret_json)["refresh_token"] == "refresh-token"


def test_connected_account_provider_listing_exposes_oauth_metadata(client):
    response = client.get("/api/connected-accounts/providers")

    assert response.status_code == 200
    providers = {item["provider"]: item for item in response.json()}
    assert providers["google_workspace"] == {
        "provider": "google_workspace",
        "display_name": "Google Workspace",
        "label": "Google Workspace",
        "env_var": "AX_GOOGLE_WORKSPACE_OAUTH",
        "auth_type": "oauth2",
        "connect_label": "Connect Google Workspace",
        "reconnect_label": "Reconnect Google Workspace",
        "supports_disconnect": True,
        "supports_test_connection": True,
        "capabilities": ["sheets", "drive", "oauth2"],
        "capability_keys": ["sheets", "drive", "oauth2"],
        "default_scopes": [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
        ],
    }
    assert providers["meta_instagram"]["connect_label"] == "Connect Instagram"
    assert providers["meta_instagram"]["reconnect_label"] == "Reconnect Instagram"
    assert providers["meta_instagram"]["supports_disconnect"] is True
    assert providers["meta_instagram"]["supports_test_connection"] is True
    assert providers["meta_instagram"]["capability_keys"] == ["instagram_publish", "oauth2"]
    assert providers["meta_instagram"]["default_scopes"] == [
        "instagram_basic",
        "instagram_content_publish",
        "pages_show_list",
    ]
    assert "firecrawl" not in providers
    assert "google_gemini" not in providers


def test_google_oauth_start_stores_hashed_state_and_returns_google_authorization_url(client, db, monkeypatch):
    configure_google_oauth_env(monkeypatch)

    response = client.post(
        "/api/connected-accounts/oauth/start",
        json={
            "provider": "google_workspace",
            "redirect_path": "/settings/credentials",
            "scopes": ["https://www.googleapis.com/auth/spreadsheets"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "google_workspace"
    parsed = urlparse(body["authorization_url"])
    params = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://accounts.google.com/o/oauth2/v2/auth"
    assert params["client_id"] == ["google-client-id"]
    assert params["redirect_uri"] == [
        "http://localhost:8000/api/connected-accounts/oauth/callback?provider=google_workspace"
    ]
    assert params["response_type"] == ["code"]
    assert params["scope"] == ["https://www.googleapis.com/auth/spreadsheets"]
    assert params["state"] == [body["state"]]
    assert params["access_type"] == ["offline"]
    assert params["prompt"] == ["consent"]
    assert params["include_granted_scopes"] == ["true"]
    assert "auth_url" not in body
    assert body["expires_at"]

    oauth_state = db.query(models.OAuthState).one()
    assert oauth_state.owner_user_id == "test-user"
    assert oauth_state.provider == "google_workspace"
    assert oauth_state.status == "pending"
    assert oauth_state.state_token != body["state"]
    assert len(oauth_state.state_token) == 64
    assert oauth_state.requested_scopes_json == ["https://www.googleapis.com/auth/spreadsheets"]
    assert oauth_state.redirect_path == "/settings/credentials"


def test_google_oauth_callback_exchanges_code_and_stores_encrypted_refresh_token(client, db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    configure_google_oauth_env(monkeypatch)
    calls = mock_google_oauth(monkeypatch)
    start_response = client.post(
        "/api/connected-accounts/oauth/start",
        json={
            "provider": "google_workspace",
            "redirect_path": "/settings/credentials",
            "scopes": ["https://www.googleapis.com/auth/spreadsheets"],
        },
    )

    response = client.get(
        "/api/connected-accounts/oauth/callback",
        params={"provider": "google_workspace", "state": start_response.json()["state"], "code": "google-code"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["redirect_path"] == "/settings/credentials"
    assert body["account"]["provider"] == "google_workspace"
    assert body["account"]["provider_account_id"] == "google_workspace"
    assert body["account"]["provider_account_label"] == "Google Workspace"
    assert body["account"]["scopes"] == ["https://www.googleapis.com/auth/spreadsheets"]
    assert calls[0]["data"]["code"] == "google-code"

    credential = db.query(models.Credential).filter_by(provider="google_workspace").one()
    secret_payload = decrypt_secret_payload(credential.secret.encrypted_secret_json)
    assert secret_payload["access_token"] == "google-access-token"
    assert secret_payload["refresh_token"] == "google-refresh-token"
    assert "google-client-secret" not in str(secret_payload)


def test_google_oauth_callback_falls_back_to_requested_scopes_when_token_response_omits_scope(client, db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    configure_google_oauth_env(monkeypatch)
    token_payload = {
        "access_token": "google-access-token",
        "refresh_token": "google-refresh-token",
        "expires_in": 3600,
        "token_type": "Bearer",
    }
    mock_google_oauth(monkeypatch, token_payload=token_payload)
    start_response = client.post(
        "/api/connected-accounts/oauth/start",
        json={
            "provider": "google_workspace",
            "redirect_path": "/settings/credentials",
            "scopes": ["https://www.googleapis.com/auth/spreadsheets"],
        },
    )

    response = client.get(
        "/api/connected-accounts/oauth/callback",
        params={"provider": "google_workspace", "state": start_response.json()["state"], "code": "google-code"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["account"]["scopes"] == ["https://www.googleapis.com/auth/spreadsheets"]
    assert body["account"]["missing_scopes"] == ["https://www.googleapis.com/auth/drive.file"]

    credential = db.query(models.Credential).filter_by(provider="google_workspace").one()
    assert credential.scopes_json == ["https://www.googleapis.com/auth/spreadsheets"]


def test_meta_oauth_start_returns_real_facebook_authorization_url(client, db, monkeypatch):
    monkeypatch.setenv("META_INSTAGRAM_APP_ID", "meta-app-id")
    monkeypatch.setenv("META_INSTAGRAM_APP_SECRET", "meta-app-secret")
    monkeypatch.setenv(
        "META_INSTAGRAM_REDIRECT_URI",
        "http://localhost:8000/api/connected-accounts/oauth/callback?provider=meta_instagram",
    )
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v24.0")

    response = client.post(
        "/api/connected-accounts/oauth/start",
        json={
            "provider": "meta_instagram",
            "redirect_path": "/build/credentials",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "meta_instagram"
    assert body["state"]
    assert body["state"] in body["authorization_url"]
    assert body["authorization_url"].startswith("https://www.facebook.com/v24.0/dialog/oauth?")
    assert "client_id=meta-app-id" in body["authorization_url"]
    assert "response_type=code" in body["authorization_url"]
    assert "instagram_basic" in body["authorization_url"]
    assert "instagram_content_publish" in body["authorization_url"]
    assert "pages_show_list" in body["authorization_url"]
    assert "meta-app-secret" not in body["authorization_url"]

    oauth_state = db.query(models.OAuthState).one()
    assert oauth_state.owner_user_id == "test-user"
    assert oauth_state.provider == "meta_instagram"
    assert oauth_state.status == "pending"
    assert oauth_state.state_token != body["state"]
    assert len(oauth_state.state_token) == 64
    assert oauth_state.requested_scopes_json == [
        "instagram_basic",
        "instagram_content_publish",
        "pages_show_list",
    ]
    assert oauth_state.redirect_path == "/build/credentials"


def test_meta_oauth_start_rejects_missing_app_config_before_state_creation(client, db, monkeypatch):
    monkeypatch.delenv("META_INSTAGRAM_APP_ID", raising=False)
    monkeypatch.delenv("META_INSTAGRAM_APP_SECRET", raising=False)
    monkeypatch.delenv("META_INSTAGRAM_REDIRECT_URI", raising=False)

    response = client.post(
        "/api/connected-accounts/oauth/start",
        json={"provider": "meta_instagram", "redirect_path": "/build/credentials"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Meta Instagram OAuth is not configured."
    assert db.query(models.OAuthState).count() == 0


def test_oauth_start_rejects_scope_escalation(client, db):
    response = client.post(
        "/api/connected-accounts/oauth/start",
        json={
            "provider": "google_workspace",
            "scopes": [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/admin.directory.user",
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Unsupported OAuth scope for google_workspace: "
        "https://www.googleapis.com/auth/admin.directory.user"
    )
    assert db.query(models.OAuthState).count() == 0


@pytest.mark.parametrize(
    "redirect_path",
    [
        "https://evil.example/callback",
        "//evil.example/callback",
        "settings/credentials",
    ],
)
def test_oauth_start_rejects_external_redirect_path(client, db, redirect_path):
    response = client.post(
        "/api/connected-accounts/oauth/start",
        json={"provider": "meta_instagram", "redirect_path": redirect_path},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "redirect_path must be an internal relative path."
    assert db.query(models.OAuthState).count() == 0


def test_canonical_get_oauth_callback_stores_encrypted_credential_and_hides_secret(client, db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    configure_google_oauth_env(monkeypatch)
    mock_google_oauth(monkeypatch)
    start_response = client.post(
        "/api/connected-accounts/oauth/start",
        json={
            "provider": "google_workspace",
            "redirect_path": "/flows/flow-1/credentials",
            "scopes": ["https://www.googleapis.com/auth/spreadsheets"],
        },
    )
    state = start_response.json()["state"]

    response = client.get(
        "/api/connected-accounts/oauth/callback",
        params={"provider": "google_workspace", "state": state, "code": "google-code"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "redirect_path": "/flows/flow-1/credentials",
        "account": {
            "id": body["account"]["id"],
            "provider": "google_workspace",
            "label": "Google Workspace",
            "auth_type": "oauth2",
            "provider_account_id": "google_workspace",
            "provider_account_label": "Google Workspace",
            "status": "active",
            "scopes": ["https://www.googleapis.com/auth/spreadsheets"],
            "missing_scopes": ["https://www.googleapis.com/auth/drive.file"],
            "expires_at": body["account"]["expires_at"],
            "last_checked_at": None,
            "capability_keys": ["sheets", "drive", "oauth2"],
            "created_at": body["account"]["created_at"],
            "updated_at": body["account"]["updated_at"],
        }
    }
    assert "access_token" not in str(body)
    assert "refresh_token" not in str(body)

    credential = db.query(models.Credential).filter_by(provider="google_workspace").one()
    assert credential.auth_type == "oauth2"
    assert credential.owner_user_id == "test-user"
    assert credential.provider_account_id == "google_workspace"
    assert credential.provider_account_label == "Google Workspace"
    assert credential.scopes_json == ["https://www.googleapis.com/auth/spreadsheets"]
    assert credential.secret_ref == f"secret://db/credential/{credential.id}"
    assert credential.secret.encrypted_secret_json["cipher"] == "fernet"
    assert "access-token" not in str(credential.secret.encrypted_secret_json)
    assert decrypt_secret_payload(credential.secret.encrypted_secret_json)["refresh_token"] == "google-refresh-token"

    oauth_state = db.query(models.OAuthState).one()
    assert oauth_state.status == "used"


def test_provider_specific_get_oauth_callback_alias_supports_browser_redirect(client, db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    configure_meta_oauth_env(monkeypatch)
    mock_meta_graph(
        monkeypatch,
        page_payloads=[
            {
                "page_id": "page-1",
                "page_name": "Creator Page",
                "page_access_token": "page-access-token-1",
                "ig_user_id": "17841405822304914",
            }
        ],
    )
    start_response = client.post(
        "/api/connected-accounts/oauth/start",
        json={
            "provider": "meta_instagram",
            "redirect_path": "/settings/social",
            "scopes": ["instagram_basic"],
        },
    )
    state = start_response.json()["state"]

    response = client.get(
        "/api/connected-accounts/meta_instagram/oauth/callback",
        params={"state": state, "code": "meta-code"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["redirect_path"] == "/settings/social"
    assert body["account"]["provider"] == "meta_instagram"
    assert body["account"]["provider_account_label"] == "Creator Page"
    assert body["account"]["provider_account_id"] == "17841405822304914"
    assert "access-token" not in str(body)


def test_meta_oauth_callback_stores_single_instagram_account_id(client, db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    configure_meta_oauth_env(monkeypatch)
    calls = mock_meta_graph(
        monkeypatch,
        page_payloads=[
            {
                "page_id": "page-1",
                "page_name": "Creator Page",
                "page_access_token": "page-access-token-1",
                "ig_user_id": "17841405822304914",
            }
        ],
    )
    start_response = client.post(
        "/api/connected-accounts/oauth/start",
        json={"provider": "meta_instagram", "redirect_path": "/build/credentials"},
    )

    response = client.get(
        "/api/connected-accounts/oauth/callback",
        params={"provider": "meta_instagram", "state": start_response.json()["state"], "code": "meta-code"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["redirect_path"] == "/build/credentials"
    assert body["account"]["provider"] == "meta_instagram"
    assert body["account"]["provider_account_id"] == "17841405822304914"
    assert body["account"]["provider_account_label"] == "Creator Page"
    assert body["account"]["scopes"] == [
        "instagram_basic",
        "instagram_content_publish",
        "pages_show_list",
    ]
    assert body["account"]["missing_scopes"] == []
    assert "meta-user-access-token" not in str(body)
    assert "page-access-token-1" not in str(body)
    assert "meta-app-secret" not in str(body)

    credential = db.query(models.Credential).filter_by(provider="meta_instagram").one()
    assert credential.provider_account_id == "17841405822304914"
    assert credential.provider_account_label == "Creator Page"
    assert credential.metadata_json == {
        "page_id": "page-1",
        "page_name": "Creator Page",
        "ig_user_id": "17841405822304914",
    }
    secret_payload = decrypt_secret_payload(credential.secret.encrypted_secret_json)
    assert secret_payload["access_token"] == "meta-user-access-token"
    assert secret_payload["provider_specific"] == {
        "page_access_token": "page-access-token-1",
        "page_id": "page-1",
        "ig_user_id": "17841405822304914",
    }
    assert db.query(models.OAuthState).one().status == "used"
    assert [call["url"] for call in calls] == [
        "https://graph.facebook.com/v24.0/oauth/access_token",
        "https://graph.facebook.com/v24.0/me/accounts",
        "https://graph.facebook.com/v24.0/page-1",
    ]


@pytest.mark.parametrize("expires_in", [float("inf"), 10**100])
def test_meta_oauth_callback_ignores_invalid_token_expiry(client, db, monkeypatch, expires_in):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    configure_meta_oauth_env(monkeypatch)
    mock_meta_graph(
        monkeypatch,
        page_payloads=[
            {
                "page_id": "page-1",
                "page_name": "Creator Page",
                "page_access_token": "page-access-token-1",
                "ig_user_id": "17841405822304914",
            }
        ],
        token_payload={
            "access_token": "meta-user-access-token",
            "token_type": "bearer",
            "expires_in": expires_in,
        },
    )
    start_response = client.post("/api/connected-accounts/oauth/start", json={"provider": "meta_instagram"})

    response = client.get(
        "/api/connected-accounts/oauth/callback",
        params={"provider": "meta_instagram", "state": start_response.json()["state"], "code": "meta-code"},
    )

    assert response.status_code == 200
    assert response.json()["account"]["expires_at"] is None
    credential = db.query(models.Credential).filter_by(provider="meta_instagram").one()
    assert credential.expires_at is None
    secret_payload = decrypt_secret_payload(credential.secret.encrypted_secret_json)
    assert "expires_at" not in secret_payload


def test_meta_oauth_callback_rejects_no_instagram_account_without_storing_credential(client, db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    configure_meta_oauth_env(monkeypatch)
    mock_meta_graph(
        monkeypatch,
        page_payloads=[
            {
                "page_id": "page-1",
                "page_name": "Creator Page",
                "page_access_token": "page-access-token-1",
                "ig_user_id": None,
            }
        ],
    )
    start_response = client.post("/api/connected-accounts/oauth/start", json={"provider": "meta_instagram"})

    response = client.get(
        "/api/connected-accounts/oauth/callback",
        params={"provider": "meta_instagram", "state": start_response.json()["state"], "code": "meta-code"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "No Instagram professional account was found."
    assert db.query(models.Credential).filter_by(provider="meta_instagram").count() == 0
    assert db.query(models.CredentialSecret).count() == 0
    assert db.query(models.OAuthState).one().status == "failed"


def test_meta_oauth_callback_rejects_multiple_instagram_accounts_without_storing_credential(client, db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    configure_meta_oauth_env(monkeypatch)
    mock_meta_graph(
        monkeypatch,
        page_payloads=[
            {
                "page_id": "page-1",
                "page_name": "Creator Page",
                "page_access_token": "page-access-token-1",
                "ig_user_id": "17841405822304914",
            },
            {
                "page_id": "page-2",
                "page_name": "Second Page",
                "page_access_token": "page-access-token-2",
                "ig_user_id": "17841405822304915",
            },
        ],
    )
    start_response = client.post("/api/connected-accounts/oauth/start", json={"provider": "meta_instagram"})

    response = client.get(
        "/api/connected-accounts/oauth/callback",
        params={"provider": "meta_instagram", "state": start_response.json()["state"], "code": "meta-code"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Multiple Instagram accounts were found; account selection is not supported yet."
    )
    assert db.query(models.Credential).filter_by(provider="meta_instagram").count() == 0
    assert db.query(models.CredentialSecret).count() == 0
    assert db.query(models.OAuthState).one().status == "failed"


def test_public_get_oauth_callback_redeems_state_without_bearer(client, db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    configure_google_oauth_env(monkeypatch)
    mock_google_oauth(monkeypatch)
    start_response = client.post(
        "/api/connected-accounts/oauth/start",
        json={
            "provider": "google_workspace",
            "redirect_path": "/settings/credentials",
            "scopes": ["https://www.googleapis.com/auth/spreadsheets"],
        },
    )

    with unauthenticated_test_client(db) as no_auth_client:
        response = no_auth_client.get(
            "/api/connected-accounts/google_workspace/oauth/callback",
            params={"state": start_response.json()["state"], "code": "google-code"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["redirect_path"] == "/settings/credentials"
    assert body["account"]["provider"] == "google_workspace"
    assert body["account"]["provider_account_label"] == "Google Workspace"
    assert db.query(models.Credential).filter_by(owner_user_id="test-user", provider="google_workspace").count() == 1


def test_public_canonical_get_oauth_callback_redeems_state_without_bearer(client, db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    configure_meta_oauth_env(monkeypatch)
    mock_meta_graph(
        monkeypatch,
        page_payloads=[
            {
                "page_id": "page-1",
                "page_name": "Creator Page",
                "page_access_token": "page-access-token-1",
                "ig_user_id": "17841405822304914",
            }
        ],
    )
    start_response = client.post(
        "/api/connected-accounts/oauth/start",
        json={
            "provider": "meta_instagram",
            "redirect_path": "/settings/social",
            "scopes": ["instagram_basic"],
        },
    )

    with unauthenticated_test_client(db) as no_auth_client:
        response = no_auth_client.get(
            "/api/connected-accounts/oauth/callback",
            params={
                "provider": "meta_instagram",
                "state": start_response.json()["state"],
                "code": "meta-code",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["redirect_path"] == "/settings/social"
    assert body["account"]["provider"] == "meta_instagram"
    assert body["account"]["provider_account_label"] == "Creator Page"
    assert body["account"]["provider_account_id"] == "17841405822304914"


def test_public_get_oauth_callback_rejects_bad_state_without_bearer(db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))

    with unauthenticated_test_client(db) as no_auth_client:
        response = no_auth_client.get(
            "/api/connected-accounts/google_workspace/oauth/callback",
            params={"state": "not-a-real-state", "code": "google-code"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid or expired OAuth state."
    assert db.query(models.Credential).filter_by(provider="google_workspace").count() == 0


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("get", "/api/connected-accounts", None),
        ("post", "/api/connected-accounts/oauth/start", {"provider": "google_workspace"}),
        ("post", "/api/connected-accounts/google_workspace/oauth/callback", {"state": "state", "code": "code"}),
        ("delete", "/api/connected-accounts/google_workspace", None),
    ],
)
def test_connected_account_management_routes_still_require_bearer(
    db,
    method,
    path,
    json_body,
):
    with unauthenticated_test_client(db) as no_auth_client:
        request = getattr(no_auth_client, method)
        kwargs = {} if json_body is None else {"json": json_body}

        response = request(path, **kwargs)

    assert response.status_code == 403
    assert response.json()["detail"] == "Not authenticated"


def test_oauth_callback_rejects_replayed_state(client, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    configure_google_oauth_env(monkeypatch)
    mock_google_oauth(monkeypatch)
    start_response = client.post(
        "/api/connected-accounts/oauth/start",
        json={"provider": "google_workspace", "scopes": ["https://www.googleapis.com/auth/spreadsheets"]},
    )
    params = {
        "provider": "google_workspace",
        "state": start_response.json()["state"],
        "code": "google-code",
    }

    first_response = client.get("/api/connected-accounts/oauth/callback", params=params)
    second_response = client.get("/api/connected-accounts/oauth/callback", params=params)

    assert first_response.status_code == 200
    assert second_response.status_code == 422
    assert second_response.json()["detail"] == "Invalid or expired OAuth state."


def test_concurrent_oauth_callback_replay_exchanges_code_once(tmp_path, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    configure_google_oauth_env(monkeypatch)
    mock_google_oauth(monkeypatch)
    engine = create_engine(
        f"sqlite:///{tmp_path / 'oauth-concurrency.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    setup_session = SessionLocal()
    try:
        start_result = connected_accounts_service.start_oauth(
            setup_session,
            provider="google_workspace",
            payload=OAuthStartPathRequest(scopes=["https://www.googleapis.com/auth/spreadsheets"]),
            owner_user_id="test-user",
        )
        state = start_result.state
    finally:
        setup_session.close()

    adapter = connected_accounts_service._OAUTH_ADAPTERS["google_workspace"]
    original_exchange_code = adapter.exchange_code
    barrier = Barrier(2)
    lock = Lock()
    exchange_count = 0
    results = []

    def blocking_exchange_code(*, code: str, scopes: list[str]):
        nonlocal exchange_count
        with lock:
            exchange_count += 1
        try:
            barrier.wait(timeout=0.5)
        except BrokenBarrierError:
            pass
        return original_exchange_code(code=code, scopes=scopes)

    monkeypatch.setattr(adapter, "exchange_code", blocking_exchange_code)

    def redeem_state():
        session = SessionLocal()
        try:
            complete_oauth_callback(
                session,
                provider="google_workspace",
                state=state,
                code="google-code",
                owner_user_id="test-user",
            )
            results.append("ok")
        except OAuthStateError:
            results.append("state-error")
        finally:
            session.close()

    threads = [Thread(target=redeem_state) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == ["ok", "state-error"]
    assert exchange_count == 1
    verify_session = SessionLocal()
    try:
        assert (
            verify_session.query(models.Credential)
            .filter_by(provider="google_workspace", status="active")
            .count()
            == 1
        )
        assert verify_session.query(models.OAuthState).one().status == "used"
    finally:
        verify_session.close()
        engine.dispose()


def test_oauth_callback_rejects_cross_owner_state(client, db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    configure_google_oauth_env(monkeypatch)
    start_response = client.post(
        "/api/connected-accounts/oauth/start",
        json={"provider": "google_workspace", "scopes": ["https://www.googleapis.com/auth/spreadsheets"]},
    )

    with pytest.raises(OAuthStateError, match="Invalid or expired OAuth state."):
        complete_oauth_callback(
            db,
            provider="google_workspace",
            state=start_response.json()["state"],
            code="google-code",
            owner_user_id="other-user",
        )

    assert db.query(models.Credential).filter_by(provider="google_workspace").count() == 0
    assert db.query(models.OAuthState).one().status == "pending"


@pytest.mark.parametrize(
    ("path", "params"),
    [
        (
            "/api/connected-accounts/oauth/callback",
            {"provider": "google_workspace", "state": "state", "code": ""},
        ),
        (
            "/api/connected-accounts/google_workspace/oauth/callback",
            {"state": "state", "code": ""},
        ),
        (
            "/api/connected-accounts/oauth/callback",
            {"provider": "google_workspace", "state": "", "code": "code"},
        ),
        (
            "/api/connected-accounts/google_workspace/oauth/callback",
            {"state": "", "code": "code"},
        ),
    ],
)
def test_get_oauth_callback_rejects_empty_query_values(client, db, monkeypatch, path, params):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))

    response = client.get(path, params=params)

    assert response.status_code == 422
    assert response.json()["detail"] == "field must not be empty"
    assert db.query(models.Credential).count() == 0


def test_connected_account_listing_returns_non_secret_metadata(client, db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="meta_instagram",
        auth_type="oauth2",
        label="Instagram",
        provider_account_id="ig-user-1",
        provider_account_label="@creator",
        scopes_json=["instagram_basic"],
        status="active",
        metadata_json={"display_name": "@creator"},
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        secret_ref="secret://db/credential/instagram",
    )
    db.add(credential)
    db.flush()
    db.add(
        models.CredentialSecret(
            credential_id=credential.id,
            encrypted_secret_json=encrypt_secret_payload({"access_token": "ig-access-token"}),
            encryption_key_version="v1",
        )
    )
    db.commit()

    response = client.get("/api/connected-accounts")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": credential.id,
            "provider": "meta_instagram",
            "label": "Instagram",
            "auth_type": "oauth2",
            "provider_account_id": "ig-user-1",
            "provider_account_label": "@creator",
            "status": "active",
            "scopes": ["instagram_basic"],
            "missing_scopes": ["instagram_content_publish", "pages_show_list"],
            "expires_at": response.json()[0]["expires_at"],
            "last_checked_at": None,
            "capability_keys": ["instagram_publish", "oauth2"],
            "created_at": response.json()[0]["created_at"],
            "updated_at": response.json()[0]["updated_at"],
        }
    ]
    assert "ig-access-token" not in str(response.json())
    assert "metadata" not in response.json()[0]
    assert "connected_at" not in response.json()[0]


def test_resolve_oauth_token_payload_returns_runtime_only_payload(db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="google_workspace",
        auth_type="oauth2",
        label="Google Workspace",
        provider_account_id="google-account-1",
        provider_account_label="creator@example.com",
        scopes_json=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
        ],
        status="active",
        metadata_json={"display_name": "Creator"},
        expires_at=expires_at,
        secret_ref="secret://db/credential/google",
    )
    db.add(credential)
    db.flush()
    db.add(
        models.CredentialSecret(
            credential_id=credential.id,
            encrypted_secret_json=encrypt_secret_payload(
                {
                    "access_token": "access-token",
                    "refresh_token": "refresh-token",
                    "expires_at": expires_at.isoformat(),
                    "token_type": "Bearer",
                }
            ),
            encryption_key_version="v1",
        )
    )
    db.commit()

    payload = resolve_oauth_token_payload(
        db,
        owner_user_id="test-user",
        provider="google_workspace",
        required_scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )

    assert payload.credential_id == credential.id
    assert payload.provider == "google_workspace"
    assert payload.provider_account_id == "google-account-1"
    assert payload.provider_account_label == "creator@example.com"
    assert payload.scopes == [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
    ]
    assert payload.access_token == "access-token"
    assert payload.expires_at == expires_at
    assert not hasattr(payload, "refresh_token")
    assert not hasattr(payload, "token_payload")
    assert "refresh-token" not in str(payload)
    assert "Bearer" not in str(payload)
    assert db.get(models.Credential, credential.id).secret_ref == "secret://db/credential/google"


def test_resolve_oauth_token_payload_uses_credential_expiry_when_secret_expiry_missing(db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="google_workspace",
        auth_type="oauth2",
        label="Google Workspace",
        scopes_json=["https://www.googleapis.com/auth/spreadsheets"],
        status="active",
        expires_at=expires_at,
        secret_ref="secret://db/credential/google",
    )
    db.add(credential)
    db.flush()
    db.add(
        models.CredentialSecret(
            credential_id=credential.id,
            encrypted_secret_json=encrypt_secret_payload({"access_token": "access-token"}),
            encryption_key_version="v1",
        )
    )
    db.commit()

    payload = resolve_oauth_token_payload(
        db,
        owner_user_id="test-user",
        provider="google_workspace",
        required_scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )

    assert payload.expires_at == expires_at


def test_resolve_oauth_token_payload_rejects_expired_credential_expiry(db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="google_workspace",
        auth_type="oauth2",
        label="Google Workspace",
        scopes_json=["https://www.googleapis.com/auth/spreadsheets"],
        status="active",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
        secret_ref="secret://db/credential/google",
    )
    db.add(credential)
    db.flush()
    db.add(
        models.CredentialSecret(
            credential_id=credential.id,
            encrypted_secret_json=encrypt_secret_payload(
                {
                    "access_token": "access-token",
                    "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                }
            ),
            encryption_key_version="v1",
        )
    )
    db.commit()

    with pytest.raises(CredentialResolutionError, match="Google Workspace account token is expired"):
        resolve_oauth_token_payload(
            db,
            owner_user_id="test-user",
            provider="google_workspace",
            required_scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )


def test_resolve_oauth_token_payload_rejects_expired_secret_expiry(db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="google_workspace",
        auth_type="oauth2",
        label="Google Workspace",
        scopes_json=["https://www.googleapis.com/auth/spreadsheets"],
        status="active",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        secret_ref="secret://db/credential/google",
    )
    db.add(credential)
    db.flush()
    db.add(
        models.CredentialSecret(
            credential_id=credential.id,
            encrypted_secret_json=encrypt_secret_payload(
                {
                    "access_token": "access-token",
                    "expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                }
            ),
            encryption_key_version="v1",
        )
    )
    db.commit()

    with pytest.raises(CredentialResolutionError, match="Google Workspace account token is expired"):
        resolve_oauth_token_payload(
            db,
            owner_user_id="test-user",
            provider="google_workspace",
            required_scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )


def test_resolve_oauth_token_payload_rejects_malformed_secret_expiry(db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="google_workspace",
        auth_type="oauth2",
        label="Google Workspace",
        scopes_json=["https://www.googleapis.com/auth/spreadsheets"],
        status="active",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        secret_ref="secret://db/credential/google",
    )
    db.add(credential)
    db.flush()
    db.add(
        models.CredentialSecret(
            credential_id=credential.id,
            encrypted_secret_json=encrypt_secret_payload(
                {"access_token": "access-token", "expires_at": "not-a-date"}
            ),
            encryption_key_version="v1",
        )
    )
    db.commit()

    with pytest.raises(CredentialResolutionError, match="Google Workspace account token has invalid expiry"):
        resolve_oauth_token_payload(
            db,
            owner_user_id="test-user",
            provider="google_workspace",
            required_scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )


def test_resolve_oauth_token_payload_requires_current_owner(db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    credential = models.Credential(
        owner_type="user",
        owner_user_id="other-user",
        workspace_id=None,
        provider="google_workspace",
        auth_type="oauth2",
        label="Google Workspace",
        scopes_json=["https://www.googleapis.com/auth/spreadsheets"],
        status="active",
        secret_ref="secret://db/credential/google",
    )
    db.add(credential)
    db.flush()
    db.add(
        models.CredentialSecret(
            credential_id=credential.id,
            encrypted_secret_json=encrypt_secret_payload({"access_token": "access-token"}),
            encryption_key_version="v1",
        )
    )
    db.commit()

    with pytest.raises(CredentialResolutionError, match="Google Workspace account is not connected"):
        resolve_oauth_token_payload(
            db,
            owner_user_id="test-user",
            provider="google_workspace",
            required_scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )


@pytest.mark.parametrize("status", ["inactive", "revoked"])
def test_resolve_oauth_token_payload_rejects_non_active_accounts(db, monkeypatch, status):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="google_workspace",
        auth_type="oauth2",
        label="Google Workspace",
        scopes_json=["https://www.googleapis.com/auth/spreadsheets"],
        status=status,
        secret_ref="secret://db/credential/google",
    )
    db.add(credential)
    db.commit()

    with pytest.raises(CredentialResolutionError, match="Google Workspace account is not connected"):
        resolve_oauth_token_payload(
            db,
            owner_user_id="test-user",
            provider="google_workspace",
            required_scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )


def test_resolve_oauth_token_payload_rejects_missing_secret(db):
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="google_workspace",
        auth_type="oauth2",
        label="Google Workspace",
        scopes_json=["https://www.googleapis.com/auth/spreadsheets"],
        status="active",
        secret_ref="secret://db/credential/google",
    )
    db.add(credential)
    db.commit()

    with pytest.raises(CredentialResolutionError, match="Google Workspace account token is unavailable"):
        resolve_oauth_token_payload(
            db,
            owner_user_id="test-user",
            provider="google_workspace",
            required_scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )


def test_resolve_oauth_token_payload_rejects_api_key_credentials(db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="google_workspace",
        auth_type="api_key",
        label="Google Workspace",
        scopes_json=["https://www.googleapis.com/auth/spreadsheets"],
        status="active",
        secret_ref="secret://db/credential/google",
    )
    db.add(credential)
    db.flush()
    db.add(
        models.CredentialSecret(
            credential_id=credential.id,
            encrypted_secret_json=encrypt_secret_payload({"api_key": "not-oauth"}),
            encryption_key_version="v1",
        )
    )
    db.commit()

    with pytest.raises(CredentialResolutionError, match="Google Workspace account is not an OAuth credential"):
        resolve_oauth_token_payload(
            db,
            owner_user_id="test-user",
            provider="google_workspace",
            required_scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )


def test_resolve_oauth_token_payload_rejects_bad_token_cipher(db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="meta_instagram",
        auth_type="oauth2",
        label="Instagram",
        scopes_json=["instagram_basic"],
        status="active",
        secret_ref="secret://db/credential/instagram",
    )
    db.add(credential)
    db.flush()
    db.add(
        models.CredentialSecret(
            credential_id=credential.id,
            encrypted_secret_json={"cipher": "fernet", "token": "bad-token"},
            encryption_key_version="v1",
        )
    )
    db.commit()

    with pytest.raises(CredentialResolutionError, match="Instagram account token could not be decrypted"):
        resolve_oauth_token_payload(
            db,
            owner_user_id="test-user",
            provider="meta_instagram",
            required_scopes=["instagram_basic"],
        )


def test_resolve_oauth_token_payload_rejects_missing_scope(db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="google_workspace",
        auth_type="oauth2",
        label="Google Workspace",
        scopes_json=["scope-a"],
        status="active",
        secret_ref="secret://db/credential/google",
    )
    db.add(credential)
    db.flush()
    db.add(
        models.CredentialSecret(
            credential_id=credential.id,
            encrypted_secret_json=encrypt_secret_payload({"access_token": "access-token"}),
            encryption_key_version="v1",
        )
    )
    db.commit()

    with pytest.raises(CredentialResolutionError, match="missing required scope"):
        resolve_oauth_token_payload(
            db,
            owner_user_id="test-user",
            provider="google_workspace",
            required_scopes=["scope-b"],
        )


def test_resolve_oauth_token_payload_rejects_missing_access_token(db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="google_workspace",
        auth_type="oauth2",
        label="Google Workspace",
        scopes_json=["https://www.googleapis.com/auth/spreadsheets"],
        status="active",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        secret_ref="secret://db/credential/google",
    )
    db.add(credential)
    db.flush()
    db.add(
        models.CredentialSecret(
            credential_id=credential.id,
            encrypted_secret_json=encrypt_secret_payload({"refresh_token": "refresh-token"}),
            encryption_key_version="v1",
        )
    )
    db.commit()

    with pytest.raises(CredentialResolutionError, match="Google Workspace account access token is unavailable"):
        resolve_oauth_token_payload(
            db,
            owner_user_id="test-user",
            provider="google_workspace",
            required_scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )


def test_oauth_credentials_are_not_injected_into_runtime_env(db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    openai = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="openai",
        auth_type="api_key",
        label="OpenAI",
        scopes_json=[],
        status="active",
        secret_ref="secret://db/credential/openai",
    )
    google = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="google_workspace",
        auth_type="oauth2",
        label="Google Workspace",
        scopes_json=["https://www.googleapis.com/auth/spreadsheets"],
        status="active",
        secret_ref="secret://db/credential/google",
    )
    db.add_all([openai, google])
    db.flush()
    db.add_all(
        [
            models.CredentialSecret(
                credential_id=openai.id,
                encrypted_secret_json=encrypt_secret_payload({"api_key": "sk-openai"}),
                encryption_key_version="v1",
            ),
            models.CredentialSecret(
                credential_id=google.id,
                encrypted_secret_json=encrypt_secret_payload({"access_token": "google-access-token"}),
                encryption_key_version="v1",
            ),
        ]
    )
    db.commit()

    env = resolve_credential_env(db, owner_user_id="test-user", providers=["openai"])

    assert env == {"OPENAI_API_KEY": "sk-openai"}
    assert "AX_GOOGLE_WORKSPACE_OAUTH" not in env
    assert "google-access-token" not in str(env)


def test_oauth_provider_cannot_be_requested_from_env_resolver(db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))

    with pytest.raises(CredentialResolutionError, match="not supported"):
        resolve_credential_env(db, owner_user_id="test-user", providers=["google_workspace"])


def test_disconnect_revokes_connected_account_and_deletes_secret(client, db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    configure_meta_oauth_env(monkeypatch)
    mock_meta_graph(
        monkeypatch,
        page_payloads=[
            {
                "page_id": "page-1",
                "page_name": "Creator Page",
                "page_access_token": "page-access-token-1",
                "ig_user_id": "17841405822304914",
            }
        ],
    )
    start_response = client.post("/api/connected-accounts/oauth/start", json={"provider": "meta_instagram"})
    callback_response = client.get(
        "/api/connected-accounts/oauth/callback",
        params={"provider": "meta_instagram", "state": start_response.json()["state"], "code": "meta-code"},
    )
    credential_id = callback_response.json()["account"]["id"]

    response = client.delete("/api/connected-accounts/meta_instagram")

    assert response.status_code == 200
    assert response.json() == {"provider": "meta_instagram", "disconnected": True}
    credential = db.get(models.Credential, credential_id)
    assert credential.status == "revoked"
    assert db.query(models.CredentialSecret).filter_by(credential_id=credential_id).one_or_none() is None
    assert client.get("/api/connected-accounts").json() == []


def test_oauth_callback_rejects_bad_state(client, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))

    response = client.get(
        "/api/connected-accounts/oauth/callback",
        params={"provider": "google_workspace", "state": "not-a-real-state", "code": "google-code"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid or expired OAuth state."


def test_canonical_oauth_callback_rejects_unsupported_provider(client, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))

    response = client.get(
        "/api/connected-accounts/oauth/callback",
        params={"provider": "unknown", "state": "state", "code": "code"},
    )

    assert response.status_code == 422
    assert "Unsupported OAuth credential provider" in response.json()["detail"]


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("post", "/api/connected-accounts/oauth/start", {"provider": "unknown"}),
        ("post", "/api/connected-accounts/unknown/oauth/start", {}),
        ("post", "/api/connected-accounts/unknown/oauth/callback", {"state": "state", "code": "code"}),
        ("delete", "/api/connected-accounts/unknown", None),
    ],
)
def test_connected_accounts_reject_unsupported_provider(client, method, path, json_body):
    request = getattr(client, method)
    kwargs = {} if json_body is None else {"json": json_body}

    response = request(path, **kwargs)

    assert response.status_code == 422
    assert "Unsupported OAuth credential provider" in response.json()["detail"]
