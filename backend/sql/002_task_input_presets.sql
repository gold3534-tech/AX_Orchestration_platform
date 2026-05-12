CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS input_preset_definitions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  key TEXT NOT NULL,
  label TEXT NOT NULL,
  input_type TEXT NOT NULL,
  description TEXT,
  is_active BOOLEAN NOT NULL DEFAULT true,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_input_preset_definitions_key UNIQUE (key)
);

CREATE TABLE IF NOT EXISTS task_input_preset_bindings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_version_id UUID NOT NULL REFERENCES asset_versions(id) ON DELETE CASCADE,
  preset_id UUID NOT NULL REFERENCES input_preset_definitions(id) ON DELETE CASCADE,
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_required BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_task_input_preset_bindings_asset_version_preset UNIQUE (asset_version_id, preset_id)
);

CREATE INDEX IF NOT EXISTS ix_task_input_preset_bindings_asset_version
  ON task_input_preset_bindings(asset_version_id, sort_order, created_at, id);

CREATE INDEX IF NOT EXISTS ix_task_input_preset_bindings_preset_id
  ON task_input_preset_bindings(preset_id);

INSERT INTO input_preset_definitions (key, label, input_type, description, is_active, sort_order)
VALUES
  ('website_url', '웹 사이트', 'url', '분석할 웹사이트 주소', true, 1),
  ('keyword', '검색어', 'text', '핵심 검색어 또는 주제', true, 2),
  ('brand_name', '브랜드명', 'text', '콘텐츠에 반영할 브랜드 이름', true, 3),
  ('target_audience', '타겟 독자', 'text', '주요 독자 또는 고객군', true, 4)
ON CONFLICT (key) DO UPDATE SET
  label = EXCLUDED.label,
  input_type = EXCLUDED.input_type,
  description = EXCLUDED.description,
  is_active = EXCLUDED.is_active,
  sort_order = EXCLUDED.sort_order,
  updated_at = now();
