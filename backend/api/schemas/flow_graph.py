from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SkipValidation, StrictInt, field_validator


class FlowGraphPosition(BaseModel):
    x: float = 0
    y: float = 0

    model_config = ConfigDict(extra="forbid")


class FlowGraphViewport(BaseModel):
    x: float = 0
    y: float = 0
    zoom: float = 1

    model_config = ConfigDict(extra="forbid")


class FlowInputField(BaseModel):
    name: str
    type: Literal["string", "number", "boolean", "object", "array"]
    required: bool = False
    default: Any | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field name must not be empty")
        return value


class FlowInputMapping(BaseModel):
    source: Literal["state", "node", "literal", "transform"]
    path: str | None = None
    paths: list[str] | None = None
    nodeId: str | None = None
    value: Any | None = None
    inputType: Literal[
        "text",
        "structured",
        "raw",
        "image",
        "pdf",
        "text_file",
        "csv",
        "json_file",
        "docx",
        "audio",
        "video",
    ] | None = None
    transform: Literal["identity_v1", "join_text_v1", "join_card_news_slides_v1", "json_stringify_v1"] | None = None
    maxChars: int | None = None
    overflow: Literal["fail", "truncate"] | None = None

    model_config = ConfigDict(extra="forbid")


class FlowOutputField(BaseModel):
    label: str
    source: Literal["state", "node", "literal"]
    path: str | None = None
    nodeId: str | None = None
    value: Any | None = None

    model_config = ConfigDict(extra="forbid")


class FlowGraphExecutionActionData(BaseModel):
    action_key: str
    credential_provider: str | None = None
    credential_id: str | None = None
    input_bindings: dict[str, FlowInputMapping] = Field(default_factory=dict)
    config_json: dict[str, Any] = Field(default_factory=dict)
    approval_mode: Literal["never", "every_run"] = "never"
    idempotency_key_strategy: str = "run_node_action_input_hash"
    output_mapping: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class FlowRouterSource(BaseModel):
    nodeId: str
    path: str

    model_config = ConfigDict(extra="forbid")


class FlowRouterCondition(BaseModel):
    source: FlowRouterSource
    operator: Literal[
        "equals",
        "not_equals",
        "contains",
        "greater_than",
        "greater_than_or_equal",
        "less_than",
        "less_than_or_equal",
        "is_true",
        "is_false",
        "exists",
        "is_empty",
    ]
    value: Any | None = None
    route: str

    model_config = ConfigDict(extra="forbid")


class FlowGraphNodeData(BaseModel):
    fields: list[FlowInputField] | list[FlowOutputField] | None = None
    triggerType: Literal["manual"] | None = None
    assetId: str | None = None
    versionId: str | None = None
    inputMappings: dict[str, FlowInputMapping] = Field(default_factory=dict)
    action_key: str | None = None
    credential_provider: str | None = None
    credential_id: str | None = None
    input_bindings: dict[str, FlowInputMapping] = Field(default_factory=dict)
    config_json: dict[str, Any] = Field(default_factory=dict)
    approval_mode: Literal["never", "every_run"] = "never"
    idempotency_key_strategy: str = "run_node_action_input_hash"
    output_mapping: dict[str, Any] = Field(default_factory=dict)
    conditions: list[FlowRouterCondition] = Field(default_factory=list)
    prompt: str | None = None
    allowedDecisions: list[str] | None = None
    onNeedsRevision: SkipValidation[Literal["retry_previous", "continue_with_feedback"]] | None = None
    feedbackPropagation: (
        SkipValidation[Literal["none", "needs_revision_only", "approved_and_needs_revision", "all_decisions"]] | None
    ) = None
    maxAttempts: StrictInt | None = None

    model_config = ConfigDict(extra="allow")


class FlowGraphNode(BaseModel):
    id: str
    type: Literal["input", "start", "crew", "router", "hitl", "output", "tool", "execution_action"]
    position: FlowGraphPosition = Field(default_factory=FlowGraphPosition)
    data: FlowGraphNodeData = Field(default_factory=FlowGraphNodeData)

    model_config = ConfigDict(extra="forbid")


class FlowGraphEdgeData(BaseModel):
    route: str | None = None

    model_config = ConfigDict(extra="allow")


class FlowGraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: Literal["flow", "route", "tool_reference"]
    data: FlowGraphEdgeData = Field(default_factory=FlowGraphEdgeData)

    model_config = ConfigDict(extra="forbid")


class FlowGraphCrewEntity(BaseModel):
    asset_id: str
    version_id: str
    version_no: int
    name: str
    status: str
    runtime_snapshot_json: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class FlowGraphEntities(BaseModel):
    crews: dict[str, FlowGraphCrewEntity] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class FlowGraphDocument(BaseModel):
    schemaVersion: Literal[1]
    layoutDirection: str | None = "LR"
    viewport: FlowGraphViewport | None = None
    nodes: list[FlowGraphNode] = Field(default_factory=list)
    edges: list[FlowGraphEdge] = Field(default_factory=list)
    entities: FlowGraphEntities = Field(default_factory=FlowGraphEntities)

    model_config = ConfigDict(extra="forbid")
