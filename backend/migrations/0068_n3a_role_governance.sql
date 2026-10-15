-- N3-A / G-ROLE-1 (owner decision 2026-10-15). There is no 1:1 mapping between the composite Desktop roles and the Web
-- roles: technical administration/configuration → ADMIN_SYSTEME_ECOLE ; superior business/financial governance →
-- GESTIONNAIRE ; operational cash desk → CAISSIER ; consultation/control → the read roles already approved.
-- PROMOTEUR, RESPONSABLE_FINANCE, PREFET_ETUDES and DIRECTION_SECTION are not modified. SCHOOL_CUSTOM delegation stays open.

-- Two rights that did not exist: the superior correction of any payment (another cashier's payment, or a closed session),
-- distinct from the cashier's correction of his own payment in his open session (finance.payments.reverse), and the
-- global closure of the school's cash day, distinct from the individual session closure (finance.cash.close).
INSERT INTO capability_catalog(code,domain_name,group_name,label,action_code,risk,offline_policy,audit_required,scope_types,source_status,registry_version) VALUES
 ('finance.payments.reverse.supervisor','Centre financier','Encaissements & reçus','Annuler ou rembourser tout paiement (autorité supérieure)','reverse','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'OWNER_APPROVED','0.68.0'),
 ('finance.cash.day.close','Centre financier','Caisse','Clôturer la journée de caisse de l''école','close','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'OWNER_APPROVED','0.68.0')
ON CONFLICT(code) DO NOTHING;

WITH grants(role_code,capability_code) AS (VALUES
  ('GESTIONNAIRE','finance.payments.reverse.supervisor'),
  ('GESTIONNAIRE','finance.advance_funds.refund'),
  ('GESTIONNAIRE','finance.cash.reopen'),
  ('GESTIONNAIRE','finance.cash.day.close'),
  ('GESTIONNAIRE','finance.decisions.create'),
  ('GESTIONNAIRE','finance.decisions.cancel'),
  ('GESTIONNAIRE','finance.decisions.read'),
  ('GESTIONNAIRE','finance.responsibility.set'),
  ('GESTIONNAIRE','finance.responsibility.read'),
  ('GESTIONNAIRE','personnel.staff_children.finance_mode'),
  ('GESTIONNAIRE','personnel.payroll_deduction.confirm'),
  ('GESTIONNAIRE','personnel.payroll_deduction.cancel'),
  ('CAISSIER','finance.cash.expense.create')
)
INSERT INTO rbac_role_capabilities(role_id,capability_code)
SELECT r.id,g.capability_code FROM grants g JOIN rbac_roles r ON r.code=g.role_code AND r.kind='SCHOOL_STANDARD'
JOIN capability_catalog c ON c.code=g.capability_code
ON CONFLICT DO NOTHING;

-- The cashier no longer refunds an advance fund freely: that operation belongs to the GESTIONNAIRE.
DELETE FROM rbac_role_capabilities rc USING rbac_roles r
 WHERE rc.role_id=r.id AND r.code='CAISSIER' AND r.kind='SCHOOL_STANDARD' AND rc.capability_code='finance.advance_funds.refund';
