-- Large family « par tranche » (owner request 2026-11-06): many schools grant the benefit per group of children —
-- 5 enrolled children → 1 free child, 10 → 2. When per_group is true, the family limit is
-- floor(enrolled children / min_children) × free beneficiaries; false keeps the fixed limit of 0062 (default, no change
-- for existing schools). Additive column only; the tenant already holds INSERT/UPDATE on the table (0062).
ALTER TABLE school_benefit_policies ADD COLUMN IF NOT EXISTS per_group boolean NOT NULL DEFAULT false;
