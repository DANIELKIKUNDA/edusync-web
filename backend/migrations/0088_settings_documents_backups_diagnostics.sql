-- Settings parity pass 3 (owner request 2026-10-24: « ajoute tout ce qui reste ») — copied from the Desktop golden
-- master (app/ui/settings_page.py: identity « devise / mention », _build_documents, _backup_now, _test_backup,
-- _export_diagnostic; app/services/diagnostics.py).
--  * schools.motto: the school motto printed under its name on documents (identity column, school-editable);
--  * school_print_settings: signatory name / title and « show the logo » (Desktop save_document_settings);
--  * the backup and diagnostic capabilities already granted by the owner to ADMIN_SYSTEME_ECOLE leave PLANNED: they
--    now protect real endpoints (school data export, export test, diagnostic). settings.backups.restore stays PLANNED:
--    restoring a school is a platform operation, never a self-service button.

ALTER TABLE schools ADD COLUMN IF NOT EXISTS motto varchar(160);
GRANT UPDATE (motto) ON schools TO edusync_tenant;

ALTER TABLE school_print_settings ADD COLUMN IF NOT EXISTS signatory_name varchar(120);
ALTER TABLE school_print_settings ADD COLUMN IF NOT EXISTS signatory_title varchar(120);
ALTER TABLE school_print_settings ADD COLUMN IF NOT EXISTS show_school_logo boolean NOT NULL DEFAULT true;

UPDATE capability_catalog SET lifecycle = 'ACTIVE', updated_at = now()
 WHERE code IN ('settings.backups.create', 'settings.backups.test', 'settings.diagnostics.read', 'settings.diagnostics.export')
   AND lifecycle = 'PLANNED';

-- Diagnostic « version du schéma » (Desktop export_diagnostic_report): read-only access to the applied migration names,
-- which contain no school data.
GRANT SELECT ON schema_migrations TO edusync_tenant;
