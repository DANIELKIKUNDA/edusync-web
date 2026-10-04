-- Point 5B: one visible logical document, immutable generation evidence.
-- Re-exporting the same logical document replaces its current object; it does not create "(1)", "(2)" files.
ALTER TABLE generated_documents ADD COLUMN IF NOT EXISTS logical_key text;
UPDATE generated_documents SET logical_key=object_key WHERE logical_key IS NULL;
ALTER TABLE generated_documents ALTER COLUMN logical_key SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_generated_documents_logical_history ON generated_documents(school_id,logical_key,generated_at DESC);

CREATE TABLE IF NOT EXISTS current_documents (
 school_id uuid NOT NULL REFERENCES schools(id), logical_key text NOT NULL,
 latest_generation_id uuid NOT NULL REFERENCES generated_documents(id),
 document_code text NOT NULL, format text NOT NULL CHECK(format IN ('PDF','XLSX','CSV')),
 title text NOT NULL, object_key text NOT NULL, sha256 char(64) NOT NULL, byte_size bigint NOT NULL CHECK(byte_size>=0),
 academic_year_id uuid NULL REFERENCES academic_years(id), updated_by uuid NOT NULL REFERENCES users(id), updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(school_id,logical_key)
);
ALTER TABLE current_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE current_documents FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS current_documents_tenant ON current_documents;
CREATE POLICY current_documents_tenant ON current_documents USING (school_id=current_setting('app.current_school_id',true)::uuid) WITH CHECK (school_id=current_setting('app.current_school_id',true)::uuid);
COMMENT ON TABLE current_documents IS 'Mutable pointer to the single current logical file. History remains append-only in generated_documents.';
