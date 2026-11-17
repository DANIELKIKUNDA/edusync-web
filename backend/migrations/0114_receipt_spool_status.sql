ALTER TABLE finance_receipt_print_jobs
  DROP CONSTRAINT finance_receipt_print_jobs_status_check,
  ADD CONSTRAINT finance_receipt_print_jobs_status_check
    CHECK (status IN ('PENDING', 'SUBMITTED', 'PRINTED', 'FAILED'));
