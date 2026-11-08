-- Enrollment conditions may target SEVERAL sections, levels or classes of the same kind (owner request 2026-11-08):
-- « quand on choisit section ou classe, on doit pouvoir cocher plusieurs ». The single scope_ref stays (first target,
-- read by existing code); the full list sits next to it, as for anticipation plans (0089).
ALTER TABLE school_admission_conditions ADD COLUMN IF NOT EXISTS scope_refs varchar(64)[];
UPDATE school_admission_conditions SET scope_refs = ARRAY[scope_ref]::varchar(64)[] WHERE scope_refs IS NULL AND scope_type <> 'SCHOOL';
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'school_admission_conditions_scope_refs_ck') THEN
    ALTER TABLE school_admission_conditions ADD CONSTRAINT school_admission_conditions_scope_refs_ck
      CHECK (scope_refs IS NULL OR cardinality(scope_refs) BETWEEN 1 AND 300);
  END IF;
END $$;
