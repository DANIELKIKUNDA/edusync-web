-- EduSync Point 4C — Élèves / Familles / Inscriptions Web deep port (2026-09-12)
-- Preservation-first + terrain-first: Nom, Postnom, Prénom et Classe suffisent pour l'inscription.
-- Date/lieu de naissance, sexe et autres informations restent complétables ultérieurement.

CREATE TABLE IF NOT EXISTS school_sequence_counters (
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  namespace varchar(48) NOT NULL,
  current_value bigint NOT NULL DEFAULT 0 CHECK (current_value >= 0),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(school_id,namespace)
);

CREATE TABLE IF NOT EXISTS families (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  code varchar(48) NOT NULL,
  display_name varchar(180) NOT NULL,
  display_name_origin varchar(24) NOT NULL DEFAULT 'STUDENT' CHECK (display_name_origin IN ('PRIMARY_GUARDIAN','STUDENT','MANUAL_OVERRIDE')),
  phone varchar(48),
  email citext,
  address text,
  contact_status varchar(24) NOT NULL DEFAULT 'TO_COMPLETE' CHECK (contact_status IN ('COMPLETE','TO_COMPLETE')),
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  UNIQUE(school_id,code)
);
CREATE INDEX IF NOT EXISTS idx_families_lookup ON families(school_id,display_name,phone);

-- Canonical contact identities are explicit. Phone is intentionally NOT unique: shared numbers are common.
CREATE TABLE IF NOT EXISTS guardians (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  full_name varchar(180) NOT NULL,
  phone varchar(48),
  normalized_phone varchar(48),
  email citext,
  address text,
  occupation varchar(160),
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_guardians_lookup ON guardians(school_id,full_name,normalized_phone);

CREATE TABLE IF NOT EXISTS family_guardians (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  guardian_id uuid NOT NULL REFERENCES guardians(id) ON DELETE CASCADE,
  role varchar(16) NOT NULL DEFAULT 'TUTEUR' CHECK (role IN ('PERE','MERE','TUTEUR','AUTRE')),
  is_primary boolean NOT NULL DEFAULT false,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  UNIQUE(school_id,family_id,guardian_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_family_one_primary_guardian ON family_guardians(school_id,family_id) WHERE active AND is_primary;

CREATE TABLE IF NOT EXISTS students (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  family_id uuid NOT NULL REFERENCES families(id),
  matricule varchar(64) NOT NULL,
  last_name varchar(120) NOT NULL,
  middle_name varchar(120) NOT NULL,
  first_name varchar(120) NOT NULL,
  gender varchar(16) CHECK (gender IS NULL OR gender IN ('M','F','X')),
  birth_date date,
  birth_place varchar(160),
  nationality varchar(96),
  address text,
  previous_school varchar(180),
  photo_url text,
  status varchar(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','ABANDON','TRANSFERRED','SUSPENDED','INACTIVE')),
  profile_completeness smallint NOT NULL DEFAULT 0 CHECK (profile_completeness BETWEEN 0 AND 100),
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  UNIQUE(school_id,matricule),
  CHECK (btrim(last_name)<>'' AND btrim(middle_name)<>'' AND btrim(first_name)<>'')
);
CREATE INDEX IF NOT EXISTS idx_students_family ON students(school_id,family_id);
CREATE INDEX IF NOT EXISTS idx_students_names ON students(school_id,last_name,middle_name,first_name);
CREATE INDEX IF NOT EXISTS idx_students_status ON students(school_id,status);

CREATE TABLE IF NOT EXISTS enrollments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  student_id uuid NOT NULL REFERENCES students(id),
  academic_year_id uuid NOT NULL REFERENCES academic_years(id),
  class_id uuid NOT NULL REFERENCES school_classes(id),
  status varchar(20) NOT NULL DEFAULT 'VALIDATED' CHECK (status IN ('DRAFT','VALIDATED','CANCELLED','COMPLETED')),
  enrollment_kind varchar(20) NOT NULL DEFAULT 'NEW' CHECK (enrollment_kind IN ('NEW','REENROLLMENT','TRANSFER_IN')),
  enrolled_on date NOT NULL DEFAULT CURRENT_DATE,
  origin_school varchar(180),
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_student_year_active_enrollment ON enrollments(school_id,student_id,academic_year_id) WHERE status <> 'CANCELLED';
CREATE INDEX IF NOT EXISTS idx_enrollments_class ON enrollments(school_id,academic_year_id,class_id,status);

CREATE TABLE IF NOT EXISTS class_assignments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  student_id uuid NOT NULL REFERENCES students(id),
  enrollment_id uuid NOT NULL REFERENCES enrollments(id),
  class_id uuid NOT NULL REFERENCES school_classes(id),
  effective_from date NOT NULL DEFAULT CURRENT_DATE,
  effective_until date,
  reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  CHECK (effective_until IS NULL OR effective_until >= effective_from)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_student_open_class_assignment ON class_assignments(school_id,enrollment_id) WHERE effective_until IS NULL;

CREATE TABLE IF NOT EXISTS student_status_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  student_id uuid NOT NULL REFERENCES students(id),
  event_type varchar(20) NOT NULL CHECK (event_type IN ('ABANDON','TRANSFER','SUSPEND','REINTEGRATE','CLASS_CHANGE')),
  effective_date date NOT NULL,
  reason text NOT NULL CHECK (btrim(reason)<>''),
  destination varchar(180),
  actor_user_id uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (event_type <> 'TRANSFER' OR btrim(coalesce(destination,''))<>'')
);
CREATE INDEX IF NOT EXISTS idx_student_status_events ON student_status_events(school_id,student_id,created_at DESC);

CREATE TABLE IF NOT EXISTS student_benefits (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  student_id uuid NOT NULL REFERENCES students(id),
  academic_year_id uuid NOT NULL REFERENCES academic_years(id),
  kind varchar(32) NOT NULL CHECK (kind IN ('LARGE_FAMILY','STAFF_CHILD','SCHOOL_SUPPORT','THIRD_PARTY','OTHER')),
  source_reference varchar(180),
  selected_explicitly boolean NOT NULL DEFAULT true CHECK (selected_explicitly=true),
  active boolean NOT NULL DEFAULT true,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  UNIQUE(school_id,student_id,academic_year_id,kind)
);

CREATE TABLE IF NOT EXISTS household_resolution_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  query_text text,
  selected_family_id uuid REFERENCES families(id),
  confidence varchar(16) NOT NULL CHECK (confidence IN ('CERTAIN','POSSIBLE','NONE')),
  candidate_count integer NOT NULL DEFAULT 0,
  resolution varchar(24) NOT NULL CHECK (resolution IN ('CONFIRMED_EXISTING','CREATED_NEW','CANCELLED')),
  actor_user_id uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Safe default: minimal terrain fields only. It is informative/configurable, not a global setup gate.
INSERT INTO school_policy_documents(school_id,kind,status,payload)
SELECT s.id,'ENROLLMENT','ACTIVE',jsonb_build_object(
  'required_student_fields',jsonb_build_array('last_name','middle_name','first_name','class_id'),
  'optional_student_fields',jsonb_build_array('gender','birth_date','birth_place','nationality','address','previous_school'),
  'guardian_required_at_enrollment',false,
  'guardian_phone_required',false,
  'family_label_strategy','AUTO_FROM_PRIMARY_GUARDIAN_OR_STUDENT',
  'allow_profile_completion_later',true
)
FROM schools s
WHERE NOT EXISTS (SELECT 1 FROM school_policy_documents p WHERE p.school_id=s.id AND p.kind='ENROLLMENT');

-- Cross-tenant referential integrity.
CREATE OR REPLACE FUNCTION validate_schooling_tenant_refs() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE ref_school uuid; ref_year uuid; ref_section uuid;
BEGIN
  IF TG_TABLE_NAME='family_guardians' THEN
    SELECT school_id INTO ref_school FROM families WHERE id=NEW.family_id;
    IF ref_school IS DISTINCT FROM NEW.school_id THEN RAISE EXCEPTION 'Foyer hors école'; END IF;
    SELECT school_id INTO ref_school FROM guardians WHERE id=NEW.guardian_id;
    IF ref_school IS DISTINCT FROM NEW.school_id THEN RAISE EXCEPTION 'Responsable hors école'; END IF;
  ELSIF TG_TABLE_NAME='students' THEN
    SELECT school_id INTO ref_school FROM families WHERE id=NEW.family_id;
    IF ref_school IS DISTINCT FROM NEW.school_id THEN RAISE EXCEPTION 'Foyer hors école'; END IF;
  ELSIF TG_TABLE_NAME='enrollments' THEN
    SELECT school_id INTO ref_school FROM students WHERE id=NEW.student_id;
    IF ref_school IS DISTINCT FROM NEW.school_id THEN RAISE EXCEPTION 'Élève hors école'; END IF;
    SELECT school_id INTO ref_school FROM academic_years WHERE id=NEW.academic_year_id;
    IF ref_school IS DISTINCT FROM NEW.school_id THEN RAISE EXCEPTION 'Année hors école'; END IF;
    SELECT school_id,academic_year_id,section_id INTO ref_school,ref_year,ref_section FROM school_classes WHERE id=NEW.class_id;
    IF ref_school IS DISTINCT FROM NEW.school_id OR ref_year IS DISTINCT FROM NEW.academic_year_id THEN RAISE EXCEPTION 'Classe hors année/école'; END IF;
  ELSIF TG_TABLE_NAME='class_assignments' THEN
    SELECT school_id INTO ref_school FROM students WHERE id=NEW.student_id;
    IF ref_school IS DISTINCT FROM NEW.school_id THEN RAISE EXCEPTION 'Élève hors école'; END IF;
    SELECT school_id INTO ref_school FROM enrollments WHERE id=NEW.enrollment_id;
    IF ref_school IS DISTINCT FROM NEW.school_id THEN RAISE EXCEPTION 'Inscription hors école'; END IF;
    SELECT school_id INTO ref_school FROM school_classes WHERE id=NEW.class_id;
    IF ref_school IS DISTINCT FROM NEW.school_id THEN RAISE EXCEPTION 'Classe hors école'; END IF;
  ELSIF TG_TABLE_NAME IN ('student_status_events','student_benefits') THEN
    SELECT school_id INTO ref_school FROM students WHERE id=NEW.student_id;
    IF ref_school IS DISTINCT FROM NEW.school_id THEN RAISE EXCEPTION 'Élève hors école'; END IF;
  ELSIF TG_TABLE_NAME='household_resolution_events' AND NEW.selected_family_id IS NOT NULL THEN
    SELECT school_id INTO ref_school FROM families WHERE id=NEW.selected_family_id;
    IF ref_school IS DISTINCT FROM NEW.school_id THEN RAISE EXCEPTION 'Foyer sélectionné hors école'; END IF;
  END IF;
  RETURN NEW;
END $$;
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['family_guardians','students','enrollments','class_assignments','student_status_events','student_benefits','household_resolution_events']
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS trg_%I_tenant_refs ON %I',t,t);
    EXECUTE format('CREATE TRIGGER trg_%I_tenant_refs BEFORE INSERT OR UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION validate_schooling_tenant_refs()',t,t);
  END LOOP;
END $$;

-- Complete Personnel deferred student FK now that Schooling is canonical.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_staff_student_links_student') THEN
    ALTER TABLE staff_student_links ADD CONSTRAINT fk_staff_student_links_student FOREIGN KEY(student_id) REFERENCES students(id);
  END IF;
END $$;
CREATE OR REPLACE FUNCTION validate_staff_student_school() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE a_school uuid; s_school uuid;
BEGIN
  SELECT school_id INTO a_school FROM staff_members WHERE id=NEW.staff_id;
  SELECT school_id INTO s_school FROM students WHERE id=NEW.student_id;
  IF a_school IS DISTINCT FROM NEW.school_id OR s_school IS DISTINCT FROM NEW.school_id THEN RAISE EXCEPTION 'Lien agent/élève hors école'; END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_staff_student_schooling_ref ON staff_student_links;
CREATE TRIGGER trg_staff_student_schooling_ref BEFORE INSERT OR UPDATE ON staff_student_links FOR EACH ROW EXECUTE FUNCTION validate_staff_student_school();

-- Optimistic versioning where records are mutable.
CREATE OR REPLACE FUNCTION touch_schooling_row() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at:=now(); NEW.version:=OLD.version+1; RETURN NEW; END $$;
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['families','guardians','family_guardians','students','enrollments','student_benefits']
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS trg_touch_%I ON %I',t,t);
    EXECUTE format('CREATE TRIGGER trg_touch_%I BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION touch_schooling_row()',t,t);
  END LOOP;
END $$;

-- Tenant isolation and historical no-delete doctrine.
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['school_sequence_counters','families','guardians','family_guardians','students','enrollments','class_assignments','student_status_events','student_benefits','household_resolution_events']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I','tenant_'||t,t);
    EXECUTE format('CREATE POLICY %I ON %I FOR ALL TO edusync_tenant USING (school_id = nullif(current_setting(''app.current_school_id'',true),'''')::uuid) WITH CHECK (school_id = nullif(current_setting(''app.current_school_id'',true),'''')::uuid)','tenant_'||t,t);
  END LOOP;
END $$;
GRANT SELECT,INSERT,UPDATE ON school_sequence_counters,families,guardians,family_guardians,students,enrollments,class_assignments,student_status_events,student_benefits,household_resolution_events TO edusync_tenant;
REVOKE DELETE ON school_sequence_counters,families,guardians,family_guardians,students,enrollments,class_assignments,student_status_events,student_benefits,household_resolution_events FROM edusync_tenant;

CREATE OR REPLACE FUNCTION forbid_schooling_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Schooling records are historical; physical DELETE is forbidden'; END $$;
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['families','guardians','family_guardians','students','enrollments','class_assignments','student_status_events','student_benefits','household_resolution_events']
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS trg_no_delete_%I ON %I',t,t);
    EXECUTE format('CREATE TRIGGER trg_no_delete_%I BEFORE DELETE ON %I FOR EACH ROW EXECUTE FUNCTION forbid_schooling_delete()',t,t);
  END LOOP;
END $$;
CREATE OR REPLACE FUNCTION forbid_schooling_append_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Schooling event history is append-only'; END $$;
DROP TRIGGER IF EXISTS trg_status_events_no_update ON student_status_events;
CREATE TRIGGER trg_status_events_no_update BEFORE UPDATE ON student_status_events FOR EACH ROW EXECUTE FUNCTION forbid_schooling_append_update();
DROP TRIGGER IF EXISTS trg_household_resolution_no_update ON household_resolution_events;
CREATE TRIGGER trg_household_resolution_no_update BEFORE UPDATE ON household_resolution_events FOR EACH ROW EXECUTE FUNCTION forbid_schooling_append_update();

-- Point 4C capability expansion: reports, profile completion, household resolution and family documents.
INSERT INTO capability_catalog(code,domain_name,group_name,label,action_code,risk,offline_policy,audit_required,scope_types,source_status,prerequisites,outputs,sensitive,notes,registry_version) VALUES
 ('students.directory.print_pdf','Élèves & inscriptions','Annuaire','Imprimer l’annuaire des élèves','print','LOW','READ_CACHE',false,'["SCHOOL","SECTION","CLASS"]','POINT4C_ENRICHED','[]','["PDF"]',false,'Respecte strictement le périmètre effectif','0.8-point4c'),
 ('students.directory.export_xlsx','Élèves & inscriptions','Annuaire','Exporter l’annuaire des élèves','export','LOW','READ_CACHE',false,'["SCHOOL","SECTION","CLASS"]','POINT4C_ENRICHED','[]','["XLSX"]',false,'Respecte strictement le périmètre effectif','0.8-point4c'),
 ('students.profile.print_pdf','Élèves & inscriptions','Fiche élève','Imprimer la fiche élève','print','LOW','READ_CACHE',false,'["SCHOOL","SECTION","CLASS"]','POINT4C_ENRICHED','[]','["PDF"]',false,'','0.8-point4c'),
 ('families.directory.print_pdf','Élèves & inscriptions','Familles','Imprimer le répertoire des familles','print','LOW','READ_CACHE',false,'["SCHOOL","SECTION"]','POINT4C_ENRICHED','[]','["PDF"]',false,'','0.8-point4c'),
 ('families.directory.export_xlsx','Élèves & inscriptions','Familles','Exporter le répertoire des familles','export','LOW','READ_CACHE',false,'["SCHOOL","SECTION"]','POINT4C_ENRICHED','[]','["XLSX"]',false,'','0.8-point4c'),
 ('families.resolution.audit','Élèves & inscriptions','Familles','Tracer la résolution de foyer','resolve','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL","SECTION"]','POINT4C_ENRICHED','[]','[]',true,'Jamais de fusion silencieuse sur nom/téléphone','0.8-point4c'),
 ('students.profile.complete','Élèves & inscriptions','Fiche élève','Compléter les informations non bloquantes','update','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL","SECTION","CLASS"]','POINT4C_ENRICHED','[]','[]',true,'Naissance, sexe, nationalité, adresse complétables après inscription','0.8-point4c')
ON CONFLICT (code) DO UPDATE SET domain_name=EXCLUDED.domain_name,group_name=EXCLUDED.group_name,label=EXCLUDED.label,action_code=EXCLUDED.action_code,risk=EXCLUDED.risk,offline_policy=EXCLUDED.offline_policy,audit_required=EXCLUDED.audit_required,scope_types=EXCLUDED.scope_types,source_status=EXCLUDED.source_status,prerequisites=EXCLUDED.prerequisites,outputs=EXCLUDED.outputs,sensitive=EXCLUDED.sensitive,notes=EXCLUDED.notes,registry_version=EXCLUDED.registry_version,updated_at=now();

-- Existing approved standard roles gain only the view-specific outputs/profile completion aligned with Point 3 doctrine.
WITH grants(role_code,capability_code) AS (VALUES
 ('PROMOTEUR','students.directory.print_pdf'),('PROMOTEUR','students.directory.export_xlsx'),('PROMOTEUR','students.profile.print_pdf'),('PROMOTEUR','families.directory.print_pdf'),('PROMOTEUR','families.directory.export_xlsx'),
 ('GESTIONNAIRE','students.directory.print_pdf'),('GESTIONNAIRE','students.directory.export_xlsx'),('GESTIONNAIRE','students.profile.print_pdf'),('GESTIONNAIRE','families.directory.print_pdf'),('GESTIONNAIRE','families.directory.export_xlsx'),
 ('PREFET_ETUDES','students.directory.print_pdf'),('PREFET_ETUDES','students.directory.export_xlsx'),('PREFET_ETUDES','students.profile.print_pdf'),('PREFET_ETUDES','families.directory.print_pdf'),('PREFET_ETUDES','families.directory.export_xlsx'),('PREFET_ETUDES','students.profile.complete'),('PREFET_ETUDES','families.resolution.audit'),
 ('DIRECTION_SECTION','students.directory.print_pdf'),('DIRECTION_SECTION','students.directory.export_xlsx'),('DIRECTION_SECTION','students.profile.print_pdf'),('DIRECTION_SECTION','families.directory.print_pdf'),('DIRECTION_SECTION','families.directory.export_xlsx'),('DIRECTION_SECTION','students.profile.complete'),('DIRECTION_SECTION','families.resolution.audit'),
 ('DIRECTEUR_ETUDES','students.directory.print_pdf'),('DIRECTEUR_ETUDES','students.directory.export_xlsx'),('DIRECTEUR_ETUDES','students.profile.print_pdf'),('DIRECTEUR_ETUDES','families.directory.print_pdf'),('DIRECTEUR_ETUDES','students.profile.complete'),
 ('DIRECTEUR_DISCIPLINE','students.directory.print_pdf'),('DIRECTEUR_DISCIPLINE','students.profile.print_pdf'),('DIRECTEUR_DISCIPLINE','students.profile.complete'),
 ('CAISSIER','students.directory.print_pdf'),('CAISSIER','students.directory.export_xlsx'),('CAISSIER','students.profile.print_pdf'),('CAISSIER','families.directory.print_pdf'),('CAISSIER','families.directory.export_xlsx'),('CAISSIER','students.profile.complete'),('CAISSIER','families.resolution.audit'),
 ('SECRETARIAT','students.directory.print_pdf'),('SECRETARIAT','students.directory.export_xlsx'),('SECRETARIAT','students.profile.print_pdf'),('SECRETARIAT','families.directory.print_pdf'),('SECRETARIAT','families.directory.export_xlsx'),('SECRETARIAT','students.profile.complete')
)
INSERT INTO rbac_role_capabilities(role_id,capability_code)
SELECT r.id,g.capability_code FROM grants g JOIN rbac_roles r ON r.code=g.role_code AND r.kind='SCHOOL_STANDARD' JOIN capability_catalog c ON c.code=g.capability_code
ON CONFLICT DO NOTHING;
