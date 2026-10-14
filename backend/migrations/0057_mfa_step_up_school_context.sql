-- Second factor, owner decisions of 2026-10-13 (MFA_PLATFORM_OPTION_B_REPORT.md §6):
--  1. step-up: sensitive platform actions need a code confirmed in the last minutes (per device session);
--  2. an account that has a second factor (or a platform role) gives it in every space, school spaces included;
--  3. a reset by another Manager alerts the account (application side, no schema change).

-- 1. Last time this device session confirmed a TOTP code (sign-in counts; then POST /auth/platform/mfa/step-up).
ALTER TABLE user_device_sessions ADD COLUMN IF NOT EXISTS mfa_stepup_at timestamptz;

-- 2. A session that must carry the second factor says so: a school-space token of such an account is refused when
--    its session never passed it (defence in depth: the sign-in itself already asks for the code).
ALTER TABLE user_device_sessions ADD COLUMN IF NOT EXISTS mfa_required boolean NOT NULL DEFAULT false;

-- The intermediate step now remembers which space it will open.
ALTER TABLE mfa_challenges ADD COLUMN IF NOT EXISTS scope varchar(16) NOT NULL DEFAULT 'PLATFORM';
ALTER TABLE mfa_challenges ADD COLUMN IF NOT EXISTS school_id uuid REFERENCES schools(id);
ALTER TABLE mfa_challenges ADD COLUMN IF NOT EXISTS membership_id uuid REFERENCES school_memberships(id);
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'mfa_challenge_scope_ck') THEN
    ALTER TABLE mfa_challenges ADD CONSTRAINT mfa_challenge_scope_ck CHECK (
      (scope = 'PLATFORM' AND school_id IS NULL AND membership_id IS NULL)
      OR (scope = 'SCHOOL' AND school_id IS NOT NULL AND membership_id IS NOT NULL));
  END IF;
END $$;

-- Open school sessions of accounts that now owe the second factor in every space (a confirmed factor, or an active
-- platform role) are marked: without a verified second factor they stop working and the person signs in again.
UPDATE user_device_sessions s SET mfa_required = true
 WHERE s.school_id IS NOT NULL AND s.revoked_at IS NULL AND (
   EXISTS (SELECT 1 FROM user_mfa_factors f WHERE f.user_id = s.user_id AND f.status = 'ACTIVE')
   OR EXISTS (SELECT 1 FROM rbac_assignments a JOIN rbac_roles r ON r.id = a.role_id
               WHERE a.user_id = s.user_id AND a.school_id IS NULL AND a.active AND r.level = 'PLATFORM' AND r.status = 'ACTIVE'));
