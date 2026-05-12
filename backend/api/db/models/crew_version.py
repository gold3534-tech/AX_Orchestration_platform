import uuid

from sqlalchemy import Boolean, Column, ForeignKey, Text, select
from sqlalchemy.orm import column_property, relationship, synonym

from api.core.database import Base
from .asset import Asset, AssetVersion, _json_type, _uuid_type


class CrewVersion(Base):
    __tablename__ = "crew_versions"

    id = Column("version_id", _uuid_type, ForeignKey("asset_versions.id", ondelete="CASCADE"), primary_key=True, default=lambda: str(uuid.uuid4()))
    process_type = Column(Text, nullable=False, default="sequential")
    manager_llm_config_json = Column(_json_type, nullable=False, default=dict)
    manager_agent_asset_id = Column(_uuid_type, ForeignKey("assets.id", ondelete="SET NULL"), nullable=True)
    function_calling_llm_config_json = Column(_json_type, nullable=False, default=dict)
    is_verbose = Column(Boolean, nullable=False, default=False)
    planning = Column(Boolean, nullable=False, default=False)
    memory_enabled = Column(Boolean, nullable=False, default=False)
    payload_json = Column(_json_type, nullable=False, default=dict)
    runtime_snapshot_json = Column(_json_type, nullable=False, default=dict)

    asset_version = relationship("AssetVersion", foreign_keys=[id], uselist=False)
    manager_agent = relationship("Asset", foreign_keys=[manager_agent_asset_id], uselist=False)

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
    description = column_property(
        select(Asset.description)
        .join(AssetVersion, Asset.id == AssetVersion.asset_id)
        .where(AssetVersion.id == id)
        .scalar_subquery()
    )
    manager_llm = synonym("manager_llm_config_json")
    manager_agent_version_id = column_property(select(None).scalar_subquery())
