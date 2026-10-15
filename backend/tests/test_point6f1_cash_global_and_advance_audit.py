from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(p): return (ROOT/p).read_text(encoding='utf-8')
def test_global_cash_is_permission_separated_and_currency_separated():
 s=read('backend/src/edusync/modules/finance_cash/api/router.py')
 assert "@router.get('/day-summary')" in s
 assert "need(actor,'finance.cash.other.read')" in s
 assert "('CDF','USD')" in s
 assert "expected_cash" in s
def test_cash_ui_is_table_first_not_card_wall():
 s=read('frontend/src/finance.tsx')
 assert 'Situation globale des caisses' in s
 assert '<table className="cashSummaryTable">' in s
 assert 'Fond initial' in s and 'Entrées' in s and 'Sorties' in s and 'Solde théorique' in s
 assert 'cashDaySummary(token,day)' in s
def test_anticipation_collection_has_single_checkout_path():
 s=read('frontend/src/finance.tsx')
 assert 'Paiement selon un plan anticipé' in s and 'Paiement avec avance' not in s
 assert "tab==='advance'" not in s
 assert 'Fonds anticipés</button>' not in s
