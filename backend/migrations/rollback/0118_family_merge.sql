DROP INDEX IF EXISTS idx_families_active;
ALTER TABLE families DROP CONSTRAINT IF EXISTS families_not_merged_into_itself_ck;
ALTER TABLE families DROP COLUMN IF EXISTS merged_by;
ALTER TABLE families DROP COLUMN IF EXISTS merged_at;
ALTER TABLE families DROP COLUMN IF EXISTS merged_into_family_id;
