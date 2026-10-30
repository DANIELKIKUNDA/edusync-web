-- Certification Intendant (2026-10-30), performance: GET /stewardship/stock/movements lists the school's most recent
-- movements (ORDER BY created_at DESC LIMIT n). The existing index (school_id,item_id,created_at) only serves one
-- item's history, so the school list scanned and sorted the whole ledger (measured: sequential scan of 50 000 rows).
CREATE INDEX IF NOT EXISTS ix_inventory_item_movements_school_recent ON inventory_item_movements(school_id, created_at DESC);
