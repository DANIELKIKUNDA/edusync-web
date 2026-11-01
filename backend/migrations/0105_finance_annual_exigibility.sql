-- MEF: annual, school-scoped financial exigibility policies.
-- Additive migration only: existing schedules, charges and settlements are unchanged.
CREATE TABLE IF NOT EXISTS finance_exigibility_policies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id),
  academic_year_id uuid NOT NULL REFERENCES academic_years(id),
  version integer NOT NULL CHECK (version > 0),
  status varchar(12) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','ACTIVE','SUPERSEDED')),
  effective_from date NOT NULL,
  created_by uuid,
  approved_by uuid,
  approved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(school_id, academic_year_id, version),
  UNIQUE(id, school_id),
  CHECK (status <> 'ACTIVE' OR approved_at IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_mef_active_policy
  ON finance_exigibility_policies(school_id, academic_year_id) WHERE status='ACTIVE';

CREATE TABLE IF NOT EXISTS finance_exigibility_rules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL,
  policy_id uuid NOT NULL,
  fee_type_id uuid NOT NULL REFERENCES fee_types(id),
  prior_mode varchar(20) NOT NULL CHECK (prior_mode IN ('NOT_APPLICABLE','FULL','CUSTOM')),
  prior_percent numeric(5,2),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(policy_id, fee_type_id),
  UNIQUE(id, school_id),
  FOREIGN KEY(policy_id, school_id) REFERENCES finance_exigibility_policies(id, school_id),
  CHECK ((prior_mode='CUSTOM' AND prior_percent BETWEEN 0 AND 100)
      OR (prior_mode<>'CUSTOM' AND prior_percent IS NULL))
);

CREATE TABLE IF NOT EXISTS finance_exigibility_day_bands (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL,
  rule_id uuid NOT NULL,
  first_day smallint NOT NULL CHECK (first_day BETWEEN 1 AND 31),
  last_day smallint CHECK (last_day BETWEEN 1 AND 31),
  percent numeric(5,2) NOT NULL CHECK (percent BETWEEN 0 AND 100),
  FOREIGN KEY(rule_id, school_id) REFERENCES finance_exigibility_rules(id, school_id),
  CHECK (last_day IS NULL OR last_day >= first_day),
  UNIQUE(rule_id, first_day)
);
-- The domain service validates complete coverage and overlapping bands before activation.

CREATE TABLE IF NOT EXISTS finance_enrollment_entry_dates (
  enrollment_id uuid PRIMARY KEY REFERENCES enrollments(id),
  school_id uuid NOT NULL REFERENCES schools(id),
  financial_entry_date date NOT NULL,
  reason text NOT NULL,
  set_by uuid,
  set_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS finance_exigibility_assessments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id),
  enrollment_id uuid NOT NULL REFERENCES enrollments(id),
  schedule_id uuid NOT NULL REFERENCES fee_schedules(id),
  policy_id uuid NOT NULL,
  status varchar(20) NOT NULL CHECK (status IN ('DUE','NOT_APPLICABLE','NOT_EXIGIBLE')),
  tariff_amount numeric(18,2) NOT NULL CHECK (tariff_amount >= 0),
  exigible_amount numeric(18,2) NOT NULL CHECK (exigible_amount >= 0),
  assessed_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(policy_id, school_id) REFERENCES finance_exigibility_policies(id, school_id),
  UNIQUE(school_id, enrollment_id, schedule_id, policy_id),
  CHECK (status='DUE' OR exigible_amount=0)
);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'finance_exigibility_policies','finance_exigibility_rules',
    'finance_exigibility_day_bands','finance_enrollment_entry_dates',
    'finance_exigibility_assessments'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I',t||'_tenant',t);
    EXECUTE format('CREATE POLICY %I ON %I USING (school_id = current_setting(''app.school_id'', true)::uuid) WITH CHECK (school_id = current_setting(''app.school_id'', true)::uuid)',t||'_tenant',t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON %I TO edusync_tenant',t);
  END LOOP;
END $$;
