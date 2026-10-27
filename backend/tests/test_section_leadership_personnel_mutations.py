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
