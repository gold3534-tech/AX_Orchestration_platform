import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import relationship, synonym

from api.core.database import Base
from .asset import _json_type, _uuid_type, utcnow


class ToolCatalog(Base):
    __tablename__ = "tool_registry"

    id = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    entrypoint = Column(Text, nullable=False)
    schema_json = Column(_json_type, nullable=True, default=dict)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class SkillCatalog:
    __abstract__ = True


class VersionTool(Base):
    __tablename__ = "version_tools"
    __table_args__ = (
        UniqueConstraint("version_id", "tool_key", name="uq_version_tools_version_id_tool_key"),
    )

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    version_id = Column(_uuid_type, ForeignKey("asset_versions.id", ondelete="CASCADE"), nullable=False)
    tool_key = Column(Text, nullable=False)
    tool_config_json = Column(_json_type, nullable=False, default=dict)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    asset_version_id = synonym("version_id")
    asset_version = relationship(
        "AssetVersion",
        primaryjoin="foreign(VersionTool.version_id) == AssetVersion.id",
        back_populates="version_tools",
        uselist=False,
    )


class VersionSkill(Base):
    __tablename__ = "version_skills"
    __table_args__ = (
        UniqueConstraint("version_id", "skill_key", name="uq_version_skills_version_id_skill_key"),
    )

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    version_id = Column(_uuid_type, ForeignKey("asset_versions.id", ondelete="CASCADE"), nullable=False)
    skill_key = Column(Text, nullable=False)
    skill_source = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    asset_version_id = synonym("version_id")
    asset_version = relationship(
        "AssetVersion",
        primaryjoin="foreign(VersionSkill.version_id) == AssetVersion.id",
        back_populates="version_skills",
        uselist=False,
    )
