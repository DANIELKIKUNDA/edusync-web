-- Settings parity pass 2 (owner request 2026-10-24) — a staff-child or large-family benefit covers SEVERAL fees.
-- In real schools the benefit often covers the tuition AND, for example, the State fee: the single fee code of 0062 is
-- kept (first code, read by existing reports) and the full list is stored next to it. An empty list keeps the 0062
-- meaning of a NULL code: every fee. The beneficiary still freezes the list of the policy at selection time.

ALTER TABLE school_benefit_policies ADD COLUMN IF NOT EXISTS applies_to_fee_codes varchar(48)[];
ALTER TABLE student_benefits ADD COLUMN IF NOT EXISTS applies_to_fee_codes varchar(48)[];

UPDATE school_benefit_policies SET applies_to_fee_codes = ARRAY[applies_to_fee_code]::varchar(48)[]
 WHERE applies_to_fee_codes IS NULL AND applies_to_fee_code IS NOT NULL;
UPDATE student_benefits SET applies_to_fee_codes = ARRAY[applies_to_fee_code]::varchar(48)[]
 WHERE applies_to_fee_codes IS NULL AND applies_to_fee_code IS NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'school_benefit_policies_fee_codes_ck') THEN
    ALTER TABLE school_benefit_policies ADD CONSTRAINT school_benefit_policies_fee_codes_ck
      CHECK (applies_to_fee_codes IS NULL OR cardinality(applies_to_fee_codes) <= 30);
  END IF;
END $$;
