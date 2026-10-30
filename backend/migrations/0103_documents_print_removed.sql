-- Owner decision 2026-10-30: « imprimer un document » is already covered by opening it (documents.open: the in-app
-- viewer prints). documents.print was PLANNED, protected nothing and had no route: it is removed from every standard
-- role. Reviewed removal migration (tools/ci/rbac_registry.py: removals are migrations of their own).
DELETE FROM rbac_role_capabilities rc USING rbac_roles r
 WHERE rc.role_id = r.id AND r.kind = 'SCHOOL_STANDARD' AND r.school_id IS NULL AND rc.capability_code = 'documents.print';
