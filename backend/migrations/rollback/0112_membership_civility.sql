ALTER TABLE school_memberships DROP CONSTRAINT IF EXISTS school_memberships_civility_ck;
ALTER TABLE school_memberships DROP COLUMN IF EXISTS civility;
