from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
router=(ROOT/'backend/src/edusync/modules/migration_import/api/router.py').read_text(encoding='utf-8')
api=(ROOT/'frontend/src/api.ts').read_text(encoding='utf-8')

def test_closed_kind_allowlist_and_tenant_filters():
 assert "_IMPORT_KIND =" in router and "Type d’import inconnu" in router
 assert "WHERE school_id=:sid" in router
 assert "student_import_batches" in router and "staff_import_batches" in router and "financial_history_import_batches" in router

def test_history_and_control_report_are_real_endpoints():
 assert "@router.get('/batches/{kind}')" in router
 assert "@router.get('/batches/{kind}/{batch_id}/control-report.xlsx')" in router
 assert "Rapport de contrôle import" in router and "Données source" in router

def test_frontend_contract_exposes_history_and_report():
 assert "importBatchHistory" in api and "importControlReport" in api

def test_import_history_is_wired_in_three_business_surfaces():
 ui=(ROOT/'frontend/src/import_history.tsx').read_text(encoding='utf-8')
 assert 'Historique des imports' in ui and 'Rapport XLSX' in ui
 assert 'kind="students"' in (ROOT/'frontend/src/schooling.tsx').read_text(encoding='utf-8')
 assert 'kind="staff"' in (ROOT/'frontend/src/personnel.tsx').read_text(encoding='utf-8')
 assert 'kind="finance-history"' in (ROOT/'frontend/src/finance.tsx').read_text(encoding='utf-8')
