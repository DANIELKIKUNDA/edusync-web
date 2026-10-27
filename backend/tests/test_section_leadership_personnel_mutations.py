"""Prevent section grants from silently authorizing schoolwide personnel writes."""
from uuid import uuid4

import pytest
from fastapi import HTTPException

from edusync.modules.personnel.api.router import _need, _SCHOOLWIDE_PERSONNEL_MUTATIONS
from edusync.shared.application.context import ActorContext


def actor_for(capability, grants):
    return ActorContext(
        user_id=uuid4(), school_id=uuid4(), membership_id=uuid4(),
        permissions=frozenset({capability}),
        capability_scopes=tuple((capability, kind, value) for kind, value in grants),
    )


@pytest.mark.parametrize("capability", sorted(_SCHOOLWIDE_PERSONNEL_MUTATIONS))
@pytest.mark.parametrize("section", ["SECONDAIRE", "PRIMAIRE", "MATERNELLE"])
def test_section_only_personnel_mutation_is_rejected(capability, section):
    with pytest.raises(HTTPException) as exc:
        _need(actor_for(capability, [("SECTION", section)]), capability)
    assert exc.value.status_code == 403


@pytest.mark.parametrize("capability", sorted(_SCHOOLWIDE_PERSONNEL_MUTATIONS))
def test_explicit_schoolwide_grant_allows_mutation(capability):
    _need(actor_for(capability, [("SCHOOL", None)]), capability)


def test_unrelated_schoolwide_permission_does_not_widen_personnel():
    # The capability's own scope must be evaluated by its resource guard.
    from edusync.modules.personnel.api.router import _scopes
    capability = "personnel.update"
    actor = ActorContext(
        user_id=uuid4(), school_id=uuid4(), membership_id=uuid4(),
        permissions=frozenset({capability, "personnel.read"}),
        capability_scopes=(
            (capability, "SECTION", "SECONDAIRE"),
            ("personnel.read", "SCHOOL", None),
        ),
    )
    _need(actor, capability)
    assert _scopes(actor, capability) == (("SECTION", "SECONDAIRE"),)


def test_missing_grant_fails_closed_in_scoped_authorizer():
    from unittest.mock import Mock
    from edusync.modules.personnel.api.router import _authorize_staff_update
    actor = actor_for("personnel.update", [])
    with pytest.raises(HTTPException) as exc:
        _authorize_staff_update(Mock(), actor, uuid4())
    assert exc.value.status_code == 403


def test_section_staff_detail_excludes_global_access_and_family_data():
    from unittest.mock import Mock
    from edusync.adapters.postgres_personnel import PostgresPersonnelRepository
    conn = Mock()
    repo = PostgresPersonnelRepository(conn)
    repo._visible_staff_ids = lambda school_id, scopes: {staff_id}
    staff_id = uuid4()
    school_id = uuid4()
    row = Mock()
    row._mapping = {"id": staff_id, "school_id": school_id, "last_name": "TEST"}
    conn.execute.return_value.first.return_value = row
    repo.list_assignments = Mock(return_value=[{"scope_type": "SECTION", "scope_value": "PRIMAIRE"}])
    repo.status_history = Mock()
    repo.access_links = Mock()
    repo.staff_children = Mock()
    result = repo.get_staff(school_id, staff_id, scopes=(("SECTION", "PRIMAIRE"),))
    assert result["assignments"][0]["scope_value"] == "PRIMAIRE"
    assert result["history"] == []
    assert result["access_links"] == []
    assert result["staff_children"] == []
    repo.status_history.assert_not_called()
    repo.access_links.assert_not_called()
    repo.staff_children.assert_not_called()


def test_section_creator_requires_initial_assignment():
    from types import SimpleNamespace
    from fastapi import Response
    from edusync.modules.personnel.api.router import ScopedStaffCreate, create_staff
    user=SimpleNamespace(
        permissions=frozenset({"personnel.create"}),
        require=lambda capability: None,
        scopes_for=lambda capability: (("SECTION", "PRIMAIRE"),),
    )
    body=ScopedStaffCreate(employee_no="EMP-1",last_name="TEST")
    with pytest.raises(HTTPException) as exc:
        create_staff(body,Response(),idempotency_key="unique",actor=user,services=None)
    assert exc.value.status_code==403


def test_creation_initial_assignment_does_not_require_client_staff_id():
    from edusync.modules.personnel.api.router import ScopedStaffCreate
    section_id=uuid4()
    function_id=uuid4()
    request=ScopedStaffCreate.model_validate({
        "employee_no":"EMP-2","last_name":"TEST",
        "initial_assignment":{
            "function_id":str(function_id),
            "scope_type":"SECTION",
            "scope_value":"PRIMAIRE",
            "section_id":str(section_id),
        }
    })
    assert request.initial_assignment.function_id==function_id
    assert not hasattr(request.initial_assignment,"staff_id")
    assert request.initial_assignment.section_id==section_id
