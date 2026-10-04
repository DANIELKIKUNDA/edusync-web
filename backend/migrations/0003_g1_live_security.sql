-- EduSync WEB-0C — G1 live security, tenant isolation and IAM foundation
-- Roles/login credentials are provisioned by scripts/provision_database.py.
-- This migration makes RLS effective even for the table owner and defines explicit
-- policies for the tenant application role and the separate Atelier Pro role.

-- Schools themselves are tenant-scoped for school traffic. Atelier Pro can see all
-- schools only because it connects with the dedicated edusync_platform role.
ALTER TABLE schools ENABLE ROW LEVEL SECURITY;
ALTER TABLE schools FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS schools_tenant ON schools;
CREATE POLICY schools_tenant ON schools
  FOR ALL TO edusync_tenant
  USING (id = nullif(current_setting('app.current_school_id', true), '')::uuid)
  WITH CHECK (id = nullif(current_setting('app.current_school_id', true), '')::uuid);

DROP POLICY IF EXISTS schools_platform ON schools;
CREATE POLICY schools_platform ON schools
  FOR ALL TO edusync_platform
  USING (true) WITH CHECK (true);

-- Every existing school-scoped table is FORCE RLS. The platform policy is role-bound,
-- not controlled by a spoofable custom session variable.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'school_memberships','audit_events','outbox_events','notifications','devices',
    'sync_inbox','sync_cursors','idempotency_registry','sync_conflicts'
  ]
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
  END LOOP;
END $$;

-- Existing *_tenant policies from 0001/0002 continue to enforce school_id.
-- Dedicated platform policies are explicit and cannot be activated by edusync_tenant.
DROP POLICY IF EXISTS school_memberships_platform ON school_memberships;
CREATE POLICY school_memberships_platform ON school_memberships FOR ALL TO edusync_platform USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS audit_events_platform ON audit_events;
CREATE POLICY audit_events_platform ON audit_events FOR ALL TO edusync_platform USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS outbox_events_platform ON outbox_events;
CREATE POLICY outbox_events_platform ON outbox_events FOR ALL TO edusync_platform USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS notifications_platform ON notifications;
CREATE POLICY notifications_platform ON notifications FOR ALL TO edusync_platform USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS devices_platform ON devices;
CREATE POLICY devices_platform ON devices FOR ALL TO edusync_platform USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS sync_inbox_platform ON sync_inbox;
CREATE POLICY sync_inbox_platform ON sync_inbox FOR ALL TO edusync_platform USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS sync_cursors_platform ON sync_cursors;
CREATE POLICY sync_cursors_platform ON sync_cursors FOR ALL TO edusync_platform USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS idempotency_registry_platform ON idempotency_registry;
CREATE POLICY idempotency_registry_platform ON idempotency_registry FOR ALL TO edusync_platform USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS sync_conflicts_platform ON sync_conflicts;
CREATE POLICY sync_conflicts_platform ON sync_conflicts FOR ALL TO edusync_platform USING (true) WITH CHECK (true);

-- membership_roles has no school_id column, therefore isolation is derived through
-- the membership it references.
ALTER TABLE membership_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE membership_roles FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS membership_roles_tenant ON membership_roles;
CREATE POLICY membership_roles_tenant ON membership_roles
  FOR ALL TO edusync_tenant
  USING (EXISTS (
    SELECT 1 FROM school_memberships m
     WHERE m.id = membership_roles.membership_id
       AND m.school_id = nullif(current_setting('app.current_school_id', true), '')::uuid
  ))
  WITH CHECK (EXISTS (
    SELECT 1 FROM school_memberships m
     WHERE m.id = membership_roles.membership_id
       AND m.school_id = nullif(current_setting('app.current_school_id', true), '')::uuid
  ));
DROP POLICY IF EXISTS membership_roles_platform ON membership_roles;
CREATE POLICY membership_roles_platform ON membership_roles FOR ALL TO edusync_platform USING (true) WITH CHECK (true);

-- Users are global identities. School traffic receives SELECT only and an RLS policy
-- restricted to app.current_user_id; global IAM lookup uses the platform connection.
-- Platform access is still constrained by RLS for defence in depth.
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS users_platform ON users;
CREATE POLICY users_platform ON users FOR ALL TO edusync_platform USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS users_tenant_self ON users;
CREATE POLICY users_tenant_self ON users
  FOR SELECT TO edusync_tenant
  USING (id = nullif(current_setting('app.current_user_id', true), '')::uuid);

-- Stronger structural guards.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname='idempotency_scope_school_consistency'
  ) THEN
    ALTER TABLE idempotency_registry
      ADD CONSTRAINT idempotency_scope_school_consistency CHECK (
        (scope_key = 'platform' AND school_id IS NULL)
        OR (scope_key <> 'platform' AND school_id IS NOT NULL AND scope_key = school_id::text)
      ) NOT VALID;
  END IF;
END $$;
-- Existing pre-WEB-0C rows may be validated after migration review; fresh deployments
-- can validate immediately through provision_database.py.

CREATE INDEX IF NOT EXISTS idx_membership_roles_membership ON membership_roles(membership_id);
CREATE INDEX IF NOT EXISTS idx_school_memberships_user_school_active
  ON school_memberships(user_id, school_id) WHERE active;

-- SECURITY NOTE: no application role receives BYPASSRLS, SUPERUSER, CREATEDB or CREATEROLE.
