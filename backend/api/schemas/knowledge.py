from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None
    source_file_name: str = Field(min_length=1)
    source_file_size: int = Field(ge=0)
    source_mime_type: str | None = None
    content: str = Field(min_length=1)


class KnowledgeResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    status: str
    source_file_name: str
    source_file_size: int
    source_mime_type: str | None = None
    embedding_provider: str
    embedding_model: str
    chunk_count: int
    attached_agent_count: int = 0
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class VersionKnowledgeUpdate(BaseModel):
    knowledge_item_ids: list[str] = Field(default_factory=list)


class VersionKnowledgeItemSummary(BaseModel):
    id: str
    name: str
    status: str
    source_file_name: str


class VersionKnowledgeResponse(BaseModel):
    id: str
    version_id: str
    knowledge_item_id: str
    sort_order: int
    knowledge: VersionKnowledgeItemSummary
    created_at: datetime
