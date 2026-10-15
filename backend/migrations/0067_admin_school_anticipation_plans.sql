-- N3-A / G-PLAN-1 (owner decision 2026-10-15): the school system administrator creates and (de)activates the payment
-- plans by default. Desktop golden master: save_anticipation_plan / set_anticipation_plan_active require ADMIN.
-- Only ADMIN_SYSTEME_ECOLE is extended (manage + the read needed to see the plans); no other standard role is widened.
-- A school may delegate the right through a SCHOOL_CUSTOM role. The cashier keeps read / membership / collect (0008).
WITH grants(role_code,capability_code) AS (VALUES
  ('ADMIN_SYSTEME_ECOLE','finance.anticipation_plans.manage'),
  ('ADMIN_SYSTEME_ECOLE','finance.anticipation_plans.read')
)
INSERT INTO rbac_role_capabilities(role_id,capability_code)
SELECT r.id,g.capability_code FROM grants g JOIN rbac_roles r ON r.code=g.role_code AND r.kind='SCHOOL_STANDARD'
JOIN capability_catalog c ON c.code=g.capability_code
ON CONFLICT DO NOTHING;
