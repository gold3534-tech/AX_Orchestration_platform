import uuid

from sqlalchemy import Boolean, Column, ForeignKey, Integer, Text, select
from sqlalchemy.orm import column_property, relationship, synonym

from api.core.database import Base
from .asset import Asset, AssetVersion, _json_type, _uuid_type


class TaskVersion(Base):
    __tablename__ = "task_versions"

    id = Column("version_id", _uuid_type, ForeignKey("asset_versions.id", ondelete="CASCADE"), primary_key=True, default=lambda: str(uuid.uuid4()))
    description = Column(Text, nullable=False)
    expected_output = Column(Text, nullable=False)
    async_execution = Column(Boolean, nullable=False, default=False)
    human_input = Column(Boolean, nullable=False, default=False)
    markdown = Column(Boolean, nullable=False, default=False)
    output_json_schema = Column(_json_type, nullable=True)
    output_pydantic_schema = Column(_json_type, nullable=True)
    guardrail_config_json = Column(_json_type, nullable=True)
    guardrail_max_retries = Column(Integer, nullable=True)
    output_file = Column(Text, nullable=True)
    create_directory = Column(Boolean, nullable=False, default=True)
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
    output_schema_json = synonym("output_json_schema")
