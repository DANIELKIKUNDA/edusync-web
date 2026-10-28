"""Regression: stewardship dashboard must honor granular inventory read rights."""
from pathlib import Path

ROUTER = (Path(__file__).resolve().parents[1] / "src/edusync/modules/stewardship/api/router.py").read_text(encoding="utf-8")


def test_dashboard_requires_inventory_permission():
    assert "'inventory.stock.read','inventory.assets.read','inventory.counts.read'" in ROUTER


def test_dashboard_does_not_expose_ungranted_datasets():
    assert "'locations':locations if 'inventory.assets.read' in permissions else []" in ROUTER
    assert "'assets':assets if 'inventory.assets.read' in permissions else []" in ROUTER
    assert "'low_stock':low if 'inventory.stock.low_alerts.read' in permissions else []" in ROUTER
    assert "'sale_stock':sales if 'inventory.stock.read' in permissions else []" in ROUTER
