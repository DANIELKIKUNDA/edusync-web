-- Owner decision 2026-10-28 (certification Responsable financier / Promoteur): the financial history import may be
-- ANALYSED by the Promoteur and the Responsable chargé des finances, never EXECUTED by them. Executing it writes old
-- payments and debts into the school's accounts — a mutation that contradicts both contracts (Promoteur: « aucune
-- mutation » ; Responsable financier: « contrôle et lecture, pas de manipulation »). Execution stays with the
-- Gestionnaire and the Caissier; a school may still grant it to a role of its choice (Accès & rôles, school adjustable).
-- Reviewed removal migration (tools/ci/rbac_registry.py: removals are migrations of their own).
DELETE FROM rbac_role_capabilities rc USING rbac_roles r
 WHERE rc.role_id = r.id AND r.kind = 'SCHOOL_STANDARD' AND r.school_id IS NULL
   AND r.code IN ('PROMOTEUR', 'RESPONSABLE_FINANCE')
   AND rc.capability_code = 'migration.finance_history.execute';
