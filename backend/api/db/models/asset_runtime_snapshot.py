from sqlalchemy import Column, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from api.core.database import Base
from .asset import _json_type, _uuid_type, utcnow


class AssetRuntimeSnapshot(Base):
    __tablename__ = "asset_runtime_snapshots"

    version_id = Column(_uuid_type, ForeignKey("asset_versions.id", ondelete="CASCADE"), primary_key=True)
    runtime_snapshot_json = Column(_json_type, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    asset_version = relationship("AssetVersion", back_populates="runtime_snapshot", uselist=False)
