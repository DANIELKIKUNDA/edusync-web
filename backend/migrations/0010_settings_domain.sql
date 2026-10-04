-- EduSync Point 4A — Paramètres Web parity foundation (2026-09-12)
-- Preservation-first: port the certified Desktop settings concepts without a global configuration lock.

CREATE TABLE IF NOT EXISTS rdc_reference_sections (
  code varchar(32) PRIMARY KEY,
  label varchar(96) NOT NULL,
  sort_order integer NOT NULL
);
INSERT INTO rdc_reference_sections(code,label,sort_order) VALUES
 ('MATERNELLE','Maternelle',10),('PRIMAIRE','Primaire',20),('SECONDAIRE','Secondaire',30)
ON CONFLICT (code) DO UPDATE SET label=EXCLUDED.label,sort_order=EXCLUDED.sort_order;

CREATE TABLE IF NOT EXISTS rdc_reference_classes (
  code varchar(48) PRIMARY KEY,
  section_code varchar(32) NOT NULL REFERENCES rdc_reference_sections(code),
  label varchar(120) NOT NULL,
  sort_order integer NOT NULL
);
INSERT INTO rdc_reference_classes(code,section_code,label,sort_order) VALUES
 ('M1','MATERNELLE','1re maternelle',10),('M2','MATERNELLE','2e maternelle',20),('M3','MATERNELLE','3e maternelle',30),
 ('P1','PRIMAIRE','1re primaire',110),('P2','PRIMAIRE','2e primaire',120),('P3','PRIMAIRE','3e primaire',130),
 ('P4','PRIMAIRE','4e primaire',140),('P5','PRIMAIRE','5e primaire',150),('P6','PRIMAIRE','6e primaire',160),
 ('S7','SECONDAIRE','7e EB',210),('S8','SECONDAIRE','8e EB',220),
 ('H1','SECONDAIRE','1re Humanités',310),('H2','SECONDAIRE','2e Humanités',320),
 ('H3','SECONDAIRE','3e Humanités',330),('H4','SECONDAIRE','4e Humanités',340)
ON CONFLICT (code) DO UPDATE SET section_code=EXCLUDED.section_code,label=EXCLUDED.label,sort_order=EXCLUDED.sort_order;

CREATE TABLE IF NOT EXISTS rdc_reference_fee_types (
  code varchar(48) PRIMARY KEY,
  label varchar(140) NOT NULL,
  periodicity varchar(24) NOT NULL CHECK (periodicity IN ('ONE_TIME','MONTHLY','PERIODIC','OPTIONAL')),
  default_currency varchar(3) NOT NULL CHECK (default_currency IN ('CDF','USD')),
  sort_order integer NOT NULL
);
INSERT INTO rdc_reference_fee_types(code,label,periodicity,default_currency,sort_order) VALUES
 ('MINERVAL','Minerval','MONTHLY','CDF',10),
 ('INSCRIPTION','Frais d''inscription','ONE_TIME','CDF',20),
 ('REINSCRIPTION','Frais de réinscription','ONE_TIME','CDF',30),
 ('EXAMEN','Frais d''examens','PERIODIC','CDF',40),
 ('BULLETIN','Bulletin / documents scolaires','OPTIONAL','CDF',50)
ON CONFLICT (code) DO UPDATE SET label=EXCLUDED.label,periodicity=EXCLUDED.periodicity,default_currency=EXCLUDED.default_currency,sort_order=EXCLUDED.sort_order;

CREATE TABLE IF NOT EXISTS settings_bootstrap_state (
  school_id uuid PRIMARY KEY REFERENCES schools(id) ON DELETE CASCADE,
  provisioning_version varchar(32) NOT NULL DEFAULT 'POINT4A-V1',
  internal_notifications_enabled boolean NOT NULL DEFAULT true,
  external_sms_enabled boolean NOT NULL DEFAULT false,
  suggested_year_code varchar(32),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS academic_years (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  code varchar(32) NOT NULL,
  label varchar(96) NOT NULL,
  start_date date NOT NULL,
  end_date date NOT NULL,
  status varchar(16) NOT NULL DEFAULT 'PREPARED' CHECK (status IN ('PREPARED','ACTIVE','CLOSED','ARCHIVED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  UNIQUE(school_id,code),
  CHECK (end_date > start_date)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_academic_year_active_per_school ON academic_years(school_id) WHERE status='ACTIVE';

CREATE TABLE IF NOT EXISTS school_sections (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  code varchar(32) NOT NULL,
  label varchar(96) NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  UNIQUE(school_id,code)
);

CREATE TABLE IF NOT EXISTS school_options (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  section_id uuid NOT NULL REFERENCES school_sections(id) ON DELETE CASCADE,
  code varchar(48) NOT NULL,
  label varchar(120) NOT NULL,
  tariff_group_code varchar(48),
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  UNIQUE(school_id,code)
);

CREATE TABLE IF NOT EXISTS school_classes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  academic_year_id uuid NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
  section_id uuid NOT NULL REFERENCES school_sections(id),
  option_id uuid REFERENCES school_options(id),
  reference_code varchar(48),
  code varchar(64) NOT NULL,
  label varchar(140) NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  UNIQUE(school_id,academic_year_id,code)
);

CREATE TABLE IF NOT EXISTS fee_types (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  code varchar(48) NOT NULL,
  label varchar(140) NOT NULL,
  periodicity varchar(24) NOT NULL CHECK (periodicity IN ('ONE_TIME','MONTHLY','PERIODIC','OPTIONAL')),
  default_currency varchar(3) NOT NULL CHECK (default_currency IN ('CDF','USD')),
  regulatory boolean NOT NULL DEFAULT false,
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  UNIQUE(school_id,code)
);

CREATE TABLE IF NOT EXISTS tariffs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  academic_year_id uuid NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
  fee_type_id uuid NOT NULL REFERENCES fee_types(id),
  class_id uuid REFERENCES school_classes(id) ON DELETE CASCADE,
  section_id uuid REFERENCES school_sections(id),
  option_id uuid REFERENCES school_options(id),
  currency varchar(3) NOT NULL CHECK (currency IN ('CDF','USD')),
  amount numeric(18,2) NOT NULL CHECK (amount > 0),
  billing_months jsonb NOT NULL DEFAULT '[]'::jsonb,
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  CHECK (class_id IS NOT NULL OR section_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_tariffs_lookup ON tariffs(school_id,academic_year_id,fee_type_id,enabled);

CREATE TABLE IF NOT EXISTS school_policy_documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  kind varchar(32) NOT NULL CHECK (kind IN ('PAYMENT','ENROLLMENT','BENEFITS','DOCUMENTS','BACKUP','COMMUNICATIONS')),
  status varchar(16) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('DRAFT','ACTIVE','ARCHIVED')),
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  effective_from date,
  effective_until date,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  UNIQUE(school_id,kind),
  CHECK (effective_until IS NULL OR effective_from IS NULL OR effective_until >= effective_from)
);

CREATE TABLE IF NOT EXISTS contribution_types (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  code varchar(48) NOT NULL,
  label varchar(140) NOT NULL,
  unit varchar(48) NOT NULL DEFAULT 'unité',
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  UNIQUE(school_id,code)
);

CREATE TABLE IF NOT EXISTS school_products (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  code varchar(48) NOT NULL,
  label varchar(160) NOT NULL,
  currency varchar(3) NOT NULL CHECK (currency IN ('CDF','USD')),
  unit_price numeric(18,2) NOT NULL CHECK (unit_price > 0),
  stock_tracking boolean NOT NULL DEFAULT false,
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  UNIQUE(school_id,code)
);

-- Safe defaults: no tariffs/classes/real sections are invented. Only non-financial policies are bootstrapped.
CREATE OR REPLACE FUNCTION provision_school_settings_defaults() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE suggested text;
BEGIN
  suggested := extract(year from CURRENT_DATE)::int || '-' || (extract(year from CURRENT_DATE)::int + 1);
  INSERT INTO settings_bootstrap_state(school_id,suggested_year_code) VALUES (NEW.id,suggested)
  ON CONFLICT (school_id) DO NOTHING;
  INSERT INTO school_policy_documents(school_id,kind,payload) VALUES
    (NEW.id,'PAYMENT','{"allow_partial_payments":true,"currencies":["CDF","USD"],"implicit_currency_conversion":false}'::jsonb),
    (NEW.id,'DOCUMENTS','{"receipt_numbering":"SERVER_SEQUENCE","document_history":true}'::jsonb),
    (NEW.id,'BACKUP','{"enabled":true,"offsite_required":true}'::jsonb),
    (NEW.id,'COMMUNICATIONS','{"internal_notifications":true,"external_sms_enabled":false}'::jsonb)
  ON CONFLICT (school_id,kind) DO NOTHING;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_provision_school_settings_defaults ON schools;
CREATE TRIGGER trg_provision_school_settings_defaults AFTER INSERT ON schools
FOR EACH ROW EXECUTE FUNCTION provision_school_settings_defaults();

-- Backfill schools created before Point 4A without inventing business decisions.
INSERT INTO settings_bootstrap_state(school_id,suggested_year_code)
SELECT id, extract(year from CURRENT_DATE)::int || '-' || (extract(year from CURRENT_DATE)::int + 1) FROM schools
ON CONFLICT (school_id) DO NOTHING;
INSERT INTO school_policy_documents(school_id,kind,payload)
SELECT s.id,v.kind,v.payload FROM schools s CROSS JOIN (VALUES
 ('PAYMENT','{"allow_partial_payments":true,"currencies":["CDF","USD"],"implicit_currency_conversion":false}'::jsonb),
 ('DOCUMENTS','{"receipt_numbering":"SERVER_SEQUENCE","document_history":true}'::jsonb),
 ('BACKUP','{"enabled":true,"offsite_required":true}'::jsonb),
 ('COMMUNICATIONS','{"internal_notifications":true,"external_sms_enabled":false}'::jsonb)
) AS v(kind,payload)
ON CONFLICT (school_id,kind) DO NOTHING;

-- Tenant isolation. Reference catalogs are read-only shared catalogs.
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['settings_bootstrap_state','academic_years','school_sections','school_options','school_classes','fee_types','tariffs','school_policy_documents','contribution_types','school_products']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I','tenant_'||t,t);
    EXECUTE format('CREATE POLICY %I ON %I FOR ALL TO edusync_tenant USING (school_id = nullif(current_setting(''app.current_school_id'',true),'''')::uuid) WITH CHECK (school_id = nullif(current_setting(''app.current_school_id'',true),'''')::uuid)','tenant_'||t,t);
  END LOOP;
END $$;

GRANT SELECT ON rdc_reference_sections,rdc_reference_classes,rdc_reference_fee_types TO edusync_tenant;
GRANT SELECT,INSERT,UPDATE,DELETE ON settings_bootstrap_state,academic_years,school_sections,school_options,school_classes,fee_types,tariffs,school_policy_documents,contribution_types,school_products TO edusync_tenant;

-- Version bump helper for optimistic concurrency on settings rows.
CREATE OR REPLACE FUNCTION touch_settings_row() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  NEW.version := OLD.version + 1;
  RETURN NEW;
END $$;
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['settings_bootstrap_state','academic_years','school_sections','school_options','school_classes','fee_types','tariffs','school_policy_documents','contribution_types','school_products']
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS trg_touch_%I ON %I',t,t);
    EXECUTE format('CREATE TRIGGER trg_touch_%I BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION touch_settings_row()',t,t);
  END LOOP;
END $$;

-- Atelier Pro may only seed the non-business bootstrap rows during school creation.
-- It receives no SELECT/UPDATE/DELETE policy on these tenant settings tables.
DROP POLICY IF EXISTS settings_bootstrap_state_platform_insert ON settings_bootstrap_state;
CREATE POLICY settings_bootstrap_state_platform_insert ON settings_bootstrap_state
  FOR INSERT TO edusync_platform WITH CHECK (true);
DROP POLICY IF EXISTS school_policy_documents_platform_insert ON school_policy_documents;
CREATE POLICY school_policy_documents_platform_insert ON school_policy_documents
  FOR INSERT TO edusync_platform WITH CHECK (true);
GRANT INSERT ON settings_bootstrap_state,school_policy_documents TO edusync_platform;

-- Exact-scope duplicate guard. PostgreSQL 15+ NULLS NOT DISTINCT prevents two active tariffs
-- for the same year/fee/scope/currency even when optional scope columns are NULL.
CREATE UNIQUE INDEX IF NOT EXISTS uq_tariffs_active_exact_scope
  ON tariffs (school_id,academic_year_id,fee_type_id,class_id,section_id,option_id,currency) NULLS NOT DISTINCT
  WHERE enabled;
