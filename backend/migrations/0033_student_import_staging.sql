-- Point 12A — Import élèves staging, preview, explicit execution
CREATE TABLE IF NOT EXISTS student_import_batches (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 academic_year_id uuid NOT NULL REFERENCES academic_years(id), filename varchar(240) NOT NULL, source_format varchar(12) NOT NULL CHECK(source_format IN ('XLSX','CSV')),
 status varchar(20) NOT NULL DEFAULT 'ANALYZED' CHECK(status IN ('ANALYZED','READY','EXECUTED','CANCELLED')), total_rows int NOT NULL DEFAULT 0, valid_rows int NOT NULL DEFAULT 0, warning_rows int NOT NULL DEFAULT 0, error_rows int NOT NULL DEFAULT 0,
 created_by uuid REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT now(), executed_at timestamptz, version bigint NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS student_import_rows (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE, batch_id uuid NOT NULL REFERENCES student_import_batches(id) ON DELETE CASCADE, row_number int NOT NULL, payload jsonb NOT NULL, normalized_payload jsonb NOT NULL DEFAULT '{}'::jsonb, status varchar(16) NOT NULL CHECK(status IN ('VALID','WARNING','ERROR','IMPORTED')), issues jsonb NOT NULL DEFAULT '[]'::jsonb, imported_student_id uuid REFERENCES students(id), imported_enrollment_id uuid REFERENCES enrollments(id), created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(batch_id,row_number));
CREATE INDEX IF NOT EXISTS idx_student_import_batches_school_created ON student_import_batches(school_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_student_import_rows_batch_status ON student_import_rows(school_id,batch_id,status,row_number);
ALTER TABLE student_import_batches ENABLE ROW LEVEL SECURITY; ALTER TABLE student_import_batches FORCE ROW LEVEL SECURITY;
ALTER TABLE student_import_rows ENABLE ROW LEVEL SECURITY; ALTER TABLE student_import_rows FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS student_import_batches_tenant ON student_import_batches; CREATE POLICY student_import_batches_tenant ON student_import_batches USING (school_id=nullif(current_setting('app.current_school_id', true), '')::uuid) WITH CHECK (school_id=nullif(current_setting('app.current_school_id', true), '')::uuid);
DROP POLICY IF EXISTS student_import_rows_tenant ON student_import_rows; CREATE POLICY student_import_rows_tenant ON student_import_rows USING (school_id=nullif(current_setting('app.current_school_id', true), '')::uuid) WITH CHECK (school_id=nullif(current_setting('app.current_school_id', true), '')::uuid);
