-- N2 (owner decisions 2026-10-14): a school administrates its own users with the capabilities the owner-approved
-- ADMIN_SYSTEME_ECOLE role already holds (access.users.create/update/activate/credentials.reset, migration 0008).
--  * accounts created or reset by a school get a temporary password that must be replaced at the first sign-in;
--  * an existing account (another school) is attached without touching its password.

ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password boolean NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_set_by varchar(16);  -- 'SELF' | 'SCHOOL' | 'PLATFORM' (informative)

-- The intermediate step table also carries the "replace your temporary password" step (purpose PASSWORD).
-- The inline CHECK of 0056 may carry a suffixed name (a legacy table renamed by 0056 kept the plain one): drop every
-- check constraint on "purpose" whatever its name, then install the named one.
DO $$
DECLARE
  c record;
BEGIN
  FOR c IN SELECT conname FROM pg_constraint
            WHERE conrelid = 'public.mfa_challenges'::regclass AND contype = 'c'
              AND conname <> 'mfa_challenges_purpose_ck' AND pg_get_constraintdef(oid) ILIKE '%purpose%' LOOP
    EXECUTE format('ALTER TABLE mfa_challenges DROP CONSTRAINT %I', c.conname);
  END LOOP;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'mfa_challenges_purpose_ck') THEN
    ALTER TABLE mfa_challenges ADD CONSTRAINT mfa_challenges_purpose_ck CHECK (purpose IN ('LOGIN', 'ENROLL', 'PASSWORD'));
  END IF;
END $$;
