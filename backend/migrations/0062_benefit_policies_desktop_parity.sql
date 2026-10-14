-- Parity lot L3 (owner decision 2026-10-14) — benefit policies copied from the Desktop golden master
-- (app/db/configuration.py::save_benefit_policy, app/db/schooling.py: _policy_for, _discount_from_policy, beneficiary
--  limits at enrollment, app/db/database.py::generate_charges_for_enrollment, app/domain/benefits.py).
--  * one policy per school year and benefit type: enabled, minimum number of children (large family), maximum number of
--    beneficiaries, discount percent, free beneficiaries (free = 100 %), fee code the benefit applies to;
--  * the beneficiary is always chosen manually by the school (selection_mode MANUAL);
--  * the beneficiary keeps the rate and fee code of the policy at selection time; the due charge carries the discount.

CREATE TABLE IF NOT EXISTS school_benefit_policies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  academic_year_id uuid NOT NULL REFERENCES academic_years(id),
  benefit_type varchar(16) NOT NULL CHECK (benefit_type IN ('LARGE_FAMILY','STAFF_CHILD','SOCIAL_CASE','BURSARY','CUSTOM')),
  enabled boolean NOT NULL DEFAULT false,
  min_children integer NOT NULL DEFAULT 0 CHECK (min_children >= 0),
  max_beneficiaries integer NOT NULL DEFAULT 0 CHECK (max_beneficiaries >= 0),
  discount_percent numeric(5,2) NOT NULL DEFAULT 0 CHECK (discount_percent BETWEEN 0 AND 100),
  free_beneficiaries integer NOT NULL DEFAULT 0 CHECK (free_beneficiaries >= 0),
  applies_to_fee_code varchar(48),
  selection_mode varchar(8) NOT NULL DEFAULT 'MANUAL' CHECK (selection_mode = 'MANUAL'),
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  UNIQUE (school_id, academic_year_id, benefit_type)
);
ALTER TABLE school_benefit_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE school_benefit_policies FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS school_benefit_policies_tenant ON school_benefit_policies;
CREATE POLICY school_benefit_policies_tenant ON school_benefit_policies
  USING (school_id = current_setting('app.school_id', true)::uuid)
  WITH CHECK (school_id = current_setting('app.school_id', true)::uuid);
GRANT SELECT, INSERT, UPDATE ON school_benefit_policies TO edusync_tenant;
DROP TRIGGER IF EXISTS trg_touch_school_benefit_policies ON school_benefit_policies;
CREATE TRIGGER trg_touch_school_benefit_policies BEFORE UPDATE ON school_benefit_policies FOR EACH ROW EXECUTE FUNCTION touch_settings_row();

-- Desktop student_benefits(configured_percent, applies_to_fee_code).
ALTER TABLE student_benefits ADD COLUMN IF NOT EXISTS configured_percent numeric(5,2) NOT NULL DEFAULT 0;
ALTER TABLE student_benefits ADD COLUMN IF NOT EXISTS applies_to_fee_code varchar(48);
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'student_benefits_percent_ck') THEN
    ALTER TABLE student_benefits ADD CONSTRAINT student_benefits_percent_ck CHECK (configured_percent BETWEEN 0 AND 100);
  END IF;
END $$;
