"""HTTP contract tests for scoped leadership roles.

These exercise FastAPI routing, dependency injection and response codes.
A separate PostgreSQL E2E suite is still required for database/RLS gates.
"""
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.modules.personnel.api.router import router
from edusync.shared.application.context import ActorContext


@pytest.fixture
def harness():
    app=FastAPI()
    app.include_router(router,prefix="/personnel")
    identity={"actor":None}
    @contextmanager
    def transaction(**kwargs):
        yield object()
    services=SimpleNamespace(tenant_db=SimpleNamespace(tenant_transaction=transaction))
    app.dependency_overrides[require_school_actor]=lambda:identity["actor"]
    app.dependency_overrides[get_services]=lambda:services
    with TestClient(app) as client:
        yield client,identity


def grant(capability,scope="SECTION",value="PRIMAIRE"):
    return ActorContext(
        user_id=uuid4(),school_id=uuid4(),membership_id=uuid4(),
        permissions=frozenset({capability}),
        capability_scopes=((capability,scope,value),),
    )


@pytest.mark.parametrize("endpoint", [
    "/personnel/history/events",
    "/personnel/12345678-1234-1234-1234-123456789012/children",
])
def test_section_cannot_read_unfiltered_global_personnel_data(harness,endpoint):
    client,state=harness
    capability="personnel.history.read" if endpoint.endswith("events") else "personnel.staff_children.read"
    state["actor"]=grant(capability)
    response=client.get(endpoint)
    assert response.status_code==403


def test_section_cannot_create_staff_without_assignment(harness):
    client,state=harness
    state["actor"]=grant("personnel.create")
    response=client.post("/personnel",headers={"Idempotency-Key":"scoped-no-assignment"},
                         json={"employee_no":"TEST-001","last_name":"TEST"})
    assert response.status_code==403


def test_section_cannot_change_staff_without_scoped_assignment(harness):
    client,state=harness
    state["actor"]=grant("personnel.update")
    # This contract checks the required concurrency and idempotency headers
    # before the database transaction is opened.
    response=client.put(
        "/personnel/12345678-1234-1234-1234-123456789012",
        headers={"Idempotency-Key":"test-update"},
        json={"employee_no":"TEST-001","last_name":"TEST"})
    assert response.status_code==428


def test_section_cannot_add_global_assignment(harness):
    client,state=harness
    state["actor"]=grant("personnel.assignments.add")
    response=client.post("/personnel/assignments",
        headers={"Idempotency-Key":"no-global"},
        json={"staff_id":str(uuid4()),"function_id":str(uuid4()),
              "scope_type":"SCHOOL"})
    assert response.status_code==403
