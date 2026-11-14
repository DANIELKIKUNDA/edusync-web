"""Certification Responsable chargé des finances + Promoteur (2026-10-28).

Both roles READ, follow, print and export; neither collects money, opens a cash desk, enrolls, changes the settings,
manages people or writes into the accounts. Owner decision 2026-11-09: historical import is hidden by default and may
only be delegated explicitly for a planned migration (migration 0110). Computed from the canonical registry.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.shared.application.context import ActorContext

ROOT = Path(__file__).resolve().parents[2]
REG = json.loads((ROOT / "contracts/CAPABILITY_REGISTRY.json").read_text(encoding="utf-8"))
LIFE = {c["code"]: c["lifecycle"] for c in REG["capabilities"]}
ROLES = ("PROMOTEUR", "RESPONSABLE_FINANCE")
# Read / follow / print / export actions; anything else that ends like a verb is a mutation.
READ_ACTIONS = ("read", "search", "filter", "drilldown", "print", "print_pdf", "export", "export_xlsx", "open", "generate", "analyze")


def active(role: str) -> set[str]:
    return {c for c in REG["standard_roles"][role]["capabilities"] if LIFE.get(c) == "ACTIVE"}


@pytest.mark.parametrize("role", ROLES)
def test_history_import_is_hidden_from_daily_supervision_roles(role):
    caps = set(REG["standard_roles"][role]["capabilities"])
    assert "migration.finance_history.analyze" not in caps
    assert "migration.finance_history.execute" not in caps
    assert "migration.finance_history.analyze" not in REG["standard_roles"]["GESTIONNAIRE"]["capabilities"]
    assert "migration.finance_history.execute" not in REG["standard_roles"]["GESTIONNAIRE"]["capabilities"]
    # the specialised migration capability still exists and can be delegated explicitly.
    assert "migration.finance_history.execute" in REG["standard_roles"]["CAISSIER"]["capabilities"]
    sql = (ROOT / "backend/migrations/0110_finance_history_import_explicit_delegation.sql").read_text(encoding="utf-8")
    assert "DELETE FROM rbac_role_capabilities" in sql and "'migration.finance_history.analyze'" in sql


@pytest.mark.parametrize("role", ROLES)
def test_role_holds_no_mutation_capability(role):
    mutations = sorted(c for c in active(role) if c.rsplit(".", 1)[-1] not in READ_ACTIONS)
    assert mutations == [], f"{role} détient des droits de modification : {mutations}"


@pytest.mark.parametrize("role", ROLES)
def test_no_cash_desk_enrolment_settings_or_people_operation(role):
    forbidden = {"finance.checkout.collect", "finance.checkout.family.collect", "finance.cash.open", "finance.cash.close",
                 "finance.cash.day.close", "finance.cash.reopen", "finance.payments.reverse.own", "finance.payments.reverse.supervisor",
                 "finance.products.sale", "enrollments.create", "students.reenroll", "settings.school_identity.update",
                 "settings.tariffs.manage", "personnel.create", "personnel.update", "access.permissions.assign",
                 "communications.send.sms", "migration.students.execute"}
    assert not active(role) & forbidden, sorted(active(role) & forbidden)


def test_responsable_finance_keeps_its_control_reads():
    assert {"finance.cash.other.read", "finance.recovery.monthly.read", "finance.reports.periodic.generate",
            "finance.analysis.by_cashier.read", "audit.school.read", "students.account.read"} <= active("RESPONSABLE_FINANCE")


def test_option_selector_is_open_to_every_member_but_administration_list_is_not():
    """Student directory filters of a finance controller called /settings/options (settings.structure.read) -> 403."""
    from edusync.modules.settings.api.router import router
    app = FastAPI(); app.include_router(router, prefix="/settings")

    @contextmanager
    def tx(**kwargs):
        yield object()

    actor = ActorContext(user_id=uuid4(), school_id=uuid4(), membership_id=uuid4(), permissions=frozenset({"students.read"}))
    app.dependency_overrides[require_school_actor] = lambda: actor
    app.dependency_overrides[get_services] = lambda: SimpleNamespace(tenant_db=SimpleNamespace(tenant_transaction=tx))
    with patch("edusync.modules.settings.api.router.PostgresSettingsRepository") as repo, TestClient(app) as client:
        repo.return_value.list_options.return_value = [{"code": "CG", "label": "Commerciale", "enabled": True},
                                                       {"code": "OLD", "label": "Ancienne", "enabled": False}]
        r = client.get("/settings/options/selector")
        assert r.status_code == 200 and [o["code"] for o in r.json()] == ["CG"]
        assert client.get("/settings/options").status_code == 403


@pytest.mark.parametrize("role", ROLES + ("GESTIONNAIRE",))
def test_supervisors_get_cash_supervision_not_an_own_cash_receipts_card(role):
    from edusync.modules.access.application.projection import widgets
    ids = {w["id"] for w in widgets(set(REG["standard_roles"][role]["capabilities"]))}
    assert "cash.receipts" not in ids and "cash.supervision" in ids
    assert "cash.receipts" in {w["id"] for w in widgets(set(REG["standard_roles"]["CAISSIER"]["capabilities"]))}


def test_responsable_finance_reads_headcounts_total_and_by_section_owner_decision_2026_10_28():
    rf = active("RESPONSABLE_FINANCE")
    assert {"headcounts.read", "headcounts.by_section.read"} <= rf
    assert not rf & {"headcounts.movements.read", "headcounts.export", "headcounts.by_class.read"}   # read only, no detail
    sql = (ROOT / "backend/migrations/0098_responsable_finance_headcounts.sql").read_text(encoding="utf-8")
    assert "'headcounts.read','headcounts.by_section.read'" in sql and "RESPONSABLE_FINANCE" in sql
    from edusync.modules.access.application.projection import widgets
    assert "headcounts.summary" in {w["id"] for w in widgets(set(REG["standard_roles"]["RESPONSABLE_FINANCE"]["capabilities"]))}
