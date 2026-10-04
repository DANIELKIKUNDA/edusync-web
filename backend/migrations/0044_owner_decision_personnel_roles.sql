-- Owner decision 2026-10-02 (Daniel) — Personnel mutations for standard school roles.
-- Before: every personnel mutation was UNDECIDED_BY_OWNER, so the Personnel module was read-only for
-- all standard roles (no one could add an agent or record a departure, leaving leavers' access active).
--   GESTIONNAIRE : add, update, assignments add/end, functions catalogue, record a departure (exit).
--   SECRETARIAT  : add and update an agent's record only (data entry), never exit.
--   Reactivation of a departed agent stays CUSTOM-ONLY (it restores access): not granted here.
--   Payroll deductions (finance-related) remain undecided.
-- Standard roles are product baselines; each school keeps its own policy through SCHOOL_CUSTOM roles.
INSERT INTO rbac_role_capabilities(role_id, capability_code)
SELECT r.id, g.capability_code
FROM (VALUES
  ('GESTIONNAIRE', 'personnel.create'),
  ('GESTIONNAIRE', 'personnel.update'),
  ('GESTIONNAIRE', 'personnel.assignments.add'),
  ('GESTIONNAIRE', 'personnel.assignments.end'),
  ('GESTIONNAIRE', 'personnel.functions.manage'),
  ('GESTIONNAIRE', 'personnel.exit'),
  ('SECRETARIAT',  'personnel.create'),
  ('SECRETARIAT',  'personnel.update')
) AS g(role_code, capability_code)
JOIN rbac_roles r ON r.code = g.role_code AND r.kind = 'SCHOOL_STANDARD' AND r.status = 'ACTIVE'
JOIN capability_catalog c ON c.code = g.capability_code
ON CONFLICT DO NOTHING;
