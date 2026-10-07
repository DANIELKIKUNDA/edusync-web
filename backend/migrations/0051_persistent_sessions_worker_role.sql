-- N0 prerequisite (owner decision 2026-10-07): a session on an approved device stays signed in.
-- No periodic re-authentication: expires_at becomes optional (NULL = no absolute expiry). Security comes from
-- rotation at every renewal, reuse detection (stolen cookie => whole session revoked), per-device revocation,
-- password change / account deactivation / membership change invalidation, and explicit logout.
ALTER TABLE user_device_sessions ALTER COLUMN expires_at DROP NOT NULL;
ALTER TABLE user_device_sessions ALTER COLUMN expires_at DROP DEFAULT;
UPDATE user_device_sessions SET expires_at = NULL WHERE revoked_at IS NULL;

-- N0 prerequisite: dedicated worker role (created by the provisioner when EDUSYNC_WORKER_DATABASE_URL is set).
-- Workers process queues of every school: they read/update only the four queue tables below, through policies
-- scoped TO edusync_worker. No business table (students, finance, personnel...) is reachable.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edusync_worker') THEN
    EXECUTE 'DROP POLICY IF EXISTS worker_queue ON outbox_events';
    EXECUTE 'CREATE POLICY worker_queue ON outbox_events TO edusync_worker USING (true) WITH CHECK (true)';
    EXECUTE 'DROP POLICY IF EXISTS worker_queue ON communication_deliveries';
    EXECUTE 'CREATE POLICY worker_queue ON communication_deliveries TO edusync_worker USING (true) WITH CHECK (true)';
    EXECUTE 'DROP POLICY IF EXISTS worker_read ON communication_messages';
    EXECUTE 'CREATE POLICY worker_read ON communication_messages FOR SELECT TO edusync_worker USING (true)';
    EXECUTE 'DROP POLICY IF EXISTS worker_read ON communication_settings';
    EXECUTE 'CREATE POLICY worker_read ON communication_settings FOR SELECT TO edusync_worker USING (true)';
  END IF;
END $$;
