"""Backend regression guards for Intendance exports and tenant ownership."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src/edusync/modules/stewardship/api"
ROUTER = (ROOT / "router.py").read_text(encoding="utf-8")


def _section(marker: str) -> str:
    return ROUTER.split(marker, 1)[1].split("\n@router.", 1)[0]


def test_stock_export_has_dedicated_capability_and_school_filter():
    section = _section("@router.get('/stock/export.xlsx')")
    assert "need(actor,'inventory.stock.export_xlsx')" in section
    assert "school_id=:sid" in section
    assert "no-store" in section


def test_count_export_checks_ownership_before_reading_lines():
    section = _section("@router.get('/counts/{count_id}/export.xlsx')")
    assert "need(actor,'inventory.counts.export_xlsx')" in section
    assert "inventory_counts WHERE id=:id AND school_id=:sid" in section
    assert "if head is None:raise HTTPException(404" in section
    assert "l.school_id=:sid" in section


def test_asset_relocation_checks_school_location():
    section = _section("@router.post('/assets/{asset_id}/status')")
    assert "inventory_locations WHERE id=:id AND school_id=:sid" in section


def test_stock_card_update_checks_school_location():
    section = _section("@router.put('/items/{item_id}')")
    assert "inventory_locations WHERE id=:id AND school_id=:sid" in section


def test_count_line_rejects_unexplained_variance():
    section = _section("@router.post('/counts/{count_id}/lines')")
    assert "Justification requise pour chaque écart" in section


def test_workbook_escapes_formula_like_user_values():
    from edusync.modules.stewardship.api.workbook import workbook_bytes
    from openpyxl import load_workbook
    from io import BytesIO
    data = workbook_bytes("Stock", ["Article"], [("=1+1",), ("+SUM(1,2)",)])
    sheet = load_workbook(BytesIO(data)).active
    assert sheet["A2"].value == "=1+1"
    assert sheet["A2"].data_type == "s"
    assert sheet["A3"].value == "+SUM(1,2)"


def test_repair_completion_requires_repairable_status():
    section = _section("@router.post('/assets/{asset_id}/repairs')")
    assert "b.completed and old['status'] not in ('IN_REPAIR','TO_REPAIR')" in section
    assert "Aucune réparation en cours à clôturer" in section


def test_asset_edit_uses_distinct_audit_event():
    section = _section("@router.put('/assets/{asset_id}')")
    assert "'UPDATE',:reason" in section
    migration = (Path(__file__).resolve().parents[1] / "migrations/0097_stewardship_asset_update_event.sql").read_text(encoding="utf-8")
    assert "'UPDATE'" in migration


def test_inventory_detail_joins_items_with_tenant_key():
    section = _section("@router.get('/counts/{count_id}')")
    assert "i.id=l.item_id AND i.school_id=l.school_id" in section


def test_movement_list_joins_items_with_tenant_key():
    section = _section("@router.get('/stock/movements')")
    assert "i.id=m.item_id AND i.school_id=m.school_id" in section


def test_assets_join_types_and_locations_with_tenant_key():
    section = _section("@router.get('/assets')")
    assert "t.id=a.asset_type_id AND t.school_id=a.school_id" in section
    assert "l.id=a.location_id AND l.school_id=a.school_id" in section
