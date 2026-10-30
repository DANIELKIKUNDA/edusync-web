"""Runtime route tests: real school leadership endpoints with fake tenant transaction.

The real route executes its authorization/scope checks; the repository is
instrumented to ensure forbidden mutations are never reached.
"""
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from edusync.modules.schooling.api import router as schooling
from edusync.shared.application.context import ActorContext


class FakeRepo:
    instances = []
    def __init__(self, conn):
        self.conn = conn
        self.mutations = []
        FakeRepo.instances.append(self)

    def get_student(self, school_id, student_id, *, scopes):
        self.conn.seen_scopes = scopes
        if scopes != (("SECTION", self.conn.allowed_section),):
            return None
        if self.conn.student_section != self.conn.allowed_section:
            return None
        return {"id": student_id, "enrollments": [{"class_id": uuid4()}]}

    def class_info(self, school_id, class_id):
        return {"id": class_id, "section_code": self.conn.target_section, "code": "TEST"}

    def change_class(self, *args, **kwargs):
        self.mutations.append("class")
        return {"id": args[1]}

    def change_status(self, *args, **kwargs):
        self.mutations.append("status")
        return {"id": args[1]}


class FakeTransaction:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *_):
        return False


class FakeTenantDb:
    def __init__(self, conn):
        self.conn = conn

    def tenant_transaction(self, *, school_id, user_id):
        return FakeTransaction(self.conn)


def actor(section, capability):
    return ActorContext(
        user_id=uuid4(), school_id=uuid4(), membership_id=uuid4(),
        permissions=frozenset({capability}),
        capability_scopes=((capability, "SECTION", section),),
    )


@pytest.fixture
def route_fakes(monkeypatch):
    FakeRepo.instances.clear()
    monkeypatch.setattr(schooling, "PostgresSchoolingRepository", FakeRepo)
    monkeypatch.setattr(schooling, "_audit_outbox", lambda *a, **k: None)

    # Execute the actual route's action within a fake tenant transaction,
    # without requiring an external database or outbox.
    def mutate(*, services, actor, key, operation, payload, action):
        with services.tenant_db.tenant_transaction(
            school_id=actor.school_id, user_id=actor.user_id
        ) as conn:
            status, body = action(conn, actor)
            return SimpleNamespace(status_code=status, body=body)

    monkeypatch.setattr(schooling, "_mutate", mutate)


@pytest.mark.parametrize("event,capability", [
    ("ABANDON", "students.lifecycle.abandon"),
    ("SUSPEND", "students.lifecycle.suspend"),
    ("TRANSFER", "students.lifecycle.transfer"),
    ("REINTEGRATE", "students.lifecycle.reintegrate"),
])
def test_lifecycle_denies_student_in_foreign_section_without_mutation(
    route_fakes, event, capability,
):
    conn = SimpleNamespace(
        allowed_section="SECONDAIRE", student_section="PRIMAIRE",
        target_section="SECONDAIRE",
    )
    services = SimpleNamespace(tenant_db=FakeTenantDb(conn))
    with pytest.raises(HTTPException) as err:
        schooling._lifecycle(
            capability, event, uuid4(),
            schooling.LifecycleBody(effective_date=date(2026, 10, 27), reason="Test de périmètre"),
            "1", "section-test-" + event, actor("SECONDAIRE", capability), services,
        )
    assert err.value.status_code == 404
    assert FakeRepo.instances[-1].mutations == []


def test_class_change_denies_target_in_foreign_section_without_mutation(route_fakes):
    conn = SimpleNamespace(
        allowed_section="SECONDAIRE", student_section="SECONDAIRE",
        target_section="PRIMAIRE",
    )
    services = SimpleNamespace(tenant_db=FakeTenantDb(conn))
    with pytest.raises(HTTPException) as err:
        schooling.class_change(
            uuid4(),
            schooling.ClassChangeBody(class_id=uuid4(), reason="Test de périmètre"),
            "section-class-change",
            actor("SECONDAIRE", "students.class.change"),
            services,
        )
    assert err.value.status_code == 403
    assert FakeRepo.instances[-1].mutations == []


def test_class_change_denies_source_in_foreign_section_without_mutation(route_fakes):
    conn = SimpleNamespace(
        allowed_section="SECONDAIRE", student_section="PRIMAIRE",
        target_section="SECONDAIRE",
    )
    services = SimpleNamespace(tenant_db=FakeTenantDb(conn))
    with pytest.raises(HTTPException) as err:
        schooling.class_change(
            uuid4(),
            schooling.ClassChangeBody(class_id=uuid4(), reason="Test de périmètre"),
            "section-class-source",
            actor("SECONDAIRE", "students.class.change"),
            services,
        )
    assert err.value.status_code == 404
    assert FakeRepo.instances[-1].mutations == []
