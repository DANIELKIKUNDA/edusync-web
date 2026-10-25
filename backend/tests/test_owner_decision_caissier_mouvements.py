"""Owner decision 2026-10-25 (migration 0091): the cashier reads the headcount movements journal, still school-adjustable."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REG = json.loads((ROOT / "contracts/CAPABILITY_REGISTRY.json").read_text(encoding="utf-8"))
CAP = next(c for c in REG["capabilities"] if c["code"] == "headcounts.movements.read")
MIG = (ROOT / "backend/migrations/0091_caissier_mouvements_effectifs.sql").read_text(encoding="utf-8")


def test_caissier_reads_movements_and_school_can_adjust():
    assert "headcounts.movements.read" in REG["standard_roles"]["CAISSIER"]["capabilities"]
    assert CAP["role_assignment"] == "OWNER_DECIDED" and CAP["school_adjustable"] and CAP["lifecycle"] == "ACTIVE"


def test_migration_is_additive_and_provisioned():
    assert "DELETE" not in MIG.upper() and "ON CONFLICT DO NOTHING" in MIG and "r.code = 'CAISSIER'" in MIG
    assert "0091_caissier_mouvements_effectifs.sql" in (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")
