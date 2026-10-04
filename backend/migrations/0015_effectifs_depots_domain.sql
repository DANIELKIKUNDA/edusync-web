-- EduSync Point 4D — Effectifs & Dépôts Web (2026-09-12)
-- Preservation-first: the certified Desktop read models remain the business oracle.
-- Scope values: ALL / MATERNELLE / PRIMAIRE / SECONDAIRE.

CREATE TABLE IF NOT EXISTS material_contributions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  academic_year_id uuid NOT NULL REFERENCES academic_years(id),
  student_id uuid NOT NULL REFERENCES students(id),
  enrollment_id uuid NOT NULL REFERENCES enrollments(id),
  contribution_type_id uuid NOT NULL REFERENCES contribution_types(id),
  quantity numeric(14,3) NOT NULL CHECK (quantity > 0),
  deposited_on date NOT NULL DEFAULT CURRENT_DATE,
  notes text,
  recorded_by uuid REFERENCES users(id),
  client_operation_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(school_id,client_operation_id)
);
CREATE INDEX IF NOT EXISTS idx_material_contributions_register
  ON material_contributions(school_id,academic_year_id,deposited_on DESC,student_id);
CREATE INDEX IF NOT EXISTS idx_material_contributions_type
  ON material_contributions(school_id,academic_year_id,contribution_type_id);

-- A deposit is an append-only physical contribution event. Corrections are separate future events,
-- never a silent rewrite of historical deposits.
CREATE OR REPLACE FUNCTION validate_material_contribution() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE y_status text; enrollment_year uuid; enrollment_student uuid; enrollment_school uuid; type_school uuid;
BEGIN
  SELECT status INTO y_status FROM academic_years WHERE id=NEW.academic_year_id AND school_id=NEW.school_id;
  IF y_status IS DISTINCT FROM 'ACTIVE' THEN RAISE EXCEPTION 'Les dépôts matériels sont enregistrables uniquement dans l''année ACTIVE'; END IF;
  SELECT academic_year_id,student_id,school_id INTO enrollment_year,enrollment_student,enrollment_school FROM enrollments WHERE id=NEW.enrollment_id;
  IF enrollment_school IS DISTINCT FROM NEW.school_id OR enrollment_year IS DISTINCT FROM NEW.academic_year_id OR enrollment_student IS DISTINCT FROM NEW.student_id THEN
    RAISE EXCEPTION 'Inscription incohérente avec le dépôt matériel';
  END IF;
  SELECT school_id INTO type_school FROM contribution_types WHERE id=NEW.contribution_type_id AND enabled;
  IF type_school IS DISTINCT FROM NEW.school_id THEN RAISE EXCEPTION 'Type de contribution invalide pour cette école'; END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_validate_material_contribution ON material_contributions;
CREATE TRIGGER trg_validate_material_contribution BEFORE INSERT ON material_contributions
FOR EACH ROW EXECUTE FUNCTION validate_material_contribution();

CREATE OR REPLACE FUNCTION forbid_material_contribution_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Le registre des dépôts matériels est append-only'; END $$;
DROP TRIGGER IF EXISTS trg_material_contribution_no_update ON material_contributions;
CREATE TRIGGER trg_material_contribution_no_update BEFORE UPDATE OR DELETE ON material_contributions
FOR EACH ROW EXECUTE FUNCTION forbid_material_contribution_mutation();

ALTER TABLE material_contributions ENABLE ROW LEVEL SECURITY;
ALTER TABLE material_contributions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_material_contributions ON material_contributions;
CREATE POLICY tenant_material_contributions ON material_contributions
  USING (school_id = current_setting('app.school_id', true)::uuid)
  WITH CHECK (school_id = current_setting('app.school_id', true)::uuid);
GRANT SELECT,INSERT ON material_contributions TO edusync_tenant;
REVOKE UPDATE,DELETE ON material_contributions FROM edusync_tenant;

-- Terrain correction from Point 4C: new enrollments require sex M/F.
-- Only repair the exact legacy default; never overwrite a school's customized policy.
UPDATE school_policy_documents
SET payload = jsonb_set(
    (payload - 'optional_student_fields'),
    '{required_student_fields}',
    '["last_name","middle_name","first_name","gender","class_id"]'::jsonb,
    true
  ) || jsonb_build_object(
    'optional_student_fields',
    '["birth_date","birth_place","nationality","address","previous_school"]'::jsonb
  ),
  updated_at=now(), version=version+1
WHERE kind='ENROLLMENT' AND status='ACTIVE'
  AND payload->'required_student_fields' = '["last_name","middle_name","first_name","class_id"]'::jsonb
  AND coalesce(payload->>'guardian_required_at_enrollment','false')='false';
