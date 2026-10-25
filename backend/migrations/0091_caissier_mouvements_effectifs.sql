-- Owner decision 2026-10-25: the CAISSIER standard role may read the headcount movements journal (abandons, transfers,
-- reinstatements, class changes) in « Effectifs & dépôts ». The capability stays school-adjustable (Accès & rôles).
-- Additive only; no separation-of-duties rule involves this read capability (registry sod_rules).
INSERT INTO rbac_role_capabilities(role_id, capability_code)
SELECT r.id, 'headcounts.movements.read' FROM rbac_roles r
 WHERE r.code = 'CAISSIER' AND r.kind = 'SCHOOL_STANDARD' AND r.school_id IS NULL
ON CONFLICT DO NOTHING;
