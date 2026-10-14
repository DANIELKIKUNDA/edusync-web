-- Parity lot L2 (owner decision 2026-10-14) — fee schedules and due charges copied from the Desktop golden master
-- (app/db/configuration.py::apply_tariff_rules_to_classes, app/db/database.py::create_fee_schedule and
--  generate_charges_for_enrollment).
--  * "Appliquer les barèmes aux classes" materialises, for each class and fee type, the schedule lines of the year:
--    one line per billed month (MONTHLY), three tranches September / January / April (PERIODIC = Desktop TERM),
--    otherwise one line; the amount is the tariff rule resolved for the class at the line's due date;
--  * every validated enrollment of the class receives one due charge per schedule line (gross, benefit discount, net);
--  * a schedule line that already received money cannot change amount or currency; a charge is never set below what
--    has been paid.

CREATE TABLE IF NOT EXISTS fee_schedules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  academic_year_id uuid NOT NULL REFERENCES academic_years(id),
  class_id uuid NOT NULL REFERENCES school_classes(id),
  fee_type_id uuid NOT NULL REFERENCES fee_types(id),
  period_code varchar(8) NOT NULL,                 -- '*' (single line), '01'..'12' (month), 'T1'..'T3' (tranche)
  period_label varchar(32),
  period_order smallint,
  due_date date,
  amount numeric(18,2) NOT NULL CHECK (amount >= 0),
  currency varchar(3) NOT NULL CHECK (currency IN ('CDF','USD')),
  tariff_id uuid REFERENCES tariffs(id),
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  UNIQUE (school_id, academic_year_id, class_id, fee_type_id, period_code),
  CHECK (period_code = '*' OR period_code ~ '^(0[1-9]|1[0-2]|T[1-3])$')
);
CREATE INDEX IF NOT EXISTS idx_fee_schedules_class ON fee_schedules(school_id, academic_year_id, class_id, active);
ALTER TABLE fee_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE fee_schedules FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS fee_schedules_tenant ON fee_schedules;
CREATE POLICY fee_schedules_tenant ON fee_schedules
  USING (school_id = current_setting('app.school_id', true)::uuid)
  WITH CHECK (school_id = current_setting('app.school_id', true)::uuid);
GRANT SELECT, INSERT, UPDATE ON fee_schedules TO edusync_tenant;
DROP TRIGGER IF EXISTS trg_touch_fee_schedules ON fee_schedules;
CREATE TRIGGER trg_touch_fee_schedules BEFORE UPDATE ON fee_schedules FOR EACH ROW EXECUTE FUNCTION touch_settings_row();

-- Desktop charges(gross_amount, discount_percent, discount_amount, net_amount).
ALTER TABLE finance_charges ADD COLUMN IF NOT EXISTS schedule_id uuid REFERENCES fee_schedules(id);
ALTER TABLE finance_charges ADD COLUMN IF NOT EXISTS gross_amount numeric(18,2);
ALTER TABLE finance_charges ADD COLUMN IF NOT EXISTS discount_percent numeric(5,2) NOT NULL DEFAULT 0;
ALTER TABLE finance_charges ADD COLUMN IF NOT EXISTS discount_amount numeric(18,2) NOT NULL DEFAULT 0;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'finance_charges_discount_ck') THEN
    ALTER TABLE finance_charges ADD CONSTRAINT finance_charges_discount_ck
      CHECK (discount_percent BETWEEN 0 AND 100 AND discount_amount >= 0 AND (gross_amount IS NULL OR gross_amount >= 0));
  END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS uq_finance_charges_schedule ON finance_charges(school_id, enrollment_id, schedule_id) WHERE schedule_id IS NOT NULL;

-- The application now generates charges (before: only seeds/imports). Narrow grants: create a charge, and update only
-- the terms that a schedule regeneration may change; payments keep their own column grant (paid_amount).
GRANT INSERT ON finance_charges TO edusync_tenant;
GRANT UPDATE (label, currency, net_amount, gross_amount, discount_percent, discount_amount, due_date, period_label, period_order,
              sequence_group, sequence_order, tariff_id, updated_at) ON finance_charges TO edusync_tenant;
