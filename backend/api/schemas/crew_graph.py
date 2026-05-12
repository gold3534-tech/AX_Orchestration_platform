from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.schemas.capabilities import CredentialRequirement


class CrewGraphNodeData(BaseModel):
    assetId: str | None = None
    versionId: str | None = None
    processType: str | None = None
    name: str | None = None
    label: str | None = None
    kind: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("assetId", "versionId", "processType", "name", "label", "kind")
    @classmethod
    def optional_fields_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("field must not be empty")
        return trimmed


class CrewGraphPosition(BaseModel):
    x: float = 0
    y: float = 0

    model_config = ConfigDict(extra="forbid")


class CrewGraphNodeStyle(BaseModel):
    width: float | None = None
    height: float | None = None

    model_config = ConfigDict(extra="forbid")


class CrewGraphViewport(BaseModel):
    x: float = 0
    y: float = 0
    zoom: float = 1

    model_config = ConfigDict(extra="forbid")


class CrewGraphNode(BaseModel):
    id: str
    type: Literal["crew", "placeholder", "agent", "task"]
    parentId: str | None = None
    extent: str | None = None
    position: CrewGraphPosition = Field(default_factory=CrewGraphPosition)
    style: CrewGraphNodeStyle | None = None
    data: CrewGraphNodeData = Field(default_factory=CrewGraphNodeData)

    model_config = ConfigDict(extra="forbid")

    @field_validator("id", "parentId", "extent")
    @classmethod
    def node_identifiers_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("field must not be empty")
        return trimmed


class CrewGraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: Literal[
        "agent_assignment",
        "task_context",
        "task_sequence",
    ]

    model_config = ConfigDict(extra="forbid")

    @field_validator("id", "source", "target")
    @classmethod
    def edge_fields_must_not_be_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("field must not be empty")
        return trimmed


class CrewGraphEntity(BaseModel):
    asset_id: str
    version_id: str
    version_no: int = 0
    name: str
    description: str | None = None
    status: str = "draft"
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @field_validator("asset_id", "version_id", "name", "status")
    @classmethod
    def entity_text_fields_must_not_be_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("field must not be empty")
        return trimmed


class CrewGraphToolAttachment(BaseModel):
    version_id: str
    tool_config_json: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0

    model_config = ConfigDict(extra="forbid")

    @field_validator("version_id")
    @classmethod
    def attachment_version_id_must_not_be_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("field must not be empty")
        return trimmed


class CrewGraphToolEntity(BaseModel):
    tool_key: str
    name: str | None = None
    description: str | None = None
    tool_type: str | None = None
    module_path: str | None = None
    class_name: str | None = None
    default_config_json: dict[str, Any] = Field(default_factory=dict)
    config_schema_json: dict[str, Any] = Field(default_factory=dict)
    input_schema_json: dict[str, Any] = Field(default_factory=dict)
    ui_schema_json: dict[str, Any] = Field(default_factory=dict)
    required_env_vars: list[dict[str, Any]] = Field(default_factory=list)
    credential_requirements: list[CredentialRequirement] = Field(default_factory=list)
    attachments: list[CrewGraphToolAttachment] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @field_validator("tool_key")
    @classmethod
    def tool_key_must_not_be_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("field must not be empty")
        return trimmed

    @field_validator("name", "description", "tool_type", "module_path", "class_name")
    @classmethod
    def optional_metadata_fields_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("field must not be empty")
        return trimmed


class CrewGraphKnowledgeAttachment(BaseModel):
    version_id: str
    sort_order: int = 0


class CrewGraphKnowledgeEntity(BaseModel):
    id: str
    name: str
    status: str
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"
    attachments: list[CrewGraphKnowledgeAttachment] = Field(default_factory=list)


class CrewGraphEntities(BaseModel):
    agents: dict[str, CrewGraphEntity] = Field(default_factory=dict)
    tasks: dict[str, CrewGraphEntity] = Field(default_factory=dict)
    crews: dict[str, CrewGraphEntity] = Field(default_factory=dict)
    tools: dict[str, CrewGraphToolEntity] = Field(default_factory=dict)
    knowledge: dict[str, CrewGraphKnowledgeEntity] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class CrewGraphDocument(BaseModel):
    schemaVersion: Literal[1]
    layoutDirection: str | None = None
    viewport: CrewGraphViewport | None = None
    nodes: list[CrewGraphNode] = Field(default_factory=list)
    edges: list[CrewGraphEdge] = Field(default_factory=list)
    entities: CrewGraphEntities = Field(default_factory=CrewGraphEntities)

    model_config = ConfigDict(extra="forbid")
