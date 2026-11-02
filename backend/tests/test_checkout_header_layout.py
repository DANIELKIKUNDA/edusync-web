"""Finance header at the cash desk (fix 2026-11-02): the « Caisse personnelle » badge and the receipts queue share the tabs
sits on the breadcrumb row so the tabs keep the whole width on one line without covering a tab, and the receipts drawer is a real page-level dialog (portal), never trapped under the page."""
from pathlib import Path

F = Path(__file__).resolve().parents[2] / "frontend/src"


def test_badge_is_laid_out_beside_the_tabs_not_floating_over_them():
    css = (F / "checkout.css").read_text(encoding="utf-8")
    assert ".financePage.deskMode .financeHero{position:absolute" not in css
    hero = css.split(".financePage.deskMode>.financeHero{", 1)[1].split("}", 1)[0]
    assert "position:absolute" not in hero and "z-index" not in hero and "var(--pf-trail-lift" in hero   # on the breadcrumb row
    assert ".financePage.deskMode>.financeTabs{flex-wrap:wrap" in css                                     # tabs: full width


def test_receipts_drawer_is_rendered_at_page_level():
    src = (F / "receipt_queue.tsx").read_text(encoding="utf-8")
    assert "import {createPortal} from 'react-dom';" in src
    assert "createPortal(<div className=\"receiptQueueBackdrop\"" in src and ",document.body)}" in src
