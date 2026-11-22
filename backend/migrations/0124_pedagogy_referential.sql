-- EduSync V2, lot 1 — official MINEDUC referential (owner, 2026-11-22).
-- Shared reference tables (one copy for every school, read-only for the application roles), loaded at provisioning
-- from backend/src/edusync/modules/pedagogy/reference/<version>/ by referential_loader. The database itself refuses an
-- inconsistent weighting: « l'examen est toujours le double de la période » (owner), semester classes without P5/P6/EX3.
-- School side: the link « classe de l'école → classe officielle » (RLS), behind the pedagogy module (lot 0).
-- Additive only.

CREATE TABLE IF NOT EXISTS ref_programme_versions (
  code varchar(40) PRIMARY KEY,
  reference_year varchar(9) NOT NULL,
  published_on date NOT NULL,
  checksum varchar(64) NOT NULL,
  loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ref_sections (
  code varchar(8) PRIMARY KEY,
  label varchar(40) NOT NULL,
  sort_order smallint NOT NULL
);

CREATE TABLE IF NOT EXISTS ref_options (
  code integer PRIMARY KEY CHECK (code BETWEEN 100 AND 999),
  sigle varchar(12) NOT NULL UNIQUE,
  label varchar(80) NOT NULL,
  option_group varchar(12) NOT NULL CHECK (option_group IN ('GENERAL','GROUPE_1','GROUPE_2')),
  sort_order smallint NOT NULL
);

CREATE TABLE IF NOT EXISTS ref_classes (
  code varchar(16) PRIMARY KEY,
  label varchar(80) NOT NULL,
  section_code varchar(8) NOT NULL REFERENCES ref_sections(code),
  option_code integer REFERENCES ref_options(code),
  level_order smallint NOT NULL CHECK (level_order > 0),
  cycle varchar(16) NOT NULL CHECK (cycle IN ('MATERNELLE','PRIMAIRE','EB','HUMANITE')),
  structure varchar(12) NOT NULL CHECK (structure IN ('TRIMESTRIEL','SEMESTRIEL')),
  CHECK ((cycle = 'HUMANITE') = (option_code IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS ref_courses (
  code varchar(96) PRIMARY KEY,
  label varchar(120) NOT NULL
);

CREATE TABLE IF NOT EXISTS ref_programme_lines (
  version_code varchar(40) NOT NULL REFERENCES ref_programme_versions(code),
  class_code varchar(16) NOT NULL REFERENCES ref_classes(code),
  course_code varchar(96) NOT NULL REFERENCES ref_courses(code),
  sort_order smallint NOT NULL CHECK (sort_order > 0),
  mandatory boolean NOT NULL,
  has_exam boolean NOT NULL,
  calculable boolean NOT NULL,
  semester_structure boolean NOT NULL,
  domain varchar(80),
  subdomain varchar(140),
  max_p1 smallint NOT NULL CHECK (max_p1 >= 0), max_p2 smallint NOT NULL CHECK (max_p2 >= 0), max_ex1 smallint NOT NULL CHECK (max_ex1 >= 0),
  max_p3 smallint NOT NULL CHECK (max_p3 >= 0), max_p4 smallint NOT NULL CHECK (max_p4 >= 0), max_ex2 smallint NOT NULL CHECK (max_ex2 >= 0),
  max_p5 smallint NOT NULL CHECK (max_p5 >= 0), max_p6 smallint NOT NULL CHECK (max_p6 >= 0), max_ex3 smallint NOT NULL CHECK (max_ex3 >= 0),
  PRIMARY KEY (version_code, class_code, course_code),
  CONSTRAINT ref_line_not_empty CHECK (max_p1+max_p2+max_ex1+max_p3+max_p4+max_ex2+max_p5+max_p6+max_ex3 > 0),
  CONSTRAINT ref_line_semester CHECK (NOT semester_structure OR (max_p5 = 0 AND max_p6 = 0 AND max_ex3 = 0)),
  CONSTRAINT ref_line_exam_is_double CHECK (NOT has_exam OR (max_ex1 = 2*max_p1 AND max_ex2 = 2*max_p3 AND max_ex3 = 2*max_p5)),
  CONSTRAINT ref_line_no_exam CHECK (has_exam OR (max_ex1 = 0 AND max_ex2 = 0 AND max_ex3 = 0))
);
CREATE INDEX IF NOT EXISTS idx_ref_programme_lines_class ON ref_programme_lines(version_code, class_code, sort_order);

-- A school class linked to its official class (one link per class; the school confirms, EduSync only suggests).
CREATE TABLE IF NOT EXISTS pedagogy_class_links (
  class_id uuid PRIMARY KEY REFERENCES school_classes(id) ON DELETE CASCADE,
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  ref_class_code varchar(16) NOT NULL REFERENCES ref_classes(code),
  linked_by uuid REFERENCES users(id),
  linked_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0)
);
CREATE INDEX IF NOT EXISTS idx_pedagogy_class_links_school ON pedagogy_class_links(school_id, ref_class_code);
ALTER TABLE pedagogy_class_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE pedagogy_class_links FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON pedagogy_class_links;
CREATE POLICY tenant_isolation ON pedagogy_class_links
  USING (school_id = current_setting('app.school_id', true)::uuid) WITH CHECK (school_id = current_setting('app.school_id', true)::uuid);

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_tenant') THEN
    GRANT SELECT ON ref_programme_versions, ref_sections, ref_options, ref_classes, ref_courses, ref_programme_lines TO edusync_tenant;
    GRANT SELECT, INSERT, UPDATE, DELETE ON pedagogy_class_links TO edusync_tenant;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_platform') THEN
    GRANT SELECT ON ref_programme_versions, ref_sections, ref_options, ref_classes, ref_courses, ref_programme_lines TO edusync_platform;
  END IF;
END $$;

-- Rights (school_adjustable: each school decides in « Accès et rôles »).
INSERT INTO capability_catalog(code,domain_name,group_name,label,action_code,risk,offline_policy,audit_required,
  scope_types,source_status,prerequisites,outputs,sensitive,notes,registry_version)
VALUES
 ('pedagogy.referential.read','Pédagogie','Référentiel','Consulter le référentiel officiel et les programmes','read','LOW','SERVER_ONLY',false,
  '["SCHOOL","SECTION"]','OWNER_APPROVED','[]','[]',false,'Module Pédagogie (V2) requis','3.0.0'),
 ('pedagogy.class_links.manage','Pédagogie','Référentiel','Relier les classes de l’école aux classes officielles','manage','MEDIUM','SERVER_ONLY',true,
  '["SCHOOL","SECTION"]','OWNER_APPROVED','[]','[]',false,'Module Pédagogie (V2) requis','3.0.0')
ON CONFLICT (code) DO UPDATE SET label=EXCLUDED.label, notes=EXCLUDED.notes, active=true, updated_at=now();
UPDATE capability_catalog SET school_adjustable=true WHERE code IN ('pedagogy.referential.read','pedagogy.class_links.manage');

INSERT INTO rbac_role_capabilities(role_id, capability_code)
SELECT r.id,'pedagogy.referential.read' FROM rbac_roles r
WHERE r.level='SCHOOL' AND r.code IN ('ADMIN_SYSTEME_ECOLE','PROMOTEUR','PREFET_ETUDES','DIRECTEUR_ETUDES','DIRECTION_SECTION')
ON CONFLICT DO NOTHING;
INSERT INTO rbac_role_capabilities(role_id, capability_code)
SELECT r.id,'pedagogy.class_links.manage' FROM rbac_roles r
WHERE r.level='SCHOOL' AND r.code IN ('ADMIN_SYSTEME_ECOLE','PREFET_ETUDES','DIRECTEUR_ETUDES')
ON CONFLICT DO NOTHING;
