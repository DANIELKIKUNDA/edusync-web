-- Point 6C — source explicite des régularisations hors caisse; jamais confondues avec les encaissements caisse.
CREATE TABLE IF NOT EXISTS finance_charge_regularizations(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 charge_id uuid NOT NULL REFERENCES finance_charges(id), amount numeric(18,2) NOT NULL CHECK(amount>0),
 reason varchar(240) NOT NULL CHECK(btrim(reason)<>''), reference varchar(120), actor_user_id uuid NOT NULL REFERENCES users(id),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_finance_regularizations_charge ON finance_charge_regularizations(school_id,charge_id,created_at);
ALTER TABLE finance_charge_regularizations ENABLE ROW LEVEL SECURITY; ALTER TABLE finance_charge_regularizations FORCE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY finance_regularizations_tenant ON finance_charge_regularizations USING (school_id=current_setting('app.school_id',true)::uuid) WITH CHECK(school_id=current_setting('app.school_id',true)::uuid); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
