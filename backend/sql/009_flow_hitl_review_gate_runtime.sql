CREATE TABLE IF NOT EXISTS flow_run_node_outputs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES flow_runs(id) ON DELETE CASCADE,
  node_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  output_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'current',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_flow_run_node_outputs_run_node_version UNIQUE (run_id, node_id, version)
);

CREATE INDEX IF NOT EXISTS ix_flow_run_node_outputs_run_node
  ON flow_run_node_outputs(run_id, node_id);

ALTER TABLE human_feedback_requests
  ADD COLUMN IF NOT EXISTS attempt_number INTEGER;

ALTER TABLE human_feedback_requests
  ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

ALTER TABLE human_feedback_requests
  ADD COLUMN IF NOT EXISTS resolved_by UUID;

ALTER TABLE human_feedback_requests
  ADD COLUMN IF NOT EXISTS idempotency_key TEXT;

CREATE INDEX IF NOT EXISTS ix_human_feedback_requests_run_node_status
  ON human_feedback_requests(run_id, node_id, status);

CREATE UNIQUE INDEX IF NOT EXISTS uq_human_feedback_requests_idempotency
  ON human_feedback_requests(run_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;
