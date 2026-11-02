"""Finance header at the cash desk (fix 2026-11-02): the « Caisse personnelle » badge and the receipts queue share the tabs
row without covering a tab, and the receipts drawer is a real page-level dialog (portal), never trapped under the page."""
from pathlib import Path

F = Path(__file__).resolve().parents[2] / "frontend/src"


def test_badge_is_laid_out_beside_the_tabs_not_floating_over_them():
    css = (F / "checkout.css").read_text(encoding="utf-8")
    assert ".financePage.deskMode .financeHero{position:absolute" not in css
    assert ".financePage.deskMode>.financeHero{grid-column:2;grid-row:1" in css
    assert ".financePage.deskMode>.financeTabs{grid-column:1;grid-row:1;flex-wrap:wrap" in css


def test_receipts_drawer_is_rendered_at_page_level():
    src = (F / "receipt_queue.tsx").read_text(encoding="utf-8")
    assert "import {createPortal} from 'react-dom';" in src
    assert "createPortal(<div className=\"receiptQueueBackdrop\"" in src and ",document.body)}" in src
