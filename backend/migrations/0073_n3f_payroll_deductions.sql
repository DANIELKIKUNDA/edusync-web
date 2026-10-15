-- N3-F — staff children finance copied from the Desktop golden master (app/db/staff_finance.py: staff_noncash_settlements).
-- A confirmed payroll deduction settles a pupil's charge for debt / status purposes, but it never creates a payment, a
-- receipt or a cash operation: cash reports stay truthful. Cancellation needs a reason and is traced (append-only here).
CREATE TABLE IF NOT EXISTS finance_noncash_settlements (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  staff_id uuid NOT NULL REFERENCES staff_members(id),
  student_id uuid NOT NULL REFERENCES students(id),
  enrollment_id uuid NOT NULL REFERENCES enrollments(id),
  charge_id uuid NOT NULL REFERENCES finance_charges(id),
  amount numeric(18,2) NOT NULL CHECK (amount > 0),
  currency varchar(3) NOT NULL CHECK (currency IN ('CDF','USD')),
  settlement_type varchar(18) NOT NULL DEFAULT 'PAYROLL_DEDUCTION' CHECK (settlement_type IN ('PAYROLL_DEDUCTION')),
  period_label varchar(80),
  reference varchar(120),
  confirmed_by uuid NOT NULL REFERENCES users(id),
  confirmed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_noncash_settlements_charge ON finance_noncash_settlements(school_id, charge_id);
CREATE INDEX IF NOT EXISTS idx_noncash_settlements_staff ON finance_noncash_settlements(school_id, staff_id, student_id);
CREATE TABLE IF NOT EXISTS finance_noncash_cancellations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  settlement_id uuid NOT NULL UNIQUE REFERENCES finance_noncash_settlements(id),
  reason text NOT NULL CHECK (length(btrim(reason)) >= 3),
  cancelled_by uuid NOT NULL REFERENCES users(id),
  cancelled_at timestamptz NOT NULL DEFAULT now()
);
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['finance_noncash_settlements','finance_noncash_cancellations'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_tenant', t);
    EXECUTE format('CREATE POLICY %I ON %I USING (school_id = current_setting(''app.current_school_id'', true)::uuid) '
                   'WITH CHECK (school_id = current_setting(''app.current_school_id'', true)::uuid)', t || '_tenant', t);
  END LOOP;
END $$;
GRANT SELECT, INSERT ON finance_noncash_settlements, finance_noncash_cancellations TO edusync_tenant;
REVOKE UPDATE, DELETE ON finance_noncash_settlements, finance_noncash_cancellations FROM edusync_tenant;

-- Settled = valid cash payments + fund imputations + confirmed non-cash settlements + outside-cash regularizations.
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
    + COALESCE((SELECT sum(ns.amount) FROM finance_noncash_settlements ns
      WHERE ns.school_id = NEW.school_id AND ns.charge_id = NEW.charge_id
        AND NOT EXISTS (SELECT 1 FROM finance_noncash_cancellations nc WHERE nc.settlement_id = ns.id)), 0)
    + COALESCE((SELECT sum(r.amount) FROM finance_charge_regularizations r
      WHERE r.school_id = NEW.school_id AND r.charge_id = NEW.charge_id), 0);
  IF v_received > GREATEST(v_obligation, 0) THEN
    RAISE EXCEPTION 'Montant reçu (%) supérieur à l''obligation (%) pour ce frais', v_received, GREATEST(v_obligation, 0)
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION finance_assert_charge_capacity() FROM PUBLIC;
DROP TRIGGER IF EXISTS trg_noncash_settlement_capacity ON finance_noncash_settlements;
CREATE TRIGGER trg_noncash_settlement_capacity AFTER INSERT ON finance_noncash_settlements
  FOR EACH ROW EXECUTE FUNCTION finance_assert_charge_capacity();
