"""Administrator finishing pass (owner request 2026-10-24):
- readiness: a NOT_APPLICABLE item never lowers the percentage (« Tout est prêt » shown with 86 %);
- school articles: unit price, opening stock (traced « Stock initial »), alert threshold, traced receipts / corrections
  with the Intendance capabilities; the quantity never goes below zero;
- anticipated-payment plans target several classes / levels / sections (migration 0089, single scope_ref kept);
- the school year carries an editable, never blocking enrollment period.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from edusync.modules.settings.domain.models import ReadinessItem, ReadinessSnapshot

ROOT = Path(__file__).resolve().parents[2]
MIG = (ROOT / "backend/migrations/0089_admin_finition_plans_years.sql").read_text(encoding="utf-8")
ROUTER = (ROOT / "backend/src/edusync/modules/settings/api/router.py").read_text(encoding="utf-8")
SETTINGS = (ROOT / "backend/src/edusync/adapters/postgres_settings.py").read_text(encoding="utf-8")
ANTICIPATION = (ROOT / "backend/src/edusync/adapters/postgres_anticipation.py").read_text(encoding="utf-8")
PROVISION = (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")


def test_not_applicable_items_never_lower_the_percentage():
    items = tuple(ReadinessItem(c, c, "READY", "") for c in "ABCDEF") + (ReadinessItem("SMS", "SMS", "NOT_APPLICABLE", ""),)
    assert ReadinessSnapshot(uuid4(), items).percent == 100
    half = (ReadinessItem("A", "A", "READY", ""), ReadinessItem("B", "B", "TO_COMPLETE", ""), ReadinessItem("C", "C", "NOT_APPLICABLE", ""))
    assert ReadinessSnapshot(uuid4(), half).percent == 50


def test_migration_0089_is_additive():
    assert "ADD COLUMN IF NOT EXISTS scope_refs varchar(64)[]" in MIG
    assert "ADD COLUMN IF NOT EXISTS enrollment_start date" in MIG and "ADD COLUMN IF NOT EXISTS enrollment_end date" in MIG
    assert "DROP" not in MIG.upper().replace("DROP POLICY", "")
    assert '("0089_admin_finition_plans_years", "0089_admin_finition_plans_years.sql")' in PROVISION


def test_product_stock_is_traced_and_never_negative():
    move = SETTINGS.split("def move_product_stock", 1)[1].split("def enrollment_windows", 1)[0]
    assert "INSERT INTO inventory_stock_movements" in move and "cur+delta<0" in move and "FOR UPDATE" in move
    create = SETTINGS.split("def create_product", 1)[1].split("def ", 1)[0]
    assert "reason='Stock initial'" in create
    stock = ROUTER.split("def product_stock_move", 1)[1].split("\n@router", 1)[0]
    assert "'inventory.stock.receive' if body.movement_type=='RECEIPT' else 'inventory.stock.adjust'" in stock


def test_plans_match_any_of_their_targets():
    match = ANTICIPATION.split("def _scope_matches", 1)[1].split("def _plan", 1)[0]
    assert 'plan.get("scope_refs") or [plan["scope_ref"]]' in match
    save = ANTICIPATION.split("def save_plan", 1)[1].split("def set_plan_active", 1)[0]
    assert "scope_refs" in save and "Une classe choisie n'appartient pas à cette année scolaire" in save


def test_enrollment_period_is_editable_and_informative():
    window = ROUTER.split("def put_enrollment_window", 1)[1].split("\nclass ", 1)[0]
    assert "_need(actor,'settings.academic_year.update')" in window and "('PREPARED','ACTIVE')" in window
    assert "ENROLLMENT_WINDOW_UPDATED" in window
    assert "La fin des inscriptions doit suivre leur début" in SETTINGS
