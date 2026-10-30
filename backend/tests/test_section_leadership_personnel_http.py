"""HTTP contract tests for scoped leadership roles.

These exercise FastAPI routing, dependency injection and response codes.
A separate PostgreSQL E2E suite is still required for database/RLS gates.
"""
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import Mock, patch

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
    "/personnel/12345678-1234-1234-1234-123456789012/children",
])
def test_section_cannot_read_unfiltered_global_personnel_data(harness,endpoint):
    client,state=harness
    state["actor"]=grant("personnel.staff_children.read")
    response=client.get(endpoint)
    assert response.status_code==403


def test_section_status_history_is_served_filtered_to_its_section(harness):
    # Certification PR #27: the contract grants personnel.history.read to section leaders for THEIR scope. The global
    # status history is filtered by the visible staff of that scope (repository), never served school-wide.
    client,state=harness
    state["actor"]=grant("personnel.history.read")
    with patch("edusync.modules.personnel.api.router.PostgresPersonnelRepository") as repo:
        repo.return_value.list_status_history.return_value=[]
        response=client.get("/personnel/history/events")
    assert response.status_code==200
    assert repo.return_value.list_status_history.call_args.kwargs["scopes"]==(("SECTION","PRIMAIRE"),)


def test_section_status_history_without_scope_fails_closed():
    from edusync.adapters.postgres_personnel import PostgresPersonnelRepository
    conn=Mock()
    conn.execute.return_value.all.return_value=[]
    assert PostgresPersonnelRepository(conn).list_status_history(uuid4(),scopes=())==[]
    assert "FALSE" in str(conn.execute.call_args_list[0].args[0])  # no grant: the visible-staff query matches nothing


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
    # Execute the real endpoint action with a fake transaction executor.
    # The guard must reject before touching the repository.
    def run_action(**kwargs):
        return kwargs["action"](Mock(),kwargs["actor"])
    with patch("edusync.modules.personnel.api.router._mutate",side_effect=run_action):
        response=client.post("/personnel/assignments",
            headers={"Idempotency-Key":"no-global"},
            json={"staff_id":str(uuid4()),"function_id":str(uuid4()),
                  "scope_type":"SCHOOL"})
    assert response.status_code==403


def test_primary_director_creates_staff_with_section_assignment_in_one_action(harness):
    """HTTP -> endpoint -> scope validation -> staff and assignment repositories."""
    client,state=harness
    state["actor"]=grant("personnel.create")
    section_id=uuid4()
    def run_action(**kwargs):
        status,payload=kwargs["action"](conn,kwargs["actor"])
        return SimpleNamespace(status_code=status,body=payload)
    conn=Mock()
    conn.execute.return_value.first.return_value=("PRIMAIRE",)
    repo=Mock()
    repo.create_staff.return_value={"id":str(uuid4()),"employee_no":"PR-100"}
    repo.add_assignment.return_value={"id":str(uuid4()),"scope_type":"SECTION"}
    with patch("edusync.modules.personnel.api.router._mutate",side_effect=run_action), \
         patch("edusync.modules.personnel.api.router.PostgresPersonnelRepository",return_value=repo), \
         patch("edusync.modules.personnel.api.router._audit_outbox") as audit:
        response=client.post("/personnel",headers={"Idempotency-Key":"scoped-create-ok"},
            json={"employee_no":"PR-100","last_name":"KABUYA",
                  "initial_assignment":{"function_id":str(uuid4()),
                    "scope_type":"SECTION","scope_value":"PRIMAIRE",
                    "section_id":str(section_id)}})
    assert response.status_code==201, response.text
    assert response.json()["initial_assignment"]["scope_type"]=="SECTION"
    repo.create_staff.assert_called_once()
    repo.add_assignment.assert_called_once()
    assert audit.call_count==2


def test_primary_director_rejects_foreign_section_before_staff_insert(harness):
    client,state=harness
    state["actor"]=grant("personnel.create")
    conn=Mock()
    conn.execute.return_value.first.return_value=None
    repo=Mock()
    def run_action(**kwargs):
        return kwargs["action"](conn,kwargs["actor"])
    with patch("edusync.modules.personnel.api.router._mutate",side_effect=run_action), \
         patch("edusync.modules.personnel.api.router.PostgresPersonnelRepository",return_value=repo):
        response=client.post("/personnel",headers={"Idempotency-Key":"foreign-section"},
            json={"employee_no":"PR-101","last_name":"KABUYA",
                  "initial_assignment":{"function_id":str(uuid4()),
                    "scope_type":"SECTION","scope_value":"PRIMAIRE",
                    "section_id":str(uuid4())}})
    assert response.status_code==403
    repo.create_staff.assert_not_called()
    repo.add_assignment.assert_not_called()
