-- EduSync Point 4B — Personnel Web deep port (2026-09-12)
-- Preservation-first: identité, catégorie, fonction, périmètre, titulariat,
-- affectations, sortie historisée, accès lié et lien enfant-personnel remain distinct.

CREATE TABLE IF NOT EXISTS staff_members (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  employee_no varchar(48) NOT NULL,
  last_name varchar(120) NOT NULL,
  first_name varchar(120),
  middle_name varchar(120),
  gender varchar(16) CHECK (gender IS NULL OR gender IN ('M','F','X')),
  birth_date date,
  phone varchar(48),
  email citext,
  address text,
  category varchar(32) NOT NULL DEFAULT 'AUTRE' CHECK (category IN ('ENSEIGNANT','ADMINISTRATIF','OUVRIER','AUTRE')),
  qualification varchar(160),
  specialty varchar(160),
  hire_date date,
  status varchar(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','SUSPENDED','INACTIVE','LEFT')),
  exit_date date,
  exit_reason text,
  photo_url text,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  UNIQUE(school_id, employee_no),
  CHECK (exit_date IS NULL OR hire_date IS NULL OR exit_date >= hire_date),
  CHECK ((status='LEFT' AND exit_date IS NOT NULL) OR status<>'LEFT')
);
CREATE INDEX IF NOT EXISTS idx_staff_members_school_status ON staff_members(school_id,status);
CREATE INDEX IF NOT EXISTS idx_staff_members_school_category ON staff_members(school_id,category);
CREATE INDEX IF NOT EXISTS idx_staff_members_search ON staff_members(school_id,last_name,first_name,employee_no);

CREATE TABLE IF NOT EXISTS staff_functions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  code varchar(64) NOT NULL,
  label varchar(160) NOT NULL,
  category varchar(32) NOT NULL DEFAULT 'AUTRE' CHECK (category IN ('ENSEIGNEMENT','DIRECTION_PEDAGOGIQUE','ADMINISTRATION','FINANCE','INTENDANCE','SUPPORT','OUVRIER','AUTRE')),
  enabled boolean NOT NULL DEFAULT true,
  sort_order integer NOT NULL DEFAULT 100,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  UNIQUE(school_id,code)
);

CREATE TABLE IF NOT EXISTS staff_assignments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  staff_id uuid NOT NULL REFERENCES staff_members(id) ON DELETE CASCADE,
  function_id uuid NOT NULL REFERENCES staff_functions(id),
  scope_type varchar(16) NOT NULL DEFAULT 'SCHOOL' CHECK (scope_type IN ('SCHOOL','SECTION','CLASS')),
  scope_value varchar(96),
  section_id uuid REFERENCES school_sections(id),
  class_id uuid REFERENCES school_classes(id),
  is_primary boolean NOT NULL DEFAULT false,
  is_titular boolean NOT NULL DEFAULT false,
  titular_class_id uuid REFERENCES school_classes(id),
  start_date date NOT NULL DEFAULT CURRENT_DATE,
  end_date date,
  end_reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  CHECK (end_date IS NULL OR end_date >= start_date),
  CHECK ((scope_type='SCHOOL' AND scope_value IS NULL AND section_id IS NULL AND class_id IS NULL)
      OR (scope_type='SECTION' AND scope_value IS NOT NULL AND section_id IS NOT NULL AND class_id IS NULL)
      OR (scope_type='CLASS' AND scope_value IS NOT NULL AND class_id IS NOT NULL)),
  CHECK ((is_titular=false AND titular_class_id IS NULL) OR (is_titular=true AND titular_class_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_staff_assignments_staff_open ON staff_assignments(school_id,staff_id) WHERE end_date IS NULL;
CREATE INDEX IF NOT EXISTS idx_staff_assignments_scope ON staff_assignments(school_id,scope_type,scope_value) WHERE end_date IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_staff_assignment_open_exact
  ON staff_assignments(school_id,staff_id,function_id,scope_type,scope_value) NULLS NOT DISTINCT WHERE end_date IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_staff_one_primary_open
  ON staff_assignments(school_id,staff_id) WHERE end_date IS NULL AND is_primary;

CREATE TABLE IF NOT EXISTS staff_status_history (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  staff_id uuid NOT NULL REFERENCES staff_members(id) ON DELETE CASCADE,
  from_status varchar(20),
  to_status varchar(20) NOT NULL CHECK (to_status IN ('ACTIVE','SUSPENDED','INACTIVE','LEFT')),
  effective_date date NOT NULL,
  reason text,
  actor_user_id uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_staff_status_history_staff ON staff_status_history(school_id,staff_id,created_at DESC);

CREATE TABLE IF NOT EXISTS staff_access_links (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  staff_id uuid NOT NULL REFERENCES staff_members(id) ON DELETE CASCADE,
  membership_id uuid NOT NULL REFERENCES school_memberships(id) ON DELETE CASCADE,
  active boolean NOT NULL DEFAULT true,
  linked_at timestamptz NOT NULL DEFAULT now(),
  unlinked_at timestamptz,
  reason text,
  UNIQUE(school_id,staff_id,membership_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_staff_active_membership_link ON staff_access_links(school_id,membership_id) WHERE active;

-- Student FK is intentionally deferred until the canonical Schooling port exists.
-- The UUID is still tenant-scoped and the link is explicit: never inferred from guardian name/phone.
CREATE TABLE IF NOT EXISTS staff_student_links (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  staff_id uuid NOT NULL REFERENCES staff_members(id) ON DELETE CASCADE,
  student_id uuid NOT NULL,
  relationship varchar(32) NOT NULL DEFAULT 'PARENT',
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  ended_at timestamptz,
  UNIQUE(school_id,staff_id,student_id)
);

CREATE TABLE IF NOT EXISTS staff_student_finance_preferences (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  staff_student_link_id uuid NOT NULL REFERENCES staff_student_links(id) ON DELETE CASCADE,
  responsibility_mode varchar(24) NOT NULL DEFAULT 'FAMILY' CHECK (responsibility_mode IN ('FAMILY','PAYROLL','SCHOOL','THIRD_PARTY')),
  effective_from date NOT NULL DEFAULT CURRENT_DATE,
  effective_until date,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  UNIQUE(school_id,staff_student_link_id),
  CHECK (effective_until IS NULL OR effective_until >= effective_from)
);

-- Cross-school integrity guards where PostgreSQL FKs alone would not compare school_id.
CREATE OR REPLACE FUNCTION validate_personnel_tenant_refs() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE ref_school uuid;
BEGIN
  IF TG_TABLE_NAME='staff_assignments' THEN
    SELECT school_id INTO ref_school FROM staff_members WHERE id=NEW.staff_id;
    IF ref_school IS DISTINCT FROM NEW.school_id THEN RAISE EXCEPTION 'Agent hors école'; END IF;
    SELECT school_id INTO ref_school FROM staff_functions WHERE id=NEW.function_id;
    IF ref_school IS DISTINCT FROM NEW.school_id THEN RAISE EXCEPTION 'Fonction hors école'; END IF;
    IF NEW.section_id IS NOT NULL THEN
      SELECT school_id INTO ref_school FROM school_sections WHERE id=NEW.section_id;
      IF ref_school IS DISTINCT FROM NEW.school_id THEN RAISE EXCEPTION 'Section hors école'; END IF;
    END IF;
    IF NEW.class_id IS NOT NULL THEN
      SELECT school_id INTO ref_school FROM school_classes WHERE id=NEW.class_id;
      IF ref_school IS DISTINCT FROM NEW.school_id THEN RAISE EXCEPTION 'Classe hors école'; END IF;
    END IF;
    IF NEW.titular_class_id IS NOT NULL THEN
      SELECT school_id INTO ref_school FROM school_classes WHERE id=NEW.titular_class_id;
      IF ref_school IS DISTINCT FROM NEW.school_id THEN RAISE EXCEPTION 'Classe de titulariat hors école'; END IF;
    END IF;
  ELSIF TG_TABLE_NAME='staff_access_links' THEN
    SELECT school_id INTO ref_school FROM staff_members WHERE id=NEW.staff_id;
    IF ref_school IS DISTINCT FROM NEW.school_id THEN RAISE EXCEPTION 'Agent hors école'; END IF;
    SELECT school_id INTO ref_school FROM school_memberships WHERE id=NEW.membership_id;
    IF ref_school IS DISTINCT FROM NEW.school_id THEN RAISE EXCEPTION 'Compte hors école'; END IF;
  ELSIF TG_TABLE_NAME='staff_student_links' THEN
    SELECT school_id INTO ref_school FROM staff_members WHERE id=NEW.staff_id;
    IF ref_school IS DISTINCT FROM NEW.school_id THEN RAISE EXCEPTION 'Agent hors école'; END IF;
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_staff_assignments_tenant_refs ON staff_assignments;
CREATE TRIGGER trg_staff_assignments_tenant_refs BEFORE INSERT OR UPDATE ON staff_assignments FOR EACH ROW EXECUTE FUNCTION validate_personnel_tenant_refs();
DROP TRIGGER IF EXISTS trg_staff_access_links_tenant_refs ON staff_access_links;
CREATE TRIGGER trg_staff_access_links_tenant_refs BEFORE INSERT OR UPDATE ON staff_access_links FOR EACH ROW EXECUTE FUNCTION validate_personnel_tenant_refs();
DROP TRIGGER IF EXISTS trg_staff_student_links_tenant_refs ON staff_student_links;
CREATE TRIGGER trg_staff_student_links_tenant_refs BEFORE INSERT OR UPDATE ON staff_student_links FOR EACH ROW EXECUTE FUNCTION validate_personnel_tenant_refs();

-- Optimistic versioning.
CREATE OR REPLACE FUNCTION touch_personnel_row() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at:=now(); NEW.version:=OLD.version+1; RETURN NEW; END $$;
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['staff_members','staff_functions','staff_assignments','staff_student_finance_preferences']
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS trg_touch_%I ON %I',t,t);
    EXECUTE format('CREATE TRIGGER trg_touch_%I BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION touch_personnel_row()',t,t);
  END LOOP;
END $$;

-- Tenant isolation.
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['staff_members','staff_functions','staff_assignments','staff_status_history','staff_access_links','staff_student_links','staff_student_finance_preferences']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I','tenant_'||t,t);
    EXECUTE format('CREATE POLICY %I ON %I FOR ALL TO edusync_tenant USING (school_id = nullif(current_setting(''app.current_school_id'',true),'''')::uuid) WITH CHECK (school_id = nullif(current_setting(''app.current_school_id'',true),'''')::uuid)','tenant_'||t,t);
  END LOOP;
END $$;
-- Personnel history is soft-state only: the tenant application role never receives DELETE.
GRANT SELECT,INSERT,UPDATE ON staff_members,staff_functions,staff_assignments,staff_status_history,staff_access_links,staff_student_links,staff_student_finance_preferences TO edusync_tenant;
REVOKE DELETE ON staff_members,staff_functions,staff_assignments,staff_status_history,staff_access_links,staff_student_links,staff_student_finance_preferences FROM edusync_tenant;

CREATE OR REPLACE FUNCTION forbid_personnel_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Personnel records are historical; physical DELETE is forbidden'; END $$;
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['staff_members','staff_functions','staff_assignments','staff_status_history','staff_access_links','staff_student_links','staff_student_finance_preferences']
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS trg_no_delete_%I ON %I',t,t);
    EXECUTE format('CREATE TRIGGER trg_no_delete_%I BEFORE DELETE ON %I FOR EACH ROW EXECUTE FUNCTION forbid_personnel_delete()',t,t);
  END LOOP;
END $$;

CREATE OR REPLACE FUNCTION forbid_staff_status_history_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'staff_status_history is append-only'; END $$;
DROP TRIGGER IF EXISTS trg_staff_status_history_no_update ON staff_status_history;
CREATE TRIGGER trg_staff_status_history_no_update BEFORE UPDATE ON staff_status_history FOR EACH ROW EXECUTE FUNCTION forbid_staff_status_history_update();

-- Point 4B capability expansion: granular exports, lifecycle and linked access.
INSERT INTO capability_catalog(code,domain_name,group_name,label,action_code,risk,offline_policy,audit_required,scope_types,source_status,prerequisites,outputs,sensitive,notes,registry_version) VALUES
 ('personnel.directory.print_pdf','Personnel','Annuaire & rapports','Imprimer le registre du personnel','print','LOW','READ_CACHE',false,'["SCHOOL","SECTION"]','POINT4B_ENRICHED','[]','["PDF"]',false,'Export filtré par périmètre effectif','0.7-point4b'),
 ('personnel.directory.export_xlsx','Personnel','Annuaire & rapports','Exporter le registre du personnel','export','LOW','READ_CACHE',false,'["SCHOOL","SECTION"]','POINT4B_ENRICHED','[]','["XLSX"]',false,'Export filtré par périmètre effectif','0.7-point4b'),
 ('personnel.profile.print_pdf','Personnel','Annuaire & rapports','Imprimer une fiche agent','print','LOW','READ_CACHE',false,'["SCHOOL","SECTION"]','POINT4B_ENRICHED','[]','["PDF"]',false,'Fiche agent avec affectations visibles','0.7-point4b'),
 ('personnel.history.read','Personnel','Cycle de vie','Consulter l’historique d’un agent','read','LOW','READ_CACHE',false,'["SCHOOL","SECTION"]','POINT4B_ENRICHED','[]','[]',false,'','0.7-point4b'),
 ('personnel.exit','Personnel','Cycle de vie','Enregistrer la sortie d’un agent','exit','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]','POINT4B_ENRICHED','[]','[]',true,'Clôture affectations + désactivation appartenance liée dans une transaction','0.7-point4b'),
 ('personnel.reactivate','Personnel','Cycle de vie','Réactiver un ancien agent','reactivate','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]','POINT4B_ENRICHED','[]','[]',true,'Ne rouvre jamais les anciennes affectations','0.7-point4b'),
 ('personnel.access_link.read','Personnel','Accès lié','Voir le compte lié à un agent','read','MEDIUM','SERVER_ONLY',false,'["SCHOOL"]','POINT4B_ENRICHED','[]','[]',true,'','0.7-point4b'),
 ('personnel.access_link.manage','Personnel','Accès lié','Lier/délier un compte utilisateur','manage','HIGH','SERVER_ONLY',true,'["SCHOOL"]','POINT4B_ENRICHED','[]','[]',true,'','0.7-point4b'),
 ('personnel.staff_children.link','Personnel','Enfants du personnel & paie','Lier explicitement un enfant à un agent','link','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]','POINT4B_ENRICHED','[]','[]',true,'Jamais déduit du responsable','0.7-point4b')
ON CONFLICT (code) DO UPDATE SET domain_name=EXCLUDED.domain_name,group_name=EXCLUDED.group_name,label=EXCLUDED.label,action_code=EXCLUDED.action_code,risk=EXCLUDED.risk,offline_policy=EXCLUDED.offline_policy,audit_required=EXCLUDED.audit_required,scope_types=EXCLUDED.scope_types,source_status=EXCLUDED.source_status,prerequisites=EXCLUDED.prerequisites,outputs=EXCLUDED.outputs,sensitive=EXCLUDED.sensitive,notes=EXCLUDED.notes,registry_version=EXCLUDED.registry_version,updated_at=now();

-- Consultation roles receive only view-specific print/export that matches the already-approved doctrine.
WITH grants(role_code,capability_code) AS (VALUES
 ('PROMOTEUR','personnel.directory.print_pdf'),('PROMOTEUR','personnel.directory.export_xlsx'),('PROMOTEUR','personnel.profile.print_pdf'),('PROMOTEUR','personnel.history.read'),
 ('GESTIONNAIRE','personnel.directory.print_pdf'),('GESTIONNAIRE','personnel.directory.export_xlsx'),('GESTIONNAIRE','personnel.profile.print_pdf'),('GESTIONNAIRE','personnel.history.read'),
 ('PREFET_ETUDES','personnel.directory.print_pdf'),('PREFET_ETUDES','personnel.directory.export_xlsx'),('PREFET_ETUDES','personnel.profile.print_pdf'),('PREFET_ETUDES','personnel.history.read'),
 ('DIRECTION_SECTION','personnel.directory.print_pdf'),('DIRECTION_SECTION','personnel.directory.export_xlsx'),('DIRECTION_SECTION','personnel.profile.print_pdf'),('DIRECTION_SECTION','personnel.history.read'),
 ('DIRECTEUR_ETUDES','personnel.directory.print_pdf'),('DIRECTEUR_ETUDES','personnel.directory.export_xlsx'),('DIRECTEUR_ETUDES','personnel.profile.print_pdf'),('DIRECTEUR_ETUDES','personnel.history.read'),
 ('DIRECTEUR_DISCIPLINE','personnel.directory.print_pdf'),('DIRECTEUR_DISCIPLINE','personnel.profile.print_pdf'),('DIRECTEUR_DISCIPLINE','personnel.history.read'),
 ('ADMIN_SYSTEME_ECOLE','personnel.access_link.read'),('ADMIN_SYSTEME_ECOLE','personnel.access_link.manage')
)
INSERT INTO rbac_role_capabilities(role_id,capability_code)
SELECT r.id,g.capability_code FROM grants g JOIN rbac_roles r ON r.code=g.role_code AND r.kind='SCHOOL_STANDARD' JOIN capability_catalog c ON c.code=g.capability_code
ON CONFLICT DO NOTHING;

-- Staff mutation capabilities deliberately remain unassigned to consultation roles.
-- A school creates a custom "Responsable du personnel" role or explicitly grants them.
