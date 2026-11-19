-- Daily section supervision does not grant school-wide financial migration.
-- Preserve custom delegations, import batches, imported data and offline operations.
DELETE FROM rbac_role_capabilities rc USING rbac_roles r
 WHERE rc.role_id=r.id AND r.kind='SCHOOL_STANDARD' AND r.school_id IS NULL
   AND r.code IN ('PREFET_ETUDES','DIRECTION_SECTION')
   AND rc.capability_code IN ('migration.finance_history.analyze','migration.finance_history.execute');
