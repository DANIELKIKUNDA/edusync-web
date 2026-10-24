"""Owner decisions 2026-10-24 (migration 0090):
- « En RDC, le caissier est généralement aussi le secrétaire » : CAISSIER ⊇ SECRÉTARIAT, every added capability stays
  school-adjustable (the school may decide otherwise in Accès & rôles);
- student import → SECRÉTARIAT (hence CAISSIER), staff import → GESTIONNAIRE;
- the rbac-contract CI proves the 0085 engine change only; later owner decisions are checked against the registry.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REG = json.loads((ROOT / "contracts/CAPABILITY_REGISTRY.json").read_text(encoding="utf-8"))
CAPS = {c["code"]: c for c in REG["capabilities"]}
ROLES = REG["standard_roles"]
MIG = (ROOT / "backend/migrations/0090_caissier_secretariat_imports.sql").read_text(encoding="utf-8")
CI = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")


def test_caissier_holds_every_secretariat_capability():
    assert set(ROLES["SECRETARIAT"]["capabilities"]) <= set(ROLES["CAISSIER"]["capabilities"])
    added = set(ROLES["SECRETARIAT"]["capabilities"])
    assert all(CAPS[c]["school_adjustable"] for c in added if CAPS[c]["lifecycle"] == "ACTIVE")   # « sauf si l'école décide autrement »


def test_imports_are_assigned():
    for cap in ("migration.students.analyze", "migration.students.execute", "documents.student_import_template.export"):
        assert cap in ROLES["SECRETARIAT"]["capabilities"] and cap in ROLES["CAISSIER"]["capabilities"]
        assert CAPS[cap]["role_assignment"] == "OWNER_DECIDED"
    for cap in ("migration.staff.analyze", "migration.staff.execute"):
        assert cap in ROLES["GESTIONNAIRE"]["capabilities"] and CAPS[cap]["role_assignment"] == "OWNER_DECIDED"


def test_migration_is_additive_and_ci_scope_is_explicit():
    assert "DELETE" not in MIG.upper() and MIG.count("ON CONFLICT DO NOTHING") == 3
    assert "JOIN rbac_role_capabilities rc ON rc.role_id = sec.id" in MIG
    proof = CI.split("Migration 0085 puis preuve de non-régression", 1)[1].split("- name:", 1)[0]
    assert "EDUSYNC_MIGRATE_UNTIL: 0085_school_rbac_policies" in proof
    assert "Migrations suivantes" in CI and "rbac_registry.py check" in CI
