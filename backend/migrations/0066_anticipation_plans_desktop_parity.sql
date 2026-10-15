-- Parity lot L6 (owner decision 2026-10-14) — payment plans copied from the Desktop golden master
-- (app/db/anticipation.py, app/db/schema.sql v8: anticipation_plans, anticipation_memberships, anticipation_installments,
--  anticipation_payment_links). Doctrine: Plan anticipé ≠ Fonds anticipé.
--  * a plan routes part of a current monthly payment to NAMED future months of one monthly fee: it never creates money,
--    never holds a provision, and never allocates to a month the plan does not name;
--  * participation is optional per enrollment or mandatory (automatic membership at the first plan payment);
--  * a membership freezes the remaining target amount and splits it equally (to the cent) over the contribution months.
-- The former Web mechanism (finance_anticipation_plans / finance_advance_allocations, a simplified plan stored as a
-- provision, see L6_ANTICIPATION_ANALYSIS.md) is kept untouched (no row exists) and is no longer used by the cash desk.

CREATE TABLE IF NOT EXISTS anticipation_plans (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  academic_year_id uuid NOT NULL REFERENCES academic_years(id),
  name varchar(160) NOT NULL,
  scope_type varchar(16) NOT NULL DEFAULT 'SCHOOL' CHECK (scope_type IN ('SCHOOL','SECTION','OPTION_GROUP','ACADEMIC_CLASS','CLASS')),
  scope_ref varchar(64) NOT NULL DEFAULT '*',
  fee_type_id uuid NOT NULL REFERENCES fee_types(id),
  target_months jsonb NOT NULL,
  contribution_months jsonb NOT NULL,
  participation_mode varchar(10) NOT NULL DEFAULT 'OPTIONAL' CHECK (participation_mode IN ('OPTIONAL','MANDATORY')),
  allocation_strategy varchar(8) NOT NULL DEFAULT 'EQUAL' CHECK (allocation_strategy IN ('EQUAL')),
  effective_from date NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  CHECK (jsonb_typeof(target_months) = 'array' AND jsonb_array_length(target_months) >= 1),
  CHECK (jsonb_typeof(contribution_months) = 'array' AND jsonb_array_length(contribution_months) >= 1)
);
CREATE INDEX IF NOT EXISTS idx_anticipation_plans_year ON anticipation_plans(school_id, academic_year_id, active, scope_type, scope_ref, effective_from);

CREATE TABLE IF NOT EXISTS anticipation_memberships (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  plan_id uuid NOT NULL REFERENCES anticipation_plans(id),
  enrollment_id uuid NOT NULL REFERENCES enrollments(id),
  status varchar(10) NOT NULL DEFAULT 'ENROLLED' CHECK (status IN ('ENROLLED','DECLINED','PAUSED','COMPLETED')),
  snapshot_target_amount numeric(18,2) NOT NULL DEFAULT 0 CHECK (snapshot_target_amount >= 0),
  currency varchar(3) NOT NULL CHECK (currency IN ('CDF','USD')),
  decided_at timestamptz NOT NULL DEFAULT now(),
  decided_by uuid REFERENCES users(id),
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version bigint NOT NULL DEFAULT 1,
  UNIQUE (school_id, plan_id, enrollment_id)
);
CREATE INDEX IF NOT EXISTS idx_anticipation_memberships_enrollment ON anticipation_memberships(school_id, enrollment_id, status);

CREATE TABLE IF NOT EXISTS anticipation_installments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  membership_id uuid NOT NULL REFERENCES anticipation_memberships(id),
  contribution_month varchar(2) NOT NULL,
  planned_amount numeric(18,2) NOT NULL CHECK (planned_amount >= 0),
  sort_order integer NOT NULL DEFAULT 100,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (membership_id, contribution_month)
);

CREATE TABLE IF NOT EXISTS anticipation_payment_links (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  membership_id uuid NOT NULL REFERENCES anticipation_memberships(id),
  payment_id uuid NOT NULL REFERENCES finance_payments(id),
  payment_allocation_id uuid NOT NULL UNIQUE REFERENCES finance_payment_allocations(id),
  contribution_month varchar(2) NOT NULL,
  target_charge_id uuid NOT NULL REFERENCES finance_charges(id),
  target_month varchar(2) NOT NULL,
  amount numeric(18,2) NOT NULL CHECK (amount > 0),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_anticipation_links_membership ON anticipation_payment_links(school_id, membership_id, contribution_month);

DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['anticipation_plans','anticipation_memberships','anticipation_installments','anticipation_payment_links'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_tenant', t);
    EXECUTE format('CREATE POLICY %I ON %I USING (school_id = current_setting(''app.current_school_id'', true)::uuid) '
                   'WITH CHECK (school_id = current_setting(''app.current_school_id'', true)::uuid)', t || '_tenant', t);
  END LOOP;
END $$;
GRANT SELECT, INSERT, UPDATE ON anticipation_plans, anticipation_memberships TO edusync_tenant;
GRANT SELECT, INSERT, DELETE ON anticipation_installments TO edusync_tenant;   -- Desktop rebuilds the schedule at each decision
GRANT SELECT, INSERT ON anticipation_payment_links TO edusync_tenant;          -- allocation links are append-only
DROP TRIGGER IF EXISTS trg_touch_anticipation_plans ON anticipation_plans;
CREATE TRIGGER trg_touch_anticipation_plans BEFORE UPDATE ON anticipation_plans FOR EACH ROW EXECUTE FUNCTION touch_settings_row();
DROP TRIGGER IF EXISTS trg_touch_anticipation_memberships ON anticipation_memberships;
CREATE TRIGGER trg_touch_anticipation_memberships BEFORE UPDATE ON anticipation_memberships FOR EACH ROW EXECUTE FUNCTION touch_settings_row();

-- Desktop financial_decisions.py::apply_lifecycle_to_future_charges (needed by plans: no allocation to a neutralized
-- month): ABANDON / TRANSFER / SUSPEND neutralize only the UNPAID future charges (due on or after the event date);
-- REINTEGRATE restores them. The neutralization is traced (event, date, reason) and reversible; nothing is deleted.
CREATE TABLE IF NOT EXISTS finance_charge_lifecycle_states (
  charge_id uuid PRIMARY KEY REFERENCES finance_charges(id),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  event_id uuid NOT NULL REFERENCES student_status_events(id),
  state varchar(12) NOT NULL DEFAULT 'NEUTRALIZED' CHECK (state = 'NEUTRALIZED'),
  effective_on date NOT NULL,
  reason text,
  created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE finance_charge_lifecycle_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance_charge_lifecycle_states FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS finance_charge_lifecycle_states_tenant ON finance_charge_lifecycle_states;
CREATE POLICY finance_charge_lifecycle_states_tenant ON finance_charge_lifecycle_states
  USING (school_id = current_setting('app.current_school_id', true)::uuid)
  WITH CHECK (school_id = current_setting('app.current_school_id', true)::uuid);
GRANT SELECT, INSERT, UPDATE, DELETE ON finance_charge_lifecycle_states TO edusync_tenant;
GRANT UPDATE (status) ON finance_charges TO edusync_tenant;
