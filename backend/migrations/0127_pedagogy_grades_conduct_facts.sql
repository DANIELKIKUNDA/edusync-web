-- EduSync V2, lot 3b — grades and conduct facts (owner, 2026-11-22). Additive only.
-- Grades: one row per (class, pupil, course, period); entered only by the teacher of the course (parent project); never
-- deleted — emptied with history; version for concurrent edits. Conduct: facts reported from the school's scale, the
-- conduct is COMPUTED (points licence); cancellation keeps the row; exceptional adjustment by the discipline director.

CREATE TABLE IF NOT EXISTS pedagogy_grades (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  academic_year_id uuid NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
  class_id uuid NOT NULL REFERENCES school_classes(id) ON DELETE CASCADE,
  student_id uuid NOT NULL REFERENCES students(id),
  course_code varchar(96) NOT NULL REFERENCES ref_courses(code),
  period_code varchar(4) NOT NULL CHECK (period_code IN ('P1','P2','EX1','P3','P4','EX2','P5','P6','EX3')),
  status varchar(10) CHECK (status IS NULL OR status IN ('NOTE','ABSENT','DISPENSE')),
  value smallint,
  max_value smallint NOT NULL CHECK (max_value > 0),
  entered_by uuid REFERENCES school_memberships(id),
  entered_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  UNIQUE (class_id, student_id, course_code, period_code),
  CONSTRAINT grade_value_coherent CHECK (
    (status IS NULL AND value IS NULL) OR (status = 'NOTE' AND value BETWEEN 0 AND max_value) OR (status IN ('ABSENT','DISPENSE') AND value IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_pedagogy_grades_sheet ON pedagogy_grades(school_id, class_id, course_code, period_code);

CREATE TABLE IF NOT EXISTS pedagogy_grade_history (
  id bigserial PRIMARY KEY,
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  grade_id uuid NOT NULL REFERENCES pedagogy_grades(id) ON DELETE CASCADE,
  old_status varchar(10), old_value smallint,
  new_status varchar(10), new_value smallint,
  changed_by uuid REFERENCES school_memberships(id),
  changed_at timestamptz NOT NULL DEFAULT now(),
  source varchar(12) NOT NULL DEFAULT 'WEB' CHECK (source IN ('WEB','OFFLINE','PASTE'))
);
CREATE INDEX IF NOT EXISTS idx_pedagogy_grade_history ON pedagogy_grade_history(grade_id, changed_at);

CREATE TABLE IF NOT EXISTS pedagogy_conduct_facts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  academic_year_id uuid NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
  class_id uuid NOT NULL REFERENCES school_classes(id) ON DELETE CASCADE,
  student_id uuid NOT NULL REFERENCES students(id),
  period_code varchar(4) NOT NULL CHECK (period_code IN ('P1','P2','P3','P4','P5','P6')),
  rule_code varchar(32) NOT NULL,
  rule_label varchar(120) NOT NULL,
  points smallint NOT NULL CHECK (points BETWEEN -50 AND 20 AND points <> 0),
  grave boolean NOT NULL DEFAULT false,
  note varchar(300),
  occurred_on date NOT NULL DEFAULT CURRENT_DATE,
  reported_by uuid REFERENCES school_memberships(id),
  reported_at timestamptz NOT NULL DEFAULT now(),
  cancelled_at timestamptz,
  cancelled_by uuid REFERENCES school_memberships(id),
  cancel_reason varchar(300),
  CHECK ((cancelled_at IS NULL) = (cancel_reason IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_pedagogy_conduct_facts_pupil ON pedagogy_conduct_facts(school_id, academic_year_id, student_id, period_code) WHERE cancelled_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_pedagogy_conduct_facts_class ON pedagogy_conduct_facts(school_id, class_id, period_code);

CREATE TABLE IF NOT EXISTS pedagogy_conduct_adjustments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  academic_year_id uuid NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
  student_id uuid NOT NULL REFERENCES students(id),
  period_code varchar(4) NOT NULL CHECK (period_code IN ('P1','P2','P3','P4','P5','P6')),
  points smallint NOT NULL CHECK (points BETWEEN -100 AND 100 AND points <> 0),
  reason varchar(300) NOT NULL CHECK (length(btrim(reason)) >= 5),
  adjusted_by uuid REFERENCES school_memberships(id),
  adjusted_at timestamptz NOT NULL DEFAULT now()
);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['pedagogy_grades','pedagogy_grade_history','pedagogy_conduct_facts','pedagogy_conduct_adjustments'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (school_id = current_setting(''app.school_id'', true)::uuid) '
                   'WITH CHECK (school_id = current_setting(''app.school_id'', true)::uuid)', t);
  END LOOP;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_tenant') THEN
    -- never deleted: a mark is emptied, a fact is cancelled (parent project: no physical deletion)
    GRANT SELECT, INSERT, UPDATE ON pedagogy_grades, pedagogy_conduct_facts TO edusync_tenant;
    GRANT SELECT, INSERT ON pedagogy_grade_history, pedagogy_conduct_adjustments TO edusync_tenant;
    GRANT USAGE, SELECT ON SEQUENCE pedagogy_grade_history_id_seq TO edusync_tenant;
  END IF;
END $$;

INSERT INTO capability_catalog(code,domain_name,group_name,label,action_code,risk,offline_policy,audit_required,
  scope_types,source_status,prerequisites,outputs,sensitive,notes,registry_version)
VALUES
 ('pedagogy.grades.enter','Pédagogie','Cotes','Saisir les cotes de ses cours','enter','MEDIUM','LOCAL_WRITE_SYNC',true,
  '["SCHOOL"]','OWNER_APPROVED','["pedagogy.teaching.own.read"]','[]',true,'Seulement les cours attribués à l’enseignant (projet père)','3.0.0'),
 ('pedagogy.grades.read','Pédagogie','Cotes','Suivre la saisie des cotes et consulter les cotes','read','LOW','SERVER_ONLY',false,
  '["SCHOOL","SECTION"]','OWNER_APPROVED','["pedagogy.referential.read"]','[]',true,'Préfet, directeurs : lecture et suivi, sans saisie (projet père)','3.0.0'),
 ('pedagogy.conduct.report','Pédagogie','Conduite','Signaler un fait de conduite','report','LOW','LOCAL_WRITE_SYNC',true,
  '["SCHOOL","SECTION"]','OWNER_APPROVED','["pedagogy.referential.read"]','[]',true,'Conduite calculée (permis à points)','3.0.0'),
 ('pedagogy.conduct.manage','Pédagogie','Conduite','Signaler les faits graves, annuler un fait, ajuster une conduite','manage','MEDIUM','SERVER_ONLY',true,
  '["SCHOOL","SECTION"]','OWNER_APPROVED','["pedagogy.conduct.report"]','[]',true,'Directeur de discipline, préfet ; motif obligatoire','3.0.0')
ON CONFLICT (code) DO UPDATE SET label=EXCLUDED.label, notes=EXCLUDED.notes, active=true, updated_at=now();
UPDATE capability_catalog SET school_adjustable=true
 WHERE code IN ('pedagogy.grades.enter','pedagogy.grades.read','pedagogy.conduct.report','pedagogy.conduct.manage');

WITH grants(role_code, capability_code) AS (VALUES
  ('ENSEIGNANT','pedagogy.grades.enter'), ('ENSEIGNANT','pedagogy.conduct.report'),
  ('ADMIN_SYSTEME_ECOLE','pedagogy.grades.read'), ('PROMOTEUR','pedagogy.grades.read'), ('PREFET_ETUDES','pedagogy.grades.read'),
  ('DIRECTEUR_ETUDES','pedagogy.grades.read'), ('DIRECTION_SECTION','pedagogy.grades.read'),
  ('PREFET_ETUDES','pedagogy.conduct.report'), ('PREFET_ETUDES','pedagogy.conduct.manage'),
  ('DIRECTEUR_DISCIPLINE','pedagogy.conduct.report'), ('DIRECTEUR_DISCIPLINE','pedagogy.conduct.manage'),
  ('DIRECTEUR_ETUDES','pedagogy.conduct.report'), ('DIRECTION_SECTION','pedagogy.conduct.report')
)
INSERT INTO rbac_role_capabilities(role_id, capability_code)
SELECT r.id, g.capability_code FROM grants g JOIN rbac_roles r ON r.code=g.role_code AND r.kind='SCHOOL_STANDARD'
JOIN capability_catalog c ON c.code=g.capability_code
ON CONFLICT DO NOTHING;
