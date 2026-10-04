-- Point 6F — Caisse industrielle multi-caissier.
-- Une caisse est une session personnelle explicite. Jamais d'ouverture silencieuse par un paiement.
ALTER TABLE finance_cash_sessions DROP CONSTRAINT IF EXISTS finance_cash_sessions_school_id_membership_id_status_key;
ALTER TABLE finance_cash_sessions ADD COLUMN IF NOT EXISTS business_date date;
ALTER TABLE finance_cash_sessions ADD COLUMN IF NOT EXISTS opening_cdf numeric(18,2) NOT NULL DEFAULT 0 CHECK(opening_cdf>=0);
ALTER TABLE finance_cash_sessions ADD COLUMN IF NOT EXISTS opening_usd numeric(18,2) NOT NULL DEFAULT 0 CHECK(opening_usd>=0);
ALTER TABLE finance_cash_sessions ADD COLUMN IF NOT EXISTS counted_cdf numeric(18,2);
ALTER TABLE finance_cash_sessions ADD COLUMN IF NOT EXISTS counted_usd numeric(18,2);
ALTER TABLE finance_cash_sessions ADD COLUMN IF NOT EXISTS close_note text;
UPDATE finance_cash_sessions SET business_date=(opened_at AT TIME ZONE 'Africa/Lubumbashi')::date WHERE business_date IS NULL;
ALTER TABLE finance_cash_sessions ALTER COLUMN business_date SET DEFAULT CURRENT_DATE;
ALTER TABLE finance_cash_sessions ALTER COLUMN business_date SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_cash_one_open_per_cashier ON finance_cash_sessions(school_id,membership_id) WHERE status='OPEN';
CREATE INDEX IF NOT EXISTS idx_cash_sessions_history ON finance_cash_sessions(school_id,business_date DESC,opened_at DESC);

CREATE TABLE IF NOT EXISTS finance_cash_expenses(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 cash_session_id uuid NOT NULL REFERENCES finance_cash_sessions(id) ON DELETE RESTRICT,
 actor_user_id uuid NOT NULL REFERENCES users(id), label varchar(180) NOT NULL,
 amount numeric(18,2) NOT NULL CHECK(amount>0), currency varchar(3) NOT NULL CHECK(currency IN('CDF','USD')),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS finance_cash_events(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 cash_session_id uuid NOT NULL REFERENCES finance_cash_sessions(id) ON DELETE RESTRICT,
 actor_user_id uuid NOT NULL REFERENCES users(id), event_type varchar(24) NOT NULL CHECK(event_type IN('OPEN','CLOSE','REOPEN','EXPENSE')),
 payload jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE finance_cash_expenses ENABLE ROW LEVEL SECURITY; ALTER TABLE finance_cash_expenses FORCE ROW LEVEL SECURITY;
ALTER TABLE finance_cash_events ENABLE ROW LEVEL SECURITY; ALTER TABLE finance_cash_events FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
 CREATE POLICY finance_cash_expenses_tenant ON finance_cash_expenses USING (school_id=current_setting('app.school_id',true)::uuid) WITH CHECK(school_id=current_setting('app.school_id',true)::uuid);
 CREATE POLICY finance_cash_events_tenant ON finance_cash_events USING (school_id=current_setting('app.school_id',true)::uuid) WITH CHECK(school_id=current_setting('app.school_id',true)::uuid);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
