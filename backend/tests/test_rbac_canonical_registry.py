"""Canonical RBAC registry contract (owner decisions 2026-10-23, items 3, 6, 7).

Static checks (no database): the database itself is checked against the registry by the CI job `rbac-contract`
(tools/ci/rbac_registry.py check) and the effective permissions by tools/ci/rbac_snapshot.py.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REG = json.loads((ROOT / "contracts" / "CAPABILITY_REGISTRY.json").read_text(encoding="utf-8"))
CAPS = {c["code"]: c for c in REG["capabilities"]}
BACKEND = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "backend" / "src").rglob("*.py"))
FRONTEND = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "frontend" / "src").rglob("*.ts*"))
LIFECYCLES = {"ACTIVE", "PLANNED", "DEPRECATED", "ALIAS"}


def literal(code: str, text: str) -> bool:
    return re.search(r"['\"`]" + re.escape(code) + r"['\"`]", text) is not None


def test_registry_is_canonical_and_well_formed():
    assert REG["status"] == "CANONICAL" and REG["capability_count"] == len(CAPS) == len(REG["capabilities"])
    for code, c in CAPS.items():
        assert c["lifecycle"] in LIFECYCLES, code
        assert (c["lifecycle"] == "ALIAS") == bool(c.get("alias_of")), code
        if c.get("alias_of"):
            target = CAPS[c["alias_of"]]
            assert target["lifecycle"] in {"ACTIVE", "PLANNED"} and target["code"].endswith(".export"), code
        if c["school_adjustable"]:
            assert c["lifecycle"] == "ACTIVE" and not code.startswith("platform."), code


def test_every_active_capability_is_enforced_by_a_real_backend_use_case():
    """Item 7: an ACTIVE capability is tied to at least one endpoint / use case. Anything else is PLANNED,
    DEPRECATED or ALIAS and hidden from the rights editor."""
    missing = sorted(code for code, c in CAPS.items() if c["lifecycle"] == "ACTIVE" and not literal(code, BACKEND))
    assert missing == []


def test_no_code_checks_a_planned_deprecated_or_alias_capability():
    inactive = [code for code, c in CAPS.items() if c["lifecycle"] != "ACTIVE"]
    assert sorted(c for c in inactive if literal(c, BACKEND)) == []
    # the frontend may still read the DEPRECATED dashboard / menu hints until /access/me replaces them entirely
    assert sorted(c for c in inactive if CAPS[c]["lifecycle"] in {"ALIAS", "PLANNED"} and literal(c, FRONTEND)) == []


def test_every_capability_named_by_the_backend_exists_in_the_registry():
    checks = set(re.findall(r"(?:_need|need|require|scopes_for|scope_allows|_scopes)\(\s*actor\s*,\s*['\"]([a-z_]+(?:\.[a-z0-9_]+)+)['\"]", BACKEND))
    checks |= set(re.findall(r"required_capability\s*=\s*['\"]([a-z_]+(?:\.[a-z0-9_]+)+)['\"]", BACKEND))
    assert checks, "pattern no longer matches the routers"
    assert sorted(checks - set(CAPS)) == []


def test_export_format_variants_are_aliases_of_one_business_capability():
    groups: dict[str, set[str]] = {}
    for code, c in CAPS.items():
        if c.get("alias_of"):
            groups.setdefault(c["alias_of"], set()).add(code)
    assert len(groups) == 10
    for canon, variants in groups.items():
        stem = canon[: -len(".export")]
        assert all(v.startswith(stem + ".") and re.search(r"\.(export_(pdf|xlsx)|print(_pdf)?)$", v) for v in variants), canon
    # different business verbs are never merged (item 3)
    assert CAPS["finance.receipts.print"]["lifecycle"] == "ACTIVE" and not CAPS["finance.receipts.print"].get("alias_of")
    assert CAPS["students.profile.print_pdf"]["lifecycle"] == "ACTIVE"


def test_standard_roles_and_protected_base():
    roles = REG["standard_roles"]
    school_roles = {k for k, r in roles.items() if r["level"] == "SCHOOL"}
    assert {"ADMIN_SYSTEME_ECOLE", "PROMOTEUR", "GESTIONNAIRE", "RESPONSABLE_FINANCE", "PREFET_ETUDES", "DIRECTION_SECTION",
            "DIRECTEUR_ETUDES", "DIRECTEUR_DISCIPLINE", "CAISSIER", "SECRETARIAT", "INTENDANT"} == school_roles
    for code, r in roles.items():
        assert set(r["capabilities"]) <= set(CAPS), code
        assert set(r["locked"]) <= set(r["capabilities"]), code
        for variant in (c for c in r["capabilities"] if CAPS[c].get("alias_of")):
            assert CAPS[variant]["alias_of"] in r["capabilities"], (code, variant)
    admin = roles["ADMIN_SYSTEME_ECOLE"]
    locked = set(admin["locked"])
    # item 2: administration / configuration only — never a business operation in the protected base
    assert {"access.roles.manage", "access.users.create", "access.permissions.assign", "settings.academic_year.read"} <= locked
    assert not any(c.split(".")[0] in {"finance", "students", "enrollments", "families", "inventory", "communications"} for c in locked)
    assert all(r["locked"] == [] for k, r in roles.items() if k != "ADMIN_SYSTEME_ECOLE")


def test_separation_of_duties_rules():
    rules = {r["code"]: r for r in REG["sod_rules"]}
    assert rules["SELF_ELEVATION"]["effect"] == "BLOCK" and rules["SELF_ELEVATION"]["school_overridable"] is False
    assert rules["GOVERNANCE_GRANT"]["effect"] == "REQUIRE_APPROVAL"
    assert {r["effect"] for r in rules.values()} <= {"ALLOW", "WARN", "REQUIRE_APPROVAL", "BLOCK"}
    for r in rules.values():
        if r["kind"] == "PAIR":
            assert len(r["capabilities"]) == 2 and all(CAPS[c]["lifecycle"] == "ACTIVE" for c in r["capabilities"])


def test_migration_0085_is_additive_and_reversible():
    sql = (ROOT / "backend" / "migrations" / "0085_school_rbac_policies.sql").read_text(encoding="utf-8")
    body = re.sub(r"--[^\n]*", "", sql)
    assert not re.search(r"\bDELETE\s+FROM\b|\bDROP\s+TABLE\b|^\s*TRUNCATE\b|\bDROP\s+COLUMN\b", body, re.I | re.M)
    assert "ON CONFLICT DO NOTHING" in sql and "ON CONFLICT (code) DO NOTHING" in sql
    down = (ROOT / "backend" / "migrations" / "rollback" / "0085_school_rbac_policies.down.sql").read_text(encoding="utf-8")
    assert "DROP TABLE IF EXISTS rbac_change_requests" in down and "MERGED_2026_10_23" in down
    provision = (ROOT / "backend" / "scripts" / "provision_database.py").read_text(encoding="utf-8")
    assert '("0085_school_rbac_policies", "0085_school_rbac_policies.sql")' in provision


def _projection():
    import sys
    sys.path.insert(0, str(ROOT / "backend" / "src"))
    from edusync.modules.access.application import projection
    return projection


def test_projection_only_relies_on_active_capabilities():
    declared = _projection().declared_capabilities()
    assert sorted(c for c in declared if c not in CAPS or CAPS[c]["lifecycle"] != "ACTIVE") == []


def test_projection_per_standard_role_owner_decision_9():
    p = _projection()
    roles = REG["standard_roles"]

    def view(code):
        caps = set(roles[code]["capabilities"])
        return ({n["key"] for n in p.navigation(caps)}, {w["id"] for w in p.widgets(caps)}, {a["id"] for a in p.actions(caps)})

    nav, widgets, actions = view("ADMIN_SYSTEME_ECOLE")
    assert {"home", "settings", "access"} <= nav and not {"finance", "students", "headcounts", "stewardship"} & nav
    assert "finance.recovery" not in widgets and "students.search" not in actions
    assert {"access.members", "settings.readiness", "settings.academic_year", "settings.structure", "audit.recent"} <= widgets
    nav, widgets, actions = view("CAISSIER")
    assert {"cash.today", "checkout.quick"} <= widgets and {"students.search", "checkout.new"} <= actions
    nav, widgets, actions = view("INTENDANT")
    assert "stewardship" in nav and "students.search" not in actions and "finance.recovery" not in widgets
    for code in ("PROMOTEUR", "GESTIONNAIRE", "RESPONSABLE_FINANCE"):
        assert "finance.recovery" in view(code)[1], code
    for code in roles:
        if roles[code]["level"] == "SCHOOL":
            assert view(code)[0], code
