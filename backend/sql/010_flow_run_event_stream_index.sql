CREATE INDEX IF NOT EXISTS ix_flow_run_events_run_created_id
  ON flow_run_events (run_id, created_at, id);
