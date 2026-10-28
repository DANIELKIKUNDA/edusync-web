"""Guard granular permissions for Intendance dashboard queries."""
from pathlib import Path

ROUTER = (Path(__file__).resolve().parents[1] / "src/edusync/modules/stewardship/api/router.py").read_text(encoding="utf-8")
DASHBOARD = ROUTER.split("@router.get('/dashboard')", 1)[1].split("@router.get('/stock')", 1)[0]


def test_dashboard_requires_inventory_permission():
    assert "'inventory.stock.read','inventory.assets.read','inventory.counts.read'" in DASHBOARD


def test_dashboard_authorizes_queries_before_execution():
    for permission, dataset in (
        ("inventory.assets.read", "locations"),
        ("inventory.assets.read", "assets"),
        ("inventory.stock.low_alerts.read", "low"),
        ("inventory.stock.read", "sales"),
    ):
        query_line = next(line for line in DASHBOARD.splitlines() if line.strip().startswith(dataset + "=rows("))
        assert "if '" + permission + "' in permissions else []" in query_line


def test_dashboard_keeps_response_contract():
    assert "return {'locations':locations,'assets':assets,'low_stock':low,'sale_stock':sales}" in DASHBOARD
