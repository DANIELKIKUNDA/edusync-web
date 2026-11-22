-- EduSync V2, lot 2 — pedagogical calendar and school programmes (owner, 2026-11-22). Additive only.
-- Calendar: one per school, year and structure (TRIMESTRIEL: maternelle / primaire; SEMESTRIEL: EB / humanités), its
-- periods and exams with dates, validated by the préfet or the directeur des études; grade entry closable per period.
-- Programme: per school, year and official class; DRAFT → VALIDATED → ARCHIVED; the database checks every line like
-- the official referential (exam = 2 × period, equal periods in a term, no exam points without exam).

CREATE TABLE IF NOT EXISTS pedagogy_calendars (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  academic_year_id uuid NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
  structure varchar(12) NOT NULL CHECK (structure IN ('TRIMESTRIEL','SEMESTRIEL')),
  status varchar(12) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','VALIDATED')),
  validated_by uuid REFERENCES users(id),
  validated_at timestamptz,
  updated_by uuid REFERENCES users(id),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  UNIQUE (school_id, academic_year_id, structure),
  CHECK ((status = 'VALIDATED') = (validated_at IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS pedagogy_calendar_periods (
  calendar_id uuid NOT NULL REFERENCES pedagogy_calendars(id) ON DELETE CASCADE,
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  code varchar(4) NOT NULL CHECK (code IN ('P1','P2','EX1','P3','P4','EX2','P5','P6','EX3')),
  sort_order smallint NOT NULL CHECK (sort_order BETWEEN 1 AND 9),
  starts_on date NOT NULL,
  ends_on date NOT NULL,
  entry_closed_at timestamptz,
  entry_closed_by uuid REFERENCES users(id),
  PRIMARY KEY (calendar_id, code),
  CHECK (ends_on >= starts_on)
);

CREATE TABLE IF NOT EXISTS pedagogy_programmes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  academic_year_id uuid NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
  ref_class_code varchar(16) NOT NULL REFERENCES ref_classes(code),
  structure varchar(12) NOT NULL CHECK (structure IN ('TRIMESTRIEL','SEMESTRIEL')),
  status varchar(12) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','VALIDATED','ARCHIVED')),
  based_on_version varchar(40) REFERENCES ref_programme_versions(code),
  replaces_id uuid REFERENCES pedagogy_programmes(id),
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  validated_by uuid REFERENCES users(id),
  validated_at timestamptz,
  archived_at timestamptz,
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  CHECK ((status = 'DRAFT') = (validated_at IS NULL))
);
-- one programme in use and at most one draft per class and year
CREATE UNIQUE INDEX IF NOT EXISTS uq_pedagogy_programme_validated ON pedagogy_programmes(school_id, academic_year_id, ref_class_code) WHERE status = 'VALIDATED';
CREATE UNIQUE INDEX IF NOT EXISTS uq_pedagogy_programme_draft ON pedagogy_programmes(school_id, academic_year_id, ref_class_code) WHERE status = 'DRAFT';

CREATE TABLE IF NOT EXISTS pedagogy_programme_lines (
  programme_id uuid NOT NULL REFERENCES pedagogy_programmes(id) ON DELETE CASCADE,
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  course_code varchar(96) NOT NULL REFERENCES ref_courses(code),
  sort_order smallint NOT NULL CHECK (sort_order > 0),
  source varchar(12) NOT NULL CHECK (source IN ('OFFICIEL','ECOLE')),
  mandatory boolean NOT NULL,
  has_exam boolean NOT NULL,
  calculable boolean NOT NULL DEFAULT true,
  semester_structure boolean NOT NULL,
  domain varchar(80),
  subdomain varchar(140),
  max_p1 smallint NOT NULL CHECK (max_p1 >= 0), max_p2 smallint NOT NULL CHECK (max_p2 >= 0), max_ex1 smallint NOT NULL CHECK (max_ex1 >= 0),
  max_p3 smallint NOT NULL CHECK (max_p3 >= 0), max_p4 smallint NOT NULL CHECK (max_p4 >= 0), max_ex2 smallint NOT NULL CHECK (max_ex2 >= 0),
  max_p5 smallint NOT NULL CHECK (max_p5 >= 0), max_p6 smallint NOT NULL CHECK (max_p6 >= 0), max_ex3 smallint NOT NULL CHECK (max_ex3 >= 0),
  PRIMARY KEY (programme_id, course_code),
  CONSTRAINT programme_line_not_empty CHECK (max_p1+max_p2+max_ex1+max_p3+max_p4+max_ex2+max_p5+max_p6+max_ex3 > 0),
  CONSTRAINT programme_line_semester CHECK (NOT semester_structure OR (max_p5 = 0 AND max_p6 = 0 AND max_ex3 = 0)),
  CONSTRAINT programme_line_exam_is_double CHECK (NOT has_exam OR (max_ex1 = 2*max_p1 AND max_ex2 = 2*max_p3 AND max_ex3 = 2*max_p5)),
  CONSTRAINT programme_line_no_exam CHECK (has_exam OR (max_ex1 = 0 AND max_ex2 = 0 AND max_ex3 = 0)),
  CONSTRAINT programme_line_equal_periods CHECK (max_p1 = max_p2 AND max_p3 = max_p4 AND max_p5 = max_p6)
);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['pedagogy_calendars','pedagogy_calendar_periods','pedagogy_programmes','pedagogy_programme_lines'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (school_id = current_setting(''app.school_id'', true)::uuid) '
                   'WITH CHECK (school_id = current_setting(''app.school_id'', true)::uuid)', t);
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_tenant') THEN
      EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO edusync_tenant', t);
    END IF;
  END LOOP;
END $$;

INSERT INTO capability_catalog(code,domain_name,group_name,label,action_code,risk,offline_policy,audit_required,
  scope_types,source_status,prerequisites,outputs,sensitive,notes,registry_version)
VALUES
 ('pedagogy.calendar.manage','Pédagogie','Calendrier','Préparer, valider et clôturer le calendrier pédagogique','manage','MEDIUM','SERVER_ONLY',true,
  '["SCHOOL"]','OWNER_APPROVED','["pedagogy.referential.read"]','[]',false,'Module Pédagogie (V2) requis','3.0.0'),
 ('pedagogy.programmes.manage','Pédagogie','Programmes','Adopter, ajuster et valider les programmes des classes','manage','MEDIUM','SERVER_ONLY',true,
  '["SCHOOL","SECTION"]','OWNER_APPROVED','["pedagogy.referential.read"]','[]',false,'Module Pédagogie (V2) requis','3.0.0')
ON CONFLICT (code) DO UPDATE SET label=EXCLUDED.label, notes=EXCLUDED.notes, active=true, updated_at=now();
UPDATE capability_catalog SET school_adjustable=true WHERE code IN ('pedagogy.calendar.manage','pedagogy.programmes.manage');

-- Owner, 2026-11-22: the préfet and the directeur des études validate (each school may adjust in « Accès et rôles »).
INSERT INTO rbac_role_capabilities(role_id, capability_code)
SELECT r.id,'pedagogy.calendar.manage' FROM rbac_roles r
WHERE r.level='SCHOOL' AND r.code IN ('ADMIN_SYSTEME_ECOLE','PREFET_ETUDES','DIRECTEUR_ETUDES')
ON CONFLICT DO NOTHING;
INSERT INTO rbac_role_capabilities(role_id, capability_code)
SELECT r.id,'pedagogy.programmes.manage' FROM rbac_roles r
WHERE r.level='SCHOOL' AND r.code IN ('ADMIN_SYSTEME_ECOLE','PREFET_ETUDES','DIRECTEUR_ETUDES','DIRECTION_SECTION')
ON CONFLICT DO NOTHING;
