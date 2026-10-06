-- Local closure 2026-10: the persistent device session was effectively permanent (cookie 3650 days,
-- no server-side expiry, no rotation). It now has an absolute lifetime, an idle timeout (computed from
-- last_seen_at by the API) and a rotating opaque token with a short grace window for concurrent tabs.
-- A rotated token presented after its grace window is treated as theft: the whole session is revoked.
ALTER TABLE user_device_sessions ADD COLUMN IF NOT EXISTS expires_at timestamptz;
ALTER TABLE user_device_sessions ADD COLUMN IF NOT EXISTS previous_token_hash varchar(64);
ALTER TABLE user_device_sessions ADD COLUMN IF NOT EXISTS previous_valid_until timestamptz;
UPDATE user_device_sessions SET expires_at = created_at + interval '90 days' WHERE expires_at IS NULL;
ALTER TABLE user_device_sessions ALTER COLUMN expires_at SET DEFAULT now() + interval '90 days';
ALTER TABLE user_device_sessions ALTER COLUMN expires_at SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_device_sessions_previous_token ON user_device_sessions(previous_token_hash) WHERE previous_token_hash IS NOT NULL;
