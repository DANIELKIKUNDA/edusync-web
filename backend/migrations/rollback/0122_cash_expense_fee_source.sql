DROP INDEX IF EXISTS idx_cash_expenses_fee;
ALTER TABLE finance_cash_expenses DROP COLUMN IF EXISTS fee_type_id;
