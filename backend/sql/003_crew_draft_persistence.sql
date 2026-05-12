CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS crew_version_drafts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  crew_asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  base_version_id UUID REFERENCES asset_versions(id) ON DELETE SET NULL,
  owner_user_id UUID NOT NULL,
  graph_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  validation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  last_test_validation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_crew_version_drafts_owner_asset UNIQUE (crew_asset_id, owner_user_id)
);
