import uuid

from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint

from api.core.database import Base
from .asset import _json_type, _uuid_type, utcnow


class FlowVersionDraft(Base):
    __tablename__ = "flow_version_drafts"
    __table_args__ = (
        UniqueConstraint("flow_asset_id", "owner_user_id", name="uq_flow_version_drafts_owner_asset"),
    )

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    flow_asset_id = Column(_uuid_type, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    base_version_id = Column(_uuid_type, ForeignKey("asset_versions.id", ondelete="SET NULL"), nullable=True)
    owner_user_id = Column(_uuid_type, nullable=False)
    graph_json = Column(_json_type, nullable=False, default=dict)
    validation_json = Column(_json_type, nullable=False, default=dict)
    last_test_validation_json = Column(_json_type, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
