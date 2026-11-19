-- Attachments of e-mails (owner, 2026-11-19: the weekly / monthly report goes « avec le PDF joint »). One row per file,
-- tied to its message; the PDF of each recipient is built for HIS scope (whole school or his section) and is never
-- shared between messages. The tenant writes its own school's rows; the worker only reads them to send.
CREATE TABLE IF NOT EXISTS communication_attachments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  message_id uuid NOT NULL REFERENCES communication_messages(id) ON DELETE CASCADE,
  file_name varchar(200) NOT NULL CHECK (length(btrim(file_name)) > 0),
  content_type varchar(80) NOT NULL CHECK (content_type IN ('application/pdf')),
  byte_size integer NOT NULL CHECK (byte_size > 0 AND byte_size <= 5242880),
  data bytea NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_communication_attachments_message ON communication_attachments(message_id);
ALTER TABLE communication_attachments ENABLE ROW LEVEL SECURITY;
ALTER TABLE communication_attachments FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON communication_attachments;
CREATE POLICY tenant_isolation ON communication_attachments
  USING (school_id=current_setting('app.school_id',true)::uuid) WITH CHECK (school_id=current_setting('app.school_id',true)::uuid);
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_tenant') THEN
    GRANT SELECT, INSERT ON communication_attachments TO edusync_tenant;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_worker') THEN
    DROP POLICY IF EXISTS worker_read ON communication_attachments;
    CREATE POLICY worker_read ON communication_attachments FOR SELECT TO edusync_worker USING (true);
    GRANT SELECT ON communication_attachments TO edusync_worker;
  END IF;
END $$;
