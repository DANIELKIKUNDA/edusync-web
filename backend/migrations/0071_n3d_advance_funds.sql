-- N3-D — « fonds anticipés » copied from the Desktop golden master (app/db/operations.py:290-470; schema.sql
-- advance_funds / advance_allocations / advance_receipts; migrations.py: origin_type, source_charge_id, origin_decision_id).
-- Doctrine L6: Plan anticipé ≠ Fonds anticipé. A fund is money received BEFORE any imputation, kept as an available
-- amount, imputed later on the oldest payable charges (same currency), or cancelled / refunded while nothing is imputed.
-- It never touches the plans tables and the plans never create a fund. The retired simplified Web mechanism
-- (finance_anticipation_plans / finance_advance_allocations / finance_advance_targets, 0 rows) stays untouched.
CREATE TABLE IF NOT EXISTS finance_advance_funds (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  student_id uuid NOT NULL REFERENCES students(id),
  enrollment_id uuid NOT NULL REFERENCES enrollments(id),
  amount numeric(18,2) NOT NULL CHECK (amount > 0),
  currency varchar(3) NOT NULL CHECK (currency IN ('CDF','USD')),
  mode varchar(16) NOT NULL CHECK (mode IN ('CASH','MOBILE_MONEY','BANQUE','AUTRE')),
  reference varchar(120),
  origin_type varchar(18) NOT NULL DEFAULT 'PAYMENT_ADVANCE' CHECK (origin_type IN ('PAYMENT_ADVANCE','DECISION_CREDIT')),
  source_charge_id uuid REFERENCES finance_charges(id),
  origin_decision_id uuid REFERENCES finance_decisions(id),
  receipt_number varchar(64),                      -- PAYMENT_ADVANCE only (Desktop advance_receipts), same sequence as payments
  cash_session_id uuid REFERENCES finance_cash_sessions(id),   -- PAYMENT_ADVANCE: the session that received the cash
  received_by uuid REFERENCES users(id),
  received_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (school_id, receipt_number)
);
CREATE INDEX IF NOT EXISTS idx_advance_funds_enrollment ON finance_advance_funds(school_id, enrollment_id, currency);
CREATE INDEX IF NOT EXISTS idx_advance_funds_origin ON finance_advance_funds(source_charge_id, origin_type);

-- Imputation of a fund on charges (Desktop advance_allocations), append-only.
CREATE TABLE IF NOT EXISTS finance_advance_fund_allocations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  fund_id uuid NOT NULL REFERENCES finance_advance_funds(id),
  charge_id uuid NOT NULL REFERENCES finance_charges(id),
  amount numeric(18,2) NOT NULL CHECK (amount > 0),
  allocated_by uuid REFERENCES users(id),
  allocated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_advance_fund_allocations_charge ON finance_advance_fund_allocations(school_id, charge_id);
CREATE INDEX IF NOT EXISTS idx_advance_fund_allocations_fund ON finance_advance_fund_allocations(fund_id);

-- End of a fund (Desktop status ANNULE / REMBOURSE): append-only. A cancelled decision credit is also closed here.
CREATE TABLE IF NOT EXISTS finance_advance_fund_closures (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  fund_id uuid NOT NULL UNIQUE REFERENCES finance_advance_funds(id),
  closure_type varchar(16) NOT NULL CHECK (closure_type IN ('ANNULATION','REMBOURSEMENT','DECISION_ANNULEE')),
  amount numeric(18,2) NOT NULL CHECK (amount >= 0),
  reason text NOT NULL CHECK (length(btrim(reason)) >= 3),
  business_date date NOT NULL,
  performed_by uuid NOT NULL REFERENCES users(id),
  performed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_advance_fund_closures_day ON finance_advance_fund_closures(school_id, business_date);

DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['finance_advance_funds','finance_advance_fund_allocations','finance_advance_fund_closures'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_tenant', t);
    EXECUTE format('CREATE POLICY %I ON %I USING (school_id = current_setting(''app.current_school_id'', true)::uuid) '
                   'WITH CHECK (school_id = current_setting(''app.current_school_id'', true)::uuid)', t || '_tenant', t);
  END LOOP;
END $$;
GRANT SELECT, INSERT ON finance_advance_funds, finance_advance_fund_allocations, finance_advance_fund_closures TO edusync_tenant;
REVOKE UPDATE, DELETE ON finance_advance_funds, finance_advance_fund_allocations, finance_advance_fund_closures FROM edusync_tenant;

DROP VIEW IF EXISTS finance_advance_fund_state;
ALTER TABLE finance_advance_fund_closures ALTER COLUMN closure_type TYPE varchar(16);
-- Available amount and Desktop status, derived (never stored, never edited).
CREATE OR REPLACE VIEW finance_advance_fund_state WITH (security_invoker = true) AS
SELECT f.*, COALESCE(a.allocated, 0)::numeric(18,2) AS allocated_amount,
       CASE WHEN c.id IS NOT NULL THEN 0 ELSE GREATEST(f.amount - COALESCE(a.allocated, 0), 0) END::numeric(18,2) AS available_amount,
       CASE WHEN c.closure_type = 'REMBOURSEMENT' THEN 'REMBOURSE' WHEN c.id IS NOT NULL THEN 'ANNULE'
            WHEN f.amount - COALESCE(a.allocated, 0) <= 0 THEN 'EPUISE' ELSE 'ACTIF' END AS status
  FROM finance_advance_funds f
  LEFT JOIN (SELECT fund_id, sum(amount) AS allocated FROM finance_advance_fund_allocations GROUP BY fund_id) a ON a.fund_id = f.id
  LEFT JOIN finance_advance_fund_closures c ON c.fund_id = f.id;
GRANT SELECT ON finance_advance_fund_state TO edusync_tenant;

-- Settled = valid cash payments + fund imputations (Desktop: ACTIF / EPUISE funds) + outside-cash regularizations.
CREATE OR REPLACE FUNCTION finance_assert_charge_capacity() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = public, pg_temp AS $$
DECLARE
  v_net numeric(18,2);
  v_obligation numeric(18,2);
  v_received numeric(18,2);
BEGIN
  SELECT net_amount INTO v_net FROM finance_charges WHERE id = NEW.charge_id AND school_id = NEW.school_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Obligation financière introuvable pour cette école' USING ERRCODE = 'foreign_key_violation';
  END IF;
  v_obligation := v_net - finance_charge_decision_amount(NEW.charge_id);
  v_received := COALESCE((SELECT sum(a.amount) FROM finance_payment_allocations a
      WHERE a.school_id = NEW.school_id AND a.charge_id = NEW.charge_id
        AND NOT EXISTS (SELECT 1 FROM finance_payment_reversals rv WHERE rv.payment_id = a.payment_id)), 0)
    + COALESCE((SELECT sum(fa.amount) FROM finance_advance_fund_allocations fa
      WHERE fa.school_id = NEW.school_id AND fa.charge_id = NEW.charge_id), 0)
    + COALESCE((SELECT sum(r.amount) FROM finance_charge_regularizations r
      WHERE r.school_id = NEW.school_id AND r.charge_id = NEW.charge_id), 0);
  IF v_received > GREATEST(v_obligation, 0) THEN
    RAISE EXCEPTION 'Montant reçu (%) supérieur à l''obligation (%) pour ce frais', v_received, GREATEST(v_obligation, 0)
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION finance_assert_charge_capacity() FROM PUBLIC;
DROP TRIGGER IF EXISTS trg_advance_fund_allocation_capacity ON finance_advance_fund_allocations;
CREATE TRIGGER trg_advance_fund_allocation_capacity AFTER INSERT ON finance_advance_fund_allocations
  FOR EACH ROW EXECUTE FUNCTION finance_assert_charge_capacity();
ALTER TABLE finance_advance_funds ADD COLUMN IF NOT EXISTS idempotency_key varchar(180);
CREATE UNIQUE INDEX IF NOT EXISTS uq_advance_funds_idempotency ON finance_advance_funds(school_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
