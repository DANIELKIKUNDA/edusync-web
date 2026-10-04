-- EduSync Point 3B addendum — leadership roles limited to Secondaire (2026-09-12)

INSERT INTO rbac_roles(code,label,description,level,kind,status)
VALUES ('DIRECTEUR_ETUDES','Directeur des études','Secondaire uniquement. Suivi pédagogique/scolaire et consultation. Finance exclue de la baseline; lecture financière ajoutable explicitement par permission si l’école le décide.','SCHOOL','SCHOOL_STANDARD','ACTIVE')
ON CONFLICT (code) WHERE kind='SCHOOL_STANDARD' DO UPDATE SET
  label=EXCLUDED.label, description=EXCLUDED.description, status='ACTIVE', version=rbac_roles.version+1, updated_at=now();

DELETE FROM rbac_role_capabilities rc USING rbac_roles r WHERE rc.role_id=r.id AND r.kind='SCHOOL_STANDARD' AND r.code='DIRECTEUR_ETUDES';

WITH grants(role_code, capability_code) AS (VALUES
  ('DIRECTEUR_ETUDES','audit.entity.history.read'),
  ('DIRECTEUR_ETUDES','communications.compose'),
  ('DIRECTEUR_ETUDES','communications.history.read'),
  ('DIRECTEUR_ETUDES','communications.read'),
  ('DIRECTEUR_ETUDES','communications.send.class'),
  ('DIRECTEUR_ETUDES','communications.send.individual'),
  ('DIRECTEUR_ETUDES','communications.send.section'),
  ('DIRECTEUR_ETUDES','communications.sms.send'),
  ('DIRECTEUR_ETUDES','dashboard.school.drilldown'),
  ('DIRECTEUR_ETUDES','dashboard.school.export'),
  ('DIRECTEUR_ETUDES','dashboard.school.print'),
  ('DIRECTEUR_ETUDES','dashboard.school.read'),
  ('DIRECTEUR_ETUDES','documents.history.read'),
  ('DIRECTEUR_ETUDES','documents.open'),
  ('DIRECTEUR_ETUDES','documents.print'),
  ('DIRECTEUR_ETUDES','enrollments.export_pdf'),
  ('DIRECTEUR_ETUDES','enrollments.export_xlsx'),
  ('DIRECTEUR_ETUDES','enrollments.print'),
  ('DIRECTEUR_ETUDES','enrollments.read'),
  ('DIRECTEUR_ETUDES','families.children.read'),
  ('DIRECTEUR_ETUDES','families.read'),
  ('DIRECTEUR_ETUDES','families.responsibles.read'),
  ('DIRECTEUR_ETUDES','headcounts.by_class.read'),
  ('DIRECTEUR_ETUDES','headcounts.by_option.read'),
  ('DIRECTEUR_ETUDES','headcounts.by_section.read'),
  ('DIRECTEUR_ETUDES','headcounts.export_pdf'),
  ('DIRECTEUR_ETUDES','headcounts.export_xlsx'),
  ('DIRECTEUR_ETUDES','headcounts.movements.read'),
  ('DIRECTEUR_ETUDES','headcounts.print'),
  ('DIRECTEUR_ETUDES','headcounts.read'),
  ('DIRECTEUR_ETUDES','notifications.internal.dismiss'),
  ('DIRECTEUR_ETUDES','notifications.internal.read'),
  ('DIRECTEUR_ETUDES','personnel.assignments.read'),
  ('DIRECTEUR_ETUDES','personnel.functions.read'),
  ('DIRECTEUR_ETUDES','personnel.read'),
  ('DIRECTEUR_ETUDES','personnel.summary.read'),
  ('DIRECTEUR_ETUDES','settings.academic_year.read'),
  ('DIRECTEUR_ETUDES','settings.school_identity.read'),
  ('DIRECTEUR_ETUDES','settings.structure.read'),
  ('DIRECTEUR_ETUDES','students.lifecycle.history.read'),
  ('DIRECTEUR_ETUDES','students.read')
)
INSERT INTO rbac_role_capabilities(role_id,capability_code)
SELECT r.id,g.capability_code FROM grants g JOIN rbac_roles r ON r.code=g.role_code AND r.kind='SCHOOL_STANDARD'
JOIN capability_catalog c ON c.code=g.capability_code
ON CONFLICT DO NOTHING;

INSERT INTO rbac_roles(code,label,description,level,kind,status)
VALUES ('DIRECTEUR_DISCIPLINE','Directeur de discipline','Secondaire uniquement. Suivi quotidien des élèves et communication forte avec les parents. Finance exclue de la baseline; toute extension reste configurable.','SCHOOL','SCHOOL_STANDARD','ACTIVE')
ON CONFLICT (code) WHERE kind='SCHOOL_STANDARD' DO UPDATE SET
  label=EXCLUDED.label, description=EXCLUDED.description, status='ACTIVE', version=rbac_roles.version+1, updated_at=now();

DELETE FROM rbac_role_capabilities rc USING rbac_roles r WHERE rc.role_id=r.id AND r.kind='SCHOOL_STANDARD' AND r.code='DIRECTEUR_DISCIPLINE';

WITH grants(role_code, capability_code) AS (VALUES
  ('DIRECTEUR_DISCIPLINE','audit.entity.history.read'),
  ('DIRECTEUR_DISCIPLINE','communications.compose'),
  ('DIRECTEUR_DISCIPLINE','communications.history.read'),
  ('DIRECTEUR_DISCIPLINE','communications.read'),
  ('DIRECTEUR_DISCIPLINE','communications.send.class'),
  ('DIRECTEUR_DISCIPLINE','communications.send.individual'),
  ('DIRECTEUR_DISCIPLINE','communications.send.section'),
  ('DIRECTEUR_DISCIPLINE','communications.sms.bulk_send'),
  ('DIRECTEUR_DISCIPLINE','communications.sms.send'),
  ('DIRECTEUR_DISCIPLINE','dashboard.school.drilldown'),
  ('DIRECTEUR_DISCIPLINE','dashboard.school.export'),
  ('DIRECTEUR_DISCIPLINE','dashboard.school.print'),
  ('DIRECTEUR_DISCIPLINE','dashboard.school.read'),
  ('DIRECTEUR_DISCIPLINE','documents.history.read'),
  ('DIRECTEUR_DISCIPLINE','documents.open'),
  ('DIRECTEUR_DISCIPLINE','documents.print'),
  ('DIRECTEUR_DISCIPLINE','enrollments.export_pdf'),
  ('DIRECTEUR_DISCIPLINE','enrollments.print'),
  ('DIRECTEUR_DISCIPLINE','enrollments.read'),
  ('DIRECTEUR_DISCIPLINE','families.children.read'),
  ('DIRECTEUR_DISCIPLINE','families.read'),
  ('DIRECTEUR_DISCIPLINE','families.responsibles.read'),
  ('DIRECTEUR_DISCIPLINE','headcounts.by_class.read'),
  ('DIRECTEUR_DISCIPLINE','headcounts.by_section.read'),
  ('DIRECTEUR_DISCIPLINE','headcounts.movements.read'),
  ('DIRECTEUR_DISCIPLINE','headcounts.print'),
  ('DIRECTEUR_DISCIPLINE','headcounts.read'),
  ('DIRECTEUR_DISCIPLINE','notifications.internal.dismiss'),
  ('DIRECTEUR_DISCIPLINE','notifications.internal.read'),
  ('DIRECTEUR_DISCIPLINE','personnel.assignments.read'),
  ('DIRECTEUR_DISCIPLINE','personnel.functions.read'),
  ('DIRECTEUR_DISCIPLINE','personnel.read'),
  ('DIRECTEUR_DISCIPLINE','settings.academic_year.read'),
  ('DIRECTEUR_DISCIPLINE','settings.school_identity.read'),
  ('DIRECTEUR_DISCIPLINE','settings.structure.read'),
  ('DIRECTEUR_DISCIPLINE','students.identity.update'),
  ('DIRECTEUR_DISCIPLINE','students.lifecycle.history.read'),
  ('DIRECTEUR_DISCIPLINE','students.read')
)
INSERT INTO rbac_role_capabilities(role_id,capability_code)
SELECT r.id,g.capability_code FROM grants g JOIN rbac_roles r ON r.code=g.role_code AND r.kind='SCHOOL_STANDARD'
JOIN capability_catalog c ON c.code=g.capability_code
ON CONFLICT DO NOTHING;


-- Hard guard: these standard leadership roles are valid only for SECTION=SECONDAIRE.
CREATE OR REPLACE FUNCTION validate_secondary_standard_role_scope()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE role_code text;
BEGIN
  SELECT r.code INTO role_code
    FROM rbac_assignments a
    JOIN rbac_roles r ON r.id=a.role_id
   WHERE a.id=NEW.assignment_id;
  IF role_code IN ('PREFET_ETUDES','DIRECTEUR_ETUDES','DIRECTEUR_DISCIPLINE') THEN
    IF NEW.scope_type <> 'SECTION' OR upper(coalesce(NEW.scope_value,'')) <> 'SECONDAIRE' THEN
      RAISE EXCEPTION 'Le rôle % est limité à la section SECONDAIRE', role_code;
    END IF;
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_secondary_standard_role_scope ON rbac_assignment_scopes;
CREATE TRIGGER trg_secondary_standard_role_scope
BEFORE INSERT OR UPDATE ON rbac_assignment_scopes
FOR EACH ROW EXECUTE FUNCTION validate_secondary_standard_role_scope();
