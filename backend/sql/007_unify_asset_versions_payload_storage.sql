CREATE EXTENSION IF NOT EXISTS "pgcrypto";

ALTER TABLE asset_versions
  ADD COLUMN IF NOT EXISTS metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE asset_versions
  ADD COLUMN IF NOT EXISTS payload_json JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS asset_runtime_snapshots (
  version_id UUID PRIMARY KEY REFERENCES asset_versions(id) ON DELETE CASCADE,
  runtime_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO asset_runtime_snapshots (version_id, runtime_snapshot_json, created_at, updated_at)
SELECT
  version_id,
  COALESCE(runtime_snapshot_json, '{}'::jsonb),
  now(),
  now()
FROM crew_versions
WHERE COALESCE(runtime_snapshot_json, '{}'::jsonb) <> '{}'::jsonb
ON CONFLICT (version_id) DO UPDATE SET
  runtime_snapshot_json = EXCLUDED.runtime_snapshot_json,
  updated_at = now();

UPDATE asset_versions asset_version
SET payload_json =
  jsonb_strip_nulls(
    jsonb_build_object('role', av.role)
    || jsonb_build_object('goal', av.goal)
    || jsonb_build_object('backstory', av.backstory)
    || jsonb_build_object('llm', NULLIF(av.llm_config_json, '{}'::jsonb))
    || jsonb_build_object('function_calling_llm', NULLIF(av.function_calling_llm_config_json, '{}'::jsonb))
    || jsonb_build_object('max_iter', av.max_iter)
    || jsonb_build_object('max_rpm', av.max_rpm)
    || jsonb_build_object('max_execution_time', av.max_execution_time)
    || jsonb_build_object('verbose', av.is_verbose)
    || jsonb_build_object('allow_delegation', av.allow_delegation)
    || jsonb_build_object('reasoning', av.reasoning)
    || jsonb_build_object('max_reasoning_attempts', av.max_reasoning_attempts)
    || jsonb_build_object('system_template', av.system_template)
    || jsonb_build_object('prompt_template', av.prompt_template)
    || jsonb_build_object('response_template', av.response_template)
  )
  || COALESCE(av.payload_json, '{}'::jsonb)
  || COALESCE(asset_version.payload_json, '{}'::jsonb)
FROM agent_versions av
WHERE av.version_id = asset_version.id;

UPDATE asset_versions asset_version
SET payload_json =
  jsonb_strip_nulls(
    jsonb_build_object('description', tv.description)
    || jsonb_build_object('expected_output', tv.expected_output)
    || jsonb_build_object('async_execution', tv.async_execution)
    || jsonb_build_object('human_input', tv.human_input)
    || jsonb_build_object('markdown', tv.markdown)
    || jsonb_build_object('guardrail_max_retries', tv.guardrail_max_retries)
    || jsonb_build_object('output_file', tv.output_file)
    || jsonb_build_object('create_directory', tv.create_directory)
  )
  || COALESCE(tv.payload_json, '{}'::jsonb)
  || COALESCE(asset_version.payload_json, '{}'::jsonb)
FROM task_versions tv
WHERE tv.version_id = asset_version.id;

UPDATE asset_versions asset_version
SET payload_json =
  jsonb_strip_nulls(
    jsonb_build_object('process', cv.process_type)
    || jsonb_build_object('manager_llm', NULLIF(cv.manager_llm_config_json, '{}'::jsonb))
    || jsonb_build_object('manager_agent_asset_id', cv.manager_agent_asset_id)
    || jsonb_build_object('function_calling_llm', NULLIF(cv.function_calling_llm_config_json, '{}'::jsonb))
    || jsonb_build_object('verbose', cv.is_verbose)
    || jsonb_build_object('planning', cv.planning)
    || jsonb_build_object('memory', cv.memory_enabled)
  )
  || COALESCE(cv.payload_json, '{}'::jsonb)
  || COALESCE(asset_version.payload_json, '{}'::jsonb)
FROM crew_versions cv
WHERE cv.version_id = asset_version.id;

ALTER TABLE crew_version_drafts
  DROP CONSTRAINT IF EXISTS crew_version_drafts_base_version_id_fkey;

ALTER TABLE crew_version_drafts
  ADD CONSTRAINT fk_crew_version_drafts_base_asset_version
  FOREIGN KEY (base_version_id) REFERENCES asset_versions(id) ON DELETE SET NULL;

ALTER TABLE task_input_preset_bindings
  DROP CONSTRAINT IF EXISTS uq_task_input_preset_bindings_task_version_preset;

ALTER TABLE task_input_preset_bindings
  DROP CONSTRAINT IF EXISTS task_input_preset_bindings_task_version_id_fkey;

DROP INDEX IF EXISTS ix_task_input_preset_bindings_task_version;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = 'task_input_preset_bindings'
      AND column_name = 'task_version_id'
  ) AND NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = 'task_input_preset_bindings'
      AND column_name = 'asset_version_id'
  ) THEN
    ALTER TABLE task_input_preset_bindings
      RENAME COLUMN task_version_id TO asset_version_id;
  END IF;
END $$;

ALTER TABLE task_input_preset_bindings
  ADD CONSTRAINT fk_task_input_preset_bindings_asset_version
  FOREIGN KEY (asset_version_id) REFERENCES asset_versions(id) ON DELETE CASCADE;

ALTER TABLE task_input_preset_bindings
  ADD CONSTRAINT uq_task_input_preset_bindings_asset_version_preset
  UNIQUE (asset_version_id, preset_id);

CREATE INDEX IF NOT EXISTS ix_task_input_preset_bindings_asset_version
  ON task_input_preset_bindings(asset_version_id, sort_order, created_at, id);

ALTER TABLE IF EXISTS flow_version_drafts
  DROP CONSTRAINT IF EXISTS flow_version_drafts_base_version_id_fkey;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_name = 'flow_version_drafts'
  ) AND NOT EXISTS (
    SELECT 1
    FROM information_schema.table_constraints
    WHERE table_name = 'flow_version_drafts'
      AND constraint_name = 'fk_flow_version_drafts_base_asset_version'
  ) THEN
    ALTER TABLE flow_version_drafts
      ADD CONSTRAINT fk_flow_version_drafts_base_asset_version
      FOREIGN KEY (base_version_id) REFERENCES asset_versions(id) ON DELETE SET NULL;
  END IF;
END $$;

ALTER TABLE IF EXISTS flow_runs
  DROP CONSTRAINT IF EXISTS flow_runs_flow_version_id_fkey;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_name = 'flow_runs'
  ) AND NOT EXISTS (
    SELECT 1
    FROM information_schema.table_constraints
    WHERE table_name = 'flow_runs'
      AND constraint_name = 'fk_flow_runs_flow_asset_version'
  ) THEN
    ALTER TABLE flow_runs
      ADD CONSTRAINT fk_flow_runs_flow_asset_version
      FOREIGN KEY (flow_version_id) REFERENCES asset_versions(id) ON DELETE CASCADE;
  END IF;
END $$;

DROP TABLE IF EXISTS agent_versions CASCADE;
DROP TABLE IF EXISTS task_versions CASCADE;
DROP TABLE IF EXISTS crew_versions CASCADE;
DROP TABLE IF EXISTS flow_versions CASCADE;
