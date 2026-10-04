-- Point 6I — Suivi des frais: taxonomie configurable sans dupliquer le recouvrement.
CREATE TABLE IF NOT EXISTS fee_categories(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 code varchar(48) NOT NULL, label varchar(140) NOT NULL, sort_order smallint NOT NULL DEFAULT 100,
 enabled boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(school_id,code)
);
ALTER TABLE fee_categories ENABLE ROW LEVEL SECURITY; ALTER TABLE fee_categories FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS fee_categories_tenant ON fee_categories;
CREATE POLICY fee_categories_tenant ON fee_categories USING(school_id=current_setting('app.school_id',true)::uuid) WITH CHECK(school_id=current_setting('app.school_id',true)::uuid);
ALTER TABLE fee_types ADD COLUMN IF NOT EXISTS category_id uuid REFERENCES fee_categories(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_fee_types_category ON fee_types(school_id,category_id,enabled);
-- Projection canonique de l'obligation nette. Une décision générale non affectée à une charge
-- reste visible/auditable mais n'est jamais répartie silencieusement entre plusieurs frais.
CREATE OR REPLACE VIEW finance_charge_effective AS
SELECT fc.*,
 greatest(fc.net_amount-coalesce((SELECT sum(d.amount) FROM finance_decisions d WHERE d.school_id=fc.school_id AND d.charge_id=fc.id AND d.status='ACTIVE' AND d.currency=fc.currency),0),0)::numeric(18,2) effective_net_amount,
 coalesce((SELECT sum(d.amount) FROM finance_decisions d WHERE d.school_id=fc.school_id AND d.charge_id=fc.id AND d.status='ACTIVE' AND d.currency=fc.currency),0)::numeric(18,2) decision_amount
FROM finance_charges fc;
