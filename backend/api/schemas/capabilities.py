from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from api.runtime.credential_providers import provider_env_var, require_supported_provider


class CredentialRequirement(BaseModel):
    provider: str
    env_var: str
    required: bool = True
    injection: str = "env"

    model_config = {"extra": "forbid"}

    @field_validator("provider", "env_var", "injection")
    @classmethod
    def text_fields_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field must not be empty")
        return value

    @field_validator("provider")
    @classmethod
    def provider_must_be_supported(cls, value: str) -> str:
        require_supported_provider(value)
        return value

    @model_validator(mode="after")
    def metadata_must_match_provider(self):
        provider = require_supported_provider(self.provider)
        expected_env_var = provider_env_var(self.provider)
        if self.env_var != expected_env_var:
            raise ValueError(f"env_var must be {expected_env_var} for provider {self.provider}")
        if provider.auth_type == "oauth2":
            if self.injection != "runtime_context":
                raise ValueError("injection must be runtime_context for OAuth providers")
        elif self.injection != "env":
            raise ValueError("injection must be env")
        return self


class ToolCatalogCreate(BaseModel):
    tool_key: str
    name: str
    description: str
    tool_type: str
    module_path: str
    class_name: str
    default_config_json: dict = Field(default_factory=dict)
    config_schema_json: dict = Field(default_factory=dict)
    input_schema_json: dict = Field(default_factory=dict)
    ui_schema_json: dict = Field(default_factory=dict)
    required_env_vars: list[dict] = Field(default_factory=list)
    credential_requirements: list[CredentialRequirement] = Field(default_factory=list)
    model_config = {"extra": "forbid"}

    @field_validator("tool_key", "name", "description", "tool_type", "module_path", "class_name")
    @classmethod
    def field_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field must not be empty")
        return value


class ToolCatalogResponse(BaseModel):
    id: str
    tool_key: str
    name: str
    description: str
    tool_type: str
    module_path: str
    class_name: str
    default_config_json: dict
    config_schema_json: dict = Field(default_factory=dict)
    input_schema_json: dict = Field(default_factory=dict)
    ui_schema_json: dict = Field(default_factory=dict)
    required_env_vars: list[dict] = Field(default_factory=list)
    credential_requirements: list[CredentialRequirement] = Field(default_factory=list)
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SkillCatalogResponse(BaseModel):
    id: str
    skill_key: str
    name: str
    description: str
    skill_source: str
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SkillCatalogCreate(BaseModel):
    skill_key: str
    name: str
    description: str
    skill_source: str
    model_config = {"extra": "forbid"}

    @field_validator("skill_key", "name", "description", "skill_source")
    @classmethod
    def field_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field must not be empty")
        return value


class VersionToolAttachCreate(BaseModel):
    tool_key: str
    tool_config_json: dict = Field(default_factory=dict)
    model_config = {"extra": "forbid"}

    @field_validator("tool_key")
    @classmethod
    def tool_key_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("tool_key must not be empty")
        return value


class VersionToolAttachmentUpdate(BaseModel):
    tool_config_json: dict | None = None
    sort_order: int | None = None
    model_config = {"extra": "forbid"}

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_nulls(cls, values):
        if isinstance(values, dict):
            if "tool_config_json" in values and values["tool_config_json"] is None:
                raise ValueError("tool_config_json must not be null")
            if "sort_order" in values and values["sort_order"] is None:
                raise ValueError("sort_order must not be null")
        return values


class VersionToolAttachmentResponse(BaseModel):
    id: str
    version_id: str
    tool_key: str
    tool_config_json: dict
    sort_order: int
    created_at: datetime

    @field_validator("id", "version_id", mode="before")
    @classmethod
    def stringify_uuid_values(cls, value):
        return str(value)


class VersionToolAttachmentReadResponse(BaseModel):
    id: str
    version_id: str
    tool_key: str
    tool_config_json: dict
    sort_order: int
    created_at: datetime

    @field_validator("id", "version_id", mode="before")
    @classmethod
    def stringify_uuid_values(cls, value):
        return str(value)


class VersionSkillAttachCreate(BaseModel):
    skill_key: str
    model_config = {"extra": "forbid"}

    @field_validator("skill_key")
    @classmethod
    def skill_key_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("skill_key must not be empty")
        return value


class VersionSkillAttachmentResponse(BaseModel):
    id: str
    version_id: str
    skill_key: str
    skill_source: str | None
    sort_order: int
    created_at: datetime

    @field_validator("id", "version_id", mode="before")
    @classmethod
    def stringify_uuid_values(cls, value):
        return str(value)


class VersionSkillAttachmentReadResponse(BaseModel):
    id: str
    version_id: str
    skill_key: str
    skill_source: str | None
    sort_order: int
    created_at: datetime

    @field_validator("id", "version_id", mode="before")
    @classmethod
    def stringify_uuid_values(cls, value):
        return str(value)


class VersionCapabilitiesBatchResponse(BaseModel):
    tools: list[VersionToolAttachmentReadResponse]
    skills: list[VersionSkillAttachmentReadResponse]


class CapabilityCatalogResponse(BaseModel):
    key: str
    type: Literal["agent_tool", "Execution_Action"]
    label: str
    description: str
    implementation_status: Literal["available", "planned"] = "available"
    is_attachable: bool = False
    is_runtime_available: bool = False
    provider: str | None = None
    auth_type: str = "none"
    required_scopes: list[str] = Field(default_factory=list)
    required_account_status: str = "active"
    input_schema: dict = Field(default_factory=dict)
    config_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    supported_approval_modes: list[str] = Field(default_factory=list)
    approval_policy: dict = Field(default_factory=dict)
    risk_level: Literal["read", "write", "upload", "publish"] = "read"
    artifact_input_requirements: dict = Field(default_factory=dict)
    implementation: str = "catalog"
    policy_rationale: str = ""
