from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import math
import os
from typing import Any
from urllib.parse import urlencode

import requests


GOOGLE_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_WORKSPACE_DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


class GoogleWorkspaceOAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class GoogleWorkspaceOAuthConfig:
    client_id: str
    client_secret: str
    redirect_uri: str

    @classmethod
    def from_env(cls) -> "GoogleWorkspaceOAuthConfig":
        client_id = _env_value("GOOGLE_WORKSPACE_CLIENT_ID")
        client_secret = _env_value("GOOGLE_WORKSPACE_CLIENT_SECRET")
        redirect_uri = _env_value("GOOGLE_WORKSPACE_REDIRECT_URI")
        if not client_id or not client_secret or not redirect_uri:
            raise RuntimeError("Google Workspace OAuth is not configured.")
        return cls(client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri)


@dataclass(frozen=True)
class GoogleOAuthTokenPayload:
    access_token: str
    refresh_token: str
    expires_at: datetime | None
    scopes: list[str]
    token_type: str = "Bearer"


class GoogleWorkspaceOAuthClient:
    def __init__(self, config: GoogleWorkspaceOAuthConfig | None = None) -> None:
        self._config = config if config is not None else GoogleWorkspaceOAuthConfig.from_env()

    def build_authorization_url(self, *, state: str, scopes: list[str]) -> str:
        query = {
            "client_id": self._config.client_id,
            "redirect_uri": self._config.redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        }
        return f"{GOOGLE_AUTHORIZATION_URL}?{urlencode(query)}"

    def exchange_code(self, *, code: str, scopes: list[str]) -> GoogleOAuthTokenPayload:
        payload = _safe_post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
                "redirect_uri": self._config.redirect_uri,
                "grant_type": "authorization_code",
                "code": code,
            },
            step="code exchange",
        )
        return _token_payload(
            payload,
            fallback_scopes=scopes,
            missing_access_token_message="Google Workspace OAuth did not return an access token.",
            missing_refresh_token_message="Google Workspace OAuth did not return a refresh token.",
        )

    def refresh_access_token(
        self,
        *,
        refresh_token: str,
        scopes: list[str],
    ) -> GoogleOAuthTokenPayload:
        payload = _safe_post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            step="token refresh",
        )
        return _token_payload(
            payload,
            fallback_scopes=scopes,
            fallback_refresh_token=refresh_token,
            missing_access_token_message="Google Workspace OAuth refresh did not return an access token.",
            missing_refresh_token_message="Google Workspace OAuth refresh did not include a refresh token.",
        )


def _safe_post(url: str, *, data: dict[str, str], step: str) -> dict[str, Any]:
    try:
        response = requests.post(url, data=data, timeout=30)
    except requests.RequestException as exc:
        raise GoogleWorkspaceOAuthError(f"Google Workspace OAuth {step} request failed.") from exc
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise GoogleWorkspaceOAuthError(f"Google Workspace OAuth {step} request failed.") from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise GoogleWorkspaceOAuthError(f"Google Workspace OAuth {step} returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise GoogleWorkspaceOAuthError(f"Google Workspace OAuth {step} returned an unexpected response.")
    return payload


def _token_payload(
    payload: dict[str, Any],
    *,
    fallback_scopes: list[str],
    missing_access_token_message: str,
    missing_refresh_token_message: str,
    fallback_refresh_token: str | None = None,
) -> GoogleOAuthTokenPayload:
    access_token = _required_string(payload.get("access_token"), missing_access_token_message)
    refresh_token = _optional_string(payload.get("refresh_token")) or fallback_refresh_token
    if refresh_token is None:
        raise GoogleWorkspaceOAuthError(missing_refresh_token_message)
    return GoogleOAuthTokenPayload(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=_expires_at(payload.get("expires_in")),
        scopes=_scopes(payload.get("scope"), fallback_scopes=fallback_scopes),
        token_type=_optional_string(payload.get("token_type")) or "Bearer",
    )


def _env_value(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _required_string(value: object, message: str) -> str:
    parsed = _optional_string(value)
    if parsed is None:
        raise GoogleWorkspaceOAuthError(message)
    return parsed


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _scopes(value: object, *, fallback_scopes: list[str]) -> list[str]:
    scope_value = _optional_string(value)
    if scope_value is None:
        return list(fallback_scopes)
    return [scope for scope in scope_value.split() if scope]


def _expires_at(expires_in: object) -> datetime | None:
    if isinstance(expires_in, bool):
        return None
    if not isinstance(expires_in, int | float) or expires_in <= 0:
        return None
    if isinstance(expires_in, float) and not math.isfinite(expires_in):
        return None
    try:
        return datetime.now(UTC) + timedelta(seconds=int(expires_in))
    except (OverflowError, ValueError):
        return None
