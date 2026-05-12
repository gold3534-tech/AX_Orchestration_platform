from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, AliasChoices, field_validator, model_validator
from api.services.task_input_presets import normalize_task_input_preset_keys


class OutputSchemaField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: Literal["str", "int", "float", "bool", "dict", "list"]
    description: str | None = None
    required: bool = True

    @field_validator("name")
    @classmethod
    def schema_field_name_must_be_identifier(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("schema field name must not be empty")
        if not trimmed.replace("_", "").isalnum():
            raise ValueError("schema field name must contain only letters, numbers, and underscores")
        if trimmed[0].isdigit():
            raise ValueError("schema field name must not start with a number")
        return trimmed


class AgentAssetPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["agent"] = "agent"
    role: str
    goal: str
    backstory: str
    # [임시 추가] 에이전트 포토 공간 시연용
    photo_url: str | None = None
    llm: str | dict[str, Any] | None = None
    function_calling_llm: str | dict[str, Any] | None = None
    max_iter: int | None = None
    max_rpm: int | None = None
    max_execution_time: int | None = None
    verbose: bool | None = None
    allow_delegation: bool | None = None
    reasoning: bool | None = None
    max_reasoning_attempts: int | None = None
    system_template: str | None = None
    prompt_template: str | None = None
    response_template: str | None = None
    cache: bool | None = None
    max_tokens: int | None = None
    allow_code_execution: bool | None = None
    respect_context_window: bool | None = None
    max_retry_limit: int | None = None
    multimodal: bool | None = None
    inject_date: bool | None = None
    date_format: str | None = None
    use_system_prompt: bool | None = None
    code_execution_mode: Literal["safe", "unsafe"] | None = None
    embedder: dict[str, Any] | None = None


class TaskAssetPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["task"] = "task"
    description: str
    expected_output: str
    async_execution: bool | None = None
    human_input: bool | None = None
    markdown: bool | None = None
    guardrail_max_retries: int | None = None
    output_file: str | None = None
    create_directory: bool | None = None
    output_type: Literal["Output JSON", "Output Pydantic"] | None = None
    output_schema_fields: list[OutputSchemaField] | None = None
    input_presets: list[str] = Field(default_factory=list)

    @field_validator("input_presets")
    @classmethod
    def normalize_input_presets(cls, value: list[str]) -> list[str]:
        return normalize_task_input_preset_keys(value)

    @model_validator(mode="after")
    def validate_output_schema_fields(self):
        if self.output_type is None and self.output_schema_fields:
            raise ValueError("output_schema_fields requires Output JSON or Output Pydantic")
        if self.output_type in {"Output JSON", "Output Pydantic"} and not self.output_schema_fields:
            raise ValueError("output_schema_fields is required for structured task output")
        return self


class CrewAssetPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["crew"] = "crew"
    process: Literal["sequential", "hierarchical"] = "sequential"
    manager_llm: str | dict[str, Any] | None = None
    manager_agent_asset_id: UUID | None = None
    function_calling_llm: str | dict[str, Any] | None = None
    verbose: bool | None = None
    planning: bool | None = None
    memory: bool | None = None
    cache: bool | None = None
    max_rpm: int | None = None
    share_crew: bool | None = None
    output_log_file: bool | str | None = None
    prompt_file: str | None = None
    planning_llm: str | dict[str, Any] | None = None
    stream: bool | None = None
    tracing: bool | None = None
    checkpoint: bool | dict[str, Any] | None = None
    embedder: dict[str, Any] | None = None
    chat_llm: str | dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_hierarchical_manager(self):
        manager_llm = self.manager_llm
        manager_llm_usable = False
        if isinstance(manager_llm, str):
            manager_llm_usable = bool(manager_llm.strip())
        elif isinstance(manager_llm, dict):
            candidate = manager_llm.get("main_model") or manager_llm.get("model")
            manager_llm_usable = isinstance(candidate, str) and bool(candidate.strip())
        if self.process == "hierarchical" and not manager_llm_usable:
            raise ValueError("hierarchical crew requires manager_llm")
        return self


class FlowAssetPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["flow"] = "flow"
    entry_method: str | None = None
    timeout_seconds: int | None = None


_payload_models: dict[str, type[BaseModel]] = {
    "agent": AgentAssetPayload,
    "task": TaskAssetPayload,
    "crew": CrewAssetPayload,
    "flow": FlowAssetPayload,
}

AssetPayload = AgentAssetPayload | TaskAssetPayload | CrewAssetPayload | FlowAssetPayload


def normalize_asset_payload(asset_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    model = _payload_models.get(asset_type)
    if model is None:
        raise ValueError(f"Unsupported asset type: {asset_type}")
    validated_payload = model.model_validate(payload)
    dumped_payload = validated_payload.model_dump(
        mode="json",
        exclude_unset=True,
        exclude_none=True,
        exclude={"type"},
    )
    if asset_type == "crew" and "process" not in dumped_payload:
        dumped_payload["process"] = validated_payload.process
    return dumped_payload


class AssetCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    type: Literal["agent", "task", "crew", "flow"]
    name: str
    description: str | None = None
    workspace_id: UUID | None = None
    payload: AssetPayload = Field(validation_alias=AliasChoices("payload", "initial_payload"))

    @field_validator("payload", mode="before")
    @classmethod
    def validate_payload_for_type(cls, value: dict[str, Any], info):
        asset_type = info.data.get("type")
        return normalize_asset_payload(asset_type, value)

    @property
    def normalized_payload(self) -> dict[str, Any]:
        if isinstance(self.payload, BaseModel):
            return self.payload.model_dump(mode="json", exclude_unset=True, exclude_none=True)
        return dict(self.payload)


class AssetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_version_id: UUID
    name: str | None = None
    description: str | None = None
    payload: dict[str, Any]
    change_summary: str | None = None


class AssetCurrentVersionResponse(BaseModel):
    id: UUID
    version_no: int
    status: str
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AssetResponse(BaseModel):
    id: UUID
    type: str
    name: str
    description: str | None = None
    workspace_id: UUID | None = None
    current_version: AssetCurrentVersionResponse
    created_at: datetime
    updated_at: datetime


class AssetVersionResponse(BaseModel):
    id: UUID
    asset_id: UUID
    version_no: int
    status: str
    payload: dict[str, Any]
    created_at: datetime


class AssetRestoreResponse(AssetResponse):
    restored_from_version_id: UUID
