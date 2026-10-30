"""Owner decisions 2026-10-30 (closing every reserve of the three-role backend certification), checked on the canonical
registry and the migrations. The behaviour on real PostgreSQL is in tools/ci/three_roles_postgres_integration.py."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REG = json.loads((ROOT / "contracts/CAPABILITY_REGISTRY.json").read_text(encoding="utf-8"))
LIFE = {c["code"]: c["lifecycle"] for c in REG["capabilities"]}
MIG = ROOT / "backend/migrations"


def caps(role: str) -> set[str]:
    return set(REG["standard_roles"][role]["capabilities"])


def test_directors_read_the_staff_of_their_section_read_only():
    assert {"personnel.read", "personnel.assignments.read", "personnel.functions.read", "personnel.summary.read"} <= caps("DIRECTEUR_ETUDES")
    assert {"personnel.read", "personnel.assignments.read", "personnel.functions.read"} <= caps("DIRECTEUR_DISCIPLINE")
    assert "personnel.summary.read" not in caps("DIRECTEUR_DISCIPLINE")          # original contract of migration 0009
    for role in ("DIRECTEUR_ETUDES", "DIRECTEUR_DISCIPLINE"):
        assert not {c for c in caps(role) if c.startswith("personnel.") and not c.endswith(".read")}, role   # no write, no export
    sql = (MIG / "0102_directors_personnel_read.sql").read_text(encoding="utf-8")
    assert "INSERT INTO rbac_role_capabilities" in sql and "DIRECTEUR_ETUDES" in sql and "DIRECTEUR_DISCIPLINE" in sql


def test_documents_print_is_removed_from_every_standard_role():
    assert not [r for r, v in REG["standard_roles"].items() if "documents.print" in v["capabilities"]]
    assert "DELETE FROM rbac_role_capabilities" in (MIG / "0103_documents_print_removed.sql").read_text(encoding="utf-8")


def test_enrollments_register_is_built_and_active():
    assert LIFE["enrollments.export"] == "ACTIVE"
    assert all(LIFE[a] == "ALIAS" for a in ("enrollments.export_pdf", "enrollments.export_xlsx", "enrollments.print"))
    router = (ROOT / "backend/src/edusync/modules/schooling/api/router.py").read_text(encoding="utf-8")
    assert "@router.get('/exports/enrollments.pdf')" in router and "@router.get('/exports/enrollments.xlsx')" in router
    assert "_need(actor,'enrollments.export')" in router and "upper(ss.code)=ANY(:secs)" in router   # scope applied in SQL


def test_journey_history_stays_planned_for_the_grades_version():
    assert LIFE["students.lifecycle.history.read"] == "PLANNED"


def test_new_migrations_are_provisioned():
    prov = (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")
    for name in ("0099_stewardship_asset_update_event", "0100_intendance_capabilities_active", "0101_inventory_movements_recent_index",
                 "0102_directors_personnel_read", "0103_documents_print_removed", "0104_enrollments_export_active"):
        assert f'"{name}"' in prov and (MIG / f"{name}.sql").exists(), name
