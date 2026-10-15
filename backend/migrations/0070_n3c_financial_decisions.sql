-- N3-C — financial decisions copied from the Desktop golden master (app/db/financial_decisions.py, schema.sql v8:
-- financial_decisions, financial_decision_applications, charge_responsibilities).
--  * a decision is an audited rule on one enrollment: scope (all fees, a fee code, a fee category, one charge), optional
--    period, nature (DISCOUNT, EXEMPTION, INDIVIDUAL_FREE, COLLECTIVE_EXEMPTION, DIRECTION_EXCEPTION, THIRD_PARTY_COVERAGE),
--    value (PERCENT or FIXED; exemptions are always 100 %), priority, cumulative flag, effective dates, reason, reference;
--  * recalculation (Desktop recalculate_enrollment_financial_decisions) materialises, per charge, the reduction applied
--    by each decision in priority order (financial_decision_applications); what the cash desk may collect is the charge
--    net minus these applications;
--  * the former Web decisions (charge + fixed amount, types REDUCTION / SPONSORSHIP / OTHER) are kept as they are, never
--    transformed: they are read as charge-scoped FIXED decisions, which is exactly what they already meant.
ALTER TABLE finance_decisions DROP CONSTRAINT IF EXISTS finance_decisions_decision_type_check;
ALTER TABLE finance_decisions ADD CONSTRAINT finance_decisions_decision_type_check CHECK (decision_type IN
  ('DISCOUNT','EXEMPTION','INDIVIDUAL_FREE','COLLECTIVE_EXEMPTION','DIRECTION_EXCEPTION','THIRD_PARTY_COVERAGE',
   'REDUCTION','SPONSORSHIP','OTHER'));   -- the last three: former Web rows only (no new creation)
ALTER TABLE finance_decisions ADD COLUMN IF NOT EXISTS scope_type varchar(14) NOT NULL DEFAULT 'CHARGE'
  CHECK (scope_type IN ('ALL_FEES','FEE_CODE','FEE_CATEGORY','CHARGE'));
ALTER TABLE finance_decisions ADD COLUMN IF NOT EXISTS scope_ref varchar(80);
ALTER TABLE finance_decisions ADD COLUMN IF NOT EXISTS period_start date;
ALTER TABLE finance_decisions ADD COLUMN IF NOT EXISTS period_end date;
ALTER TABLE finance_decisions ADD COLUMN IF NOT EXISTS value_type varchar(8) NOT NULL DEFAULT 'FIXED' CHECK (value_type IN ('PERCENT','FIXED'));
ALTER TABLE finance_decisions ADD COLUMN IF NOT EXISTS value_amount numeric(18,2);
ALTER TABLE finance_decisions ADD COLUMN IF NOT EXISTS priority integer NOT NULL DEFAULT 100;
ALTER TABLE finance_decisions ADD COLUMN IF NOT EXISTS cumulative boolean NOT NULL DEFAULT true;
ALTER TABLE finance_decisions ADD COLUMN IF NOT EXISTS effective_to date;
ALTER TABLE finance_decisions ADD COLUMN IF NOT EXISTS reference varchar(120);
ALTER TABLE finance_decisions ADD COLUMN IF NOT EXISTS model varchar(8) NOT NULL DEFAULT 'WEB_V1' CHECK (model IN ('WEB_V1','DESKTOP'));
UPDATE finance_decisions SET value_amount = amount WHERE value_amount IS NULL;   -- same value, read as FIXED on its charge
ALTER TABLE finance_decisions ALTER COLUMN charge_id DROP NOT NULL;
GRANT INSERT (scope_type, scope_ref, period_start, period_end, value_type, value_amount, priority, cumulative, effective_to, reference, model)
  ON finance_decisions TO edusync_tenant;

CREATE TABLE IF NOT EXISTS finance_decision_applications (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  decision_id uuid NOT NULL REFERENCES finance_decisions(id),
  charge_id uuid NOT NULL REFERENCES finance_charges(id),
  base_amount numeric(18,2) NOT NULL,
  applied_amount numeric(18,2) NOT NULL CHECK (applied_amount > 0),
  net_after numeric(18,2) NOT NULL CHECK (net_after >= 0),
  applied_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (decision_id, charge_id)
);
CREATE INDEX IF NOT EXISTS idx_decision_applications_charge ON finance_decision_applications(school_id, charge_id);

-- Desktop set_charge_responsibility: planned settlement of one charge (family cash, payroll deduction, third party);
-- planned amount <= real remaining; a new one replaces the PLANNED one (cancelled, never deleted).
CREATE TABLE IF NOT EXISTS finance_charge_responsibilities (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  charge_id uuid NOT NULL REFERENCES finance_charges(id),
  responsibility_type varchar(18) NOT NULL CHECK (responsibility_type IN ('FAMILY_CASH','PAYROLL_DEDUCTION','THIRD_PARTY')),
  responsible_name varchar(160),
  planned_amount numeric(18,2) NOT NULL CHECK (planned_amount > 0),
  currency varchar(3) NOT NULL CHECK (currency IN ('CDF','USD')),
  status varchar(10) NOT NULL DEFAULT 'PLANNED' CHECK (status IN ('PLANNED','CANCELLED')),
  reference varchar(120), reason text NOT NULL,
  created_by uuid NOT NULL REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT now(),
  cancelled_by uuid REFERENCES users(id), cancelled_at timestamptz, cancellation_reason text
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_charge_responsibility_planned ON finance_charge_responsibilities(charge_id) WHERE status='PLANNED';

DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['finance_decision_applications','finance_charge_responsibilities'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_tenant', t);
    EXECUTE format('CREATE POLICY %I ON %I USING (school_id = current_setting(''app.current_school_id'', true)::uuid) '
                   'WITH CHECK (school_id = current_setting(''app.current_school_id'', true)::uuid)', t || '_tenant', t);
  END LOOP;
END $$;
GRANT SELECT, INSERT, DELETE ON finance_decision_applications TO edusync_tenant;   -- rebuilt at each recalculation (Desktop)
GRANT SELECT, INSERT ON finance_charge_responsibilities TO edusync_tenant;
GRANT UPDATE (status, cancelled_by, cancelled_at, cancellation_reason) ON finance_charge_responsibilities TO edusync_tenant;

-- Existing Web decisions get their application now (charge-scoped FIXED, capped by the charge net, priority order).
INSERT INTO finance_decision_applications(school_id, decision_id, charge_id, base_amount, applied_amount, net_after)
SELECT d.school_id, d.id, d.charge_id, fc.net_amount, LEAST(d.amount, fc.net_amount), GREATEST(fc.net_amount - d.amount, 0)
  FROM finance_decisions d JOIN finance_charges fc ON fc.id = d.charge_id
 WHERE d.status = 'ACTIVE' AND d.charge_id IS NOT NULL AND d.amount > 0 AND d.currency = fc.currency AND fc.net_amount > 0
ON CONFLICT (decision_id, charge_id) DO NOTHING;

-- One definition of "reduced by decisions" for every reader (cash desk, fee tracking, capacity guard, imports).
CREATE OR REPLACE FUNCTION finance_charge_decision_amount(p_charge uuid) RETURNS numeric
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = public, pg_temp AS $$
  SELECT COALESCE(sum(a.applied_amount), 0)::numeric(18,2) FROM finance_decision_applications a
    JOIN finance_decisions d ON d.id = a.decision_id AND d.status = 'ACTIVE' WHERE a.charge_id = p_charge
$$;
GRANT EXECUTE ON FUNCTION finance_charge_decision_amount(uuid) TO edusync_tenant;

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
    + COALESCE((SELECT sum(r.amount) FROM finance_charge_regularizations r
      WHERE r.school_id = NEW.school_id AND r.charge_id = NEW.charge_id), 0);
  IF v_received > GREATEST(v_obligation, 0) THEN
    RAISE EXCEPTION 'Montant reçu (%) supérieur à l''obligation (%) pour ce frais', v_received, GREATEST(v_obligation, 0)
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION finance_assert_charge_capacity() FROM PUBLIC;

-- Canonical read view: same columns and order (0045), decisions now read from their applications (aggregated once).
CREATE OR REPLACE VIEW finance_charge_effective WITH (security_invoker = true) AS
SELECT fc.id, fc.school_id, fc.enrollment_id, fc.label, fc.currency, fc.net_amount, fc.paid_amount,
       fc.periodicity, fc.period_label, fc.period_order, fc.due_date, fc.status, fc.created_at, fc.updated_at,
       fc.sequence_group, fc.sequence_order, fc.fee_type_id, fc.tariff_id,
       GREATEST(fc.net_amount - COALESCE(d.amount, 0), 0)::numeric(18,2) AS effective_net_amount,
       COALESCE(d.amount, 0)::numeric(18,2) AS decision_amount,
       COALESCE(r.amount, 0)::numeric(18,2) AS outside_cash_amount
  FROM finance_charges fc
  LEFT JOIN (SELECT a.school_id, a.charge_id, sum(a.applied_amount) AS amount
               FROM finance_decision_applications a JOIN finance_decisions dd ON dd.id = a.decision_id AND dd.status = 'ACTIVE'
              GROUP BY a.school_id, a.charge_id) d
         ON d.school_id = fc.school_id AND d.charge_id = fc.id
  LEFT JOIN (SELECT school_id, charge_id, sum(amount) AS amount
               FROM finance_charge_regularizations
              GROUP BY school_id, charge_id) r
         ON r.school_id = fc.school_id AND r.charge_id = fc.id;
ALTER VIEW finance_charge_effective SET (security_invoker = true);
