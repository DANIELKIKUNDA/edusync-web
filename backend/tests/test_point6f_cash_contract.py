from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(p):return (ROOT/p).read_text(encoding='utf-8')
def test_cash_migration_is_personal_and_explicit():
 s=read('backend/migrations/0021_finance_cash_industrial.sql')
 assert "WHERE status='OPEN'" in s and 'opening_cdf' in s and 'counted_cdf' in s
 assert 'finance_cash_events' in s and "'OPEN','CLOSE','REOPEN','EXPENSE'" in s
def test_checkout_still_fails_closed_without_open_cash():
 s=read('backend/src/edusync/adapters/postgres_finance_checkout.py')
 assert "status='OPEN'" in s and ('Caisse fermée' in s or 'caisse' in s.lower())
def test_cash_ui_requires_explicit_open_and_real_count_close():
 s=read('frontend/src/finance.tsx')+read('frontend/src/cash_desk.tsx')  # 2026-10-25: the cash desk moved to cash_desk.tsx
 assert 'Ouvrir ma caisse' in s and 'Clôturer ma caisse' in s and 'Compté {c}' in s and "(['CDF', 'USD'] as Cur[])" in s   # counted per currency
 assert 'Caisses passées' in s and 'cashSessions(token, {start: range[0], end: range[1]' in s   # history over a period, not one day
def test_cash_rbac_preserved():
 s=read('contracts/CAPABILITY_REGISTRY.json')
 for cap in ['finance.cash.open','finance.cash.close','finance.cash.read','finance.cash.other.read','finance.cash.reopen']:
  assert cap in s
