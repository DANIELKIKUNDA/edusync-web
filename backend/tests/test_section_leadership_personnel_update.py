"""Scoped personnel mutations: shared staff must be denied (unit security gates)."""
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from edusync.modules.personnel.api.router import _authorize_staff_update


def actor(*scopes):
    return SimpleNamespace(school_id=uuid4(), permissions=frozenset({"personnel.update"}),
                           scopes_for=lambda capability: scopes)


def conn_for(*assignments):
    conn = Mock()
    conn.execute.return_value.first.return_value = (uuid4(),)
    conn.execute.return_value.all.return_value = list(assignments)
    return conn


def test_section_only_staff_can_be_edited():
    conn=conn_for(("SECTION","PRIMAIRE","PRIMAIRE",None))
    _authorize_staff_update(conn,actor(("SECTION","PRIMAIRE")),uuid4())
    assert conn.execute.call_count==2


def test_class_in_section_can_be_edited():
    _authorize_staff_update(
        conn_for(("CLASS","7A","SECONDAIRE","7A")),
        actor(("SECTION","SECONDAIRE")),uuid4())


def test_multiple_grants_allow_multi_section_staff():
    _authorize_staff_update(
        conn_for(("SECTION","PRIMAIRE","PRIMAIRE",None),
                 ("SECTION","MATERNELLE","MATERNELLE",None)),
        actor(("SECTION","PRIMAIRE"),("SECTION","MATERNELLE")),uuid4())


@pytest.mark.parametrize("assignments", [
    [("SECTION","PRIMAIRE","PRIMAIRE",None),("SECTION","SECONDAIRE","SECONDAIRE",None)],
    [("SECTION","PRIMAIRE","PRIMAIRE",None),("SCHOOL",None,None,None)],
    [],
])
def test_shared_global_or_unassigned_staff_cannot_be_edited(assignments):
    with pytest.raises(HTTPException) as exc:
        _authorize_staff_update(conn_for(*assignments),
                                actor(("SECTION","PRIMAIRE")),uuid4())
    assert exc.value.status_code==403


def test_class_grant_does_not_edit_entire_section():
    with pytest.raises(HTTPException) as exc:
        _authorize_staff_update(
            conn_for(("SECTION","PRIMAIRE","PRIMAIRE",None)),
            actor(("CLASS","1A")),uuid4())
    assert exc.value.status_code==403


def test_explicit_schoolwide_scope_needs_no_assignment_check():
    conn=conn_for()
    _authorize_staff_update(conn,actor(("SCHOOL",None)),uuid4())
    conn.execute.assert_not_called()
