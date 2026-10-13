-- Second factor for platform accounts (MFA_PROPOSAL.md, option B; owner decision 2026-10-13).
-- TOTP secrets are stored encrypted (AES-256-GCM, key outside the database); recovery codes as Argon2 hashes.
-- These tables are reachable by the platform/IAM role only: a school (tenant) connection can never read them.

-- Reconciliation: an earlier prototype, never committed, created tables with the same names in some local
-- databases (detected by the absence of the "status" column). They are kept for traceability under a legacy name,
-- out of reach of the application roles; their factors are not trusted, so sessions they marked as verified lose it.
DO $$
DECLARE
  t text;
  idx record;
BEGIN
  IF to_regclass('public.user_mfa_factors') IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'user_mfa_factors' AND column_name = 'status') THEN
    FOREACH t IN ARRAY ARRAY['user_mfa_factors', 'user_mfa_recovery_codes', 'mfa_challenges'] LOOP
      IF to_regclass('public.' || t) IS NOT NULL THEN
        FOR idx IN SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = t LOOP
          EXECUTE format('ALTER INDEX %I RENAME TO %I', idx.indexname, left('legacy_proto_' || idx.indexname, 63));
        END LOOP;
        EXECUTE format('ALTER TABLE %I RENAME TO %I', t, 'legacy_prototype_' || t);
        EXECUTE format('REVOKE ALL ON %I FROM PUBLIC, edusync_tenant, edusync_platform', 'legacy_prototype_' || t);
      END IF;
    END LOOP;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'user_device_sessions' AND column_name = 'mfa_verified_at') THEN
      UPDATE user_device_sessions SET mfa_verified_at = NULL WHERE mfa_verified_at IS NOT NULL;
    END IF;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS user_mfa_factors (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id),
  kind varchar(16) NOT NULL DEFAULT 'TOTP' CHECK (kind = 'TOTP'),
  status varchar(16) NOT NULL CHECK (status IN ('PENDING', 'ACTIVE', 'REVOKED')),
  secret_ciphertext text NOT NULL,
  -- Highest TOTP step accepted so far: a code is never accepted twice (replay inside its own 30 s window included).
  last_used_step bigint NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  confirmed_at timestamptz,
  revoked_at timestamptz,
  revoked_reason varchar(64),
  CONSTRAINT mfa_factor_active_confirmed CHECK (status <> 'ACTIVE' OR confirmed_at IS NOT NULL),
  CONSTRAINT mfa_factor_revoked_dated CHECK (status <> 'REVOKED' OR revoked_at IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_mfa_factor_one_active ON user_mfa_factors(user_id) WHERE status = 'ACTIVE';
CREATE UNIQUE INDEX IF NOT EXISTS ux_mfa_factor_one_pending ON user_mfa_factors(user_id) WHERE status = 'PENDING';

CREATE TABLE IF NOT EXISTS user_mfa_recovery_codes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id),
  factor_id uuid NOT NULL REFERENCES user_mfa_factors(id),
  code_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  used_at timestamptz,
  revoked_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_mfa_recovery_usable ON user_mfa_recovery_codes(user_id) WHERE used_at IS NULL AND revoked_at IS NULL;

-- Intermediate step between the password and the session: an opaque single-use token (hash only), short-lived,
-- with its own attempt counter. It is not a JWT and no API route accepts it as a credential.
CREATE TABLE IF NOT EXISTS mfa_challenges (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id),
  purpose varchar(16) NOT NULL CHECK (purpose IN ('LOGIN', 'ENROLL')),
  token_hash varchar(64) NOT NULL UNIQUE,
  user_version integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  attempts integer NOT NULL DEFAULT 0,
  consumed_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_mfa_challenges_user ON mfa_challenges(user_id, created_at DESC);

-- A platform session exists only after the second factor; the access-token check reads this column.
ALTER TABLE user_device_sessions ADD COLUMN IF NOT EXISTS mfa_verified_at timestamptz;
ALTER TABLE user_device_sessions ADD COLUMN IF NOT EXISTS mfa_method varchar(16);

ALTER TABLE user_mfa_factors ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_mfa_factors FORCE ROW LEVEL SECURITY;
ALTER TABLE user_mfa_recovery_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_mfa_recovery_codes FORCE ROW LEVEL SECURITY;
ALTER TABLE mfa_challenges ENABLE ROW LEVEL SECURITY;
ALTER TABLE mfa_challenges FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS mfa_platform_only ON user_mfa_factors;
CREATE POLICY mfa_platform_only ON user_mfa_factors TO edusync_platform USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS mfa_platform_only ON user_mfa_recovery_codes;
CREATE POLICY mfa_platform_only ON user_mfa_recovery_codes TO edusync_platform USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS mfa_platform_only ON mfa_challenges;
CREATE POLICY mfa_platform_only ON mfa_challenges TO edusync_platform USING (true) WITH CHECK (true);

REVOKE ALL ON user_mfa_factors, user_mfa_recovery_codes, mfa_challenges FROM PUBLIC;
REVOKE ALL ON user_mfa_factors, user_mfa_recovery_codes, mfa_challenges FROM edusync_tenant;
-- No DELETE: factors and recovery codes are revoked, never erased (audit trail).
GRANT SELECT, INSERT, UPDATE ON user_mfa_factors, user_mfa_recovery_codes, mfa_challenges TO edusync_platform;
-- Default privileges of the database may add DELETE/TRUNCATE at creation time: take them back explicitly.
REVOKE DELETE, TRUNCATE ON user_mfa_factors, user_mfa_recovery_codes, mfa_challenges FROM edusync_platform;
