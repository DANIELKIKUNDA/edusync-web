from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from edusync.modules.iam.application.capability_registry import CapabilityRegistry
from edusync.modules.iam.domain.authorization import (
    AuthorizationContext,
    Role,
    RoleAssignment,
    RoleKind,
    RoleLevel,
    RoleStatus,
    ScopeRef,
    ScopeType,
    decide,
)

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "contracts" / "CAPABILITY_REGISTRY.json"
MIGRATION = ROOT / "backend" / "migrations" / "0006_capability_rbac_engine.sql"
OWNER_MIGRATION = ROOT / "backend" / "migrations" / "0007_owner_decision_manager_systeme.sql"
DECISIONS = ROOT / "contracts" / "POINT3B_ROLE_DECISIONS_FINAL.json"


def registry() -> CapabilityRegistry:
    return CapabilityRegistry.from_json(REGISTRY)


def test_registry_has_current_unique_capabilities():
    r = registry()
    assert len(r.capabilities) == 277  # N3-A (2026-10-15): reverse.supervisor, cash.day.close
    assert len(r.by_code()) == 277
    assert "platform.notifications.system.send" in r.by_code()


def test_registry_exposes_expected_domains():
    tree = registry().tree()
    assert "Centre financier" in tree
    assert "Intendance" in tree
    assert "Notifications & communications" in tree
    assert "Utilisateurs & accès" in tree
    assert "Atelier Pro" in tree


def test_print_and_export_are_first_class_capabilities():
    r = registry().by_code()
    assert "dashboard.school.print" in r
    assert "dashboard.school.export" in r
    assert "inventory.stock.sheet.print" in r
    assert "inventory.stock.export_xlsx" in r


def test_manager_system_owner_decision_is_locked_and_all_atelier_pro():
    payload = json.loads(DECISIONS.read_text(encoding="utf-8"))
    manager = next(x for x in payload["roles"] if x["code"] == "MANAGER_SYSTEME")
    expected = {c.code for c in registry().capabilities if c.domain == "Atelier Pro"}
    assert manager["level"] == "PLATFORM"
    assert manager["owner_decision"] == "APPROVED"
    assert set(manager["final_capabilities"]) == expected
    assert "platform.notifications.system.send" in expected
    assert len(expected) == 10


def test_standard_role_decisions_are_finalized_and_owner_approved():
    payload = json.loads(DECISIONS.read_text(encoding="utf-8"))
    assert payload["finalized"] is True
    assert all(role["owner_decision"] == "APPROVED" for role in payload["roles"])
    assert all(role["final_capabilities"] is not None for role in payload["roles"])


def test_draft_role_cannot_activate_without_owner_approval():
    role = Role("CAISSIER", "Caissier", RoleLevel.SCHOOL, RoleKind.SCHOOL_STANDARD)
    with pytest.raises(ValueError):
        role.activate()
    role.approve_by_owner()
    role.activate()
    assert role.status == RoleStatus.ACTIVE


def test_custom_school_role_requires_school_id():
    with pytest.raises(ValueError):
        Role("ASSISTANT", "Assistant", RoleLevel.SCHOOL, RoleKind.SCHOOL_CUSTOM)
    role = Role("ASSISTANT", "Assistant", RoleLevel.SCHOOL, RoleKind.SCHOOL_CUSTOM, school_id=uuid4())
    assert role.school_id is not None


def test_school_assignment_requires_membership_and_scope():
    role = Role("PREFET", "Préfet", RoleLevel.SCHOOL, RoleKind.SCHOOL_STANDARD)
    role.approve_by_owner(); role.activate()
    with pytest.raises(ValueError):
        RoleAssignment(uuid4(), role.id, RoleLevel.SCHOOL, school_id=uuid4(), membership_id=None,
                       scopes=(ScopeRef(ScopeType.SCHOOL),))


def test_union_of_roles_grants_capability_without_hardcoded_job_title():
    user = uuid4(); school = uuid4(); membership = uuid4()
    reader = Role("LECTURE", "Lecture", RoleLevel.SCHOOL, RoleKind.SCHOOL_STANDARD)
    reader.capability_codes.add("finance.views.read")
    reader.approve_by_owner(); reader.activate()
    cashier = Role("CAISSE", "Caisse", RoleLevel.SCHOOL, RoleKind.SCHOOL_STANDARD)
    cashier.capability_codes.add("finance.collect")
    cashier.approve_by_owner(); cashier.activate()
    assignments = (
        RoleAssignment(user, reader.id, RoleLevel.SCHOOL, school, membership, (ScopeRef(ScopeType.SCHOOL),)),
        RoleAssignment(user, cashier.id, RoleLevel.SCHOOL, school, membership, (ScopeRef(ScopeType.SCHOOL),)),
    )
    roles = {reader.id: reader, cashier.id: cashier}
    assert decide(AuthorizationContext(user, "finance.collect", school), assignments, roles).allowed
    assert decide(AuthorizationContext(user, "finance.views.read", school), assignments, roles).allowed
    assert not decide(AuthorizationContext(user, "settings.backups.restore", school), assignments, roles).allowed


def test_section_scope_does_not_leak_to_another_section():
    user = uuid4(); school = uuid4(); membership = uuid4()
    role = Role("DIRECTION", "Direction section", RoleLevel.SCHOOL, RoleKind.SCHOOL_STANDARD)
    role.capability_codes.add("students.read")
    role.approve_by_owner(); role.activate()
    assignment = RoleAssignment(user, role.id, RoleLevel.SCHOOL, school, membership,
                                (ScopeRef(ScopeType.SECTION, "PRIMAIRE"),))
    roles = {role.id: role}
    assert decide(AuthorizationContext(user, "students.read", school, ScopeRef(ScopeType.SECTION, "PRIMAIRE")), (assignment,), roles).allowed
    assert not decide(AuthorizationContext(user, "students.read", school, ScopeRef(ScopeType.SECTION, "SECONDAIRE")), (assignment,), roles).allowed


def test_platform_role_does_not_grant_school_business_access():
    user = uuid4(); school = uuid4()
    role = Role("MANAGER_SYSTEME", "Manager système", RoleLevel.PLATFORM, RoleKind.PLATFORM_STANDARD)
    role.capability_codes.add("platform.schools.create")
    role.approve_by_owner(); role.activate()
    assignment = RoleAssignment(user, role.id, RoleLevel.PLATFORM, scopes=(ScopeRef(ScopeType.PLATFORM),))
    roles = {role.id: role}
    assert decide(AuthorizationContext(user, "platform.schools.create"), (assignment,), roles).allowed
    assert not decide(AuthorizationContext(user, "students.read", school), (assignment,), roles).allowed


def test_migration_contains_industrial_rbac_structures_and_rls():
    sql = MIGRATION.read_text(encoding="utf-8")
    for token in (
        "CREATE TABLE IF NOT EXISTS capability_catalog",
        "CREATE TABLE IF NOT EXISTS rbac_roles",
        "CREATE TABLE IF NOT EXISTS rbac_role_capabilities",
        "CREATE TABLE IF NOT EXISTS rbac_assignments",
        "CREATE TABLE IF NOT EXISTS rbac_assignment_scopes",
        "CREATE TABLE IF NOT EXISTS rbac_exception_grants",
        "FORCE ROW LEVEL SECURITY",
        "validate_rbac_assignment",
    ):
        assert token in sql


def test_migration_seeds_258_capabilities_and_keeps_manager_draft():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert sql.count("INSERT INTO capability_catalog(") == 258
    assert "'MANAGER_SYSTEME'" in sql
    assert "'DRAFT'" in sql
    assert "must be ACTIVE before assignment" in sql

def test_owner_migration_activates_manager_and_grants_system_notifications():
    sql = OWNER_MIGRATION.read_text(encoding="utf-8")
    assert "platform.notifications.system.send" in sql
    assert "status='OWNER_APPROVED'" in sql
    assert "status='ACTIVE'" in sql
    assert "c.domain_name='Atelier Pro'" in sql


def test_admin_system_school_v1_is_technical_not_business_operator():
    payload = json.loads(DECISIONS.read_text(encoding="utf-8"))
    admin = next(x for x in payload["roles"] if x["code"] == "ADMIN_SYSTEME_ECOLE")
    caps = set(admin["final_capabilities"])
    assert admin["owner_decision"] == "APPROVED"
    assert len(caps) == 88  # + finance.anticipation_plans.manage/read (G-PLAN-1, 2026-10-15)
    assert "access.roles.manage" in caps
    assert "settings.backups.restore" in caps
    assert "sync.conflicts.resolve" in caps
    assert "audit.school.export" in caps
    assert "notifications.internal.configure" in caps
    assert "finance.checkout.collect" not in caps
    assert "finance.payments.reverse" not in caps
    assert "students.create" not in caps
    assert "inventory.stock.issue" not in caps
    assert "communications.sms.bulk_send" not in caps
    assert "sync.finance.reconcile" not in caps

