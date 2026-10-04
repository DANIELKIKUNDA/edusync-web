-- Certification 2026-10-01 — database invariant: money received for a charge never exceeds its obligation.
-- Defects reproduced live: the cash desk collected a charge already settled outside cash (60 000 received
-- for 30 000 owed), and two stale finance-history batches regularized 100 000 on a 50 000 charge.
-- Application code now re-validates under lock; this trigger is the last line of defence for any writer.
-- Obligation = net - ACTIVE charge decisions (same definition as finance_charge_effective).
-- Received  = cash allocations + outside-cash regularizations.
-- Decisions themselves are not blocked: an exemption granted after payment legitimately creates a credit.
CREATE OR REPLACE FUNCTION finance_assert_charge_capacity() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = public, pg_temp AS $$
DECLARE
  v_net numeric(18,2);
  v_currency varchar(3);
  v_obligation numeric(18,2);
  v_received numeric(18,2);
BEGIN
  -- Serialise every writer of this charge (cash desk, history import, future modules).
  SELECT net_amount, currency INTO v_net, v_currency
    FROM finance_charges WHERE id = NEW.charge_id AND school_id = NEW.school_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Obligation financière introuvable pour cette école' USING ERRCODE = 'foreign_key_violation';
  END IF;
  v_obligation := v_net - COALESCE((SELECT sum(d.amount) FROM finance_decisions d
      WHERE d.school_id = NEW.school_id AND d.charge_id = NEW.charge_id AND d.status = 'ACTIVE' AND d.currency = v_currency), 0);
  v_received := COALESCE((SELECT sum(a.amount) FROM finance_payment_allocations a
      WHERE a.school_id = NEW.school_id AND a.charge_id = NEW.charge_id), 0)
    + COALESCE((SELECT sum(r.amount) FROM finance_charge_regularizations r
      WHERE r.school_id = NEW.school_id AND r.charge_id = NEW.charge_id), 0);
  IF v_received > GREATEST(v_obligation, 0) THEN
    RAISE EXCEPTION 'Montant reçu (%) supérieur à l''obligation (%) pour ce frais', v_received, GREATEST(v_obligation, 0)
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION finance_assert_charge_capacity() FROM PUBLIC;

DROP TRIGGER IF EXISTS trg_payment_allocation_capacity ON finance_payment_allocations;
CREATE TRIGGER trg_payment_allocation_capacity AFTER INSERT ON finance_payment_allocations
  FOR EACH ROW EXECUTE FUNCTION finance_assert_charge_capacity();
DROP TRIGGER IF EXISTS trg_charge_regularization_capacity ON finance_charge_regularizations;
CREATE TRIGGER trg_charge_regularization_capacity AFTER INSERT ON finance_charge_regularizations
  FOR EACH ROW EXECUTE FUNCTION finance_assert_charge_capacity();
