CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS flow_version_drafts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  flow_asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  base_version_id UUID REFERENCES asset_versions(id) ON DELETE SET NULL,
  owner_user_id UUID NOT NULL,
  graph_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  validation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  last_test_validation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_flow_version_drafts_owner_asset UNIQUE (flow_asset_id, owner_user_id)
);

CREATE TABLE IF NOT EXISTS flow_run_state_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES flow_runs(id) ON DELETE CASCADE,
  node_id TEXT,
  state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS flow_run_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES flow_runs(id) ON DELETE CASCADE,
  node_id TEXT,
  event_type TEXT NOT NULL,
  event_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS human_feedback_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES flow_runs(id) ON DELETE CASCADE,
  node_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  prompt_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  response_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  responded_at TIMESTAMPTZ
);
