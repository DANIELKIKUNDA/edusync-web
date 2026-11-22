-- EduSync V2, lot 3a — teachers, course assignments, class titulars, conduct scale (owner, 2026-11-22). Additive only.
-- Parent project rules: grades are entered only by the ENSEIGNANT who teaches that course in that class; a class has one
-- titular (an ENSEIGNANT); the titular's powers are effective in maternelle / primaire. Owner: a teacher may be titular of
-- 2 or 3 classes; conduct is COMPUTED from reported facts (points licence), each school has its own scale.

INSERT INTO rbac_roles(code,label,description,level,kind,status)
VALUES ('ENSEIGNANT','Enseignant','Saisit les cotes des cours qui lui sont attribués et signale les faits de conduite. Voit ses classes, ses cours et le référentiel.','SCHOOL','SCHOOL_STANDARD','ACTIVE')
ON CONFLICT (code) WHERE kind='SCHOOL_STANDARD' DO UPDATE SET
  label=EXCLUDED.label, description=EXCLUDED.description, status='ACTIVE', version=rbac_roles.version+1, updated_at=now();

CREATE TABLE IF NOT EXISTS pedagogy_teaching_assignments (
  class_id uuid NOT NULL REFERENCES school_classes(id) ON DELETE CASCADE,
  course_code varchar(96) NOT NULL REFERENCES ref_courses(code),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  membership_id uuid NOT NULL REFERENCES school_memberships(id) ON DELETE CASCADE,
  assigned_by uuid REFERENCES users(id),
  assigned_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (class_id, course_code)
);
CREATE INDEX IF NOT EXISTS idx_pedagogy_teaching_member ON pedagogy_teaching_assignments(school_id, membership_id);

-- one titular per class; the same teacher may hold several classes (owner, 2026-11-22)
CREATE TABLE IF NOT EXISTS pedagogy_class_titulars (
  class_id uuid PRIMARY KEY REFERENCES school_classes(id) ON DELETE CASCADE,
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  membership_id uuid NOT NULL REFERENCES school_memberships(id) ON DELETE CASCADE,
  assigned_by uuid REFERENCES users(id),
  assigned_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_pedagogy_titular_member ON pedagogy_class_titulars(school_id, membership_id);

CREATE TABLE IF NOT EXISTS pedagogy_conduct_rules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  code varchar(32) NOT NULL CHECK (code ~ '^[A-Z0-9_]{2,32}$'),
  label varchar(120) NOT NULL CHECK (length(btrim(label)) >= 3),
  points smallint NOT NULL CHECK (points BETWEEN -50 AND 20 AND points <> 0),
  grave boolean NOT NULL DEFAULT false,
  active boolean NOT NULL DEFAULT true,
  sort_order smallint NOT NULL DEFAULT 1,
  updated_by uuid REFERENCES users(id),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (school_id, code)
);

CREATE TABLE IF NOT EXISTS pedagogy_conduct_settings (
  school_id uuid PRIMARY KEY REFERENCES schools(id) ON DELETE CASCADE,
  late_rule_code varchar(32) NOT NULL DEFAULT 'RETARD',
  late_threshold smallint NOT NULL DEFAULT 5 CHECK (late_threshold BETWEEN 0 AND 20),
  late_penalty smallint NOT NULL DEFAULT 5 CHECK (late_penalty BETWEEN 0 AND 50),
  alert_below smallint NOT NULL DEFAULT 50 CHECK (alert_below BETWEEN 0 AND 100),
  updated_by uuid REFERENCES users(id),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0)
);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['pedagogy_teaching_assignments','pedagogy_class_titulars','pedagogy_conduct_rules','pedagogy_conduct_settings'] LOOP
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
 ('pedagogy.teaching.own.read','Pédagogie','Enseignants','Voir ses classes, ses cours et ses titulariats','read','LOW','SERVER_ONLY',false,
  '["SCHOOL"]','OWNER_APPROVED','[]','[]',false,'Rôle Enseignant ; module Pédagogie (V2) requis','3.0.0'),
 ('pedagogy.teaching.manage','Pédagogie','Enseignants','Attribuer les cours aux enseignants et choisir les titulaires','manage','MEDIUM','SERVER_ONLY',true,
  '["SCHOOL","SECTION"]','OWNER_APPROVED','["pedagogy.referential.read"]','[]',false,'Module Pédagogie (V2) requis','3.0.0'),
 ('pedagogy.conduct.configure','Pédagogie','Conduite','Régler le barème de conduite de l’école','configure','MEDIUM','SERVER_ONLY',true,
  '["SCHOOL"]','OWNER_APPROVED','["pedagogy.referential.read"]','[]',false,'Conduite calculée (permis à points) ; module Pédagogie (V2) requis','3.0.0')
ON CONFLICT (code) DO UPDATE SET label=EXCLUDED.label, notes=EXCLUDED.notes, active=true, updated_at=now();
UPDATE capability_catalog SET school_adjustable=true
 WHERE code IN ('pedagogy.teaching.own.read','pedagogy.teaching.manage','pedagogy.conduct.configure');

WITH grants(role_code, capability_code) AS (VALUES
  ('ENSEIGNANT','pedagogy.teaching.own.read'), ('ENSEIGNANT','pedagogy.referential.read'),
  ('ADMIN_SYSTEME_ECOLE','pedagogy.teaching.manage'), ('PREFET_ETUDES','pedagogy.teaching.manage'),
  ('DIRECTEUR_ETUDES','pedagogy.teaching.manage'), ('DIRECTION_SECTION','pedagogy.teaching.manage'),
  ('ADMIN_SYSTEME_ECOLE','pedagogy.conduct.configure'), ('PREFET_ETUDES','pedagogy.conduct.configure'),
  ('DIRECTEUR_DISCIPLINE','pedagogy.conduct.configure'), ('DIRECTEUR_DISCIPLINE','pedagogy.referential.read')
)
INSERT INTO rbac_role_capabilities(role_id, capability_code)
SELECT r.id, g.capability_code FROM grants g JOIN rbac_roles r ON r.code=g.role_code AND r.kind='SCHOOL_STANDARD'
JOIN capability_catalog c ON c.code=g.capability_code
ON CONFLICT DO NOTHING;
