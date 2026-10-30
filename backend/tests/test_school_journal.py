"""« Journal de l'établissement » (2026-10-28): the school audit trail finally has a screen. The read model returns the
actor's name, a domain filter covers several entity types at once, and every filter still requires audit.school.filter."""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.modules.audit.api.router import router
from edusync.shared.application.context import ActorContext


class _Conn:
    def __init__(self, rows=None):
        self.calls, self.rows = [], rows or []

    def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params or {}))
        return SimpleNamespace(all=lambda: self.rows)


ACTOR = uuid4()


class _Row(dict):
    @property
    def _mapping(self):
        return self


def _client(perms: set[str], rows=None):
    app = FastAPI(); app.include_router(router, prefix="/audit")
    conn, platform = _Conn(rows), _Conn([(ACTOR, "Grâce Mutombo")])

    @contextmanager
    def tx(**kwargs):
        yield conn

    @contextmanager
    def ptx():
        yield platform

    actor = ActorContext(user_id=uuid4(), school_id=uuid4(), membership_id=uuid4(), permissions=frozenset(perms))
    app.dependency_overrides[require_school_actor] = lambda: actor
    app.dependency_overrides[get_services] = lambda: SimpleNamespace(tenant_db=SimpleNamespace(tenant_transaction=tx),
                                                                     platform_db=SimpleNamespace(platform_transaction=ptx))
    client = TestClient(app); client.platform = platform
    return client, conn


def test_journal_lists_with_actor_name_without_filter_right():
    row = _Row(id=uuid4(), occurred_at="2026-10-28T10:00:00", actor_user_id=ACTOR, membership_id=None, action="RECORD_EXPENSE",
               entity_type="CashExpense", entity_id=uuid4(), source="API", result="SUCCESS", reason=None, correlation_id=None)
    client, conn = _client({"audit.school.read"}, rows=[row])
    r = client.get("/audit/events")
    assert r.status_code == 200 and r.json()["items"][0]["actor_name"] == "Grâce Mutombo"
    sql, _ = conn.calls[0]
    assert "e.school_id=:sid" in sql and "users" not in sql     # the tenant query never reads users (RLS: self only)
    psql, pparams = client.platform.calls[0]
    # names: platform connection, members of THIS school only, ids of the page only
    assert "JOIN school_memberships m ON m.user_id=u.id" in psql and "m.school_id=:sid" in psql and pparams["ids"] == [str(ACTOR)]


def test_domain_filter_needs_the_filter_right_and_binds_every_type():
    client, _ = _client({"audit.school.read"})
    assert client.get("/audit/events", params=[("entity_types", "FinancePayment")]).status_code == 403
    client, conn = _client({"audit.school.read", "audit.school.filter"})
    r = client.get("/audit/events", params=[("entity_types", "FinancePayment"), ("entity_types", "CashExpense")])
    assert r.status_code == 200
    sql, params = conn.calls[0]
    assert "e.entity_type = ANY(:ets)" in sql and params["ets"] == ["FinancePayment", "CashExpense"]


def test_entity_history_returns_actor_name_and_needs_its_right():
    client, _ = _client({"audit.school.read"})
    assert client.get(f"/audit/entities/FinancePayment/{uuid4()}").status_code == 403
    # the history right alone is not enough: the domain of the entity must be readable too (2026-10-30)
    client, _ = _client({"audit.entity.history.read"})
    assert client.get(f"/audit/entities/FinancePayment/{uuid4()}").status_code == 404
    client, conn = _client({"audit.entity.history.read", "finance.cash.read"})
    assert client.get(f"/audit/entities/FinancePayment/{uuid4()}").status_code == 200
    assert "users" not in conn.calls[0][0]
