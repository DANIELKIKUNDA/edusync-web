-- N3-B — payment / cash-desk integrity, copied from the Desktop golden master (app/db/operations.py:225-598) and
-- transposed to the Web multi-cashier model (owner decision 2026-10-15, G-CAI-4: individual sessions are kept, a global
-- closure of the school's cash day is added on top of them).

-- G-REV-1 — counter-operation of a payment (Desktop reverse_payment / payment_reversals + SORTIE cash operation).
-- A payment is never updated nor deleted: the reversal is an append-only row; the payment counts as reversed when such a
-- row exists. The outflow is booked in the cash session that returns the money (the cashier's own open session), or, for
-- a superior correction (GESTIONNAIRE, no personal session), in the school's cash day of the reversal.
CREATE TABLE IF NOT EXISTS finance_payment_reversals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  payment_id uuid NOT NULL UNIQUE REFERENCES finance_payments(id),
  reversal_type varchar(14) NOT NULL CHECK (reversal_type IN ('ANNULATION','REMBOURSEMENT')),
  amount numeric(18,2) NOT NULL CHECK (amount > 0),
  currency varchar(3) NOT NULL CHECK (currency IN ('CDF','USD')),
  reason text NOT NULL CHECK (length(btrim(reason)) >= 3),
  authority varchar(10) NOT NULL CHECK (authority IN ('OWN','SUPERVISOR')),
  cash_session_id uuid REFERENCES finance_cash_sessions(id),
  business_date date NOT NULL,
  performed_by uuid NOT NULL REFERENCES users(id),
  performed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_payment_reversals_day ON finance_payment_reversals(school_id, business_date);
CREATE INDEX IF NOT EXISTS idx_payment_reversals_session ON finance_payment_reversals(cash_session_id);

-- G-CAI-1 — Desktop record_expense: category, reason (>= 3 characters), optional reference.
ALTER TABLE finance_cash_expenses ADD COLUMN IF NOT EXISTS category varchar(80);
ALTER TABLE finance_cash_expenses ADD COLUMN IF NOT EXISTS reason text;
ALTER TABLE finance_cash_expenses ADD COLUMN IF NOT EXISTS reference varchar(80);

-- G-CAI-2/3/4 — the school's cash day (Desktop cash_days + cash_closure_snapshots): one row per school and business
-- date, closed globally by the superior authority once every individual session is closed, reopened with a reason.
CREATE TABLE IF NOT EXISTS finance_cash_days (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  business_date date NOT NULL,
  status varchar(8) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','CLOSED')),
  closed_at timestamptz, closed_by uuid REFERENCES users(id),
  reopened_at timestamptz, reopened_by uuid REFERENCES users(id), reopen_reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (school_id, business_date)
);
CREATE TABLE IF NOT EXISTS finance_cash_day_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  cash_day_id uuid NOT NULL REFERENCES finance_cash_days(id),
  currency varchar(3) NOT NULL CHECK (currency IN ('CDF','USD')),
  entries numeric(18,2) NOT NULL, outflows numeric(18,2) NOT NULL, net numeric(18,2) NOT NULL,
  sessions integer NOT NULL DEFAULT 0,
  closed_by uuid NOT NULL REFERENCES users(id), closed_at timestamptz NOT NULL
);

DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['finance_payment_reversals','finance_cash_days','finance_cash_day_snapshots'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_tenant', t);
    EXECUTE format('CREATE POLICY %I ON %I USING (school_id = current_setting(''app.current_school_id'', true)::uuid) '
                   'WITH CHECK (school_id = current_setting(''app.current_school_id'', true)::uuid)', t || '_tenant', t);
  END LOOP;
END $$;
GRANT SELECT, INSERT ON finance_payment_reversals, finance_cash_day_snapshots TO edusync_tenant;   -- append-only evidence
REVOKE UPDATE, DELETE ON finance_payment_reversals, finance_cash_day_snapshots FROM edusync_tenant;
GRANT SELECT, INSERT, UPDATE ON finance_cash_days TO edusync_tenant;
REVOKE DELETE ON finance_cash_days FROM edusync_tenant;
GRANT INSERT (category, reason, reference) ON finance_cash_expenses TO edusync_tenant;
ALTER TABLE finance_cash_events DROP CONSTRAINT IF EXISTS finance_cash_events_event_type_check;
ALTER TABLE finance_cash_events ADD CONSTRAINT finance_cash_events_event_type_check
  CHECK (event_type IN ('OPEN','CLOSE','REOPEN','EXPENSE','REVERSAL'));

-- The capacity guard (0043) must count only the payments that still count (Desktop: balances use status='VALIDE'):
-- an allocation of a reversed payment no longer settles the charge, so the charge can be collected again.
CREATE OR REPLACE FUNCTION finance_assert_charge_capacity() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = public, pg_temp AS $$
DECLARE
  v_net numeric(18,2);
  v_currency varchar(3);
  v_obligation numeric(18,2);
  v_received numeric(18,2);
BEGIN
  SELECT net_amount, currency INTO v_net, v_currency
    FROM finance_charges WHERE id = NEW.charge_id AND school_id = NEW.school_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Obligation financière introuvable pour cette école' USING ERRCODE = 'foreign_key_violation';
  END IF;
  v_obligation := v_net - COALESCE((SELECT sum(d.amount) FROM finance_decisions d
      WHERE d.school_id = NEW.school_id AND d.charge_id = NEW.charge_id AND d.status = 'ACTIVE' AND d.currency = v_currency), 0);
  v_received := COALESCE((SELECT sum(a.amount) FROM finance_payment_allocations a
      WHERE a.school_id = NEW.school_id AND a.charge_id = NEW.charge_id
        AND NOT EXISTS (SELECT 1 FROM finance_payment_reversals rv WHERE rv.payment_id = a.payment_id)), 0)
    + COALESCE((SELECT sum(r.amount) FROM finance_charge_regularizations r
      WHERE r.school_id = NEW.school_id AND r.charge_id = NEW.charge_id), 0);
  IF v_received > GREATEST(v_obligation, 0) THEN
    RAISE EXCEPTION 'Montant reçu (%) supérieur à l''obligation (%) pour ce frais', v_received, GREATEST(v_obligation, 0)
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION finance_assert_charge_capacity() FROM PUBLIC;
