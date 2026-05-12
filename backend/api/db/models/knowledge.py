import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import relationship, synonym

from api.core.database import Base
from .asset import _json_type, _uuid_type, utcnow


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(_uuid_type, nullable=False)
    owner_user_id = Column(_uuid_type, nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="uploaded")
    source_mime_type = Column(Text, nullable=True)
    source_file_name = Column(Text, nullable=False)
    source_file_size = Column(Integer, nullable=False)
    storage_bucket = Column(Text, nullable=False)
    storage_path = Column(Text, nullable=False)
    parser = Column(Text, nullable=True)
    embedding_provider = Column(Text, nullable=False, default="openai")
    embedding_model = Column(Text, nullable=False, default="text-embedding-3-small")
    chunk_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    chunks = relationship(
        "KnowledgeChunk",
        back_populates="knowledge_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    version_bindings = relationship(
        "VersionKnowledge",
        back_populates="knowledge_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("knowledge_item_id", "chunk_index", name="uq_knowledge_chunks_item_index"),
    )

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    knowledge_item_id = Column(_uuid_type, ForeignKey("knowledge_items.id", ondelete="CASCADE"), nullable=False)
    workspace_id = Column(_uuid_type, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    content_hash = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=True)
    metadata_json = Column(_json_type, nullable=False, default=dict)
    # Production Postgres stores the searchable vector in knowledge_chunks.embedding
    # from backend/sql/014_knowledge_upload_real_rag.sql. SQLite tests keep this
    # JSON column as an explicit fallback so local unit tests do not need pgvector.
    embedding_json = Column(_json_type, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    knowledge_item = relationship("KnowledgeItem", back_populates="chunks")


class VersionKnowledge(Base):
    __tablename__ = "version_knowledge"
    __table_args__ = (
        UniqueConstraint("version_id", "knowledge_item_id", name="uq_version_knowledge_version_id_item_id"),
    )

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    version_id = Column(_uuid_type, ForeignKey("asset_versions.id", ondelete="CASCADE"), nullable=False)
    knowledge_item_id = Column(_uuid_type, ForeignKey("knowledge_items.id", ondelete="CASCADE"), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    asset_version_id = synonym("version_id")
    asset_version = relationship(
        "AssetVersion",
        primaryjoin="foreign(VersionKnowledge.version_id) == AssetVersion.id",
        back_populates="version_knowledge",
        uselist=False,
    )
    knowledge_item = relationship("KnowledgeItem", back_populates="version_bindings")
