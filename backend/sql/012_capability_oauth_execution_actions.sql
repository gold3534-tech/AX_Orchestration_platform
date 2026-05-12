ALTER TABLE credentials ADD COLUMN IF NOT EXISTS auth_type TEXT NOT NULL DEFAULT 'api_key';
ALTER TABLE credentials ADD COLUMN IF NOT EXISTS provider_account_id TEXT;
ALTER TABLE credentials ADD COLUMN IF NOT EXISTS provider_account_label TEXT;
ALTER TABLE credentials ADD COLUMN IF NOT EXISTS metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE credentials ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS oauth_states (
    id UUID PRIMARY KEY,
    owner_user_id UUID NOT NULL,
    provider TEXT NOT NULL,
    state_token TEXT NOT NULL UNIQUE,
    requested_scopes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    redirect_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_oauth_states_owner_provider_status
    ON oauth_states (owner_user_id, provider, status);

CREATE TABLE IF NOT EXISTS run_artifacts (
    id UUID PRIMARY KEY,
    owner_user_id UUID NOT NULL,
    run_id UUID NOT NULL REFERENCES flow_runs(id) ON DELETE CASCADE,
    node_id TEXT,
    artifact_type TEXT NOT NULL CHECK (artifact_type IN ('image', 'file')),
    media_type TEXT NOT NULL,
    sha256 TEXT,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    storage_backend TEXT NOT NULL CHECK (storage_backend IN ('ax_managed', 'temporary', 'google_drive')),
    storage_reference TEXT NOT NULL,
    storage_bucket TEXT,
    storage_path TEXT,
    source_tool TEXT,
    source_capability TEXT,
    retention_mode TEXT NOT NULL DEFAULT 'temporary' CHECK (retention_mode IN ('temporary', 'ax_managed')),
    retention_expires_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available', 'expired', 'failed')),
    CONSTRAINT ck_run_artifacts_size_bytes_non_negative CHECK (size_bytes >= 0),
    CONSTRAINT ck_run_artifacts_storage_retention_mode CHECK (
        (storage_backend = 'temporary' AND retention_mode = 'temporary')
        OR (storage_backend = 'ax_managed' AND retention_mode = 'ax_managed')
        OR (storage_backend = 'google_drive' AND retention_mode = 'temporary')
    ),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_run_artifacts_owner_created
    ON run_artifacts (owner_user_id, created_at, id);

CREATE INDEX IF NOT EXISTS ix_run_artifacts_run_node
    ON run_artifacts (run_id, node_id);

CREATE TABLE IF NOT EXISTS execution_action_runs (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL,
    node_id TEXT NOT NULL,
    action_key TEXT NOT NULL,
    owner_user_id UUID NOT NULL,
    credential_id UUID,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL,
    input_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_execution_action_runs_idempotency
    ON execution_action_runs (run_id, node_id, action_key, idempotency_key);
