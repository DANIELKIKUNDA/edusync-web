-- Point 10H9: keyset pagination for append-only/high-volume journals.
CREATE INDEX IF NOT EXISTS idx_audit_school_occurred_id_desc ON audit_events(school_id, occurred_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_audit_school_action_occurred_id_desc ON audit_events(school_id, action, occurred_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_audit_school_entity_occurred_id_desc ON audit_events(school_id, entity_type, occurred_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_sync_conflict_school_received_id_desc ON sync_inbox(school_id, received_at DESC, id DESC) WHERE status IN ('CONFLICT','REJECTED');
CREATE INDEX IF NOT EXISTS idx_outbox_pending_school_created_id_desc ON outbox_events(school_id, created_at DESC, id DESC) WHERE published_at IS NULL;
