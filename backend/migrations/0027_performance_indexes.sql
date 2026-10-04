-- Point 10H query-path indexes. Validate with EXPLAIN ANALYZE on production-like volumes before changing further.
CREATE INDEX IF NOT EXISTS idx_finance_payments_school_created ON finance_payments(school_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_finance_payments_enrollment_created ON finance_payments(school_id,enrollment_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_outbox_pending_school_created ON outbox_events(school_id,created_at) WHERE published_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(school_id,user_id,created_at DESC) WHERE read_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_sync_inbox_device_received ON sync_inbox(school_id,device_id,received_at DESC);
