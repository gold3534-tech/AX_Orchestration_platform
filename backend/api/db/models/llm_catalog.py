import os

from sqlalchemy import Boolean, Column, ForeignKey, Integer, JSON, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from api.core.database import Base

_db_url = os.getenv("DATABASE_URL", "sqlite:///:memory:")
if _db_url.startswith("postgresql"):
    from sqlalchemy.dialects.postgresql import JSONB as _JSONB

    _json_type = _JSONB
else:
    _json_type = JSON


class LLMProvider(Base):
    __tablename__ = "llm_providers"

    provider_key = Column(Text, primary_key=True)
    display_name = Column(Text, nullable=False)
    provider_type = Column(Text, nullable=False)
    credential_provider = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    metadata_json = Column(_json_type, nullable=False, default=dict)

    models = relationship(
        "LLMModel",
        back_populates="provider",
        cascade="all, delete-orphan",
        primaryjoin="LLMProvider.provider_key == foreign(LLMModel.provider_key)",
    )


class LLMModel(Base):
    __tablename__ = "llm_models"
    __table_args__ = (
        UniqueConstraint("model_key", name="uq_llm_models_model_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_key = Column(Text, ForeignKey("llm_providers.provider_key", ondelete="CASCADE"), nullable=False)
    model_key = Column(Text, nullable=False)
    display_name = Column(Text, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    llm_metadata_json = Column(_json_type, nullable=False, default=dict)

    provider = relationship("LLMProvider", back_populates="models")
