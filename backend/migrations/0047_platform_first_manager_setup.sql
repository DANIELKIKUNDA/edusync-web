-- Local closure 2026-10: first Manager Système from the login page of an empty installation.
-- The singleton row is the irreversible lock: once a first manager exists (created by the page or by
-- scripts/bootstrap_platform_admin.py), public setup is closed forever, even if that account is later
-- deactivated. Recovery then goes through the operator script, never through the public page.
CREATE TABLE IF NOT EXISTS platform_setup_completion (
 singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
 completed_at timestamptz NOT NULL DEFAULT now(),
 manager_user_id uuid NOT NULL REFERENCES users(id),
 method varchar(32) NOT NULL CHECK (method IN ('SETUP_PAGE','OPERATOR_SCRIPT','EXISTING_INSTALLATION'))
);
-- Installations that already have an active platform manager are closed immediately.
INSERT INTO platform_setup_completion(singleton,manager_user_id,method)
SELECT true,a.user_id,'EXISTING_INSTALLATION'
  FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id
 WHERE r.code='MANAGER_SYSTEME' AND a.school_id IS NULL
 ORDER BY a.valid_from LIMIT 1
ON CONFLICT (singleton) DO NOTHING;
GRANT SELECT, INSERT ON platform_setup_completion TO edusync_platform;
REVOKE UPDATE, DELETE ON platform_setup_completion FROM edusync_platform, edusync_tenant;
