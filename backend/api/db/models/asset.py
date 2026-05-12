import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from api.core.database import Base

_db_url = os.getenv("DATABASE_URL", "sqlite:///:memory:")
if _db_url.startswith("postgresql"):
    from sqlalchemy.dialects.postgresql import UUID as _UUID, JSONB as _JSONB

    _uuid_type = _UUID(as_uuid=True)
    _json_type = _JSONB
else:
    _uuid_type = String(36)
    _json_type = JSON


def utcnow():
    return datetime.now(timezone.utc)


class Asset(Base):
    __tablename__ = "assets"

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_type = Column("asset_type", Text, nullable=False)
    workspace_id = Column(_uuid_type, nullable=False, default=lambda: str(uuid.UUID("00000000-0000-0000-0000-000000000000")))
    owner_user_id = Column(_uuid_type, nullable=False, default=lambda: str(uuid.UUID("00000000-0000-0000-0000-000000000000")))
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="active")
    source_asset_id = Column(_uuid_type, ForeignKey("assets.id", ondelete="SET NULL"), nullable=True)
    root_asset_id = Column(_uuid_type, ForeignKey("assets.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    versions = relationship(
        "AssetVersion",
        back_populates="asset",
        cascade="all, delete-orphan",
        foreign_keys=lambda: [AssetVersion.asset_id],
    )


class AssetVersion(Base):
    __tablename__ = "asset_versions"
    __table_args__ = (
        UniqueConstraint("asset_id", "version_no", name="uq_asset_versions_asset_version_no"),
    )

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_id = Column(_uuid_type, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    version_number = Column("version_no", Integer, nullable=False, default=1)
    status = Column(Text, nullable=False, default="draft")
    base_version_id = Column(_uuid_type, ForeignKey("asset_versions.id", ondelete="SET NULL"), nullable=True)
    created_by = Column(_uuid_type, nullable=False, default=lambda: str(uuid.UUID("00000000-0000-0000-0000-000000000000")))
    revision = Column(Integer, nullable=False, default=1)
    metadata_json = Column(_json_type, nullable=False, default=dict)
    payload_json = Column(_json_type, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    asset = relationship("Asset", back_populates="versions", foreign_keys=[asset_id])
    base_version = relationship("AssetVersion", remote_side=lambda: [AssetVersion.id], uselist=False)
    outgoing_links = relationship(
        "VersionLink",
        back_populates="source_version",
        cascade="all, delete-orphan",
        foreign_keys="VersionLink.source_version_id",
    )
    incoming_links = relationship(
        "VersionLink",
        back_populates="target_version",
        cascade="all, delete-orphan",
        foreign_keys="VersionLink.target_version_id",
    )
    version_tools = relationship(
        "VersionTool",
        back_populates="asset_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
        primaryjoin="AssetVersion.id == foreign(VersionTool.version_id)",
    )
    version_skills = relationship(
        "VersionSkill",
        back_populates="asset_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
        primaryjoin="AssetVersion.id == foreign(VersionSkill.version_id)",
    )
    version_knowledge = relationship(
        "VersionKnowledge",
        back_populates="asset_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
        primaryjoin="AssetVersion.id == foreign(VersionKnowledge.version_id)",
    )
    runtime_snapshot = relationship(
        "AssetRuntimeSnapshot",
        back_populates="asset_version",
        cascade="all, delete-orphan",
        uselist=False,
        passive_deletes=True,
    )


class VersionLink(Base):
    __tablename__ = "version_links"

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    source_version_id = Column("parent_version_id", _uuid_type, ForeignKey("asset_versions.id", ondelete="CASCADE"), nullable=False)
    target_version_id = Column("child_version_id", _uuid_type, ForeignKey("asset_versions.id", ondelete="CASCADE"), nullable=False)
    link_type = Column(Text, nullable=False, default="derived_from")
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    source_version = relationship("AssetVersion", back_populates="outgoing_links", foreign_keys=[source_version_id])
    target_version = relationship("AssetVersion", back_populates="incoming_links", foreign_keys=[target_version_id])
