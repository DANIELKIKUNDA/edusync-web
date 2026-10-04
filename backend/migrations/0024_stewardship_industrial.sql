-- Point 9 — Intendance industrielle: patrimoine, locaux, consommables, ventes et inventaires physiques.
CREATE TABLE IF NOT EXISTS inventory_locations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 code varchar(48) NOT NULL, label varchar(160) NOT NULL, location_type varchar(32) NOT NULL DEFAULT 'ROOM',
 capacity integer CHECK(capacity IS NULL OR capacity>=0), status varchar(24) NOT NULL DEFAULT 'OPERATIONAL' CHECK(status IN('OPERATIONAL','MAINTENANCE','OUT_OF_SERVICE')),
 notes text, version bigint NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE(school_id,code));
CREATE TABLE IF NOT EXISTS inventory_items (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 code varchar(64) NOT NULL, label varchar(180) NOT NULL, item_kind varchar(24) NOT NULL CHECK(item_kind IN('CONSUMABLE','SALE_PRODUCT')),
 unit varchar(32) NOT NULL, product_id uuid REFERENCES school_products(id) ON DELETE SET NULL,
 quantity numeric(18,3) NOT NULL DEFAULT 0 CHECK(quantity>=0), low_threshold numeric(18,3) NOT NULL DEFAULT 0 CHECK(low_threshold>=0),
 location_id uuid REFERENCES inventory_locations(id) ON DELETE SET NULL, enabled boolean NOT NULL DEFAULT true,
 version bigint NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE(school_id,code));
CREATE TABLE IF NOT EXISTS inventory_item_movements (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 item_id uuid NOT NULL REFERENCES inventory_items(id) ON DELETE RESTRICT,
 movement_type varchar(20) NOT NULL CHECK(movement_type IN('RECEIPT','ISSUE','SALE','ADJUSTMENT','COUNT_ADJUSTMENT')),
 quantity_delta numeric(18,3) NOT NULL CHECK(quantity_delta<>0), reason text NOT NULL, destination varchar(180), reference varchar(96),
 actor_user_id uuid NOT NULL REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS inventory_asset_types (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 code varchar(64) NOT NULL, label varchar(180) NOT NULL, unit varchar(32) NOT NULL DEFAULT 'pièce', enabled boolean NOT NULL DEFAULT true, UNIQUE(school_id,code));
CREATE TABLE IF NOT EXISTS inventory_assets (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 asset_type_id uuid NOT NULL REFERENCES inventory_asset_types(id) ON DELETE RESTRICT, asset_tag varchar(96), quantity numeric(18,3) NOT NULL DEFAULT 1 CHECK(quantity>0),
 location_id uuid REFERENCES inventory_locations(id) ON DELETE SET NULL,
 status varchar(24) NOT NULL DEFAULT 'GOOD' CHECK(status IN('GOOD','TO_REPAIR','IN_REPAIR','OUT_OF_SERVICE','LOST','DISPOSED')),
 acquired_on date, notes text, version bigint NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS inventory_asset_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 asset_id uuid NOT NULL REFERENCES inventory_assets(id) ON DELETE RESTRICT, event_type varchar(24) NOT NULL CHECK(event_type IN('CREATE','MOVE','STATUS','REPAIR','DISPOSE')),
 from_status varchar(24), to_status varchar(24), from_location_id uuid, to_location_id uuid, reason text NOT NULL,
 actor_user_id uuid NOT NULL REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS inventory_counts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 code varchar(64) NOT NULL, counted_on date NOT NULL DEFAULT current_date, status varchar(16) NOT NULL DEFAULT 'DRAFT' CHECK(status IN('DRAFT','VALIDATED')),
 notes text, created_by_user_id uuid NOT NULL REFERENCES users(id), validated_by_user_id uuid REFERENCES users(id), validated_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(school_id,code));
CREATE TABLE IF NOT EXISTS inventory_count_lines (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 count_id uuid NOT NULL REFERENCES inventory_counts(id) ON DELETE CASCADE, item_id uuid NOT NULL REFERENCES inventory_items(id) ON DELETE RESTRICT,
 theoretical_quantity numeric(18,3) NOT NULL, counted_quantity numeric(18,3) NOT NULL CHECK(counted_quantity>=0), reason text,
 UNIQUE(count_id,item_id));
CREATE INDEX IF NOT EXISTS ix_inventory_item_movements ON inventory_item_movements(school_id,item_id,created_at DESC);
CREATE INDEX IF NOT EXISTS ix_inventory_assets_status ON inventory_assets(school_id,status);
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['inventory_locations','inventory_items','inventory_item_movements','inventory_asset_types','inventory_assets','inventory_asset_events','inventory_counts','inventory_count_lines'] LOOP
 EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t); EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I',t); EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (school_id=current_setting(''app.school_id'',true)::uuid) WITH CHECK (school_id=current_setting(''app.school_id'',true)::uuid)',t);
 END LOOP; END $$;
GRANT SELECT,INSERT,UPDATE ON inventory_locations,inventory_items,inventory_item_movements,inventory_asset_types,inventory_assets,inventory_asset_events,inventory_counts,inventory_count_lines TO edusync_tenant;
-- Existing Point 6B sale stock remains authoritative for school_products; Intendance reads it rather than duplicating sale inventory.
-- Permission hardening confirmed at Point 9: secondary Directors are schooling-first.
-- No Personnel or Finance capability is part of their baseline. Schools may add explicit exception grants.
DELETE FROM rbac_role_capabilities rc USING rbac_roles r
WHERE rc.role_id=r.id AND r.kind='SCHOOL_STANDARD' AND r.code IN ('DIRECTEUR_ETUDES','DIRECTEUR_DISCIPLINE')
  AND (rc.capability_code LIKE 'finance.%' OR rc.capability_code LIKE 'personnel.%');
