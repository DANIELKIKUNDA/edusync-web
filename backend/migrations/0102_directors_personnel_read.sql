-- Owner decision 2026-10-30 (certification Directeur des études / Directeur de discipline): both Directors READ the
-- staff of their section — the original grants of migration 0009 that 0024 (point 9) had removed. Read only: no export,
-- no change. Visibility follows the section isolation (decision 2026-10-28): only agents assigned to the section,
-- never agents of other sections nor agents assigned to the whole school. Additive grant, school-adjustable.
INSERT INTO rbac_role_capabilities(role_id, capability_code)
SELECT r.id, c FROM rbac_roles r, unnest(ARRAY['personnel.read','personnel.assignments.read','personnel.functions.read','personnel.summary.read']::varchar[]) c
 WHERE r.code = 'DIRECTEUR_ETUDES' AND r.kind = 'SCHOOL_STANDARD' AND r.school_id IS NULL
ON CONFLICT DO NOTHING;
INSERT INTO rbac_role_capabilities(role_id, capability_code)
SELECT r.id, c FROM rbac_roles r, unnest(ARRAY['personnel.read','personnel.assignments.read','personnel.functions.read']::varchar[]) c
 WHERE r.code = 'DIRECTEUR_DISCIPLINE' AND r.kind = 'SCHOOL_STANDARD' AND r.school_id IS NULL
ON CONFLICT DO NOTHING;
