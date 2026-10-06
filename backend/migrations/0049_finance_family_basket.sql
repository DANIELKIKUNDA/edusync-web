-- Local closure 2026-10: family basket ("panier familial", capability finance.checkout.family.collect).
-- One operation = several explicit lines (one child, the charges chosen by the cashier, one amount, one
-- currency). Every line is an ordinary payment with its own receipt, allocated by the unchanged checkout
-- rule; the basket only groups them atomically (all lines or none) under one Idempotency-Key.
CREATE TABLE IF NOT EXISTS finance_family_baskets (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 school_id uuid NOT NULL REFERENCES schools(id),
 family_id uuid NOT NULL REFERENCES families(id),
 idempotency_key varchar(180) NOT NULL,
 request_sha256 char(64) NOT NULL,
 cash_session_id uuid NOT NULL REFERENCES finance_cash_sessions(id),
 actor_user_id uuid NOT NULL REFERENCES users(id),
 line_count integer NOT NULL CHECK (line_count BETWEEN 1 AND 20),
 totals_json jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (school_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS finance_family_basket_payments (
 basket_id uuid NOT NULL REFERENCES finance_family_baskets(id),
 school_id uuid NOT NULL REFERENCES schools(id),
 line_no integer NOT NULL CHECK (line_no BETWEEN 1 AND 20),
 payment_id uuid NOT NULL UNIQUE REFERENCES finance_payments(id),
 PRIMARY KEY (basket_id, line_no)
);
ALTER TABLE finance_family_baskets ENABLE ROW LEVEL SECURITY; ALTER TABLE finance_family_baskets FORCE ROW LEVEL SECURITY;
ALTER TABLE finance_family_basket_payments ENABLE ROW LEVEL SECURITY; ALTER TABLE finance_family_basket_payments FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS finance_family_baskets_tenant ON finance_family_baskets;
CREATE POLICY finance_family_baskets_tenant ON finance_family_baskets USING (school_id=current_setting('app.current_school_id',true)::uuid) WITH CHECK (school_id=current_setting('app.current_school_id',true)::uuid);
DROP POLICY IF EXISTS finance_family_basket_payments_tenant ON finance_family_basket_payments;
CREATE POLICY finance_family_basket_payments_tenant ON finance_family_basket_payments USING (school_id=current_setting('app.current_school_id',true)::uuid) WITH CHECK (school_id=current_setting('app.current_school_id',true)::uuid);
-- Append-only, like the ledger.
GRANT SELECT, INSERT ON finance_family_baskets, finance_family_basket_payments TO edusync_tenant;
REVOKE UPDATE, DELETE ON finance_family_baskets, finance_family_basket_payments FROM edusync_tenant;
