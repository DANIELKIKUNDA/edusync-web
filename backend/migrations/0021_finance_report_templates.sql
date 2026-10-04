-- Point 6G — modèles de rapports financiers par école (additif, tenant-safe)
CREATE TABLE IF NOT EXISTS finance_report_templates(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL,
 code text NOT NULL, label text NOT NULL, description text,
 scope_mode text NOT NULL DEFAULT 'MY_CASH' CHECK(scope_mode IN('MY_CASH','ONE_CASHIER','ALL_CASHIERS')),
 sections jsonb NOT NULL DEFAULT '[]'::jsonb, system_template boolean NOT NULL DEFAULT false,
 enabled boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(school_id,code)
);
ALTER TABLE finance_report_templates ENABLE ROW LEVEL SECURITY; ALTER TABLE finance_report_templates FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS finance_report_templates_tenant ON finance_report_templates;
CREATE POLICY finance_report_templates_tenant ON finance_report_templates USING (school_id=current_setting('app.school_id',true)::uuid) WITH CHECK (school_id=current_setting('app.school_id',true)::uuid);
CREATE INDEX IF NOT EXISTS ix_finance_report_templates_school ON finance_report_templates(school_id,enabled,label);
