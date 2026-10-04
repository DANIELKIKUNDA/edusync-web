-- Point 6A.1 — séquençage universel + anticipation intégrée au guichet unique.
ALTER TABLE finance_charges DROP CONSTRAINT IF EXISTS finance_charges_periodicity_check;
ALTER TABLE finance_charges ADD CONSTRAINT finance_charges_periodicity_check CHECK(periodicity IN('ONE_OFF','MONTHLY','PERIODIC','INSTALLMENT'));
ALTER TABLE finance_charges ADD COLUMN IF NOT EXISTS sequence_group varchar(96);
ALTER TABLE finance_charges ADD COLUMN IF NOT EXISTS sequence_order smallint;
CREATE INDEX IF NOT EXISTS idx_finance_charges_sequence ON finance_charges(school_id,enrollment_id,sequence_group,sequence_order) WHERE status='ACTIVE';

CREATE TABLE IF NOT EXISTS finance_anticipation_plans(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,academic_year_id uuid NOT NULL REFERENCES academic_years(id),
 label varchar(160) NOT NULL,currency varchar(3) NOT NULL CHECK(currency IN('CDF','USD')),enabled boolean NOT NULL DEFAULT true,
 rules_json jsonb NOT NULL DEFAULT '{}'::jsonb,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS finance_anticipation_memberships(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,plan_id uuid NOT NULL REFERENCES finance_anticipation_plans(id),
 enrollment_id uuid NOT NULL REFERENCES enrollments(id),status varchar(12) NOT NULL CHECK(status IN('ACCEPTED','DECLINED')),decided_at timestamptz NOT NULL DEFAULT now(),decided_by uuid REFERENCES users(id),
 UNIQUE(school_id,plan_id,enrollment_id));
CREATE TABLE IF NOT EXISTS finance_advance_allocations(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,payment_id uuid NOT NULL REFERENCES finance_payments(id),
 enrollment_id uuid NOT NULL REFERENCES enrollments(id),plan_id uuid NOT NULL REFERENCES finance_anticipation_plans(id),currency varchar(3) NOT NULL CHECK(currency IN('CDF','USD')),
 amount numeric(18,2) NOT NULL CHECK(amount>0),remaining_amount numeric(18,2) NOT NULL CHECK(remaining_amount>=0),target_summary varchar(240),created_at timestamptz NOT NULL DEFAULT now());
ALTER TABLE finance_anticipation_plans ENABLE ROW LEVEL SECURITY; ALTER TABLE finance_anticipation_plans FORCE ROW LEVEL SECURITY;
ALTER TABLE finance_anticipation_memberships ENABLE ROW LEVEL SECURITY; ALTER TABLE finance_anticipation_memberships FORCE ROW LEVEL SECURITY;
ALTER TABLE finance_advance_allocations ENABLE ROW LEVEL SECURITY; ALTER TABLE finance_advance_allocations FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
 CREATE POLICY finance_anticipation_plans_tenant ON finance_anticipation_plans USING(school_id=current_setting('app.school_id',true)::uuid) WITH CHECK(school_id=current_setting('app.school_id',true)::uuid);
 CREATE POLICY finance_anticipation_memberships_tenant ON finance_anticipation_memberships USING(school_id=current_setting('app.school_id',true)::uuid) WITH CHECK(school_id=current_setting('app.school_id',true)::uuid);
 CREATE POLICY finance_advance_allocations_tenant ON finance_advance_allocations USING(school_id=current_setting('app.school_id',true)::uuid) WITH CHECK(school_id=current_setting('app.school_id',true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
REVOKE UPDATE,DELETE ON finance_advance_allocations FROM PUBLIC;
