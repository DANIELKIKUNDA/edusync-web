-- Administrator finishing pass (owner request 2026-10-24).
--  * An anticipated-payment plan may target SEVERAL classes, levels, sections or Humanités groups of the same kind
--    (« un plan anticipé peut s'appliquer à une seule classe ou à quelques classes seulement »). The 0066 single target
--    stays (first target, read by existing code); the full list sits next to it.
--  * A school year carries its enrollment period (« intervalle d'inscription »), editable while the year is prepared or
--    active. It is informative, never blocking: in the DRC late enrollments and transfers happen after the period.

ALTER TABLE anticipation_plans ADD COLUMN IF NOT EXISTS scope_refs varchar(64)[];
UPDATE anticipation_plans SET scope_refs = ARRAY[scope_ref]::varchar(64)[] WHERE scope_refs IS NULL AND scope_type <> 'SCHOOL';
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'anticipation_plans_scope_refs_ck') THEN
    ALTER TABLE anticipation_plans ADD CONSTRAINT anticipation_plans_scope_refs_ck
      CHECK (scope_refs IS NULL OR cardinality(scope_refs) BETWEEN 1 AND 200);
  END IF;
END $$;

ALTER TABLE academic_years ADD COLUMN IF NOT EXISTS enrollment_start date;
ALTER TABLE academic_years ADD COLUMN IF NOT EXISTS enrollment_end date;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'academic_years_enrollment_window_ck') THEN
    ALTER TABLE academic_years ADD CONSTRAINT academic_years_enrollment_window_ck
      CHECK (enrollment_start IS NULL OR enrollment_end IS NULL OR enrollment_start <= enrollment_end);
  END IF;
END $$;
