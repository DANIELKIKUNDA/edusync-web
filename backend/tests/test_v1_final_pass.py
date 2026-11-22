"""Passe définitive V1 (owner, 2026-11-22).

1. « Les nombres contiennent tous des petits carrés » — the standard PDF fonts cannot draw U+202F / U+00A0: no such
   character anywhere in the server code that produces documents.
2. « Le rapport doit très bien spécifier les frais » — money received split by fee (dashboard and daily report), an
   expense may name the fee it is taken from, and the daily report shows entries / outflows / balance per fee.
3. Dashboard money cards open a breakdown on hover (computer) or tap (phone).
4. « Rapport de direction » tab without the explanatory sentences.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "backend/src/edusync"


def test_no_invisible_space_that_pdf_fonts_cannot_draw():
    bad = [str(p.relative_to(ROOT)) for p in SRC.rglob("*.py") if any(ch in p.read_text(encoding="utf-8") for ch in (" ", " "))]
    assert bad == [], bad


def test_dashboard_breakdown_uses_exactly_the_card_movements():
    shared = (SRC / "modules/finance_recovery/application/by_fee.py").read_text(encoding="utf-8")
    for part in ("finance_payment_allocations", "finance_payment_reversals", "finance_advance_funds", "finance_advance_fund_closures",
                 "financial_history_import_ledger", "Ventes d’articles", "Avance non encore affectée"):
        assert part in shared
    router = (SRC / "modules/finance_recovery/api/router.py").read_text(encoding="utf-8")
    assert "'by_fee':by_fee[cur]" in router and "PILOTAGE_BY_FEE_SQL" in router


def test_expense_names_its_fee_and_daily_report_splits_by_fee():
    mig = (ROOT / "backend/migrations/0122_cash_expense_fee_source.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS fee_type_id uuid REFERENCES fee_types(id)" in mig and "DROP" not in mig.upper()
    assert (ROOT / "backend/migrations/rollback/0122_cash_expense_fee_source.sql").exists()
    assert '"0122_cash_expense_fee_source"' in (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")
    repo = (SRC / "adapters/postgres_cash_integrity.py").read_text(encoding="utf-8")
    assert "def day_by_fee(" in repo and '"by_fee": self.day_by_fee(school_id, day)' in repo
    assert "Type de frais introuvable pour cette école" in repo                       # a fee of another school is refused
    api = (SRC / "modules/finance_cash/api/router.py").read_text(encoding="utf-8")
    assert "@router.get('/expense-sources')" in api and "fee_type_id=b.fee_type_id" in api
    pdf = (SRC / "modules/finance_cash/application/documents.py").read_text(encoding="utf-8")
    assert "Répartition par type de frais" in pdf


def test_screens():
    cash = (ROOT / "frontend/src/cash_controls.tsx").read_text(encoding="utf-8")
    assert "Pris dans les frais de" in cash and "fee_type_id: source || null" in cash and "Répartition par type de frais" in cash
    home = (ROOT / "frontend/src/exec_home.tsx").read_text(encoding="utf-8")
    assert "by_fee" in home and "onMouseEnter={hover?()=>setOpen(k)" in home and "Reste à recouvrer, par frais" in home
    assert "Calcul : <b>" not in home                                                  # the long explanation is gone
    assert 'createPortal(<div className="ex-sheet-backdrop"' in home   # phones: bottom sheet, the grid never jumps
    direction = (ROOT / "frontend/src/recovery_direction.tsx").read_text(encoding="utf-8")
    assert 'className="dirBar"' in direction and "Une lettre claire pour la direction" not in direction
    assert "Le PDF contient aussi le détail par classe" not in direction
    assert "Envoyer aux responsables" not in direction and "recoveryDigestSend" not in direction   # sent automatically
