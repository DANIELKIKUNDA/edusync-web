from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FINAL = ROOT / "contracts" / "POINT3B_ROLE_DECISIONS_FINAL.json"
REGISTRY = ROOT / "contracts" / "CAPABILITY_REGISTRY.json"
MIGRATION = ROOT / "backend" / "migrations" / "0008_owner_approved_school_roles.sql"
MIGRATION_09 = ROOT / "backend" / "migrations" / "0009_secondary_leadership_roles.sql"


def payload():
    return json.loads(FINAL.read_text(encoding="utf-8"))


def role(code: str):
    return next(r for r in payload()["roles"] if r["code"] == code)


def caps(code: str):
    return set(role(code)["final_capabilities"])


def test_all_standard_roles_are_owner_approved_and_finalized():
    p = payload()
    assert p["finalized"] is True
    assert len(p["roles"]) == 12
    assert all(r["owner_decision"] == "APPROVED" for r in p["roles"])
    assert all(r["status"] == "LOCKED_OWNER_APPROVED" for r in p["roles"])


def test_all_grants_exist_in_capability_registry():
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    known = {c["code"] for c in reg["capabilities"]}
    for r in payload()["roles"]:
        assert set(r["final_capabilities"]) <= known


def test_promoteur_is_governance_reader_not_operator_or_parent_sender():
    c = caps("PROMOTEUR")
    assert "finance.dashboard.read" in c
    assert "inventory.stock.read" in c
    assert "students.read" in c
    assert "finance.checkout.collect" not in c
    assert "students.identity.update" not in c
    assert "inventory.stock.issue" not in c
    assert "communications.sms.send" not in c
    assert "communications.send.all_parents" not in c


def test_gestionnaire_does_not_inherit_system_configuration_or_daily_execution():
    c = caps("GESTIONNAIRE")
    assert len(c) == 104
    for required in (
        "dashboard.school.read", "audit.school.read", "personnel.summary.read",
        "finance.cash.other.read", "finance.reports.history.read", "documents.history.read",
    ):
        assert required in c
    for forbidden in (
        "settings.tariffs.manage", "access.permissions.assign", "finance.checkout.collect",
        "personnel.create", "personnel.update", "personnel.status.change", "personnel.exit",
        "communications.sms.send", "communications.send.all_parents",
        "finance.cash.open", "finance.cash.expense.create", "finance.decisions.create",
    ):
        assert forbidden not in c


def test_chief_section_roles_are_identical_and_include_parent_communications_and_transfer():
    p = caps("PREFET_ETUDES")
    d = caps("DIRECTION_SECTION")
    assert p == d
    for required in (
        "students.lifecycle.abandon", "students.lifecycle.transfer", "students.lifecycle.reintegrate",
        "personnel.read", "communications.send.individual", "communications.send.class",
        "communications.send.section", "communications.sms.send", "communications.sms.bulk_send",
    ):
        assert required in p
    assert "communications.send.all_parents" not in p
    assert "finance.checkout.collect" not in p


def test_cashier_is_operational_but_cannot_see_other_cash_detail_or_transfer_student():
    c = caps("CAISSIER")
    for required in (
        "enrollments.create", "enrollments.reenroll", "finance.checkout.collect", "finance.checkout.offline_cash",
        "finance.cash.open", "finance.cash.close", "finance.payments.reverse", "students.identity.update",
        "students.lifecycle.abandon", "sync.finance.arm", "sync.finance.reconcile",
    ):
        assert required in c
    assert "finance.cash.other.read" not in c
    assert "finance.analysis.by_cashier.read" not in c
    assert "students.lifecycle.transfer" not in c
    assert "students.lifecycle.reintegrate" not in c
    assert "settings.tariffs.manage" not in c


def test_secretariat_is_optional_minimal_without_finance():
    c = caps("SECRETARIAT")
    assert "communications.compose" in c
    assert "documents.print" in c
    assert not any(x.startswith("finance.") for x in c)


def test_intendant_has_full_inventory_domain_but_no_finance():
    c = caps("INTENDANT")
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    inventory = {x["code"] for x in reg["capabilities"] if x["code"].startswith("inventory.") and x.get("source_status") != "MERGED_2026_10_23"}
    assert inventory <= c
    assert not any(x.startswith("finance.") for x in c)


def test_finance_controller_is_supervisory_not_cash_operator():
    c = caps("RESPONSABLE_FINANCE")
    assert "finance.cash.other.read" in c
    assert "finance.analysis.by_cashier.read" in c
    assert "finance.reports.periodic.export_xlsx" in c
    assert "finance.checkout.collect" not in c
    assert "finance.cash.open" not in c
    assert "finance.payments.reverse" not in c


def test_admin_system_school_is_locked_technical_role():
    c = caps("ADMIN_SYSTEME_ECOLE")
    assert "access.roles.manage" in c
    assert "settings.backups.restore" in c
    assert "finance.checkout.collect" not in c
    assert "inventory.stock.issue" not in c


def test_assistant_promoteur_is_blueprint_not_hardcoded_standard_role():
    p = payload()
    assert all(r["code"] != "ASSISTANT_PROMOTEUR" for r in p["roles"])
    bp = next(x for x in p["custom_role_blueprints"] if x["code"] == "ASSISTANT_PROMOTEUR")
    assert bp["kind"] == "SCHOOL_CUSTOM"


def test_owner_approved_migration_seeds_all_school_standard_roles():
    sql = MIGRATION.read_text(encoding="utf-8")
    for code in (
        "ADMIN_SYSTEME_ECOLE","PROMOTEUR","GESTIONNAIRE","RESPONSABLE_FINANCE","PREFET_ETUDES",
        "DIRECTION_SECTION","CAISSIER","SECRETARIAT","INTENDANT",
    ):
        assert code in sql
    assert "ASSISTANT_PROMOTEUR" in sql and "SCHOOL_CUSTOM" in sql
    assert "DELETE FROM rbac_role_capabilities" in sql
    sql9 = MIGRATION_09.read_text(encoding="utf-8")
    assert "DIRECTEUR_ETUDES" in sql9
    assert "DIRECTEUR_DISCIPLINE" in sql9
