-- N1 certification 2026-10: in-app notifications as business objects + push subscription abstraction.
-- * a notification can be addressed to a platform account (school_id NULL) or to a school member;
-- * a campaign never creates two notifications for the same recipient (unique index);
-- * optional expiry and internal link (relative path only, validated by the API and here);
-- * push subscriptions are per device, revocable; no real provider is wired (BLOCKED_EXTERNAL).

ALTER TABLE notifications ADD COLUMN IF NOT EXISTS campaign_id uuid REFERENCES platform_system_notifications(id);
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS severity varchar(16) NOT NULL DEFAULT 'INFO';
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS link_path varchar(200);
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS expires_at timestamptz;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='notifications_severity_ck') THEN
    ALTER TABLE notifications ADD CONSTRAINT notifications_severity_ck CHECK (severity IN ('INFO','WARNING','CRITICAL'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='notifications_link_path_ck') THEN
    -- internal relative path only: no scheme, no host, no protocol-relative URL, no backslash
    ALTER TABLE notifications ADD CONSTRAINT notifications_link_path_ck
      CHECK (link_path IS NULL OR (link_path ~ '^/[A-Za-z0-9/_?=&.-]*$' AND link_path !~ '^//' AND position('\' in link_path)=0));
  END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_campaign_recipient
  ON notifications(campaign_id, user_id, coalesce(school_id, '00000000-0000-0000-0000-000000000000'::uuid)) WHERE campaign_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_notifications_inbox ON notifications(user_id, school_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(user_id, school_id) WHERE read_at IS NULL;

-- Campaign targeting beyond "all active schools" / "one school".
DO $$
DECLARE c record;
BEGIN
  FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='platform_system_notifications'::regclass AND contype='c'
           AND pg_get_constraintdef(oid) LIKE '%target_scope%' LOOP
    EXECUTE format('ALTER TABLE platform_system_notifications DROP CONSTRAINT %I', c.conname);
  END LOOP;
END $$;
ALTER TABLE platform_system_notifications ADD COLUMN IF NOT EXISTS target_json jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE platform_system_notifications ADD COLUMN IF NOT EXISTS link_path varchar(200);
ALTER TABLE platform_system_notifications ADD COLUMN IF NOT EXISTS expires_at timestamptz;
ALTER TABLE platform_system_notifications ADD CONSTRAINT platform_system_notifications_target_scope_ck CHECK (target_scope IN
  ('ALL_ACTIVE_SCHOOLS','SCHOOL','SCHOOLS','SCHOOL_ROLE','SCHOOL_USER','PLATFORM_ALL','PLATFORM_ROLE','PLATFORM_USER'));
ALTER TABLE platform_system_notifications ADD CONSTRAINT platform_system_notification_target_ck CHECK (
  (target_scope='ALL_ACTIVE_SCHOOLS' AND target_school_id IS NULL) OR
  (target_scope='SCHOOL' AND target_school_id IS NOT NULL) OR
  (target_scope NOT IN ('ALL_ACTIVE_SCHOOLS','SCHOOL')));

CREATE TABLE IF NOT EXISTS push_subscriptions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id),
  school_id uuid REFERENCES schools(id),
  provider varchar(16) NOT NULL CHECK (provider IN ('MOCK','WEBPUSH','FCM')),
  endpoint_hash char(64) NOT NULL,
  device_label varchar(120),
  created_at timestamptz NOT NULL DEFAULT now(),
  last_used_at timestamptz,
  revoked_at timestamptz,
  revoked_reason varchar(48)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_push_subscription_active ON push_subscriptions(user_id, endpoint_hash) WHERE revoked_at IS NULL;
ALTER TABLE push_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE push_subscriptions FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_platform') THEN
    DROP POLICY IF EXISTS push_subscriptions_platform ON push_subscriptions;
    CREATE POLICY push_subscriptions_platform ON push_subscriptions FOR ALL TO edusync_platform USING (true) WITH CHECK (true);
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_tenant') THEN
    DROP POLICY IF EXISTS push_subscriptions_tenant ON push_subscriptions;
    CREATE POLICY push_subscriptions_tenant ON push_subscriptions FOR ALL TO edusync_tenant
      USING (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid
             AND user_id = nullif(current_setting('app.current_user_id', true), '')::uuid)
      WITH CHECK (school_id = nullif(current_setting('app.current_school_id', true), '')::uuid
             AND user_id = nullif(current_setting('app.current_user_id', true), '')::uuid);
  END IF;
END $$;
