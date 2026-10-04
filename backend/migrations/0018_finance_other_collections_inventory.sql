-- Point 6B — Autres encaissements: ventes reliées au stock + dettes transannuelles.
CREATE TABLE IF NOT EXISTS inventory_stock (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 product_id uuid NOT NULL REFERENCES school_products(id) ON DELETE RESTRICT,
 quantity numeric(18,3) NOT NULL DEFAULT 0 CHECK(quantity>=0), low_threshold numeric(18,3) NOT NULL DEFAULT 0 CHECK(low_threshold>=0),
 updated_at timestamptz NOT NULL DEFAULT now(), version bigint NOT NULL DEFAULT 1, UNIQUE(school_id,product_id));
CREATE TABLE IF NOT EXISTS inventory_stock_movements (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 product_id uuid NOT NULL REFERENCES school_products(id) ON DELETE RESTRICT, movement_type varchar(16) NOT NULL CHECK(movement_type IN('RECEIPT','SALE','ISSUE','ADJUSTMENT')),
 quantity_delta numeric(18,3) NOT NULL CHECK(quantity_delta<>0), reason text, reference varchar(96), actor_user_id uuid, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS finance_product_sales (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 student_id uuid REFERENCES students(id) ON DELETE RESTRICT, enrollment_id uuid REFERENCES enrollments(id) ON DELETE RESTRICT,
 cash_session_id uuid NOT NULL REFERENCES finance_cash_sessions(id) ON DELETE RESTRICT, payment_id uuid NOT NULL REFERENCES finance_payments(id) ON DELETE RESTRICT,
 product_id uuid NOT NULL REFERENCES school_products(id) ON DELETE RESTRICT, quantity numeric(18,3) NOT NULL CHECK(quantity>0), unit_price numeric(18,2) NOT NULL CHECK(unit_price>0),
 currency varchar(3) NOT NULL CHECK(currency IN('CDF','USD')), total numeric(18,2) NOT NULL CHECK(total>0), actor_user_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS ix_stock_movements_school_product_created ON inventory_stock_movements(school_id,product_id,created_at DESC);
CREATE INDEX IF NOT EXISTS ix_product_sales_school_created ON finance_product_sales(school_id,created_at DESC);
CREATE INDEX IF NOT EXISTS ix_finance_charges_old_debt ON finance_charges(school_id,enrollment_id,status) WHERE net_amount>paid_amount;
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['inventory_stock','inventory_stock_movements','finance_product_sales'] LOOP
 EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t); EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I',t); EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (school_id = current_setting(''app.school_id'',true)::uuid) WITH CHECK (school_id = current_setting(''app.school_id'',true)::uuid)',t);
 END LOOP; END $$;
GRANT SELECT,INSERT,UPDATE ON inventory_stock,inventory_stock_movements,finance_product_sales TO edusync_tenant;
