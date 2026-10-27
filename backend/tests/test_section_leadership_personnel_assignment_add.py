"""Scoped assignment writes must check the target inside the transaction."""
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from edusync.modules.personnel.api.router import AssignmentCreate, _authorize_assignment_add
from edusync.modules.personnel.domain.models import AssignmentScope


def actor(scopes):
    return SimpleNamespace(
        school_id=uuid4(),
        scopes_for=lambda capability: scopes,
        permissions=frozenset({"personnel.assignments.add"}),
    )


def body(staff_id, **changes):
    values=dict(staff_id=staff_id,function_id=uuid4(),scope_type=AssignmentScope.SECTION,
                scope_value="PRIMAIRE",section_id=uuid4())
    values.update(changes)
    return AssignmentCreate(**values)


def verify(scopes, assignment, visible, rows=()):
    conn=Mock()
    conn.execute.return_value.first.side_effect=[(assignment.staff_id,),*list(rows)]
    with patch("edusync.modules.personnel.api.router.PostgresPersonnelRepository") as factory:
        factory.return_value._visible_staff_ids.return_value=visible
        _authorize_assignment_add(conn,actor(scopes),assignment)
    return conn


def test_section_can_assign_existing_visible_staff():
    staff=uuid4()
    conn=verify((("SECTION","PRIMAIRE"),),body(staff),{staff},[("PRIMAIRE",)])
    assert conn.execute.call_count==2


@pytest.mark.parametrize("scope", [("SECTION","SECONDAIRE"),("CLASS","7A")])
def test_other_section_or_class_cannot_assign(scope):
    staff=uuid4()
    with pytest.raises(HTTPException) as exc:
        verify((scope,),body(staff),{staff},[("PRIMAIRE",)])
    assert exc.value.status_code==403


def test_staff_not_visible_cannot_be_assigned():
    with pytest.raises(HTTPException) as exc:
        verify((("SECTION","PRIMAIRE"),),body(uuid4()),set())
    assert exc.value.status_code==403


def test_school_assignment_denied_for_section_grant():
    with pytest.raises(HTTPException) as exc:
        verify((("SECTION","PRIMAIRE"),),body(uuid4(),scope_type=AssignmentScope.SCHOOL,
               scope_value=None,section_id=None),set())
    assert exc.value.status_code==403


def test_primary_assignment_denied_for_section_grant():
    with pytest.raises(HTTPException) as exc:
        verify((("SECTION","PRIMAIRE"),),body(uuid4(),is_primary=True),set())
    assert exc.value.status_code==403


def test_dual_section_grant_can_assign_second_section():
    staff=uuid4()
    verify((("SECTION","PRIMAIRE"),("SECTION","MATERNELLE")),
           body(staff,scope_value="MATERNELLE"),{staff},[("MATERNELLE",)])


def test_class_grant_can_assign_exact_class():
    staff=uuid4()
    verify((("CLASS","7A"),),body(staff,scope_type=AssignmentScope.CLASS,
           scope_value="7A",class_id=uuid4(),section_id=None),{staff},
           [("7A","SECONDAIRE",uuid4())])



def test_missing_staff_is_rejected_before_visibility_query():
    staff=uuid4()
    conn=Mock()
    conn.execute.return_value.first.return_value=None
    with patch("edusync.modules.personnel.api.router.PostgresPersonnelRepository") as factory:
        with pytest.raises(HTTPException) as exc:
            _authorize_assignment_add(
                conn,actor((("SECTION","PRIMAIRE"),)),body(staff))
    assert exc.value.status_code==403
    factory.return_value._visible_staff_ids.assert_not_called()
