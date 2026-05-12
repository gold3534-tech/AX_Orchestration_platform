import uuid

from sqlalchemy import Boolean, Column, ForeignKey, Integer, JSON, String, Text, select
from sqlalchemy.orm import column_property, relationship

from api.core.database import Base
from .asset import Asset, AssetVersion, _json_type, _uuid_type


class AgentVersion(Base):
    __tablename__ = "agent_versions"

    id = Column("version_id", _uuid_type, ForeignKey("asset_versions.id", ondelete="CASCADE"), primary_key=True, default=lambda: str(uuid.uuid4()))
    role = Column(Text, nullable=False)
    goal = Column(Text, nullable=False)
    backstory = Column(Text, nullable=False)
    llm_config_json = Column(_json_type, nullable=False, default=dict)
    function_calling_llm_config_json = Column(_json_type, nullable=False, default=dict)
    max_iter = Column(Integer, nullable=True)
    max_rpm = Column(Integer, nullable=True)
    max_execution_time = Column(Integer, nullable=True)
    is_verbose = Column(Boolean, nullable=False, default=False)
    allow_delegation = Column(Boolean, nullable=False, default=False)
    reasoning = Column(Boolean, nullable=False, default=False)
    max_reasoning_attempts = Column(Integer, nullable=True)
    system_template = Column(Text, nullable=True)
    prompt_template = Column(Text, nullable=True)
    response_template = Column(Text, nullable=True)
    memory_scope_path = Column(Text, nullable=True)
    payload_json = Column(_json_type, nullable=False, default=dict)

    asset_version = relationship("AssetVersion", foreign_keys=[id], uselist=False)

    asset_id = column_property(
        select(AssetVersion.asset_id).where(AssetVersion.id == id).scalar_subquery()
    )
    version_number = column_property(
        select(AssetVersion.version_number).where(AssetVersion.id == id).scalar_subquery()
    )
    name = column_property(
        select(Asset.name)
        .join(AssetVersion, Asset.id == AssetVersion.asset_id)
        .where(AssetVersion.id == id)
        .scalar_subquery()
    )
    enabled = column_property(select(True).scalar_subquery())
