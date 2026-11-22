-- « Lors d'une sortie on peut demander au caissier de prendre dans le frais de l'État ou autre frais ce jour-là »
-- (owner, 2026-11-22). An expense may name the fee whose money it uses; NULL = not specified (every past expense).
-- The daily report then shows, per currency and per fee: entries, outflows and balance. Additive only.
ALTER TABLE finance_cash_expenses ADD COLUMN IF NOT EXISTS fee_type_id uuid REFERENCES fee_types(id);
CREATE INDEX IF NOT EXISTS idx_cash_expenses_fee ON finance_cash_expenses(school_id, fee_type_id) WHERE fee_type_id IS NOT NULL;
