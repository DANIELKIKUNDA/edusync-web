-- Vigie EduSync: incidents métier durables, séparant l'état mesuré de la réponse humaine.
-- Les destinataires ne sont jamais attachés à un nom de rôle : le moteur route par capacité et périmètre RBAC.
CREATE TABLE IF NOT EXISTS supervision_incidents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  rule_code varchar(80) NOT NULL,
  fingerprint varchar(180) NOT NULL,
  domain varchar(32) NOT NULL CHECK (domain IN ('FINANCE','CASH','SCHOOLING','ACADEMIC','DISCIPLINE','PERSONNEL','STEWARDSHIP','CONFIGURATION','TECHNICAL')),
  severity varchar(16) NOT NULL CHECK (severity IN ('INFO','WARNING','CRITICAL')),
  condition_status varchar(16) NOT NULL DEFAULT 'OPEN' CHECK (condition_status IN ('OPEN','RESOLVED')),
  response_status varchar(24) NOT NULL DEFAULT 'NEW' CHECK (response_status IN ('NEW','ACKNOWLEDGED','IN_PROGRESS','CLOSED')),
  title varchar(180) NOT NULL,
  summary text NOT NULL,
  explanation text NOT NULL DEFAULT '',
  recommendation text NOT NULL DEFAULT '',
  metric_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  target_path varchar(200),
  required_capability varchar(160) NOT NULL REFERENCES capability_catalog(code),
  scope_type varchar(24),
  scope_value varchar(160),
  opened_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  last_notified_at timestamptz,
  reminder_count integer NOT NULL DEFAULT 0 CHECK (reminder_count >= 0),
  acknowledged_at timestamptz,
  acknowledged_by uuid REFERENCES users(id),
  resolved_at timestamptz,
  closed_at timestamptz,
  closed_by uuid REFERENCES users(id),
  CHECK (target_path IS NULL OR (target_path ~ '^/[A-Za-z0-9/_?=&.-]*$' AND target_path !~ '^//')),
  CHECK (resolved_at IS NULL OR resolved_at >= opened_at)
);
CREATE UNIQUE INDEX IF NOT EXISTS supervision_one_open_incident
  ON supervision_incidents(school_id, rule_code, fingerprint) WHERE condition_status='OPEN';
CREATE INDEX IF NOT EXISTS supervision_school_state
  ON supervision_incidents(school_id, condition_status, response_status, severity, last_seen_at DESC);
CREATE INDEX IF NOT EXISTS supervision_scope
  ON supervision_incidents(school_id, scope_type, scope_value) WHERE condition_status='OPEN';

ALTER TABLE supervision_incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE supervision_incidents FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_tenant') THEN
    DROP POLICY IF EXISTS supervision_incidents_tenant ON supervision_incidents;
    CREATE POLICY supervision_incidents_tenant ON supervision_incidents FOR ALL TO edusync_tenant
      USING (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid)
      WITH CHECK (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid);
    GRANT SELECT, INSERT, UPDATE ON supervision_incidents TO edusync_tenant;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_platform') THEN
    DROP POLICY IF EXISTS supervision_incidents_platform ON supervision_incidents;
    CREATE POLICY supervision_incidents_platform ON supervision_incidents FOR ALL TO edusync_platform USING (true) WITH CHECK (true);
    GRANT SELECT ON supervision_incidents TO edusync_platform;
  END IF;
END $$;
