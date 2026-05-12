from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.attributes import set_committed_value

from api.db.models import Credential, CredentialSecret
from api.runtime.credential_providers import provider_label, require_supported_provider
from api.runtime.credential_resolver import CredentialResolutionError
from api.runtime.credential_store import (
    CredentialEncryptionError,
    CredentialEncryptionNotConfiguredError,
    decrypt_secret_payload,
    encrypt_secret_payload,
)


@dataclass(frozen=True)
class RuntimeOAuthToken:
    credential_id: str
    provider: str
    access_token: str
    expires_at: datetime | None
    scopes: list[str]
    provider_account_id: str | None
    provider_account_label: str | None


@dataclass(frozen=True)
class RefreshedOAuthToken:
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    scopes: list[str]
    token_type: str = "Bearer"


def _require_oauth_provider(provider: str) -> None:
    try:
        definition = require_supported_provider(provider)
    except ValueError as exc:
        raise CredentialResolutionError("OAuth credential provider is not supported.") from exc
    if definition.auth_type != "oauth2":
        raise CredentialResolutionError(f"{provider_label(provider)} does not support OAuth runtime tokens.")


def validate_required_scopes(
    *,
    provider: str,
    granted_scopes: list[str],
    required_scopes: list[str],
) -> None:
    granted_scope_set = set(granted_scopes)
    missing_scopes = [scope for scope in required_scopes if scope not in granted_scope_set]
    if missing_scopes:
        raise CredentialResolutionError(
            f"{provider_label(provider)} account is missing required scope: {', '.join(missing_scopes)}"
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_secret_expiry(provider: str, expires_at: object) -> datetime | None:
    if expires_at is None:
        return None
    if not isinstance(expires_at, str) or not expires_at.strip():
        raise CredentialResolutionError(f"{provider_label(provider)} account token has invalid expiry.")
    try:
        parsed = datetime.fromisoformat(expires_at)
    except ValueError:
        raise CredentialResolutionError(f"{provider_label(provider)} account token has invalid expiry.")
    return _as_utc(parsed)


def _checked_expiry(provider: str, expires_at: datetime | None, *, now: datetime) -> datetime | None:
    if expires_at is None:
        return None
    if expires_at <= now:
        raise CredentialResolutionError(f"{provider_label(provider)} account token is expired.")
    return expires_at


def _active_oauth_credential(
    db: Session,
    *,
    owner_user_id: str,
    provider: str,
) -> Credential:
    credential = (
        db.query(Credential)
        .filter(
            Credential.owner_type == "user",
            Credential.owner_user_id == owner_user_id,
            Credential.workspace_id.is_(None),
            Credential.provider == provider,
            Credential.status == "active",
        )
        .one_or_none()
    )
    if credential is None:
        raise CredentialResolutionError(f"{provider_label(provider)} account is not connected.")
    if credential.auth_type != "oauth2":
        raise CredentialResolutionError(f"{provider_label(provider)} account is not an OAuth credential.")
    return credential


def _persist_refreshed_oauth_token(
    db: Session,
    *,
    provider: str,
    credential_id: str,
    encrypted_secret_json: dict[str, str],
    scopes: list[str],
    expires_at: datetime | None,
) -> None:
    SessionLocal = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    persistence_db = SessionLocal()
    try:
        credential = persistence_db.get(Credential, credential_id)
        secret = persistence_db.get(CredentialSecret, credential_id)
        if credential is None or secret is None:
            raise CredentialResolutionError(
                f"{provider_label(provider)} account token persistence failed."
            )
        credential.scopes_json = list(scopes)
        credential.expires_at = expires_at
        secret.encrypted_secret_json = encrypted_secret_json
        persistence_db.commit()
    except CredentialResolutionError:
        persistence_db.rollback()
        raise
    except SQLAlchemyError as exc:
        persistence_db.rollback()
        raise CredentialResolutionError(
            f"{provider_label(provider)} account token persistence failed."
        ) from exc
    finally:
        persistence_db.close()


def resolve_oauth_token_payload(
    db: Session,
    *,
    owner_user_id: str,
    provider: str,
    required_scopes: list[str],
    refresh_handler: Callable[[str, list[str]], RefreshedOAuthToken] | None = None,
) -> RuntimeOAuthToken:
    _require_oauth_provider(provider)
    credential = _active_oauth_credential(
        db,
        owner_user_id=owner_user_id,
        provider=provider,
    )
    granted_scopes = credential.scopes_json if isinstance(credential.scopes_json, list) else []
    validate_required_scopes(
        provider=provider,
        granted_scopes=granted_scopes,
        required_scopes=required_scopes,
    )

    secret = (
        db.query(CredentialSecret)
        .filter(CredentialSecret.credential_id == credential.id)
        .one_or_none()
    )
    if secret is None:
        raise CredentialResolutionError(f"{provider_label(provider)} account token is unavailable.")

    try:
        token_payload = decrypt_secret_payload(secret.encrypted_secret_json)
    except CredentialEncryptionNotConfiguredError as exc:
        raise CredentialResolutionError("Credential encryption is not configured.") from exc
    except CredentialEncryptionError as exc:
        raise CredentialResolutionError(
            f"{provider_label(provider)} account token could not be decrypted."
        ) from exc

    access_token = token_payload.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise CredentialResolutionError(f"{provider_label(provider)} account access token is unavailable.")

    now = datetime.now(UTC)
    secret_expires_at = _parse_secret_expiry(provider, token_payload.get("expires_at"))
    credential_expires_at = (
        _as_utc(credential.expires_at) if credential.expires_at is not None else None
    )
    available_expiries = [
        expires_at
        for expires_at in (secret_expires_at, credential_expires_at)
        if expires_at is not None
    ]
    expires_at = min(available_expiries) if available_expiries else None
    if expires_at is not None and expires_at <= now:
        if refresh_handler is None:
            raise CredentialResolutionError(f"{provider_label(provider)} account token is expired.")
        refresh_token = token_payload.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token.strip():
            raise CredentialResolutionError(
                f"{provider_label(provider)} account refresh token is unavailable."
            )
        try:
            refreshed = refresh_handler(refresh_token.strip(), list(granted_scopes))
        except CredentialResolutionError:
            raise
        except Exception as exc:
            raise CredentialResolutionError(
                f"{provider_label(provider)} account token refresh failed."
            ) from exc
        if not isinstance(refreshed.access_token, str) or not refreshed.access_token.strip():
            raise CredentialResolutionError(
                f"{provider_label(provider)} account access token is unavailable."
            )
        validate_required_scopes(
            provider=provider,
            granted_scopes=refreshed.scopes,
            required_scopes=required_scopes,
        )
        refreshed_payload = {
            "access_token": refreshed.access_token.strip(),
            "refresh_token": refreshed.refresh_token or refresh_token.strip(),
            "expires_at": (
                refreshed.expires_at.isoformat() if refreshed.expires_at is not None else None
            ),
            "token_type": refreshed.token_type or "Bearer",
        }
        try:
            encrypted_secret_json = encrypt_secret_payload(
                {key: value for key, value in refreshed_payload.items() if value is not None}
            )
        except CredentialEncryptionNotConfiguredError as exc:
            raise CredentialResolutionError("Credential encryption is not configured.") from exc
        except CredentialEncryptionError as exc:
            raise CredentialResolutionError(
                f"{provider_label(provider)} account token could not be encrypted."
            ) from exc
        _persist_refreshed_oauth_token(
            db,
            provider=provider,
            credential_id=credential.id,
            encrypted_secret_json=encrypted_secret_json,
            scopes=refreshed.scopes,
            expires_at=refreshed.expires_at,
        )
        db.refresh(credential)
        db.refresh(secret)
        set_committed_value(credential, "scopes_json", list(refreshed.scopes))
        set_committed_value(credential, "expires_at", refreshed.expires_at)
        set_committed_value(secret, "encrypted_secret_json", encrypted_secret_json)
        access_token = refreshed.access_token.strip()
        granted_scopes = list(refreshed.scopes)
        expires_at = refreshed.expires_at

    return RuntimeOAuthToken(
        credential_id=credential.id,
        provider=provider,
        access_token=access_token,
        expires_at=expires_at,
        scopes=list(granted_scopes),
        provider_account_id=credential.provider_account_id,
        provider_account_label=credential.provider_account_label,
    )
