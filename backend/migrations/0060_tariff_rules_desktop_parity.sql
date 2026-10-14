-- Parity lot L1 (owner decision 2026-10-14) — tariff rules copied from the Desktop golden master
-- (app/db/configuration.py: upsert_tariff_rule, save_tariff_group_rule, set_option_tariff_group,
--  save_monthly_billing_policy, resolve_tariff_for_class; app/db/schema.sql: tariff_rules, tariff_group_rules,
--  monthly_billing_policy).
--
-- A tariff rule targets the whole school, a section, an academic class (reference level), an Humanities tariff group
-- or one open class; it is effective-dated and carries an official status. Resolution for a class at a date keeps the
-- most precise rule: class 600 > academic class 500 > Humanities group 350 > section 200 > school 100.
-- The existing `tariffs` table is extended (every current row targets a class) so that its consumers keep working.

ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS scope_type varchar(16);
ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS scope_ref varchar(64);
ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS effective_from date;
ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS status varchar(20) NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS source_reference varchar(240);

UPDATE tariffs t SET scope_type = CASE WHEN t.class_id IS NOT NULL THEN 'CLASS' ELSE 'SECTION' END,
                     scope_ref  = CASE WHEN t.class_id IS NOT NULL THEN t.class_id::text ELSE t.section_id::text END
 WHERE t.scope_type IS NULL;
UPDATE tariffs t SET effective_from = y.start_date FROM academic_years y WHERE y.id = t.academic_year_id AND t.effective_from IS NULL;

ALTER TABLE tariffs ALTER COLUMN scope_type SET NOT NULL;
ALTER TABLE tariffs ALTER COLUMN scope_ref SET NOT NULL;
ALTER TABLE tariffs ALTER COLUMN effective_from SET NOT NULL;
-- Desktop: amount may be unknown while the official scale is pending; zero is a valid (more precise) tariff.
ALTER TABLE tariffs ALTER COLUMN amount DROP NOT NULL;

DO $$
DECLARE c record;
BEGIN
  FOR c IN SELECT conname FROM pg_constraint
            WHERE conrelid = 'public.tariffs'::regclass AND contype = 'c'
              AND conname NOT LIKE 'tariffs\_%\_ck'
              AND (pg_get_constraintdef(oid) ILIKE '%amount%' OR pg_get_constraintdef(oid) ILIKE '%class_id IS NOT NULL%section_id IS NOT NULL%') LOOP
    EXECUTE format('ALTER TABLE tariffs DROP CONSTRAINT %I', c.conname);
  END LOOP;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'tariffs_amount_ck') THEN
    ALTER TABLE tariffs ADD CONSTRAINT tariffs_amount_ck CHECK (amount IS NULL OR amount >= 0);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'tariffs_scope_ck') THEN
    ALTER TABLE tariffs ADD CONSTRAINT tariffs_scope_ck CHECK (scope_type IN ('SCHOOL','SECTION','ACADEMIC_CLASS','OPTION_GROUP','CLASS'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'tariffs_status_ck') THEN
    ALTER TABLE tariffs ADD CONSTRAINT tariffs_status_ck CHECK (status IN ('ACTIVE','PENDING_OFFICIAL','INACTIVE'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'tariffs_active_has_amount_ck') THEN
    ALTER TABLE tariffs ADD CONSTRAINT tariffs_active_has_amount_ck CHECK (status <> 'ACTIVE' OR amount IS NOT NULL);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'tariffs_group_ref_ck') THEN
    ALTER TABLE tariffs ADD CONSTRAINT tariffs_group_ref_ck CHECK (scope_type <> 'OPTION_GROUP' OR scope_ref IN ('GENERAL','TECHNICAL','OTHER'));
  END IF;
END $$;

-- One rule per (year, fee, target, effective date) — Desktop UNIQUE(academic_year_id,fee_type_id,scope_type,scope_ref,effective_from).
-- The previous Web model allowed the same fee twice on one class (e.g. one row per currency): keep the oldest enabled
-- row, disable the later ones (never deleted, kept for history).
WITH ranked AS (
  SELECT id, row_number() OVER (PARTITION BY school_id, academic_year_id, fee_type_id, scope_type, scope_ref, effective_from
                                ORDER BY created_at, id) AS rn
    FROM tariffs WHERE enabled
)
UPDATE tariffs t SET enabled = false, status = 'INACTIVE',
       source_reference = left(coalesce(t.source_reference || ' — ', '') || 'Désactivé à la migration 0060 : doublon de règle (même cible, même date)', 240)
  FROM ranked r WHERE r.id = t.id AND r.rn > 1;
-- The former Web uniqueness (one row per class/section/option/currency, no date) contradicts dated rules: replaced.
DROP INDEX IF EXISTS uq_tariffs_active_exact_scope;
CREATE UNIQUE INDEX IF NOT EXISTS uq_tariffs_rule ON tariffs(school_id, academic_year_id, fee_type_id, scope_type, scope_ref, effective_from)
  WHERE enabled;
CREATE INDEX IF NOT EXISTS idx_tariffs_resolve ON tariffs(school_id, academic_year_id, fee_type_id, scope_type, scope_ref, effective_from)
  WHERE enabled AND status = 'ACTIVE';

-- Humanities tariff groups (Desktop TARIFF_GROUP_LABELS): closed list.
UPDATE school_options SET tariff_group_code = NULL WHERE tariff_group_code IS NOT NULL AND tariff_group_code NOT IN ('GENERAL','TECHNICAL','OTHER');
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'school_options_tariff_group_ck') THEN
    ALTER TABLE school_options ADD CONSTRAINT school_options_tariff_group_ck CHECK (tariff_group_code IS NULL OR tariff_group_code IN ('GENERAL','TECHNICAL','OTHER'));
  END IF;
END $$;

-- Monthly billing policy (Desktop monthly_billing_policy, permanent school setting).
CREATE TABLE IF NOT EXISTS school_billing_policy (
  school_id uuid PRIMARY KEY REFERENCES schools(id) ON DELETE CASCADE,
  billing_months jsonb NOT NULL DEFAULT '["09","10","11","12","01","02","03","04","05","06"]'::jsonb,
  month_due_at_enrollment varchar(2),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  CHECK (jsonb_typeof(billing_months) = 'array' AND jsonb_array_length(billing_months) BETWEEN 1 AND 12),
  CHECK (month_due_at_enrollment IS NULL OR billing_months ? month_due_at_enrollment)
);
ALTER TABLE school_billing_policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE school_billing_policy FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS school_billing_policy_tenant ON school_billing_policy;
CREATE POLICY school_billing_policy_tenant ON school_billing_policy
  USING (school_id = current_setting('app.school_id', true)::uuid)
  WITH CHECK (school_id = current_setting('app.school_id', true)::uuid);
GRANT SELECT, INSERT, UPDATE ON school_billing_policy TO edusync_tenant;

DROP TRIGGER IF EXISTS trg_school_billing_policy_version ON school_billing_policy;
CREATE TRIGGER trg_school_billing_policy_version BEFORE UPDATE ON school_billing_policy
FOR EACH ROW EXECUTE FUNCTION touch_settings_row();
