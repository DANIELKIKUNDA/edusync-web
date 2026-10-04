-- Point 12B — Import personnel staging and explicit execution
CREATE TABLE IF NOT EXISTS staff_import_batches (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 filename varchar(240) NOT NULL, source_format varchar(12) NOT NULL CHECK(source_format IN ('XLSX','CSV')),
 status varchar(20) NOT NULL DEFAULT 'ANALYZED' CHECK(status IN ('ANALYZED','READY','EXECUTED','CANCELLED')), total_rows int NOT NULL DEFAULT 0, valid_rows int NOT NULL DEFAULT 0, warning_rows int NOT NULL DEFAULT 0, error_rows int NOT NULL DEFAULT 0,
 created_by uuid REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT now(), executed_at timestamptz, version bigint NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS staff_import_rows (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE, batch_id uuid NOT NULL REFERENCES staff_import_batches(id) ON DELETE CASCADE, row_number int NOT NULL, payload jsonb NOT NULL, normalized_payload jsonb NOT NULL DEFAULT '{}'::jsonb, status varchar(16) NOT NULL CHECK(status IN ('VALID','WARNING','ERROR','IMPORTED')), issues jsonb NOT NULL DEFAULT '[]'::jsonb, imported_staff_id uuid REFERENCES staff_members(id), created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(batch_id,row_number));
CREATE INDEX IF NOT EXISTS idx_staff_import_batches_school_created ON staff_import_batches(school_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_staff_import_rows_batch_status ON staff_import_rows(school_id,batch_id,status,row_number);
ALTER TABLE staff_import_batches ENABLE ROW LEVEL SECURITY; ALTER TABLE staff_import_batches FORCE ROW LEVEL SECURITY;
ALTER TABLE staff_import_rows ENABLE ROW LEVEL SECURITY; ALTER TABLE staff_import_rows FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS staff_import_batches_tenant ON staff_import_batches; CREATE POLICY staff_import_batches_tenant ON staff_import_batches USING (school_id=nullif(current_setting('app.current_school_id', true), '')::uuid) WITH CHECK (school_id=nullif(current_setting('app.current_school_id', true), '')::uuid);
DROP POLICY IF EXISTS staff_import_rows_tenant ON staff_import_rows; CREATE POLICY staff_import_rows_tenant ON staff_import_rows USING (school_id=nullif(current_setting('app.current_school_id', true), '')::uuid) WITH CHECK (school_id=nullif(current_setting('app.current_school_id', true), '')::uuid);
INSERT INTO capability_catalog(code,domain_name,group_name,label,action_code,risk,offline_policy,audit_required,scope_types,source_status,registry_version) VALUES
 ('migration.staff.analyze','Migration & import','Imports','Analyser un fichier personnel','analyze','MEDIUM','SERVER_ONLY',false,'["SCHOOL"]'::jsonb,'OWNER_APPROVED','0.43.0'),
 ('migration.staff.execute','Migration & import','Imports','Importer le personnel','import','HIGH','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'OWNER_APPROVED','0.43.0')
ON CONFLICT(code) DO NOTHING;
INSERT INTO rbac_role_capabilities(role_id,capability_code)
 SELECT DISTINCT rc.role_id,c.code FROM rbac_role_capabilities rc CROSS JOIN (VALUES('migration.staff.analyze'),('migration.staff.execute')) c(code)
 WHERE rc.capability_code='personnel.create' ON CONFLICT DO NOTHING;
