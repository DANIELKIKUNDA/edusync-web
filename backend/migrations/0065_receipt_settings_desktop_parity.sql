-- Parity lot L7 (owner decision 2026-10-14) — receipt settings copied from the Desktop golden master
-- (app/db/configuration.py::save_document_settings; app/db/database.py::next_receipt_no -> PREFIX-YEAR-000123, one atomic
--  counter per calendar year, consumed in the payment transaction; app/services/documents.py: receipt copies 1..5 and
--  formats THERMAL_80 / THERMAL_58 / A5).
-- Not ported as active settings (Desktop stores them but no document reads them): signatory name/title, show-logo flag.
-- Report prefix: the Web has no numbered reports yet (N3 reports).

ALTER TABLE school_print_settings ADD COLUMN IF NOT EXISTS receipt_prefix varchar(12) NOT NULL DEFAULT 'REC';
ALTER TABLE school_print_settings ADD COLUMN IF NOT EXISTS receipt_copies smallint NOT NULL DEFAULT 1;
DO $$
DECLARE c record;
BEGIN
  FOR c IN SELECT conname FROM pg_constraint WHERE conrelid = 'public.school_print_settings'::regclass AND contype = 'c'
            AND pg_get_constraintdef(oid) ILIKE '%receipt_format%' LOOP
    EXECUTE format('ALTER TABLE school_print_settings DROP CONSTRAINT %I', c.conname);
  END LOOP;
  ALTER TABLE school_print_settings ADD CONSTRAINT school_print_settings_format_ck CHECK (receipt_format IN ('A5','80MM','58MM'));
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'school_print_settings_copies_ck') THEN
    ALTER TABLE school_print_settings ADD CONSTRAINT school_print_settings_copies_ck CHECK (receipt_copies BETWEEN 1 AND 5);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'school_print_settings_prefix_ck') THEN
    ALTER TABLE school_print_settings ADD CONSTRAINT school_print_settings_prefix_ck CHECK (receipt_prefix ~ '^[A-Z0-9]{1,12}$');
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS finance_receipt_sequences (
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  year integer NOT NULL CHECK (year BETWEEN 2000 AND 2999),
  last_number bigint NOT NULL CHECK (last_number >= 1),
  PRIMARY KEY (school_id, year)
);
ALTER TABLE finance_receipt_sequences ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance_receipt_sequences FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS finance_receipt_sequences_tenant ON finance_receipt_sequences;
CREATE POLICY finance_receipt_sequences_tenant ON finance_receipt_sequences
  USING (school_id = current_setting('app.current_school_id', true)::uuid)
  WITH CHECK (school_id = current_setting('app.current_school_id', true)::uuid);
GRANT SELECT, INSERT, UPDATE ON finance_receipt_sequences TO edusync_tenant;
