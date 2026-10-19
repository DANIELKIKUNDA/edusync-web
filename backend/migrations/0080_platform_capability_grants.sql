-- Équipe plateforme, lot 2026-10: individual platform capabilities (positive overrides), permanent or temporary.
--
-- EffectiveCapabilities(user) = UNION(capabilities of the user's ACTIVE platform roles) ∪ (active, valid individual grants)
-- An individual grant only supplements a platform role: without an active platform role it grants nothing.
-- The school-scoped rbac_exception_grants (0006) stay untouched: they belong to the school domain.
--
-- Guards in the database (the API enforces the same, the database is the last line):
--   * platform-scoped capabilities only;
--   * never a reserved capability (platform_reserved_capabilities: non-delegable);
--   * one active grant per (user, capability): a replay or a race cannot create two links;
--   * a temporary grant ends by itself (valid_until), no human intervention: it simply stops counting.
CREATE TABLE IF NOT EXISTS platform_capability_grants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id),
  capability_code varchar(128) NOT NULL REFERENCES capability_catalog(code),
  valid_from timestamptz NOT NULL DEFAULT now(),
  valid_until timestamptz,
  granted_by_user_id uuid NOT NULL REFERENCES users(id),
  reason text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  ended_at timestamptz,
  ended_by_user_id uuid REFERENCES users(id),
  end_reason text,
  end_kind varchar(16) CHECK (end_kind IN ('REVOKED','EXPIRED','ACCESS_REMOVED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  CHECK (valid_until IS NULL OR valid_until > valid_from),
  CHECK (length(trim(reason)) >= 5),
  CHECK (active OR ended_at IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_platform_capability_grants_active
  ON platform_capability_grants(user_id, capability_code) WHERE active;
CREATE INDEX IF NOT EXISTS idx_platform_capability_grants_user ON platform_capability_grants(user_id) WHERE active;

CREATE OR REPLACE FUNCTION platform_capability_grant_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM capability_catalog WHERE code = NEW.capability_code AND scope_types ? 'PLATFORM') THEN
    RAISE EXCEPTION 'Capacité individuelle : capacité plateforme uniquement (%).', NEW.capability_code USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.active AND EXISTS (SELECT 1 FROM platform_reserved_capabilities WHERE capability_code = NEW.capability_code) THEN
    RAISE EXCEPTION 'Capacité réservée : elle ne peut pas être attribuée individuellement (%).', NEW.capability_code USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_platform_capability_grant_guard ON platform_capability_grants;
CREATE TRIGGER trg_platform_capability_grant_guard BEFORE INSERT OR UPDATE ON platform_capability_grants
  FOR EACH ROW EXECUTE FUNCTION platform_capability_grant_guard();

ALTER TABLE platform_capability_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE platform_capability_grants FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_platform') THEN
    DROP POLICY IF EXISTS platform_capability_grants_platform ON platform_capability_grants;
    CREATE POLICY platform_capability_grants_platform ON platform_capability_grants FOR ALL TO edusync_platform USING (true) WITH CHECK (true);
    GRANT SELECT, INSERT, UPDATE ON platform_capability_grants TO edusync_platform;
  END IF;
END $$;

-- Naming (no business change): the descriptions of the two standard platform roles still said « Atelier Pro ».
UPDATE rbac_roles SET description = 'Propriétaire technique de la Plateforme EduSync : gouvernance complète de la plateforme et de son équipe.'
 WHERE code = 'MANAGER_SYSTEME' AND level = 'PLATFORM' AND kind = 'PLATFORM_STANDARD' AND description LIKE '%Atelier Pro%';
UPDATE rbac_roles SET description = 'Second rôle de la Plateforme EduSync, à privilèges limités, pour seconder le Manager Système.'
 WHERE code = 'COLLABORATEUR_PLATEFORME' AND level = 'PLATFORM' AND kind = 'PLATFORM_STANDARD' AND description LIKE '%Atelier Pro%';
