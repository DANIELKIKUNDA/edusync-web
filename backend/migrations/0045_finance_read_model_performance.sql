-- Certification 2026-10 — finance read models at school scale (measured, not guessed).
-- Volume test: 12 000 pupils / 132 000 charges in one school (+ 660 000 charges in another school).
-- EXPLAIN ANALYZE showed every recovery / fee-tracking screen running correlated sub-queries once per
-- charge (120 004 loops each): the decisions sum twice inside finance_charge_effective and the
-- outside-cash regularization sum in each read model -> 10 s to 28 s per screen.
-- Fix: aggregate decisions and regularizations ONCE (grouped LEFT JOIN) and expose the outside-cash
-- amount on the canonical view. Column names, order and semantics are unchanged; one column is appended.
-- The view keeps security_invoker so tenant RLS still applies to every underlying table.
CREATE OR REPLACE VIEW finance_charge_effective WITH (security_invoker = true) AS
SELECT fc.id, fc.school_id, fc.enrollment_id, fc.label, fc.currency, fc.net_amount, fc.paid_amount,
       fc.periodicity, fc.period_label, fc.period_order, fc.due_date, fc.status, fc.created_at, fc.updated_at,
       fc.sequence_group, fc.sequence_order, fc.fee_type_id, fc.tariff_id,
       GREATEST(fc.net_amount - COALESCE(d.amount, 0), 0)::numeric(18,2) AS effective_net_amount,
       COALESCE(d.amount, 0)::numeric(18,2) AS decision_amount,
       COALESCE(r.amount, 0)::numeric(18,2) AS outside_cash_amount
  FROM finance_charges fc
  LEFT JOIN (SELECT school_id, charge_id, currency, sum(amount) AS amount
               FROM finance_decisions
              WHERE status = 'ACTIVE' AND charge_id IS NOT NULL
              GROUP BY school_id, charge_id, currency) d
         ON d.school_id = fc.school_id AND d.charge_id = fc.id AND d.currency = fc.currency
  LEFT JOIN (SELECT school_id, charge_id, sum(amount) AS amount
               FROM finance_charge_regularizations
              GROUP BY school_id, charge_id) r
         ON r.school_id = fc.school_id AND r.charge_id = fc.id;
ALTER VIEW finance_charge_effective SET (security_invoker = true);

-- Lookups by charge (cash desk payable, capacity trigger, class register) and by cash session.
CREATE INDEX IF NOT EXISTS idx_finance_decisions_active_charge
  ON finance_decisions(school_id, charge_id) WHERE status = 'ACTIVE' AND charge_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_finance_advance_targets_charge ON finance_advance_targets(school_id, charge_id);
CREATE INDEX IF NOT EXISTS idx_finance_payments_cash_session ON finance_payments(cash_session_id);
CREATE INDEX IF NOT EXISTS idx_finance_allocations_charge ON finance_payment_allocations(school_id, charge_id);
