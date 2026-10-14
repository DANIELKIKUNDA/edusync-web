-- Parity lot L4 (owner decision 2026-10-14) — admission conditions copied from the Desktop golden master
-- (app/db/configuration.py: upsert_enrollment_policy_item, set_enrollment_policy_item_active,
--  mark_enrollment_policy_reviewed; app/db/terrain.py: registration_bundle_codes / registration_bundle_due;
--  app/db/finance_checkout.py: "Les obligations exigées à l'inscription doivent être soldées avant les autres frais").
--  * an admission condition belongs to a school year: label, linked fee type, required, payment timing
--    (AT_ENROLLMENT / AFTER_ENROLLMENT / OPTIONAL), can be paid later, bundle code, target (school / section /
--    academic class / class), order, active;
--  * the required AT_ENROLLMENT conditions that target a student form his "registration bundle"; the cash desk refuses
--    unrelated fees while the bundle is still due;
--  * the school validates the rubric even when it requires no fee at enrollment (review); until then a school without
--    any condition keeps the Desktop historical bundle (INSCRIPTION + June school fees).

CREATE TABLE IF NOT EXISTS school_admission_conditions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  academic_year_id uuid NOT NULL REFERENCES academic_years(id),
  fee_type_id uuid REFERENCES fee_types(id),
  label varchar(160) NOT NULL,
  scope_type varchar(16) NOT NULL DEFAULT 'SCHOOL' CHECK (scope_type IN ('SCHOOL','SECTION','ACADEMIC_CLASS','CLASS')),
  scope_ref varchar(64) NOT NULL DEFAULT '*',
  required boolean NOT NULL DEFAULT true,
  payment_timing varchar(20) NOT NULL DEFAULT 'AT_ENROLLMENT' CHECK (payment_timing IN ('AT_ENROLLMENT','AFTER_ENROLLMENT','OPTIONAL')),
  bundle_code varchar(48),
  can_pay_later boolean NOT NULL DEFAULT false,
  active boolean NOT NULL DEFAULT true,
  sort_order integer NOT NULL DEFAULT 100,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_admission_conditions_scope ON school_admission_conditions(school_id, academic_year_id, scope_type, scope_ref, active);
ALTER TABLE school_admission_conditions ENABLE ROW LEVEL SECURITY;
ALTER TABLE school_admission_conditions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS school_admission_conditions_tenant ON school_admission_conditions;
CREATE POLICY school_admission_conditions_tenant ON school_admission_conditions
  USING (school_id = current_setting('app.school_id', true)::uuid)
  WITH CHECK (school_id = current_setting('app.school_id', true)::uuid);
GRANT SELECT, INSERT, UPDATE ON school_admission_conditions TO edusync_tenant;
DROP TRIGGER IF EXISTS trg_touch_school_admission_conditions ON school_admission_conditions;
CREATE TRIGGER trg_touch_school_admission_conditions BEFORE UPDATE ON school_admission_conditions FOR EACH ROW EXECUTE FUNCTION touch_settings_row();

-- Desktop school preference "enrollment policy reviewed" (permanent).
ALTER TABLE settings_bootstrap_state ADD COLUMN IF NOT EXISTS admission_reviewed_at timestamptz;
ALTER TABLE settings_bootstrap_state ADD COLUMN IF NOT EXISTS admission_reviewed_by uuid REFERENCES users(id);
