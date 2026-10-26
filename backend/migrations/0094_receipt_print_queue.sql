-- Durable cashier receipt queue. Browser PDF requests are not evidence of paper output.
-- New payments are enqueued in the same transaction that commits the payment.
CREATE TABLE IF NOT EXISTS finance_receipt_print_jobs (
  school_id uuid NOT NULL REFERENCES schools(id),
  payment_id uuid PRIMARY KEY REFERENCES finance_payments(id),
  status varchar(12) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','PRINTED','FAILED')),
  queued_at timestamptz NOT NULL DEFAULT now(),
  printed_at timestamptz,
  printed_by uuid REFERENCES users(id),
  failed_at timestamptz,
  failure_reason varchar(240),
  attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_finance_receipt_jobs_queue ON finance_receipt_print_jobs(school_id,status,queued_at DESC);
ALTER TABLE finance_receipt_print_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance_receipt_print_jobs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS finance_receipt_print_jobs_tenant ON finance_receipt_print_jobs;
CREATE POLICY finance_receipt_print_jobs_tenant ON finance_receipt_print_jobs
  USING (school_id=current_setting('app.current_school_id',true)::uuid)
  WITH CHECK (school_id=current_setting('app.current_school_id',true)::uuid);
GRANT SELECT, INSERT ON finance_receipt_print_jobs TO edusync_tenant;
GRANT UPDATE (status, printed_at, printed_by, failed_at, failure_reason, attempts, updated_at)
  ON finance_receipt_print_jobs TO edusync_tenant;
REVOKE DELETE ON finance_receipt_print_jobs FROM edusync_tenant;

CREATE OR REPLACE FUNCTION edusync_enqueue_payment_receipt() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO finance_receipt_print_jobs(school_id,payment_id)
  VALUES(NEW.school_id,NEW.id)
  ON CONFLICT(payment_id) DO NOTHING;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_finance_payment_receipt_queue ON finance_payments;
CREATE TRIGGER trg_finance_payment_receipt_queue
AFTER INSERT ON finance_payments FOR EACH ROW EXECUTE FUNCTION edusync_enqueue_payment_receipt();
-- Legacy PDF requests did not prove printing; no guessed backfill is performed.
