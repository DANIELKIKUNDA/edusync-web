-- Parity lot L5 (owner decision 2026-10-14) — cash-desk rules copied from the Desktop golden master
-- (app/db/configuration.py::save_payment_policy / get_payment_policy; app/db/finance_checkout.py: partial payments,
--  minimum deposit, future months, accepted payment modes; app/db/schema.sql: payment_policy).
--  * permanent school setting: partial payments allowed (yes/no), minimum deposit, presentation of deposits in the
--    reports (INCLUDE / SEPARATE / EXCLUDE_UNTIL_SETTLED), advance payments allowed, payment of future months allowed,
--    accepted modes (cash, mobile money, bank, other);
--  * every payment records its mode (and an optional reference: mobile-money or bank transaction number).

CREATE TABLE IF NOT EXISTS school_payment_policy (
  school_id uuid PRIMARY KEY REFERENCES schools(id) ON DELETE CASCADE,
  partial_payments_enabled boolean NOT NULL DEFAULT true,
  partial_min_amount numeric(18,2) NOT NULL DEFAULT 0 CHECK (partial_min_amount >= 0),
  partial_reporting_mode varchar(24) NOT NULL DEFAULT 'SEPARATE' CHECK (partial_reporting_mode IN ('INCLUDE','SEPARATE','EXCLUDE_UNTIL_SETTLED')),
  advance_payments_enabled boolean NOT NULL DEFAULT true,
  future_charge_payments_enabled boolean NOT NULL DEFAULT true,
  accepted_modes jsonb NOT NULL DEFAULT '["CASH","MOBILE_MONEY","BANQUE","AUTRE"]'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  CHECK (jsonb_typeof(accepted_modes) = 'array' AND jsonb_array_length(accepted_modes) >= 1)
);
ALTER TABLE school_payment_policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE school_payment_policy FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS school_payment_policy_tenant ON school_payment_policy;
CREATE POLICY school_payment_policy_tenant ON school_payment_policy
  USING (school_id = current_setting('app.school_id', true)::uuid)
  WITH CHECK (school_id = current_setting('app.school_id', true)::uuid);
GRANT SELECT, INSERT, UPDATE ON school_payment_policy TO edusync_tenant;
DROP TRIGGER IF EXISTS trg_touch_school_payment_policy ON school_payment_policy;
CREATE TRIGGER trg_touch_school_payment_policy BEFORE UPDATE ON school_payment_policy FOR EACH ROW EXECUTE FUNCTION touch_settings_row();

ALTER TABLE finance_payments ADD COLUMN IF NOT EXISTS payment_mode varchar(16) NOT NULL DEFAULT 'CASH';
ALTER TABLE finance_payments ADD COLUMN IF NOT EXISTS payment_reference varchar(80);
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'finance_payments_mode_ck') THEN
    ALTER TABLE finance_payments ADD CONSTRAINT finance_payments_mode_ck CHECK (payment_mode IN ('CASH','MOBILE_MONEY','BANQUE','AUTRE'));
  END IF;
END $$;
GRANT INSERT (payment_mode, payment_reference) ON finance_payments TO edusync_tenant;
