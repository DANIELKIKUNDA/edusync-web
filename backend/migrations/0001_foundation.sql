-- EduSync WEB-0A — PostgreSQL foundation
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE IF NOT EXISTS schools (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code varchar(32) NOT NULL UNIQUE,
  name varchar(160) NOT NULL,
  status varchar(16) NOT NULL CHECK (status IN ('ACTIVE','SUSPENDED','DISABLED')) DEFAULT 'ACTIVE',
  logo_url text,
  email text,
  phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email citext UNIQUE,
  full_name varchar(180) NOT NULL,
  password_hash text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  is_platform_admin boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS school_memberships (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id),
  user_id uuid NOT NULL REFERENCES users(id),
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (school_id, user_id)
);

CREATE TABLE IF NOT EXISTS roles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code varchar(64) NOT NULL UNIQUE,
  label varchar(128) NOT NULL,
  system_role boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS permissions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code varchar(96) NOT NULL UNIQUE,
  label varchar(160) NOT NULL
);

CREATE TABLE IF NOT EXISTS role_permissions (
  role_id uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  permission_id uuid NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
  PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS membership_roles (
  membership_id uuid NOT NULL REFERENCES school_memberships(id) ON DELETE CASCADE,
  role_id uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  PRIMARY KEY (membership_id, role_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  occurred_at timestamptz NOT NULL DEFAULT now(),
  school_id uuid REFERENCES schools(id),
  actor_user_id uuid REFERENCES users(id),
  membership_id uuid REFERENCES school_memberships(id),
  action varchar(96) NOT NULL,
  entity_type varchar(96) NOT NULL,
  entity_id uuid,
  source varchar(24) NOT NULL CHECK (source IN ('WEB','OFFLINE','SYNC','SYSTEM','IMPORT','MIGRATION')),
  result varchar(24) NOT NULL CHECK (result IN ('SUCCESS','REJECTED','FAILED')) DEFAULT 'SUCCESS',
  old_json jsonb,
  new_json jsonb,
  reason text,
  device_id uuid,
  correlation_id uuid,
  causation_id uuid,
  idempotency_key varchar(160)
);

CREATE TABLE IF NOT EXISTS outbox_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid REFERENCES schools(id),
  event_type varchar(128) NOT NULL,
  aggregate_type varchar(96) NOT NULL,
  aggregate_id uuid NOT NULL,
  payload jsonb NOT NULL,
  correlation_id uuid,
  causation_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz,
  attempts integer NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS notifications (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid REFERENCES schools(id),
  user_id uuid NOT NULL REFERENCES users(id),
  category varchar(64) NOT NULL DEFAULT 'GENERAL',
  title varchar(180) NOT NULL,
  body text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  read_at timestamptz
);

CREATE TABLE IF NOT EXISTS devices (
  id uuid PRIMARY KEY,
  school_id uuid NOT NULL REFERENCES schools(id),
  user_id uuid NOT NULL REFERENCES users(id),
  label varchar(160),
  platform varchar(40),
  last_seen_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sync_inbox (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id),
  device_id uuid NOT NULL REFERENCES devices(id),
  idempotency_key varchar(180) NOT NULL,
  operation_type varchar(128) NOT NULL,
  aggregate_type varchar(96) NOT NULL,
  aggregate_id uuid NOT NULL,
  payload jsonb NOT NULL,
  base_version bigint,
  status varchar(24) NOT NULL DEFAULT 'RECEIVED',
  received_at timestamptz NOT NULL DEFAULT now(),
  processed_at timestamptz,
  UNIQUE (school_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS sync_cursors (
  school_id uuid NOT NULL REFERENCES schools(id),
  device_id uuid NOT NULL REFERENCES devices(id),
  stream varchar(96) NOT NULL,
  cursor_value bigint NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (school_id, device_id, stream)
);

-- append-only audit at database level
CREATE OR REPLACE FUNCTION forbid_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_events is append-only';
END;
$$;
DROP TRIGGER IF EXISTS trg_audit_no_update ON audit_events;
CREATE TRIGGER trg_audit_no_update BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION forbid_audit_mutation();

-- Seed permissions / roles. The exact set will expand during domain ports.
INSERT INTO roles(code,label) VALUES
 ('SCHOOL_ADMIN','Administrateur école'),('DIRECTION','Direction'),('CAISSIER','Caissier'),
 ('SECRETARIAT','Secrétariat'),('INTENDANT','Intendant')
ON CONFLICT (code) DO NOTHING;

INSERT INTO permissions(code,label) VALUES
 ('school.manage','Gérer l’école'),('users.manage','Gérer les utilisateurs'),
 ('configuration.manage','Gérer les paramètres'),('audit.read','Consulter l’audit'),
 ('schooling.manage','Gérer la scolarité'),('finance.collect','Encaisser'),
 ('cash.manage','Gérer la caisse'),('receipts.reprint','Réimprimer les reçus'),
 ('stewardship.manage','Gérer l’intendance'),('stock.manage','Gérer les stocks'),
 ('suppliers.manage','Gérer les fournisseurs')
ON CONFLICT (code) DO NOTHING;



-- Default permission mapping. Roles remain permission bundles, never hard-coded business branches.
INSERT INTO role_permissions(role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p ON (
  (r.code='SCHOOL_ADMIN') OR
  (r.code='DIRECTION' AND p.code IN ('audit.read')) OR
  (r.code='CAISSIER' AND p.code IN ('finance.collect','cash.manage','receipts.reprint')) OR
  (r.code='SECRETARIAT' AND p.code IN ('schooling.manage')) OR
  (r.code='INTENDANT' AND p.code IN ('stewardship.manage','stock.manage','suppliers.manage'))
)
ON CONFLICT DO NOTHING;

-- RLS: every tenant table is protected by school_id.
ALTER TABLE school_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbox_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_inbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_cursors ENABLE ROW LEVEL SECURITY;

CREATE POLICY school_memberships_tenant ON school_memberships
  USING (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid)
  WITH CHECK (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid);
CREATE POLICY audit_events_tenant ON audit_events
  USING (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid)
  WITH CHECK (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid);
CREATE POLICY outbox_events_tenant ON outbox_events
  USING (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid)
  WITH CHECK (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid);
CREATE POLICY notifications_tenant ON notifications
  USING (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid)
  WITH CHECK (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid);
CREATE POLICY devices_tenant ON devices
  USING (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid)
  WITH CHECK (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid);
CREATE POLICY sync_inbox_tenant ON sync_inbox
  USING (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid)
  WITH CHECK (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid);
CREATE POLICY sync_cursors_tenant ON sync_cursors
  USING (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid)
  WITH CHECK (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid);

-- Prevent accidental cross-tenant queries by application role unless the request sets the tenant.
-- Platform administration uses a separate privileged DB role in production; it must never be reused for school traffic.
