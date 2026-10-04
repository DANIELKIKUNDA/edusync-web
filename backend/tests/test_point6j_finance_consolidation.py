from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def read(p): return (ROOT/p).read_text(encoding='utf-8')

def test_finance_navigation_has_one_entry_per_responsibility():
    f=read('frontend/src/finance.tsx')
    for label in ['Encaissement','Recouvrement','Caisse','Rapports','Suivi des frais','Décisions financières']:
        assert f'>{label}<' in f
    for obsolete in ['>Fonds anticipés<','>Suivi opérateur<','>Analyses<','>Audit<']:
        assert obsolete not in f

def test_fee_tracking_is_read_only_projection_and_recovery_owns_recovery_views():
    fee=read('backend/src/edusync/modules/finance_fee_tracking/api/router.py')
    rec=read('frontend/src/recovery.tsx')
    assert "@router.get('/students')" in fee and "@router.post('/" not in fee
    for x in ['Suivi mensuel','Registre des classes','Synthèse par classe','Synthèse par section','Synthèse école']:
        assert x in rec

def test_cash_and_reports_are_separate_responsibilities():
    f=read('frontend/src/finance.tsx')
    assert 'Situation globale des caisses' in f and 'Solde théorique global' in f
    assert 'ReportsDesk' in f and 'CashDesk' in f
    assert "can('finance.cash.other.read')" in f

def test_student_family_financial_views_reuse_fee_projection_api():
    s=read('frontend/src/schooling.tsx')
    api=read('frontend/src/api.ts')
    assert 'studentFeeSummary' in s and 'familyFeeSummary' in s
    assert '/finance/fees/student/' in api and '/finance/fees/family/' in api

def test_advance_funds_not_daily_finance_tab_but_domain_preserved():
    f=read('frontend/src/finance.tsx')
    cat=read('backend/src/edusync/modules/documents/domain/catalog.py')
    assert '>Fonds anticipés<' not in f
    assert 'finance.advance_funds' in cat

def test_currency_separation_is_explicit_in_cash_ui():
    f=read('frontend/src/finance.tsx')
    assert "row('CDF'" in f and "row('USD'" in f
