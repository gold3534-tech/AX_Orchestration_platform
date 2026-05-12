import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from api.core.database import Base
from .asset import _uuid_type, utcnow


class InputPresetDefinition(Base):
    __tablename__ = "input_preset_definitions"
    __table_args__ = (UniqueConstraint("key", name="uq_input_preset_definitions_key"),)

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    key = Column(Text, nullable=False)
    label = Column(Text, nullable=False)
    input_type = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    task_version_bindings = relationship(
        "TaskInputPresetBinding",
        back_populates="preset_definition",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class TaskInputPresetBinding(Base):
    __tablename__ = "task_input_preset_bindings"
    __table_args__ = (
        UniqueConstraint("asset_version_id", "preset_id", name="uq_task_input_preset_bindings_asset_version_preset"),
    )

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_version_id = Column(_uuid_type, ForeignKey("asset_versions.id", ondelete="CASCADE"), nullable=False)
    preset_id = Column(_uuid_type, ForeignKey("input_preset_definitions.id", ondelete="CASCADE"), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_required = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    asset_version = relationship("AssetVersion", uselist=False)
    preset_definition = relationship("InputPresetDefinition", back_populates="task_version_bindings", uselist=False)
