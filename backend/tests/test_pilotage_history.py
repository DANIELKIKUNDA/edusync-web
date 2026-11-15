"""Executive home money cards include the payments taken over from the previous system (owner, 2026-11-15).

« Ces cartes doivent contenir l'argent encaissé : les paiements que nous venons de reprendre sont réels. » The imported
history (one ledger line per source payment, at its real date) is added to today / week / month / since the start of the
year, shown apart (« dont … repris de l'ancien système »), limited to the chosen year, and never enters a cash desk balance.
"""
from __future__ import annotations

from pathlib import Path

from edusync.modules.finance_recovery.api.router import PILOTAGE_SQL

ROOT = Path(__file__).resolve().parents[2]
ROUTER = (ROOT / "backend/src/edusync/modules/finance_recovery/api/router.py").read_text(encoding="utf-8")
HOME = (ROOT / "frontend/src/exec_home.tsx").read_text(encoding="utf-8")


def test_history_ledger_is_counted_at_its_real_date_for_the_chosen_year_only():
    hist = PILOTAGE_SQL.split("FROM financial_history_import_ledger l", 1)[1].split("SELECT mv.currency", 1)[0]
    assert "l.historical_paid_on, l.currency, l.amount, 'H'" in PILOTAGE_SQL
    assert "e.academic_year_id=%(yid)s" in hist and "l.school_id=%(sid)s" in hist
    assert "kind='H'),0) AS year_history" in PILOTAGE_SQL
    assert "'yid':y['id']" in ROUTER and "'year_history')" in ROUTER


def test_history_never_counts_as_a_cash_receipt_or_cancellation_of_the_day():
    assert "AND kind='R'),0) AS today_receipts" in PILOTAGE_SQL and "AND kind='C'),0) AS today_cancellations" in PILOTAGE_SQL


def test_year_starts_when_enrolment_opens_and_the_screen_says_so():
    assert "start=min(y['start_date'],y.get('enrollment_start') or y['start_date'],today)" in ROUTER
    assert "'period_start':str(start)" in ROUTER
    assert "d.academic_year.period_start||d.academic_year.start_date" in HOME
    assert "repris de l’ancien système" in HOME and "cash.CDF.year_history" in HOME
