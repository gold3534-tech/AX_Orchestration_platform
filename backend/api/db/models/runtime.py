import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, and_
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship, synonym

from api.core.database import Base
from .asset import _json_type, _uuid_type, utcnow


class Credential(Base):
    __tablename__ = "credentials"

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_type = Column(Text, nullable=False)
    owner_user_id = Column(_uuid_type, nullable=True)
    workspace_id = Column(_uuid_type, nullable=True)
    provider = Column(Text, nullable=False)
    auth_type = Column(Text, nullable=False, default="api_key")
    label = Column(Text, nullable=False)
    provider_account_id = Column(Text, nullable=True)
    provider_account_label = Column(Text, nullable=True)
    secret_ref = Column(Text, nullable=False)
    scopes_json = Column(_json_type, nullable=False, default=list)
    status = Column(Text, nullable=False, default="active")
    metadata_json = Column(_json_type, nullable=False, default=dict)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    name = synonym("label")
    secret = relationship(
        "CredentialSecret",
        back_populates="credential",
        uselist=False,
        cascade="all, delete-orphan",
    )

    @hybrid_property
    def enabled(self):
        return self.status == "active"


Index(
    "ix_credentials_active_user_provider",
    Credential.owner_user_id,
    Credential.provider,
    unique=True,
    sqlite_where=and_(
        Credential.owner_type == "user",
        Credential.workspace_id.is_(None),
        Credential.status == "active",
    ),
    postgresql_where=and_(
        Credential.owner_type == "user",
        Credential.workspace_id.is_(None),
        Credential.status == "active",
    ),
)


class CredentialSecret(Base):
    __tablename__ = "credential_secrets"

    credential_id = Column(
        _uuid_type,
        ForeignKey("credentials.id", ondelete="CASCADE"),
        primary_key=True,
    )
    encrypted_secret_json = Column(_json_type, nullable=False, default=dict)
    encryption_key_version = Column(Text, nullable=False, default="v1")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    credential = relationship("Credential", back_populates="secret", uselist=False)


class OAuthState(Base):
    __tablename__ = "oauth_states"

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_user_id = Column(_uuid_type, nullable=False)
    provider = Column(Text, nullable=False)
    state_token = Column(Text, nullable=False, unique=True)
    requested_scopes_json = Column(_json_type, nullable=False, default=list)
    redirect_path = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class ExecutionBinding(Base):
    __tablename__ = "execution_bindings"
    __table_args__ = (
        UniqueConstraint(
            "subject_version_id",
            "binding_type",
            "binding_key",
            name="uq_execution_bindings_subject_binding",
        ),
    )

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(_uuid_type, nullable=False)
    subject_version_id = Column(_uuid_type, ForeignKey("asset_versions.id", ondelete="CASCADE"), nullable=False)
    binding_type = Column(Text, nullable=False)
    binding_key = Column(Text, nullable=False)
    credential_id = Column(_uuid_type, ForeignKey("credentials.id", ondelete="RESTRICT"), nullable=False)
    created_by = Column(_uuid_type, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    asset_version_id = synonym("subject_version_id")

    credential = relationship("Credential")
    asset_version = relationship("AssetVersion", foreign_keys=[subject_version_id])


class FlowRun(Base):
    __tablename__ = "flow_runs"

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    flow_version_id = Column(_uuid_type, ForeignKey("asset_versions.id", ondelete="CASCADE"), nullable=False)
    status = Column(Text, nullable=False, default="pending")
    input_json = Column(_json_type, nullable=False, default=dict)
    output_json = Column(_json_type, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    flow_asset_version = relationship("AssetVersion", foreign_keys=[flow_version_id])


class RunArtifact(Base):
    __tablename__ = "run_artifacts"
    __table_args__ = (
        CheckConstraint("artifact_type IN ('image', 'file')", name="ck_run_artifacts_artifact_type"),
        CheckConstraint(
            "storage_backend IN ('ax_managed', 'temporary', 'google_drive')",
            name="ck_run_artifacts_storage_backend",
        ),
        CheckConstraint(
            "retention_mode IN ('temporary', 'ax_managed')",
            name="ck_run_artifacts_retention_mode",
        ),
        CheckConstraint(
            "status IN ('available', 'expired', 'failed')",
            name="ck_run_artifacts_status",
        ),
        CheckConstraint("size_bytes >= 0", name="ck_run_artifacts_size_bytes_non_negative"),
        CheckConstraint(
            "(storage_backend = 'temporary' AND retention_mode = 'temporary') "
            "OR (storage_backend = 'ax_managed' AND retention_mode = 'ax_managed') "
            "OR (storage_backend = 'google_drive' AND retention_mode = 'temporary')",
            name="ck_run_artifacts_storage_retention_mode",
        ),
        Index("ix_run_artifacts_owner_created", "owner_user_id", "created_at", "id"),
        Index("ix_run_artifacts_run_node", "run_id", "node_id"),
    )

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_user_id = Column(_uuid_type, nullable=False)
    run_id = Column(_uuid_type, ForeignKey("flow_runs.id", ondelete="CASCADE"), nullable=False)
    node_id = Column(Text, nullable=True)
    artifact_type = Column(Text, nullable=False)
    media_type = Column(Text, nullable=False)
    sha256 = Column(Text, nullable=True)
    size_bytes = Column(Integer, nullable=False, default=0)
    storage_backend = Column(Text, nullable=False)
    storage_reference = Column(Text, nullable=False)
    storage_bucket = Column(Text, nullable=True)
    storage_path = Column(Text, nullable=True)
    source_tool = Column(Text, nullable=True)
    source_capability = Column(Text, nullable=True)
    retention_mode = Column(Text, nullable=False, default="temporary")
    retention_expires_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(Text, nullable=False, default="available")
    metadata_json = Column(_json_type, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    flow_run = relationship("FlowRun")

    @property
    def mime_type(self):
        return self.media_type

    @property
    def expires_at(self):
        return self.retention_expires_at


class FlowRunExecution(Base):
    __tablename__ = "flow_run_executions"

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    flow_run_id = Column(_uuid_type, ForeignKey("flow_runs.id", ondelete="CASCADE"), nullable=False)
    execution_binding_id = Column(_uuid_type, ForeignKey("execution_bindings.id", ondelete="CASCADE"), nullable=False)
    status = Column(Text, nullable=False, default="pending")
    result_json = Column(_json_type, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    flow_run = relationship("FlowRun")
    execution_binding = relationship("ExecutionBinding")


class ExecutionActionRun(Base):
    __tablename__ = "execution_action_runs"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "node_id",
            "action_key",
            "idempotency_key",
            name="uq_execution_action_runs_idempotency",
        ),
    )

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(_uuid_type, nullable=False)
    node_id = Column(Text, nullable=False)
    action_key = Column(Text, nullable=False)
    owner_user_id = Column(_uuid_type, nullable=False)
    credential_id = Column(_uuid_type, nullable=True)
    idempotency_key = Column(Text, nullable=False)
    status = Column(Text, nullable=False)
    input_json = Column(_json_type, nullable=False, default=dict)
    output_json = Column(_json_type, nullable=False, default=dict)
    error_code = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class FlowRunStateSnapshot(Base):
    __tablename__ = "flow_run_state_snapshots"

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(_uuid_type, ForeignKey("flow_runs.id", ondelete="CASCADE"), nullable=False)
    node_id = Column(Text, nullable=True)
    state_json = Column(_json_type, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class FlowRunEvent(Base):
    __tablename__ = "flow_run_events"
    __table_args__ = (
        Index("ix_flow_run_events_run_created_id", "run_id", "created_at", "id"),
    )

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(_uuid_type, ForeignKey("flow_runs.id", ondelete="CASCADE"), nullable=False)
    node_id = Column(Text, nullable=True)
    event_type = Column(Text, nullable=False)
    event_payload_json = Column(_json_type, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class FlowRunNodeOutput(Base):
    __tablename__ = "flow_run_node_outputs"
    __table_args__ = (
        UniqueConstraint("run_id", "node_id", "version", name="uq_flow_run_node_outputs_run_node_version"),
        Index("ix_flow_run_node_outputs_run_node", "run_id", "node_id"),
    )

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(_uuid_type, ForeignKey("flow_runs.id", ondelete="CASCADE"), nullable=False)
    node_id = Column(Text, nullable=False)
    version = Column(Integer, nullable=False)
    output_json = Column(_json_type, nullable=False, default=dict)
    status = Column(Text, nullable=False, default="current")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class HumanFeedbackRequest(Base):
    __tablename__ = "human_feedback_requests"

    id = Column(_uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(_uuid_type, ForeignKey("flow_runs.id", ondelete="CASCADE"), nullable=False)
    node_id = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="pending")
    prompt_json = Column(_json_type, nullable=False, default=dict)
    response_json = Column(_json_type, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    responded_at = Column(DateTime(timezone=True), nullable=True)
    attempt_number = Column(Integer, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(_uuid_type, nullable=True)
    idempotency_key = Column(Text, nullable=True)


Index(
    "ix_human_feedback_requests_run_node_status",
    HumanFeedbackRequest.run_id,
    HumanFeedbackRequest.node_id,
    HumanFeedbackRequest.status,
)

Index(
    "uq_human_feedback_requests_idempotency",
    HumanFeedbackRequest.run_id,
    HumanFeedbackRequest.idempotency_key,
    unique=True,
    sqlite_where=HumanFeedbackRequest.idempotency_key.is_not(None),
    postgresql_where=HumanFeedbackRequest.idempotency_key.is_not(None),
)
