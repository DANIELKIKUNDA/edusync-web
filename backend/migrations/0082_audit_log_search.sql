-- Journal d'audit, lot 2026-10: indexes for the server-side search and the quick categories (read path only: the audit
-- trail stays append-only, trigger trg_audit_no_update untouched).
CREATE INDEX IF NOT EXISTS idx_audit_search_trgm ON audit_events
  USING gin ((edusync_search_key(action || ' ' || entity_type || ' ' || coalesce(reason, ''))) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_audit_failures_occurred ON audit_events(occurred_at DESC, id DESC) WHERE result <> 'SUCCESS';
CREATE INDEX IF NOT EXISTS idx_audit_entity_type_occurred ON audit_events(entity_type, occurred_at DESC, id DESC);
