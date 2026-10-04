-- EduSync WEB-0B — idempotence, concurrence optimiste et conflits offline
-- Cette migration complète 0001_foundation.sql sans porter encore les domaines métier Desktop.

ALTER TABLE schools ADD COLUMN IF NOT EXISTS version bigint NOT NULL DEFAULT 1;
ALTER TABLE users ADD COLUMN IF NOT EXISTS version bigint NOT NULL DEFAULT 1;
ALTER TABLE school_memberships ADD COLUMN IF NOT EXISTS version bigint NOT NULL DEFAULT 1;

-- Registre d'idempotence. scope_key vaut 'platform' pour Atelier Pro ou le school_id texte pour un tenant.
CREATE TABLE IF NOT EXISTS idempotency_registry (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scope_key varchar(96) NOT NULL,
  school_id uuid REFERENCES schools(id),
  actor_user_id uuid REFERENCES users(id),
  idempotency_key varchar(180) NOT NULL,
  request_hash char(64) NOT NULL,
  operation varchar(128) NOT NULL,
  status varchar(24) NOT NULL CHECK (status IN ('PROCESSING','SUCCEEDED','FAILED')),
  response_status integer,
  response_json jsonb,
  error_code varchar(96),
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  expires_at timestamptz,
  UNIQUE (scope_key, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_idempotency_school_created
  ON idempotency_registry(school_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_idempotency_processing
  ON idempotency_registry(status, created_at)
  WHERE status = 'PROCESSING';

-- Conflits issus de synchronisation/offline ou d'une version obsolète.
CREATE TABLE IF NOT EXISTS sync_conflicts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id),
  device_id uuid REFERENCES devices(id),
  actor_user_id uuid REFERENCES users(id),
  operation_id uuid,
  idempotency_key varchar(180),
  aggregate_type varchar(96) NOT NULL,
  aggregate_id uuid NOT NULL,
  expected_version bigint,
  actual_version bigint,
  client_payload jsonb,
  server_snapshot jsonb,
  policy varchar(64) NOT NULL DEFAULT 'MANUAL_REVIEW',
  status varchar(24) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','RESOLVED','DISMISSED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz,
  resolved_by uuid REFERENCES users(id),
  resolution_note text
);

CREATE INDEX IF NOT EXISTS idx_sync_conflicts_school_open
  ON sync_conflicts(school_id, created_at DESC)
  WHERE status = 'OPEN';

-- La déduplication de l'outbox empêche un même événement logique d'être publié deux fois
-- lorsqu'une commande applicative est retentée.
ALTER TABLE outbox_events ADD COLUMN IF NOT EXISTS deduplication_key varchar(180);
CREATE UNIQUE INDEX IF NOT EXISTS uq_outbox_scope_dedup
  ON outbox_events(COALESCE(school_id::text, 'platform'), deduplication_key)
  WHERE deduplication_key IS NOT NULL;

-- L'inbox existante garantit déjà UNIQUE(school_id,idempotency_key).
-- Ajout d'un identifiant d'opération client unique par école lorsqu'il est fourni.
ALTER TABLE sync_inbox ADD COLUMN IF NOT EXISTS operation_id uuid;
CREATE UNIQUE INDEX IF NOT EXISTS uq_sync_inbox_school_operation
  ON sync_inbox(school_id, operation_id)
  WHERE operation_id IS NOT NULL;

-- RLS des nouvelles tables tenant. Les entrées platform de idempotency_registry sont volontairement
-- invisibles au rôle d'application scolaire; Atelier Pro utilisera un rôle DB plateforme séparé.
ALTER TABLE idempotency_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_conflicts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS idempotency_registry_tenant ON idempotency_registry;
CREATE POLICY idempotency_registry_tenant ON idempotency_registry
  USING (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid)
  WITH CHECK (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid);

DROP POLICY IF EXISTS sync_conflicts_tenant ON sync_conflicts;
CREATE POLICY sync_conflicts_tenant ON sync_conflicts
  USING (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid)
  WITH CHECK (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid);

-- Fonction utilitaire de concurrence optimiste. Les repositories peuvent également utiliser
-- UPDATE ... WHERE id=:id AND version=:expected_version RETURNING version.
CREATE OR REPLACE FUNCTION bump_version_if_current(
  p_table regclass,
  p_id uuid,
  p_expected bigint
) RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE
  v_new bigint;
BEGIN
  EXECUTE format('UPDATE %s SET version = version + 1, updated_at = now() WHERE id = $1 AND version = $2 RETURNING version', p_table)
    INTO v_new USING p_id, p_expected;
  IF v_new IS NULL THEN
    RAISE EXCEPTION 'optimistic_concurrency_conflict';
  END IF;
  RETURN v_new;
END;
$$;
