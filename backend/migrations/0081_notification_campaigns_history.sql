-- Notifications système, lot 2026-10: history searchable and paginated server-side; audience size kept per campaign.
--
-- people_count: distinct accounts reached (a member of several schools sees the notification in each school space, so
-- recipient_count = deliveries can be larger). NULL for campaigns sent before this lot (shown as « non mesuré »).
ALTER TABLE platform_system_notifications ADD COLUMN IF NOT EXISTS people_count integer CHECK (people_count IS NULL OR people_count >= 0);
CREATE INDEX IF NOT EXISTS idx_platform_system_notifications_search
  ON platform_system_notifications USING gin ((edusync_search_key(title)) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_platform_system_notifications_author
  ON platform_system_notifications(created_by, created_at DESC, id DESC);
