-- Regrouper les frères et sœurs (owner, 2026-11-21). A pupil imported from the old software arrived in a family of
-- its own. Merging moves the children (and the guardians) to one family; the emptied family is KEPT, marked as merged
-- into the other (history: old receipts, family baskets, audit), and no longer listed. No amount is touched.
ALTER TABLE families ADD COLUMN IF NOT EXISTS merged_into_family_id uuid REFERENCES families(id);
ALTER TABLE families ADD COLUMN IF NOT EXISTS merged_at timestamptz;
ALTER TABLE families ADD COLUMN IF NOT EXISTS merged_by uuid REFERENCES users(id);
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'families_not_merged_into_itself_ck') THEN
    ALTER TABLE families ADD CONSTRAINT families_not_merged_into_itself_ck
      CHECK (merged_into_family_id IS NULL OR merged_into_family_id <> id);
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_families_active ON families(school_id) WHERE merged_into_family_id IS NULL;
