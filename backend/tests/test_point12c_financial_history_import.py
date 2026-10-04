from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_financial_history_import_is_explicitly_outside_cash():
 s=(ROOT/'backend/src/edusync/modules/migration_import/api/router.py').read_text()
 assert "finance-history/analyze" in s and "finance-history/batches/{batch_id}/execute" in s
 assert "finance_charge_regularizations" in s
 section=s.split('# Point 12C')[1]
 assert "INSERT INTO finance_payments" not in section
 assert "cash_created':False" in section and 'confirm_outside_cash' in section
 assert 'FOR UPDATE' in section and 'Idempotency-Key obligatoire' in section
def test_financial_history_schema_is_rls_and_audited():
 s=(ROOT/'backend/migrations/0035_financial_history_import.sql').read_text()
 assert s.count('FORCE ROW LEVEL SECURITY')==3
 assert 'migration.finance_history.execute' in s and "'CRITICAL'" in s
 assert 'financial_history_import_ledger' in s
def test_financial_history_ui_explains_no_cash_receipt():
 s=(ROOT/'frontend/src/finance.tsx').read_text()
 assert 'Import historique' in s and 'Aucun encaissement de caisse ni reçu EduSync créé' in s
