-- Owner decisions 2026-10-24 (standard school roles).
--  1. Imports: student import (analyse, execution, Excel template) → SECRÉTARIAT; staff import (analyse, execution) →
--     GESTIONNAIRE. They were held by no standard role (registry: UNDECIDED_BY_OWNER / no role).
--  2. « En RDC, le caissier est généralement aussi le secrétaire » : the CAISSIER standard role holds EVERY capability
--     of the SECRÉTARIAT standard role (enrollments, student files, families, communication, headcounts, personnel…),
--     unless the school decides otherwise: each of these capabilities stays school-adjustable (Accès & rôles).
-- Additive only: no capability is removed from any role. No separation-of-duties rule is hit (registry sod_rules).

INSERT INTO rbac_role_capabilities(role_id, capability_code)
SELECT r.id, c FROM rbac_roles r, unnest(ARRAY['migration.students.analyze','migration.students.execute','documents.student_import_template.export']::varchar[]) c
 WHERE r.code = 'SECRETARIAT' AND r.kind = 'SCHOOL_STANDARD' AND r.school_id IS NULL
ON CONFLICT DO NOTHING;

INSERT INTO rbac_role_capabilities(role_id, capability_code)
SELECT r.id, c FROM rbac_roles r, unnest(ARRAY['migration.staff.analyze','migration.staff.execute']::varchar[]) c
 WHERE r.code = 'GESTIONNAIRE' AND r.kind = 'SCHOOL_STANDARD' AND r.school_id IS NULL
ON CONFLICT DO NOTHING;

INSERT INTO rbac_role_capabilities(role_id, capability_code)
SELECT cais.id, rc.capability_code
  FROM rbac_roles cais
  JOIN rbac_roles sec ON sec.code = 'SECRETARIAT' AND sec.kind = 'SCHOOL_STANDARD' AND sec.school_id IS NULL
  JOIN rbac_role_capabilities rc ON rc.role_id = sec.id
 WHERE cais.code = 'CAISSIER' AND cais.kind = 'SCHOOL_STANDARD' AND cais.school_id IS NULL
ON CONFLICT DO NOTHING;
