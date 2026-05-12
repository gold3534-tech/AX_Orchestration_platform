from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from typing import Any
from urllib.parse import urlparse, urlencode
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.db.models import Credential, CredentialSecret, OAuthState
from api.integrations.google_oauth import (
    GOOGLE_WORKSPACE_DEFAULT_SCOPES,
    GoogleWorkspaceOAuthClient,
)
from api.integrations.meta_oauth import (
    META_INSTAGRAM_OAUTH_SCOPES,
    MetaInstagramOAuthClient,
)
from api.db.models.asset import utcnow
from api.runtime.credential_providers import (
    CredentialProvider,
    SUPPORTED_CREDENTIAL_PROVIDERS,
)
from api.runtime.credential_store import encrypt_secret_payload
from api.schemas.runtime import (
    ConnectedAccountProviderResponse,
    ConnectedAccountResponse,
    OAuthStartBaseRequest,
)


class OAuthStateError(ValueError):
    pass


@dataclass(frozen=True)
class OAuthTokenResult:
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    scopes: list[str]
    external_account_id: str | None = None
    external_account_label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    secret_payload_extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CompletedOAuthCallback:
    credential: Credential
    redirect_path: str | None


@dataclass(frozen=True)
class ClaimedOAuthState:
    id: str
    owner_user_id: str
    requested_scopes: list[str]
    redirect_path: str | None


class OAuthProviderAdapter:
    authorize_base_url = "https://auth.local"

    def __init__(self, provider: str, default_scopes: list[str]) -> None:
        self.provider = provider
        self.default_scopes = default_scopes

    def build_authorization_url(self, *, state: str, nonce: str, scopes: list[str], redirect_path: str | None) -> str:
        query = {
            "response_type": "code",
            "state": state,
            "nonce": nonce,
            "scope": " ".join(scopes),
        }
        if redirect_path:
            query["redirect_path"] = redirect_path
        return f"{self.authorize_base_url}/{self.provider}?{urlencode(query)}"

    def validate_ready(self) -> None:
        return None

    def exchange_code(self, *, code: str, scopes: list[str]) -> OAuthTokenResult:
        account_label = code
        return OAuthTokenResult(
            access_token=f"access-token-{self.provider}-{code}",
            refresh_token=f"refresh-token-{self.provider}-{code}",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            scopes=scopes,
            external_account_id=f"{self.provider}:{code}",
            external_account_label=account_label,
            metadata={"display_name": account_label},
        )


class GoogleWorkspaceOAuthAdapter(OAuthProviderAdapter):
    def __init__(self) -> None:
        super().__init__("google_workspace", GOOGLE_WORKSPACE_DEFAULT_SCOPES)

    def validate_ready(self) -> None:
        GoogleWorkspaceOAuthClient()

    def build_authorization_url(self, *, state: str, nonce: str, scopes: list[str], redirect_path: str | None) -> str:
        return GoogleWorkspaceOAuthClient().build_authorization_url(state=state, scopes=scopes)

    def exchange_code(self, *, code: str, scopes: list[str]) -> OAuthTokenResult:
        resolved = GoogleWorkspaceOAuthClient().exchange_code(code=code, scopes=scopes)
        return OAuthTokenResult(
            access_token=resolved.access_token,
            refresh_token=resolved.refresh_token,
            expires_at=resolved.expires_at,
            scopes=resolved.scopes,
            external_account_id="google_workspace",
            external_account_label="Google Workspace",
            metadata={"display_name": "Google Workspace"},
        )


class MetaInstagramOAuthAdapter(OAuthProviderAdapter):
    def __init__(self) -> None:
        super().__init__("meta_instagram", META_INSTAGRAM_OAUTH_SCOPES)

    def validate_ready(self) -> None:
        MetaInstagramOAuthClient()

    def build_authorization_url(self, *, state: str, nonce: str, scopes: list[str], redirect_path: str | None) -> str:
        return MetaInstagramOAuthClient().build_authorization_url(state=state, scopes=scopes)

    def exchange_code(self, *, code: str, scopes: list[str]) -> OAuthTokenResult:
        resolved = MetaInstagramOAuthClient().exchange_code(code=code)
        account = resolved.account
        return OAuthTokenResult(
            access_token=resolved.access_token,
            refresh_token=None,
            expires_at=resolved.expires_at,
            scopes=scopes,
            external_account_id=account.ig_user_id,
            external_account_label=account.label,
            metadata={
                "page_id": account.page_id,
                "page_name": account.page_name,
                "ig_user_id": account.ig_user_id,
            },
            secret_payload_extra={
                "provider_specific": {
                    "page_access_token": account.page_access_token,
                    "page_id": account.page_id,
                    "ig_user_id": account.ig_user_id,
                }
            },
        )


_OAUTH_ADAPTERS: dict[str, OAuthProviderAdapter] = {
    "google_workspace": GoogleWorkspaceOAuthAdapter(),
    "meta_instagram": MetaInstagramOAuthAdapter(),
}


def _hash_state(state: str) -> str:
    return sha256(state.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _required_callback_value(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("field must not be empty")
    return value


def _oauth_provider(provider: str) -> CredentialProvider:
    metadata = SUPPORTED_CREDENTIAL_PROVIDERS.get(provider)
    if metadata is None or metadata.auth_type != "oauth2":
        raise ValueError(f"Unsupported OAuth credential provider: {provider}")
    return metadata


def _adapter_for(provider: str) -> OAuthProviderAdapter:
    _oauth_provider(provider)
    try:
        return _OAUTH_ADAPTERS[provider]
    except KeyError as exc:  # pragma: no cover - protected by provider registry in current catalog
        raise ValueError(f"Unsupported OAuth credential provider: {provider}") from exc


def _capabilities_for_provider(provider: str) -> list[str]:
    metadata = SUPPORTED_CREDENTIAL_PROVIDERS.get(provider)
    if metadata is None:
        return []
    return list(metadata.capabilities)


def _default_scopes_for_provider(provider: str) -> list[str]:
    adapter = _OAUTH_ADAPTERS.get(provider)
    if adapter is None:
        return []
    return list(adapter.default_scopes)


def _missing_scopes(provider: str, granted_scopes: list[str]) -> list[str]:
    granted_scope_set = set(granted_scopes)
    return [scope for scope in _default_scopes_for_provider(provider) if scope not in granted_scope_set]


def _requested_scopes(provider: str, scopes: list[str] | None) -> list[str]:
    allowed_scopes = _default_scopes_for_provider(provider)
    if not scopes:
        return allowed_scopes
    unsupported_scopes = [scope for scope in scopes if scope not in allowed_scopes]
    if unsupported_scopes:
        raise ValueError(f"Unsupported OAuth scope for {provider}: {unsupported_scopes[0]}")
    return list(scopes)


def _validated_redirect_path(redirect_path: str | None) -> str | None:
    if redirect_path is None:
        return None
    parsed = urlparse(redirect_path)
    if parsed.scheme or parsed.netloc or not redirect_path.startswith("/") or redirect_path.startswith("//"):
        raise ValueError("redirect_path must be an internal relative path.")
    return redirect_path


def _last_checked_at(credential: Credential) -> datetime | None:
    metadata_json = credential.metadata_json or {}
    last_checked_at = metadata_json.get("last_checked_at")
    if isinstance(last_checked_at, datetime):
        return last_checked_at
    return None


def _mark_oauth_state_status(db: Session, *, state_id: str, status: str) -> None:
    db.query(OAuthState).filter(OAuthState.id == state_id).update(
        {"status": status},
        synchronize_session=False,
    )
    db.commit()


def _claim_pending_oauth_state(
    db: Session,
    *,
    owner_user_id: str | None,
    provider: str,
    state: str,
) -> ClaimedOAuthState:
    filters = [
        OAuthState.provider == provider,
        OAuthState.state_token == _hash_state(state),
        OAuthState.status == "pending",
    ]
    if owner_user_id is not None:
        filters.append(OAuthState.owner_user_id == owner_user_id)
    oauth_state = (
        db.query(OAuthState)
        .filter(*filters)
        .one_or_none()
    )
    if oauth_state is None or _as_utc(oauth_state.expires_at) < datetime.now(UTC):
        raise OAuthStateError("Invalid or expired OAuth state.")

    claimed = ClaimedOAuthState(
        id=oauth_state.id,
        owner_user_id=oauth_state.owner_user_id,
        requested_scopes=list(oauth_state.requested_scopes_json or []),
        redirect_path=oauth_state.redirect_path,
    )
    updated_count = (
        db.query(OAuthState)
        .filter(
            OAuthState.id == oauth_state.id,
            OAuthState.status == "pending",
        )
        .update({"status": "processing"}, synchronize_session=False)
    )
    if updated_count != 1:
        db.rollback()
        raise OAuthStateError("Invalid or expired OAuth state.")
    db.commit()
    return claimed


def list_oauth_providers() -> list[ConnectedAccountProviderResponse]:
    return [
        ConnectedAccountProviderResponse(
            provider=metadata.provider,
            display_name=metadata.label,
            label=metadata.label,
            env_var=metadata.env_var,
            auth_type=metadata.auth_type,
            connect_label=f"Connect {metadata.label}",
            reconnect_label=f"Reconnect {metadata.label}",
            supports_disconnect=True,
            supports_test_connection=True,
            capabilities=list(metadata.capabilities),
            capability_keys=list(metadata.capabilities),
            default_scopes=_default_scopes_for_provider(metadata.provider),
        )
        for metadata in SUPPORTED_CREDENTIAL_PROVIDERS.values()
        if metadata.auth_type == "oauth2"
    ]


def connected_account_response(credential: Credential) -> ConnectedAccountResponse:
    scopes = credential.scopes_json if isinstance(credential.scopes_json, list) else []
    return ConnectedAccountResponse(
        id=credential.id,
        provider=credential.provider,
        label=credential.label,
        auth_type=credential.auth_type,
        provider_account_id=credential.provider_account_id,
        provider_account_label=credential.provider_account_label,
        status=credential.status,
        scopes=list(scopes),
        missing_scopes=_missing_scopes(credential.provider, scopes),
        expires_at=credential.expires_at,
        last_checked_at=_last_checked_at(credential),
        capability_keys=_capabilities_for_provider(credential.provider),
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )


def list_connected_accounts(db: Session, *, owner_user_id: str) -> list[ConnectedAccountResponse]:
    credentials = (
        db.query(Credential)
        .filter(
            Credential.owner_type == "user",
            Credential.owner_user_id == owner_user_id,
            Credential.workspace_id.is_(None),
            Credential.auth_type == "oauth2",
            Credential.status == "active",
        )
        .order_by(Credential.created_at.asc())
        .all()
    )
    return [connected_account_response(credential) for credential in credentials]


@dataclass(frozen=True)
class OAuthStartResult:
    provider: str
    authorization_url: str
    state: str
    expires_at: datetime


def start_oauth(
    db: Session,
    *,
    provider: str,
    payload: OAuthStartBaseRequest,
    owner_user_id: str,
) -> OAuthStartResult:
    adapter = _adapter_for(provider)
    state = token_urlsafe(32)
    nonce = token_urlsafe(24)
    expires_at = datetime.now(UTC) + timedelta(minutes=10)
    scopes = _requested_scopes(provider, payload.scopes)
    redirect_path = _validated_redirect_path(payload.redirect_path)
    adapter.validate_ready()
    oauth_state = OAuthState(
        id=str(uuid.uuid4()),
        owner_user_id=owner_user_id,
        provider=provider,
        state_token=_hash_state(state),
        requested_scopes_json=scopes,
        redirect_path=redirect_path,
        status="pending",
        expires_at=expires_at,
    )
    db.add(oauth_state)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise RuntimeError("OAuth state could not be created.")

    return OAuthStartResult(
        provider=provider,
        authorization_url=adapter.build_authorization_url(
            state=state,
            nonce=nonce,
            scopes=scopes,
            redirect_path=redirect_path,
        ),
        state=state,
        expires_at=expires_at,
    )


def complete_oauth_callback(
    db: Session,
    *,
    provider: str,
    state: str,
    code: str,
    owner_user_id: str | None = None,
) -> CompletedOAuthCallback:
    provider = _required_callback_value(provider)
    state = _required_callback_value(state)
    code = _required_callback_value(code)
    definition = _oauth_provider(provider)
    claimed_state = _claim_pending_oauth_state(
        db,
        owner_user_id=owner_user_id,
        provider=provider,
        state=state,
    )
    try:
        token_result = _adapter_for(provider).exchange_code(
            code=code,
            scopes=claimed_state.requested_scopes,
        )
        secret_json = {
            "access_token": token_result.access_token,
            "refresh_token": token_result.refresh_token,
            "expires_at": token_result.expires_at.isoformat() if token_result.expires_at is not None else None,
            "token_type": "Bearer",
        }
        secret_json.update(token_result.secret_payload_extra)
        encrypted_secret_json = encrypt_secret_payload(
            {key: value for key, value in secret_json.items() if value is not None}
        )

        credential = (
            db.query(Credential)
            .filter(
                Credential.owner_type == "user",
                Credential.owner_user_id == claimed_state.owner_user_id,
                Credential.workspace_id.is_(None),
                Credential.provider == provider,
                Credential.auth_type == "oauth2",
                Credential.status == "active",
            )
            .one_or_none()
        )
        if credential is None:
            credential = Credential(
                id=str(uuid.uuid4()),
                owner_type="user",
                owner_user_id=claimed_state.owner_user_id,
                workspace_id=None,
                provider=provider,
                auth_type=definition.auth_type,
                label=definition.label,
                secret_ref="",
                scopes_json=token_result.scopes,
                status="active",
                metadata_json=token_result.metadata,
                expires_at=token_result.expires_at,
            )
            credential.secret_ref = f"secret://db/credential/{credential.id}"
            db.add(credential)
        else:
            credential.auth_type = definition.auth_type
            credential.label = definition.label
            credential.scopes_json = token_result.scopes
            credential.metadata_json = token_result.metadata
            credential.expires_at = token_result.expires_at
            credential.secret_ref = f"secret://db/credential/{credential.id}"
            credential.updated_at = utcnow()

        credential.provider_account_id = token_result.external_account_id
        credential.provider_account_label = token_result.external_account_label
        db.flush()

        existing_secret = (
            db.query(CredentialSecret)
            .filter(CredentialSecret.credential_id == credential.id)
            .one_or_none()
        )
        if existing_secret is None:
            db.add(
                CredentialSecret(
                    credential_id=credential.id,
                    encrypted_secret_json=encrypted_secret_json,
                    encryption_key_version="v1",
                )
            )
        else:
            existing_secret.encrypted_secret_json = encrypted_secret_json
            existing_secret.encryption_key_version = "v1"
            existing_secret.updated_at = utcnow()

        db.query(OAuthState).filter(
            OAuthState.id == claimed_state.id,
            OAuthState.status == "processing",
        ).update({"status": "used"}, synchronize_session=False)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _mark_oauth_state_status(db, state_id=claimed_state.id, status="failed")
        raise RuntimeError("OAuth credential could not be stored.") from exc
    except Exception:
        db.rollback()
        # A provider code may have been touched after the state was claimed, so
        # failed exchanges intentionally consume the state instead of reopening replay.
        _mark_oauth_state_status(db, state_id=claimed_state.id, status="failed")
        raise
    db.refresh(credential)
    return CompletedOAuthCallback(credential=credential, redirect_path=claimed_state.redirect_path)


def disconnect_connected_account(db: Session, *, provider: str, owner_user_id: str) -> None:
    _oauth_provider(provider)
    credential = (
        db.query(Credential)
        .filter(
            Credential.owner_type == "user",
            Credential.owner_user_id == owner_user_id,
            Credential.workspace_id.is_(None),
            Credential.provider == provider,
            Credential.auth_type == "oauth2",
            Credential.status == "active",
        )
        .one_or_none()
    )
    if credential is None:
        raise LookupError(f"Connected account not found for provider: {provider}")
    db.query(CredentialSecret).filter(CredentialSecret.credential_id == credential.id).delete()
    credential.status = "revoked"
    credential.updated_at = utcnow()
    db.commit()
