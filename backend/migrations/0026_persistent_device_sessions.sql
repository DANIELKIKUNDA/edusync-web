-- POINT 10H: persistent same-device sessions. Access JWT stays short-lived; durable session is opaque, revocable and server-side.
CREATE TABLE IF NOT EXISTS user_device_sessions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 school_id uuid REFERENCES schools(id) ON DELETE CASCADE, membership_id uuid REFERENCES school_memberships(id) ON DELETE CASCADE,
 token_hash varchar(64) NOT NULL UNIQUE, label varchar(160), user_agent_hash varchar(64),
 created_at timestamptz NOT NULL DEFAULT now(), last_seen_at timestamptz NOT NULL DEFAULT now(),
 rotated_at timestamptz, revoked_at timestamptz, revoked_reason varchar(96),
 user_version integer NOT NULL, membership_version integer
);
CREATE INDEX IF NOT EXISTS idx_device_sessions_user ON user_device_sessions(user_id,revoked_at,last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_device_sessions_school ON user_device_sessions(school_id,user_id,revoked_at);
ALTER TABLE user_device_sessions ENABLE ROW LEVEL SECURITY; ALTER TABLE user_device_sessions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS device_session_tenant ON user_device_sessions;
CREATE POLICY device_session_tenant ON user_device_sessions USING (school_id IS NULL OR school_id=nullif(current_setting('app.current_school_id',true),'')::uuid) WITH CHECK (school_id IS NULL OR school_id=nullif(current_setting('app.current_school_id',true),'')::uuid);
GRANT SELECT,INSERT,UPDATE ON user_device_sessions TO edusync_tenant,edusync_platform;
REVOKE DELETE ON user_device_sessions FROM edusync_tenant,edusync_platform;
DROP POLICY IF EXISTS device_session_platform ON user_device_sessions;
CREATE POLICY device_session_platform ON user_device_sessions TO edusync_platform USING (true) WITH CHECK (true);
