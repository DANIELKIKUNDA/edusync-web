-- Distinguish asset metadata edits from actual status changes in the patrimonial ledger.
ALTER TABLE inventory_asset_events DROP CONSTRAINT IF EXISTS inventory_asset_events_event_type_check;
ALTER TABLE inventory_asset_events ADD CONSTRAINT inventory_asset_events_event_type_check
 CHECK (event_type IN ('CREATE','MOVE','STATUS','REPAIR','DISPOSE','UPDATE'));
