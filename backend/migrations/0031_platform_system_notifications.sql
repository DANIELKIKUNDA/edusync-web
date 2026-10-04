-- Point 11C — durable platform system-notification campaigns.
CREATE TABLE IF NOT EXISTS platform_system_notifications (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title varchar(180) NOT NULL,
  body text NOT NULL,
  severity varchar(16) NOT NULL CHECK (severity IN ('INFO','WARNING','CRITICAL')),
  target_scope varchar(24) NOT NULL CHECK (target_scope IN ('ALL_ACTIVE_SCHOOLS','SCHOOL')),
  target_school_id uuid REFERENCES schools(id),
  created_by uuid NOT NULL REFERENCES users(id),
  recipient_count integer NOT NULL DEFAULT 0 CHECK (recipient_count >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT platform_system_notification_target_ck CHECK (
    (target_scope='ALL_ACTIVE_SCHOOLS' AND target_school_id IS NULL) OR
    (target_scope='SCHOOL' AND target_school_id IS NOT NULL)
  )
);
CREATE INDEX IF NOT EXISTS idx_platform_system_notifications_created
  ON platform_system_notifications(created_at DESC,id DESC);
