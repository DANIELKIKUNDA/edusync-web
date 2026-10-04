from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_register_has_no_duplicate_month_generation():
    s=(ROOT/'backend/src/edusync/adapters/postgres_finance_recovery.py').read_text()
    assert "columns.setdefault(key" in s and "key=f\"MONTH:" in s
def test_register_export_and_year_class_filters_exist():
    s=(ROOT/'backend/src/edusync/modules/finance_recovery/api/router.py').read_text()
    assert '/class-register.pdf' in s and '/class-register.xlsx' in s and 'class_id:UUID' in s and 'year_id:UUID|None' in s
def test_ui_has_real_register_tab_and_modern_exports():
    s=(ROOT/'frontend/src/recovery.tsx').read_text()
    assert 'Registre des classes' in s and 'recoveryClassRegisterExport' in s and '<svg' in s
def test_anticipation_target_ledger_is_additive():
    s=(ROOT/'backend/migrations/0020_recovery_class_register.sql').read_text()
    assert 'finance_advance_targets' in s and 'fee_type_id' in s
