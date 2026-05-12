from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import math
import os
from typing import Any
from urllib.parse import urlencode

import requests


META_DEFAULT_GRAPH_VERSION = "v24.0"
META_INSTAGRAM_OAUTH_SCOPES = [
    "instagram_basic",
    "instagram_content_publish",
    "pages_show_list",
]


class MetaInstagramOAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class MetaInstagramOAuthConfig:
    app_id: str
    app_secret: str
    redirect_uri: str
    graph_version: str = META_DEFAULT_GRAPH_VERSION

    @classmethod
    def from_env(cls) -> "MetaInstagramOAuthConfig":
        app_id = _env_value("META_INSTAGRAM_APP_ID")
        app_secret = _env_value("META_INSTAGRAM_APP_SECRET")
        redirect_uri = _env_value("META_INSTAGRAM_REDIRECT_URI")
        graph_version = _env_value("META_GRAPH_API_VERSION") or META_DEFAULT_GRAPH_VERSION
        if not app_id or not app_secret or not redirect_uri:
            raise RuntimeError("Meta Instagram OAuth is not configured.")
        return cls(
            app_id=app_id,
            app_secret=app_secret,
            redirect_uri=redirect_uri,
            graph_version=graph_version.lstrip("/"),
        )

    @property
    def graph_base_url(self) -> str:
        return f"https://graph.facebook.com/{self.graph_version}"

    @property
    def authorization_base_url(self) -> str:
        return f"https://www.facebook.com/{self.graph_version}/dialog/oauth"


@dataclass(frozen=True)
class MetaInstagramAccountCandidate:
    page_id: str
    page_name: str | None
    page_access_token: str | None
    ig_user_id: str

    @property
    def label(self) -> str:
        return self.page_name or self.ig_user_id


@dataclass(frozen=True)
class MetaInstagramResolvedToken:
    access_token: str
    token_type: str
    expires_at: datetime | None
    account: MetaInstagramAccountCandidate


class MetaInstagramOAuthClient:
    def __init__(self, config: MetaInstagramOAuthConfig | None = None) -> None:
        self._config = config if config is not None else MetaInstagramOAuthConfig.from_env()

    def build_authorization_url(self, *, state: str, scopes: list[str]) -> str:
        query = {
            "client_id": self._config.app_id,
            "redirect_uri": self._config.redirect_uri,
            "response_type": "code",
            "state": state,
            "scope": ",".join(scopes),
        }
        return f"{self._config.authorization_base_url}?{urlencode(query)}"

    def exchange_code(self, *, code: str) -> MetaInstagramResolvedToken:
        token_payload = self._get_oauth_access_token(code=code)
        access_token = _required_string(
            token_payload.get("access_token"),
            "Meta Instagram OAuth did not return an access token.",
        )
        token_type = _optional_string(token_payload.get("token_type")) or "Bearer"
        expires_at = _expires_at(token_payload.get("expires_in"))
        account = self.resolve_single_instagram_account(access_token=access_token)
        return MetaInstagramResolvedToken(
            access_token=access_token,
            token_type=token_type,
            expires_at=expires_at,
            account=account,
        )

    def resolve_single_instagram_account(self, *, access_token: str) -> MetaInstagramAccountCandidate:
        pages_payload = self._graph_get(
            "/me/accounts",
            access_token=access_token,
            params={"fields": "id,name,access_token,tasks"},
            step="Page lookup",
        )
        pages = pages_payload.get("data")
        if not isinstance(pages, list):
            raise MetaInstagramOAuthError("Meta Instagram Page lookup returned an unexpected response.")

        candidates: dict[str, MetaInstagramAccountCandidate] = {}
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_id = _optional_string(page.get("id"))
            if page_id is None:
                continue
            page_access_token = _optional_string(page.get("access_token"))
            page_name = _optional_string(page.get("name"))
            account_payload = self._graph_get(
                f"/{page_id}",
                access_token=page_access_token or access_token,
                params={"fields": "instagram_business_account"},
                step="Instagram account lookup",
            )
            ig_account = account_payload.get("instagram_business_account")
            if not isinstance(ig_account, dict):
                continue
            ig_user_id = _optional_string(ig_account.get("id"))
            if ig_user_id is None:
                continue
            candidates[ig_user_id] = MetaInstagramAccountCandidate(
                page_id=page_id,
                page_name=page_name,
                page_access_token=page_access_token,
                ig_user_id=ig_user_id,
            )

        if not candidates:
            raise MetaInstagramOAuthError("No Instagram professional account was found.")
        if len(candidates) > 1:
            raise MetaInstagramOAuthError(
                "Multiple Instagram accounts were found; account selection is not supported yet."
            )
        return next(iter(candidates.values()))

    def _get_oauth_access_token(self, *, code: str) -> dict[str, Any]:
        return _safe_get(
            f"{self._config.graph_base_url}/oauth/access_token",
            params={
                "client_id": self._config.app_id,
                "client_secret": self._config.app_secret,
                "redirect_uri": self._config.redirect_uri,
                "code": code,
            },
            headers=None,
            step="code exchange",
        )

    def _graph_get(
        self,
        path: str,
        *,
        access_token: str,
        params: dict[str, str],
        step: str,
    ) -> dict[str, Any]:
        return _safe_get(
            f"{self._config.graph_base_url}/{path.lstrip('/')}",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
            step=step,
        )


def _safe_get(
    url: str,
    *,
    params: dict[str, str],
    headers: dict[str, str] | None,
    step: str,
) -> dict[str, Any]:
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
    except requests.RequestException as exc:
        raise MetaInstagramOAuthError(f"Meta Instagram {step} request failed.") from exc
    if not response.ok:
        raise MetaInstagramOAuthError(f"Meta Instagram {step} request failed.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise MetaInstagramOAuthError(f"Meta Instagram {step} returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise MetaInstagramOAuthError(f"Meta Instagram {step} returned an unexpected response.")
    return payload


def _env_value(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _required_string(value: object, message: str) -> str:
    parsed = _optional_string(value)
    if parsed is None:
        raise MetaInstagramOAuthError(message)
    return parsed


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


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
