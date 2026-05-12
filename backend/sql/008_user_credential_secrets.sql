CREATE TABLE IF NOT EXISTS credential_secrets (
  credential_id UUID PRIMARY KEY REFERENCES credentials(id) ON DELETE CASCADE,
  encrypted_secret_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  encryption_key_version TEXT NOT NULL DEFAULT 'v1',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

WITH ranked_active_credentials AS (
  SELECT
    id,
    ROW_NUMBER() OVER (
      PARTITION BY owner_user_id, provider
      ORDER BY created_at DESC, updated_at DESC, id DESC
    ) AS active_rank
  FROM credentials
  WHERE status = 'active'
    AND owner_type = 'user'
    AND workspace_id IS NULL
    AND owner_user_id IS NOT NULL
)
UPDATE credentials
SET
  status = 'revoked',
  updated_at = now()
FROM ranked_active_credentials
WHERE credentials.id = ranked_active_credentials.id
  AND ranked_active_credentials.active_rank > 1;

DROP INDEX IF EXISTS ix_credentials_active_user_provider;

CREATE UNIQUE INDEX IF NOT EXISTS ix_credentials_active_user_provider
  ON credentials(owner_user_id, provider)
  WHERE status = 'active'
    AND owner_type = 'user'
    AND workspace_id IS NULL;
