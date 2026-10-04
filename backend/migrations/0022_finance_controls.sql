-- Point 6H — Décisions financières, responsabilités et crédits/trop-perçus.
-- Remplace le fourre-tout UI « Suivi opérateur » par trois domaines financiers explicites.
CREATE TABLE IF NOT EXISTS finance_decisions(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id),
 enrollment_id uuid NOT NULL REFERENCES enrollments(id) ON DELETE RESTRICT,
 charge_id uuid REFERENCES finance_charges(id) ON DELETE RESTRICT,
 decision_type varchar(24) NOT NULL CHECK(decision_type IN ('EXEMPTION','REDUCTION','SPONSORSHIP','OTHER')),
 currency varchar(3) NOT NULL CHECK(currency IN ('CDF','USD')), amount numeric(18,2) NOT NULL CHECK(amount>=0),
 reason text NOT NULL, effective_date date NOT NULL, status varchar(16) NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','CANCELLED')),
 created_by uuid NOT NULL REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT now(),
 cancelled_by uuid REFERENCES users(id), cancelled_at timestamptz, cancel_reason text
);
CREATE INDEX IF NOT EXISTS idx_finance_decisions_school_date ON finance_decisions(school_id,effective_date DESC,created_at DESC);
ALTER TABLE finance_decisions ENABLE ROW LEVEL SECURITY; ALTER TABLE finance_decisions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS finance_decisions_tenant ON finance_decisions;
CREATE POLICY finance_decisions_tenant ON finance_decisions USING(school_id=current_setting('app.school_id',true)::uuid) WITH CHECK(school_id=current_setting('app.school_id',true)::uuid);

CREATE TABLE IF NOT EXISTS finance_responsibilities(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id),
 enrollment_id uuid NOT NULL REFERENCES enrollments(id) ON DELETE RESTRICT,
 responsibility_mode varchar(24) NOT NULL CHECK(responsibility_mode IN ('FAMILY','PAYROLL','SCHOOL','THIRD_PARTY')),
 responsible_label varchar(160), effective_from date NOT NULL, effective_until date, notes text,
 created_by uuid NOT NULL REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT now(),
 CHECK(effective_until IS NULL OR effective_until>=effective_from)
);
CREATE INDEX IF NOT EXISTS idx_finance_responsibility_enrollment ON finance_responsibilities(school_id,enrollment_id,effective_from DESC);
ALTER TABLE finance_responsibilities ENABLE ROW LEVEL SECURITY; ALTER TABLE finance_responsibilities FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS finance_responsibilities_tenant ON finance_responsibilities;
CREATE POLICY finance_responsibilities_tenant ON finance_responsibilities USING(school_id=current_setting('app.school_id',true)::uuid) WITH CHECK(school_id=current_setting('app.school_id',true)::uuid);

-- Append-only credit ledger. No manual cashier mutation capability exists in the certified RBAC registry.
CREATE TABLE IF NOT EXISTS finance_credits(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id),
 enrollment_id uuid REFERENCES enrollments(id) ON DELETE RESTRICT, payment_id uuid REFERENCES finance_payments(id) ON DELETE RESTRICT,
 currency varchar(3) NOT NULL CHECK(currency IN ('CDF','USD')), original_amount numeric(18,2) NOT NULL CHECK(original_amount>0),
 consumed_amount numeric(18,2) NOT NULL DEFAULT 0 CHECK(consumed_amount>=0 AND consumed_amount<=original_amount),
 origin varchar(32) NOT NULL, status varchar(16) NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','CONSUMED','REFUNDED','CANCELLED')),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_finance_credits_open ON finance_credits(school_id,status,created_at DESC);
ALTER TABLE finance_credits ENABLE ROW LEVEL SECURITY; ALTER TABLE finance_credits FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS finance_credits_tenant ON finance_credits;
CREATE POLICY finance_credits_tenant ON finance_credits USING(school_id=current_setting('app.school_id',true)::uuid) WITH CHECK(school_id=current_setting('app.school_id',true)::uuid);
