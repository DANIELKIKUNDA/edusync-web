-- A numbered official report must have one immutable archived PDF and one replay key.
ALTER TABLE finance_generated_reports
  ADD COLUMN IF NOT EXISTS request_key varchar(160),
  ADD COLUMN IF NOT EXISTS document_generation_id uuid REFERENCES generated_documents(id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_finance_report_request_key
  ON finance_generated_reports(school_id,request_key) WHERE request_key IS NOT NULL;
GRANT UPDATE (document_generation_id) ON finance_generated_reports TO edusync_tenant;
-- Existing historical reports keep NULL: their original archive status is not inferred.
