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
    capability = "personnel.update"
    actor = ActorContext(
        user_id=uuid4(), school_id=uuid4(), membership_id=uuid4(),
        permissions=frozenset({capability, "personnel.read"}),
        capability_scopes=(
            (capability, "SECTION", "SECONDAIRE"),
            ("personnel.read", "SCHOOL", None),
        ),
    )
    with pytest.raises(HTTPException) as exc:
        _need(actor, capability)
    assert exc.value.status_code == 403


def test_missing_grant_denied_even_if_permission_present():
    with pytest.raises(HTTPException) as exc:
        _need(actor_for("personnel.create", []), "personnel.create")
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
