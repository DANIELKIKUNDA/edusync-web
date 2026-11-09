-- Owner decision 2026-11-09: historical finance import is a migration operation, not a daily supervision tool.
-- It is therefore absent from Promoteur, Responsable chargé des finances and Gestionnaire by default. A school may
-- still delegate analyse/execution explicitly through a custom role when an authorised migration is planned.
DELETE FROM rbac_role_capabilities rc USING rbac_roles r
 WHERE rc.role_id = r.id AND r.kind = 'SCHOOL_STANDARD' AND r.school_id IS NULL
   AND r.code IN ('PROMOTEUR', 'RESPONSABLE_FINANCE', 'GESTIONNAIRE')
   AND rc.capability_code IN ('migration.finance_history.analyze', 'migration.finance_history.execute');
