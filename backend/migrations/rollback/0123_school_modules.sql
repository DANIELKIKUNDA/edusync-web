-- Rollback of 0123_school_modules (manual, owner decision only). Removes what 0123 added and nothing else:
-- the V1 modules recorded by the migration, the two platform capabilities and the catalogue wording.
-- Pedagogy activations made by the platform (source MANUAL) are kept: they are business decisions, audited.
DELETE FROM rbac_role_capabilities WHERE capability_code IN ('platform.school_modules.read','platform.school_modules.manage');
DELETE FROM capability_catalog WHERE code IN ('platform.school_modules.read','platform.school_modules.manage');
DELETE FROM saas_entitlements WHERE source='MIGRATION' AND subscription_id IS NULL
   AND reason='Module V1 déjà en service avant la gestion des modules (lot 0, 22/11/2026)';
UPDATE saas_modules SET label='Gestion académique', description='', version=version+1, updated_at=now() WHERE code='ACADEMIC';
DELETE FROM schema_migrations WHERE version='0123_school_modules';
