-- Month of departure (owner, 2026-11-19): « c'est à chaque école de définir la date ». A pupil who abandons or is
-- transferred on day D of a month: if D <= departure_month_not_due_until_day, that month is no longer owed (like the
-- months after); otherwise it stays owed. NULL = the school has not set a rule → month of departure owed (previous
-- behaviour). Per school, in the monthly billing policy.
ALTER TABLE school_billing_policy ADD COLUMN IF NOT EXISTS departure_month_not_due_until_day smallint;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'school_billing_policy_departure_day_ck') THEN
    ALTER TABLE school_billing_policy ADD CONSTRAINT school_billing_policy_departure_day_ck
      CHECK (departure_month_not_due_until_day IS NULL OR departure_month_not_due_until_day BETWEEN 1 AND 31);
  END IF;
END $$;
