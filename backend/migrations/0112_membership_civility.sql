-- Civility of a school member (owner request 2026-11-09): « Promotrice, Directrice… » on the home page and, later, on
-- signed documents. Per school membership (the school knows its staff; no platform-wide personal data), optional:
-- NULL = not stated → neutral wording. Never used for rights.
ALTER TABLE school_memberships ADD COLUMN IF NOT EXISTS civility varchar(4);
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'school_memberships_civility_ck') THEN
    ALTER TABLE school_memberships ADD CONSTRAINT school_memberships_civility_ck CHECK (civility IS NULL OR civility IN ('M','MME'));
  END IF;
END $$;
