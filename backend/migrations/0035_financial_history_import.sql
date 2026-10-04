-- Point 12C — reprise historique financière. Une reprise n'est jamais un nouvel encaissement de caisse.
CREATE TABLE IF NOT EXISTS financial_history_import_batches(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 filename varchar(240) NOT NULL, source_format varchar(12) NOT NULL CHECK(source_format IN('XLSX','CSV')),
 status varchar(20) NOT NULL DEFAULT 'ANALYZED' CHECK(status IN('ANALYZED','READY','EXECUTED','CANCELLED')),
 total_rows int NOT NULL DEFAULT 0, valid_rows int NOT NULL DEFAULT 0, warning_rows int NOT NULL DEFAULT 0, error_rows int NOT NULL DEFAULT 0,
 created_by uuid REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT now(), executed_at timestamptz, version bigint NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS financial_history_import_rows(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 batch_id uuid NOT NULL REFERENCES financial_history_import_batches(id) ON DELETE CASCADE, row_number int NOT NULL,
 payload jsonb NOT NULL, normalized_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
 status varchar(16) NOT NULL CHECK(status IN('VALID','WARNING','ERROR','IMPORTED')), issues jsonb NOT NULL DEFAULT '[]'::jsonb,
 imported_regularization_id uuid REFERENCES finance_charge_regularizations(id), created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(batch_id,row_number));
CREATE TABLE IF NOT EXISTS financial_history_import_ledger(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 batch_id uuid NOT NULL REFERENCES financial_history_import_batches(id), row_id uuid NOT NULL REFERENCES financial_history_import_rows(id),
 charge_id uuid NOT NULL REFERENCES finance_charges(id), regularization_id uuid NOT NULL REFERENCES finance_charge_regularizations(id),
 historical_paid_on date NOT NULL, historical_reference varchar(120), amount numeric(18,2) NOT NULL CHECK(amount>0), currency varchar(3) NOT NULL CHECK(currency IN('CDF','USD')),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(school_id,batch_id,row_id));
CREATE INDEX IF NOT EXISTS idx_fin_hist_batches_school_created ON financial_history_import_batches(school_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fin_hist_rows_batch_status ON financial_history_import_rows(school_id,batch_id,status,row_number);
ALTER TABLE financial_history_import_batches ENABLE ROW LEVEL SECURITY; ALTER TABLE financial_history_import_batches FORCE ROW LEVEL SECURITY;
ALTER TABLE financial_history_import_rows ENABLE ROW LEVEL SECURITY; ALTER TABLE financial_history_import_rows FORCE ROW LEVEL SECURITY;
ALTER TABLE financial_history_import_ledger ENABLE ROW LEVEL SECURITY; ALTER TABLE financial_history_import_ledger FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS fin_hist_batches_tenant ON financial_history_import_batches; CREATE POLICY fin_hist_batches_tenant ON financial_history_import_batches USING(school_id=nullif(current_setting('app.current_school_id', true), '')::uuid) WITH CHECK(school_id=nullif(current_setting('app.current_school_id', true), '')::uuid);
DROP POLICY IF EXISTS fin_hist_rows_tenant ON financial_history_import_rows; CREATE POLICY fin_hist_rows_tenant ON financial_history_import_rows USING(school_id=nullif(current_setting('app.current_school_id', true), '')::uuid) WITH CHECK(school_id=nullif(current_setting('app.current_school_id', true), '')::uuid);
DROP POLICY IF EXISTS fin_hist_ledger_tenant ON financial_history_import_ledger; CREATE POLICY fin_hist_ledger_tenant ON financial_history_import_ledger USING(school_id=nullif(current_setting('app.current_school_id', true), '')::uuid) WITH CHECK(school_id=nullif(current_setting('app.current_school_id', true), '')::uuid);
INSERT INTO capability_catalog(code,domain_name,group_name,label,action_code,risk,offline_policy,audit_required,scope_types,source_status,registry_version) VALUES
 ('migration.finance_history.analyze','Migration & import','Imports','Analyser une reprise financière historique','analyze','HIGH','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'OWNER_APPROVED','0.44.0'),
 ('migration.finance_history.execute','Migration & import','Imports','Exécuter une reprise financière historique','import','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'OWNER_APPROVED','0.44.0') ON CONFLICT(code) DO NOTHING;
INSERT INTO rbac_role_capabilities(role_id,capability_code)
 SELECT DISTINCT rc.role_id,c.code FROM rbac_role_capabilities rc CROSS JOIN (VALUES('migration.finance_history.analyze'),('migration.finance_history.execute')) c(code)
 WHERE rc.capability_code IN('finance.recovery.monthly.read','finance.reports.history.read') ON CONFLICT DO NOTHING;
