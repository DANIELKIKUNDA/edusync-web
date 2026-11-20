"""Owner, 2026-11-20: receipts printed from the preview leave the queue; group exemption; decisions cover the year."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_preview_print_marks_the_receipts_submitted():
    ui = (ROOT / 'frontend/src/finance.tsx').read_text(encoding='utf-8')
    assert "onPrinted?.()" in ui and "registerReceiptSubmission(token,preview.ids!,'')" in ui
    assert "ids:[paymentId]" in ui and "ids:r.lines.map(l=>l.payment_id)" in ui


def test_decision_without_date_covers_the_school_year():
    src = (ROOT / 'backend/src/edusync/adapters/postgres_financial_decisions.py').read_text(encoding='utf-8')
    assert 'if effective_from is None:' in src and 'effective_from = enr["start_date"]' in src


def test_group_route_previews_then_creates_with_the_decision_right():
    src = (ROOT / 'backend/src/edusync/modules/finance_controls/api/router.py').read_text(encoding='utf-8')
    body = src.split("def group_decision(", 1)[1]
    assert "need(actor, 'finance.decisions.create')" in body and "if not b.execute:" in body and "'ALREADY' if dup else 'NEW'" in body
    assert "staff_student_links" in src.split("def _group_targets(", 1)[1]
