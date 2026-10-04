-- Point 6D — registre de classe intelligent et traçabilité tarifaire/anticipation.
ALTER TABLE finance_charges ADD COLUMN IF NOT EXISTS fee_type_id uuid REFERENCES fee_types(id);
ALTER TABLE finance_charges ADD COLUMN IF NOT EXISTS tariff_id uuid REFERENCES tariffs(id);
CREATE INDEX IF NOT EXISTS ix_finance_charges_register ON finance_charges(school_id,enrollment_id,fee_type_id,period_order,status);
CREATE TABLE IF NOT EXISTS finance_advance_targets(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 advance_allocation_id uuid NOT NULL REFERENCES finance_advance_allocations(id) ON DELETE CASCADE,
 charge_id uuid NOT NULL REFERENCES finance_charges(id), amount numeric(18,2) NOT NULL CHECK(amount>0), created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(school_id,advance_allocation_id,charge_id));
ALTER TABLE finance_advance_targets ENABLE ROW LEVEL SECURITY; ALTER TABLE finance_advance_targets FORCE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY finance_advance_targets_tenant ON finance_advance_targets USING(school_id=current_setting('app.school_id',true)::uuid) WITH CHECK(school_id=current_setting('app.school_id',true)::uuid); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
REVOKE UPDATE,DELETE ON finance_advance_targets FROM PUBLIC;
