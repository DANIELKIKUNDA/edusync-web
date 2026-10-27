-- Owner decision 2026-10-27 (Gestionnaire certification): « le Gestionnaire n'est pas un opérateur permanent, c'est un
-- chef ; exiger qu'il clôture la journée est une absurdité » — he would block the cashiers' day.
-- The GESTIONNAIRE standard role no longer closes nor reopens the school's cash day. Nothing requires a closed day
-- (closing only blocks further collections of that day; each cashier closes HIS session), so no standard role holds
-- these two capabilities any more; a school may still grant them to a role of its choice (Accès & rôles, school
-- adjustable). Reviewed removal migration (tools/ci/rbac_registry.py: removals are migrations of their own).
DELETE FROM rbac_role_capabilities rc USING rbac_roles r
 WHERE rc.role_id = r.id AND r.kind = 'SCHOOL_STANDARD' AND r.school_id IS NULL AND r.code = 'GESTIONNAIRE'
   AND rc.capability_code IN ('finance.cash.day.close', 'finance.cash.reopen');
