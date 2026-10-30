"""Reserve of the three-role handoff (2026-10-30): GET /audit/entities/{type}/{id} checked the capability and the school but
not the domain nor the SECTION scope of the entity — a Secondaire-only actor could read old_json / new_json of a primary
pupil, a payment or a member account. Reproduced here with HTTP calls; the route now answers 404 outside domain/scope."""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.modules.audit.api.router import router
from edusync.shared.application.context import ActorContext

SECONDARY_PUPIL, PRIMARY_PUPIL = uuid4(), uuid4()


class _Conn:
    """Fake tenant connection: the scope query answers « in scope » only for SECONDARY_PUPIL in section SECONDAIRE."""
    def __init__(self):
        self.calls = []

    def execute(self, stmt, params=None):
        sql, params = str(stmt), params or {}
        self.calls.append((sql, params))
        if "FROM audit_events" in sql:
            return SimpleNamespace(all=lambda: [], first=lambda: None)
        hit = params.get("eid") == str(SECONDARY_PUPIL) and "SECONDAIRE" in params.get("secs", [])
        return SimpleNamespace(first=lambda: (1,) if hit else None, all=lambda: [])


def _client(perms: dict[str, list[tuple[str, str | None]]]):
    app = FastAPI(); app.include_router(router, prefix="/audit")
    conn = _Conn()

    @contextmanager
    def tx(**kwargs):
        yield conn

    actor = ActorContext(user_id=uuid4(), school_id=uuid4(), membership_id=uuid4(), permissions=frozenset(perms),
                         capability_scopes=tuple((cap, t, v) for cap, scopes in perms.items() for t, v in scopes))
    app.dependency_overrides[require_school_actor] = lambda: actor
    app.dependency_overrides[get_services] = lambda: SimpleNamespace(tenant_db=SimpleNamespace(tenant_transaction=tx))
    return TestClient(app), conn


SEC = [("SECTION", "SECONDAIRE")]
DIRECTEUR = {"audit.entity.history.read": SEC, "students.read": SEC, "families.read": SEC, "personnel.read": SEC}
INTENDANT = {"audit.entity.history.read": [("SCHOOL", None)], "inventory.stock.read": [("SCHOOL", None)], "personnel.read": [("SCHOOL", None)]}


def test_secondary_director_reads_the_history_of_a_secondary_pupil():
    client, conn = _client(DIRECTEUR)
    assert client.get(f"/audit/entities/Student/{SECONDARY_PUPIL}").status_code == 200
    assert any("FROM audit_events" in sql for sql, _ in conn.calls)


@pytest.mark.parametrize("entity_type,entity_id", [
    ("Student", PRIMARY_PUPIL),          # another section
    ("FinancePayment", uuid4()),         # finance: no finance read right, and not section data
    ("school_membership", uuid4()),      # access accounts
    ("SchoolClass", uuid4()),            # school-level record, outside a section-only scope
    ("UserSecurity", uuid4()),           # personal security record: never
    ("UnknownThing", uuid4()),
])
def test_secondary_director_cannot_read_other_sections_or_domains(entity_type, entity_id):
    client, conn = _client(DIRECTEUR)
    r = client.get(f"/audit/entities/{entity_type}/{entity_id}")
    assert r.status_code == 404
    assert not any("FROM audit_events" in sql for sql, _ in conn.calls)   # the old/new values are never even read


def test_intendant_reads_stock_history_but_not_payments():
    client, _ = _client(INTENDANT)
    assert client.get(f"/audit/entities/inventory_item/{uuid4()}").status_code == 200
    assert client.get(f"/audit/entities/FinancePayment/{uuid4()}").status_code == 404
    assert client.get(f"/audit/entities/Student/{uuid4()}").status_code == 404     # no students.read


def test_history_right_still_required():
    client, _ = _client({"students.read": [("SCHOOL", None)]})
    assert client.get(f"/audit/entities/Student/{SECONDARY_PUPIL}").status_code == 403


def test_scope_queries_are_tenant_bound():
    from edusync.modules.audit.api.router import _SCOPED_SQL
    for kind, sql in _SCOPED_SQL.items():
        assert ":sid" in sql and "school_id" in sql, kind
    assert "y.status='ACTIVE'" in _SCOPED_SQL["student"]
