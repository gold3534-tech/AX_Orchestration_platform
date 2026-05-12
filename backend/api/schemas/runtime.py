from datetime import datetime
from typing import Any, Annotated, Literal, TypedDict
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, Field, field_validator


def _coerce_runtime_id(value: Any) -> str:
    if isinstance(value, UUID):
        return str(value)
    return value


CanonicalRuntimeId = Annotated[str, BeforeValidator(_coerce_runtime_id)]


class AuthenticatedUser(TypedDict):
    id: str
    email: str | None


class CredentialCreate(BaseModel):
    label: str
    provider: str
    secret_json: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    model_config = {"extra": "forbid"}

    @field_validator("label", "provider")
    @classmethod
    def field_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field must not be empty")
        return value


class CredentialProviderUpsert(BaseModel):
    api_key: str
    label: str | None = None

    model_config = {"extra": "forbid"}

    @field_validator("api_key")
    @classmethod
    def api_key_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("api_key must not be empty")
        return value

    @field_validator("label")
    @classmethod
    def label_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class CredentialResponse(BaseModel):
    id: CanonicalRuntimeId
    label: str
    provider: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ConnectedAccountProviderResponse(BaseModel):
    provider: str
    display_name: str
    label: str
    env_var: str
    auth_type: str
    connect_label: str
    reconnect_label: str
    supports_disconnect: bool = True
    supports_test_connection: bool = True
    capabilities: list[str]
    capability_keys: list[str] = Field(default_factory=list)
    default_scopes: list[str] = Field(default_factory=list)


class ConnectedAccountResponse(BaseModel):
    id: CanonicalRuntimeId
    provider: str
    label: str
    auth_type: str
    provider_account_id: str | None = None
    provider_account_label: str | None = None
    status: str
    scopes: list[str] = Field(default_factory=list)
    missing_scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    last_checked_at: datetime | None = None
    capability_keys: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class OAuthStartBaseRequest(BaseModel):
    scopes: list[str] | None = None
    redirect_path: str | None = None

    model_config = {"extra": "forbid"}

    @field_validator("scopes")
    @classmethod
    def scopes_must_not_be_blank(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        scopes = [scope.strip() for scope in value if scope.strip()]
        return scopes or None

    @field_validator("redirect_path")
    @classmethod
    def redirect_path_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class OAuthStartRequest(OAuthStartBaseRequest):
    provider: str

    @field_validator("provider")
    @classmethod
    def provider_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("provider must not be empty")
        return value


class OAuthStartPathRequest(OAuthStartBaseRequest):
    pass


class OAuthStartResponse(BaseModel):
    provider: str
    authorization_url: str
    state: str
    expires_at: datetime


class OAuthCallbackRequest(BaseModel):
    state: str
    code: str

    model_config = {"extra": "forbid"}

    @field_validator("state", "code")
    @classmethod
    def field_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field must not be empty")
        return value


class OAuthCallbackResponse(BaseModel):
    account: ConnectedAccountResponse
    redirect_path: str | None = None


class ConnectedAccountDisconnectResponse(BaseModel):
    provider: str
    disconnected: bool


class ExecutionBindingCreate(BaseModel):
    binding_type: str
    binding_key: str
    credential_id: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}

    @field_validator("binding_type", "binding_key", "credential_id")
    @classmethod
    def field_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field must not be empty")
        return value


class ExecutionBindingResponse(BaseModel):
    id: CanonicalRuntimeId
    subject_version_id: CanonicalRuntimeId
    binding_type: str
    binding_key: str
    credential_id: CanonicalRuntimeId
    metadata_json: dict[str, Any] | None = Field(
        default=None,
        description="API-only compatibility metadata synthesized by binding create responses.",
    )
    created_at: datetime


class StagingArtifactResponse(BaseModel):
    id: CanonicalRuntimeId
    run_id: CanonicalRuntimeId
    node_id: str | None = None
    artifact_type: Literal["image", "file"]
    mime_type: str
    media_type: str
    sha256: str | None = None
    size_bytes: int = 0
    storage_backend: Literal["ax_managed", "temporary", "google_drive"]
    source_tool: str | None = None
    source_capability: str | None = None
    retention_mode: Literal["temporary", "ax_managed"] = "temporary"
    expires_at: datetime | None = None
    retention_expires_at: datetime | None = None
    preview_url: str | None = None
    download_url: str | None = None
    status: Literal["available", "expired", "failed"]
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    self_delete_supported: bool = False
    created_at: datetime
    updated_at: datetime
