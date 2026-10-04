-- POINT 10H10: crash-safe workers. PostgreSQL is authoritative; Redis is a wake-up/transport layer.
ALTER TABLE outbox_events ADD COLUMN IF NOT EXISTS next_attempt_at timestamptz;
ALTER TABLE outbox_events ADD COLUMN IF NOT EXISTS locked_until timestamptz;
ALTER TABLE outbox_events ADD COLUMN IF NOT EXISTS processing_token uuid;
ALTER TABLE outbox_events ADD COLUMN IF NOT EXISTS last_error_code varchar(80);
ALTER TABLE outbox_events ADD COLUMN IF NOT EXISTS dead_lettered_at timestamptz;
CREATE INDEX IF NOT EXISTS idx_outbox_dispatch_due
  ON outbox_events(created_at,id)
  WHERE published_at IS NULL AND dead_lettered_at IS NULL;

ALTER TABLE communication_deliveries ADD COLUMN IF NOT EXISTS locked_until timestamptz;
ALTER TABLE communication_deliveries ADD COLUMN IF NOT EXISTS processing_token uuid;
CREATE INDEX IF NOT EXISTS idx_comm_delivery_due_recovery
  ON communication_deliveries(next_attempt_at,created_at,id)
  WHERE status IN ('PENDING','QUEUED','FAILED');
