"""Home cards of the finance module open THEIR screen (owner, 2026-11-02): « Encaissements du jour » opened the quick
checkout instead of the cash desk, « Articles à surveiller » too instead of the articles. Every finance widget the server
can project must have an explicit destination in the home page, so a new card can never silently fall back."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def finance_widget_ids():
    src = (ROOT / "backend/src/edusync/modules/access/application/projection.py").read_text(encoding="utf-8")
    return re.findall(r'\{"id": "([a-z_.]+)", "title": "[^"]+", "module": "finance"', src)


def test_every_finance_card_has_a_destination():
    home = (ROOT / "frontend/src/home.tsx").read_text(encoding="utf-8")
    mapping = home.split("const financeTarget=", 1)[1].split("\n", 1)[0]
    ids = finance_widget_ids()
    assert {"cash.receipts", "products.watch"} <= set(ids)
    missing = [i for i in ids if f"'{i}'" not in mapping]
    assert not missing, f"cartes finance sans destination : {missing}"
    assert "id==='cash.receipts'?'cash'" in mapping
    assert "id==='products.watch'?'products'" in mapping


def test_products_target_opens_the_articles_part_of_the_cash_desk():
    fin = (ROOT / "frontend/src/finance.tsx").read_text(encoding="utf-8")
    assert "x==='products'?canProducts" in fin and "requested==='products'&&canProducts?'other':'quick'" in fin
    assert "initialMode={checkoutMode}" in fin
