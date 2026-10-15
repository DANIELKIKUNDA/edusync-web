-- N3-G — periodic financial reports copied from the Desktop golden master (app/db/terrain.py register_generated_report,
-- report_sequences / generated_reports; app/db/configuration.py save_document_settings report_prefix = 'RAP').
-- The official PDF consumes a number per academic year: PREFIX-NNN; the Excel companion never consumes one.
ALTER TABLE school_print_settings ADD COLUMN IF NOT EXISTS report_prefix varchar(12) NOT NULL DEFAULT 'RAP';
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='school_print_settings_report_prefix_ck') THEN
    ALTER TABLE school_print_settings ADD CONSTRAINT school_print_settings_report_prefix_ck CHECK (report_prefix ~ '^[A-Z0-9]{1,12}$');
  END IF;
END $$;
GRANT INSERT (report_prefix), UPDATE (report_prefix) ON school_print_settings TO edusync_tenant;

CREATE TABLE IF NOT EXISTS finance_report_sequences (
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  academic_year_id uuid NOT NULL REFERENCES academic_years(id),
  last_number integer NOT NULL DEFAULT 0 CHECK (last_number >= 0),
  PRIMARY KEY (school_id, academic_year_id)
);
CREATE TABLE IF NOT EXISTS finance_generated_reports (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  academic_year_id uuid NOT NULL REFERENCES academic_years(id),
  report_no integer NOT NULL,
  report_label varchar(32) NOT NULL,
  profile_code varchar(32) NOT NULL,
  period_type varchar(16) NOT NULL CHECK (period_type IN ('JOURNALIER','HEBDOMADAIRE','MENSUEL','PERSONNALISE')),
  start_date date NOT NULL, end_date date NOT NULL,
  partial_reporting_mode varchar(24) NOT NULL,
  totals jsonb NOT NULL DEFAULT '{}'::jsonb,
  generated_by uuid NOT NULL REFERENCES users(id),
  generated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (school_id, academic_year_id, report_no)
);
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['finance_report_sequences','finance_generated_reports'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_tenant', t);
    EXECUTE format('CREATE POLICY %I ON %I USING (school_id = current_setting(''app.current_school_id'', true)::uuid) '
                   'WITH CHECK (school_id = current_setting(''app.current_school_id'', true)::uuid)', t || '_tenant', t);
  END LOOP;
END $$;
GRANT SELECT, INSERT, UPDATE ON finance_report_sequences TO edusync_tenant;
GRANT SELECT, INSERT ON finance_generated_reports TO edusync_tenant;
REVOKE UPDATE, DELETE ON finance_generated_reports FROM edusync_tenant;
