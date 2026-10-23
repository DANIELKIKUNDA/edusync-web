-- Reverses 0085 (never run automatically; owner decision 12: strictly additive AND reversible).
-- Restores the exact pre-0085 state: the canonical *.export rows added to roles and the catalog are removed, the new
-- tables and columns dropped. Format variant capabilities were never touched by 0085, so every role keeps its grants.
BEGIN;
DROP TABLE IF EXISTS rbac_change_requests, rbac_school_sod_overrides, rbac_sod_rules, rbac_school_role_policies, rbac_role_constraints;
DROP FUNCTION IF EXISTS validate_rbac_school_role_policy();
DELETE FROM rbac_role_capabilities WHERE capability_code IN (SELECT code FROM capability_catalog WHERE source_status='MERGED_2026_10_23');
DELETE FROM rbac_exception_grants WHERE capability_code IN (SELECT code FROM capability_catalog WHERE source_status='MERGED_2026_10_23');
ALTER TABLE capability_catalog DROP CONSTRAINT IF EXISTS capability_catalog_alias_chk, DROP CONSTRAINT IF EXISTS capability_catalog_alias_fk,
  DROP CONSTRAINT IF EXISTS capability_catalog_lifecycle_chk;
DELETE FROM capability_catalog WHERE source_status='MERGED_2026_10_23';
ALTER TABLE capability_catalog DROP COLUMN IF EXISTS school_adjustable, DROP COLUMN IF EXISTS replaced_by, DROP COLUMN IF EXISTS alias_of,
  DROP COLUMN IF EXISTS lifecycle;
DELETE FROM schema_migrations WHERE version='0085_school_rbac_policies';
COMMIT;
