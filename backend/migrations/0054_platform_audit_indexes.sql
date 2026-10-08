-- N1 certification 2026-10: platform-wide audit search (no school filter) and team idempotency replay.
CREATE INDEX IF NOT EXISTS idx_audit_occurred_id_desc ON audit_events(occurred_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action_occurred ON audit_events(action, occurred_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor_occurred ON audit_events(actor_user_id, occurred_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_audit_correlation ON audit_events(correlation_id) WHERE correlation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_entity_global ON audit_events(entity_id, occurred_at DESC) WHERE entity_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_idempotency_replay ON audit_events(idempotency_key, action, actor_user_id) WHERE idempotency_key IS NOT NULL;
