-- Local closure 2026-10: documents on S3-compatible object storage.
-- PostgreSQL keeps metadata/evidence (this file), the object store keeps bytes (private bucket).
-- Object keys always start with schools/<school_id>/ and are built server-side only.

-- School branding (logo used by the interface and every generated document).
CREATE TABLE IF NOT EXISTS school_branding (
 school_id uuid PRIMARY KEY REFERENCES schools(id) ON DELETE CASCADE,
 logo_object_key text NOT NULL CHECK (logo_object_key LIKE 'schools/' || school_id::text || '/branding/%'),
 logo_content_type varchar(64) NOT NULL CHECK (logo_content_type IN ('image/png','image/jpeg')),
 logo_sha256 char(64) NOT NULL, logo_byte_size integer NOT NULL CHECK (logo_byte_size BETWEEN 1 AND 1048576),
 updated_by uuid NOT NULL REFERENCES users(id), updated_at timestamptz NOT NULL DEFAULT now(), version integer NOT NULL DEFAULT 1
);
ALTER TABLE school_branding ENABLE ROW LEVEL SECURITY; ALTER TABLE school_branding FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS school_branding_tenant ON school_branding;
CREATE POLICY school_branding_tenant ON school_branding USING (school_id=current_setting('app.current_school_id',true)::uuid) WITH CHECK (school_id=current_setting('app.current_school_id',true)::uuid);
GRANT SELECT, INSERT, UPDATE ON school_branding TO edusync_tenant;
REVOKE DELETE ON school_branding FROM edusync_tenant;

-- Generated documents archive (Point 5B doctrine): append-only history + one current pointer per logical document.
ALTER TABLE generated_documents ADD COLUMN IF NOT EXISTS content_type varchar(96);
ALTER TABLE generated_documents ADD COLUMN IF NOT EXISTS file_name varchar(200);
-- Capability that produced the document: other users see it only with that capability at school scope
-- (a class-scoped user never opens a school-wide document through the archive).
ALTER TABLE generated_documents ADD COLUMN IF NOT EXISTS required_capability varchar(128);
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='generated_documents_object_key_tenant') THEN
  ALTER TABLE generated_documents ADD CONSTRAINT generated_documents_object_key_tenant CHECK (object_key LIKE 'schools/' || school_id::text || '/%') NOT VALID;
 END IF;
END $$;
GRANT SELECT, INSERT ON generated_documents TO edusync_tenant;
REVOKE UPDATE, DELETE ON generated_documents FROM edusync_tenant;
GRANT SELECT, INSERT, UPDATE ON current_documents TO edusync_tenant;
REVOKE DELETE ON current_documents FROM edusync_tenant;
CREATE INDEX IF NOT EXISTS ix_current_documents_school_date ON current_documents(school_id,updated_at DESC);
