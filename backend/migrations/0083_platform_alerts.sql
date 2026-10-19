-- Alertes et incidents de la plateforme (lot 2026-10, « niveau plateforme terminé »).
-- platform_incidents : historique des incidents (un composant « Hors service »), ouverture, notification, résolution.
-- platform_alert_recipients : adresses supplémentaires d'astreinte, gérées par un Manager depuis État du service
-- (les Managers Système actifs reçoivent toujours les alertes). Aucune adresse n'est écrite dans le code.
CREATE TABLE IF NOT EXISTS platform_incidents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  component_key varchar(48) NOT NULL,
  component_label varchar(120) NOT NULL,
  severity varchar(16) NOT NULL DEFAULT 'critical' CHECK (severity IN ('critical','warning')),
  explain text NOT NULL DEFAULT '',
  opened_at timestamptz NOT NULL DEFAULT now(),
  notified_at timestamptz,
  resolved_at timestamptz,
  resolution_notified_at timestamptz,
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  CHECK (resolved_at IS NULL OR resolved_at >= opened_at)
);
CREATE UNIQUE INDEX IF NOT EXISTS platform_incidents_one_open ON platform_incidents(component_key) WHERE resolved_at IS NULL;
CREATE INDEX IF NOT EXISTS platform_incidents_opened ON platform_incidents(opened_at DESC);

CREATE TABLE IF NOT EXISTS platform_alert_recipients (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email varchar(254) NOT NULL CHECK (email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  label varchar(120),
  active boolean NOT NULL DEFAULT true,
  added_by_user_id uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  removed_at timestamptz,
  removed_by_user_id uuid REFERENCES users(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS platform_alert_recipients_active_email ON platform_alert_recipients(lower(email)) WHERE active;

ALTER TABLE platform_incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE platform_incidents FORCE ROW LEVEL SECURITY;
ALTER TABLE platform_alert_recipients ENABLE ROW LEVEL SECURITY;
ALTER TABLE platform_alert_recipients FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_platform') THEN
    DROP POLICY IF EXISTS platform_incidents_platform ON platform_incidents;
    CREATE POLICY platform_incidents_platform ON platform_incidents FOR ALL TO edusync_platform USING (true) WITH CHECK (true);
    GRANT SELECT, INSERT, UPDATE ON platform_incidents TO edusync_platform;
    DROP POLICY IF EXISTS platform_alert_recipients_platform ON platform_alert_recipients;
    CREATE POLICY platform_alert_recipients_platform ON platform_alert_recipients FOR ALL TO edusync_platform USING (true) WITH CHECK (true);
    GRANT SELECT, INSERT, UPDATE ON platform_alert_recipients TO edusync_platform;
  END IF;
END $$;
