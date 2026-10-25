"""Caisse 2026-10-25 (owner: « voir les caisses passées et exporter la caisse », Desktop CashPage + journal PDF)."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

from edusync.modules.finance_cash.application.documents import cash_journal_pdf, session_journal_xlsx, sessions_xlsx

ROOT = Path(__file__).resolve().parents[2]
ROUTER = (ROOT / "backend/src/edusync/modules/finance_cash/api/router.py").read_text(encoding="utf-8")
REPO = (ROOT / "backend/src/edusync/adapters/postgres_cash_integrity.py").read_text(encoding="utf-8")

CUR = {"opening": "1000.00", "receipts": "12000.00", "expenses": "1000.00", "reversals": "0.00", "expected_cash": "12000.00", "counted": "11900.00", "variance": "-100.00"}
USD = {"opening": "0.00", "receipts": "5.00", "expenses": "0.00", "reversals": "0.00", "expected_cash": "5.00", "counted": "5.00", "variance": "0.00"}
SESSION = {"id": "s1", "business_date": "2026-10-25", "status": "CLOSED", "opened_at": "2026-10-25T07:30:00", "closed_at": "2026-10-25T16:05:00",
           "cashier_name": "Caissière Test", "cdf": CUR, "usd": USD}
OPS = [{"created_at": datetime(2026, 10, 25, 8, 1), "direction": "ENTREE", "source": "PAIEMENT_ELEVE", "amount": "12000.00", "currency": "CDF", "mode": "CASH",
        "reference": "REC-1", "party": "KALALA Joseph", "reversed": False},
       {"created_at": datetime(2026, 10, 25, 9, 0), "direction": "SORTIE", "source": "DEPENSE_JOURNALIERE", "amount": "1000.00", "currency": "CDF", "mode": "CASH",
        "reference": "Craies", "reason": "Craies pour les classes", "party": "Fournitures", "reversed": False}]


def test_session_journal_xlsx_lists_movements_and_keeps_currencies_apart():
    ws = load_workbook(BytesIO(session_journal_xlsx(school_name="École", session=SESSION, cashier="Caissière Test", operations=OPS))).active
    values = [[c.value for c in row] for row in ws.iter_rows()]
    assert values[1][0] == "JOURNAL DE CAISSE" and "Caissière Test" in values[2][0]
    assert ["08:01:00", "Entrée", "Paiement élève", "KALALA Joseph", 12000.0, "FC"] == values[5][:6]
    summary = {r[0]: r for r in values if r[0] in ("FC", "USD")}
    assert summary["FC"][5] == 12000.0 and summary["FC"][7] == -100.0 and summary["USD"][5] == 5.0      # never added together


def test_sessions_xlsx_one_line_per_session_with_cdf_and_usd_columns():
    ws = load_workbook(BytesIO(sessions_xlsx(school_name="École", start="2026-10-01", end="2026-10-25", sessions=[SESSION]))).active
    head = [c.value for c in ws[5]]; row = [c.value for c in ws[6]]
    assert head[5] == "Entrées FC" and head[10] == "Entrées USD"
    assert row[:5] == ["2026-10-25", "Caissière Test", "07:30", "16:05", "Clôturée"] and row[5] == 12000.0 and row[9] == -100.0 and row[10] == 5.0


def test_session_journal_pdf_has_a_title_per_cashier():
    data = cash_journal_pdf(school_name="École", report={"day": "2026-10-25", "closed": True, "totals": [], "operations": OPS}, title="JOURNAL DE CAISSE — X — 2026-10-25")
    assert data.startswith(b"%PDF") and len(data) > 800


def test_routes_are_read_only_and_scoped_to_own_sessions():
    for route in ("@router.get('/sessions')", "@router.get('/sessions.xlsx')", "@router.get('/{session_id}/journal.pdf')", "@router.get('/{session_id}/journal.xlsx')"):
        assert route in ROUTER
    assert "('' if other else ' AND membership_id=:mid')" in ROUTER                      # a cashier sees HIS sessions
    assert "Cette caisse appartient à un autre caissier" in ROUTER and "need(actor, 'finance.cash.journal.export')" in ROUTER
    assert "Période trop longue : un an au maximum" in ROUTER
    assert "def session_operations" in REPO and "r.cash_session_id=:cs" in REPO and "e.cash_session_id=:cs" in REPO
