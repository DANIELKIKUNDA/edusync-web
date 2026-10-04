-- Point 5 Documents/Exports: immutable generation history + server object locator.
CREATE TABLE IF NOT EXISTS generated_documents (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id),
 academic_year_id uuid NULL REFERENCES academic_years(id), document_code text NOT NULL,
 format text NOT NULL CHECK(format IN ('PDF','XLSX','CSV')), title text NOT NULL,
 object_key text NOT NULL, sha256 char(64) NOT NULL, byte_size bigint NOT NULL CHECK(byte_size>=0),
 source_entity_type text NULL, source_entity_id uuid NULL, filters_json jsonb NOT NULL DEFAULT '{}'::jsonb,
 generated_by uuid NOT NULL REFERENCES users(id), generated_at timestamptz NOT NULL DEFAULT now(),
 regeneration_of uuid NULL REFERENCES generated_documents(id), correlation_id uuid NULL
);
CREATE INDEX IF NOT EXISTS ix_generated_documents_school_date ON generated_documents(school_id,generated_at DESC);
CREATE INDEX IF NOT EXISTS ix_generated_documents_school_code ON generated_documents(school_id,document_code,generated_at DESC);
ALTER TABLE generated_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE generated_documents FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS generated_documents_tenant ON generated_documents;
CREATE POLICY generated_documents_tenant ON generated_documents USING (school_id=current_setting('app.current_school_id',true)::uuid) WITH CHECK (school_id=current_setting('app.current_school_id',true)::uuid);
REVOKE UPDATE,DELETE ON generated_documents FROM PUBLIC;
COMMENT ON TABLE generated_documents IS 'Append-only documentary evidence. Regeneration creates a new row; it never mutates a financial transaction.';
