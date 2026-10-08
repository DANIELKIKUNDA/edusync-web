-- N1 certification 2026-10: platform role governance (PLATFORM_CUSTOM) and platform account status.
-- Rules enforced here (defence in depth; the API enforces them too):
--  * a PLATFORM_CUSTOM role is global (school_id NULL) and never visible to the tenant role (existing RLS);
--  * a PLATFORM role can only contain capabilities whose scope is PLATFORM: no implicit SCHOOL capability;
--  * reserved capabilities (team governance) can never be placed in a PLATFORM_CUSTOM role.

DO $$
DECLARE c record;
BEGIN
  FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='rbac_roles'::regclass AND contype='c'
           AND (pg_get_constraintdef(oid) LIKE '%PLATFORM_STANDARD%') LOOP
    EXECUTE format('ALTER TABLE rbac_roles DROP CONSTRAINT %I', c.conname);
  END LOOP;
END $$;

ALTER TABLE rbac_roles ADD CONSTRAINT rbac_roles_kind_check
  CHECK (kind IN ('PLATFORM_STANDARD','PLATFORM_CUSTOM','SCHOOL_STANDARD','SCHOOL_CUSTOM'));
ALTER TABLE rbac_roles ADD CONSTRAINT rbac_roles_level_kind_scope_check CHECK (
    (level='PLATFORM' AND kind IN ('PLATFORM_STANDARD','PLATFORM_CUSTOM') AND school_id IS NULL)
    OR (level='SCHOOL' AND kind='SCHOOL_STANDARD' AND school_id IS NULL)
    OR (level='SCHOOL' AND kind='SCHOOL_CUSTOM' AND school_id IS NOT NULL));

-- One code space for every platform role, standard or custom.
CREATE UNIQUE INDEX IF NOT EXISTS uq_rbac_platform_any_code ON rbac_roles(code) WHERE level='PLATFORM';

ALTER TABLE rbac_roles ADD COLUMN IF NOT EXISTS archived_at timestamptz;
ALTER TABLE rbac_roles ADD COLUMN IF NOT EXISTS cloned_from_role_id uuid REFERENCES rbac_roles(id);

CREATE TABLE IF NOT EXISTS platform_reserved_capabilities (
  capability_code varchar(128) PRIMARY KEY REFERENCES capability_catalog(code),
  reason text NOT NULL
);
INSERT INTO platform_reserved_capabilities(capability_code, reason) VALUES
  ('platform.collaborators.manage', 'Gouvernance de l’équipe plateforme (comptes, rôles, attributions) : réservée au Manager système')
ON CONFLICT (capability_code) DO NOTHING;

CREATE OR REPLACE FUNCTION rbac_platform_role_capability_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r record; scopes jsonb;
BEGIN
  SELECT level, kind INTO r FROM rbac_roles WHERE id = NEW.role_id;
  SELECT scope_types INTO scopes FROM capability_catalog WHERE code = NEW.capability_code;
  IF r.level = 'PLATFORM' AND NOT (coalesce(scopes, '[]'::jsonb) ? 'PLATFORM') THEN
    RAISE EXCEPTION 'Un rôle plateforme ne peut contenir que des capacités plateforme (%).', NEW.capability_code
      USING ERRCODE = 'check_violation';
  END IF;
  IF r.level = 'SCHOOL' AND (coalesce(scopes, '[]'::jsonb) ? 'PLATFORM') AND NOT (scopes ? 'SCHOOL') THEN
    RAISE EXCEPTION 'Un rôle école ne peut pas contenir de capacité plateforme (%).', NEW.capability_code
      USING ERRCODE = 'check_violation';
  END IF;
  IF r.kind = 'PLATFORM_CUSTOM' AND EXISTS (SELECT 1 FROM platform_reserved_capabilities WHERE capability_code = NEW.capability_code) THEN
    RAISE EXCEPTION 'Capacité réservée : elle ne peut pas être déléguée dans un rôle personnalisé (%).', NEW.capability_code
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_rbac_platform_role_capability_guard ON rbac_role_capabilities;
CREATE TRIGGER trg_rbac_platform_role_capability_guard BEFORE INSERT OR UPDATE ON rbac_role_capabilities
  FOR EACH ROW EXECUTE FUNCTION rbac_platform_role_capability_guard();

-- Platform account status: suspending a platform account is distinct from its roles (reactivation restores them).
CREATE TABLE IF NOT EXISTS platform_account_status (
  user_id uuid PRIMARY KEY REFERENCES users(id),
  status varchar(16) NOT NULL CHECK (status IN ('ACTIVE','SUSPENDED')),
  reason text NOT NULL DEFAULT '',
  changed_by_user_id uuid REFERENCES users(id),
  changed_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1
);
ALTER TABLE platform_account_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE platform_account_status FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_platform') THEN
    DROP POLICY IF EXISTS platform_account_status_platform ON platform_account_status;
    CREATE POLICY platform_account_status_platform ON platform_account_status FOR ALL TO edusync_platform USING (true) WITH CHECK (true);
  END IF;
END $$;
