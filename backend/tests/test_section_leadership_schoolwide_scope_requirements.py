"""Explicit SCHOOL scope is required for unfiltered school-wide reads."""
from uuid import uuid4

import pytest
from fastapi import HTTPException

from edusync.modules.documents.application.object_store import school_wide_capabilities
from edusync.modules.schooling.api.router import _require_schoolwide_parity
from edusync.shared.application.context import ActorContext


def make_actor(scopes):
    return ActorContext(
        user_id=uuid4(), school_id=uuid4(), membership_id=uuid4(),
        permissions=frozenset({"families.read", "documents.open", "students.read"}),
        capability_scopes=tuple(scopes),
    )


@pytest.mark.parametrize("scopes", [
    (),
    (("families.read", "SECTION", "PRIMAIRE"),),
    (("families.read", "SECTION", "MATERNELLE"),),
    (("families.read", "SECTION", "SECONDAIRE"),),
])
def test_parity_denies_missing_or_section_scope(scopes):
    with pytest.raises(HTTPException) as exc:
        _require_schoolwide_parity(make_actor(scopes), "families.read")
    assert exc.value.status_code == 403


def test_parity_allows_only_explicit_school_scope():
    _require_schoolwide_parity(make_actor((("families.read", "SCHOOL", None),)), "families.read")


def test_archive_capabilities_fail_closed_without_scope():
    assert school_wide_capabilities(make_actor(())) == []


def test_archive_capabilities_never_upgrade_section_to_school():
    actor = make_actor((
        ("families.read", "SECTION", "PRIMAIRE"),
        ("documents.open", "SECTION", "PRIMAIRE"),
        ("students.read", "SECTION", "MATERNELLE"),
    ))
    assert school_wide_capabilities(actor) == []


def test_archive_capabilities_allow_only_explicit_school_grant():
    actor = make_actor((
        ("families.read", "SECTION", "PRIMAIRE"),
        ("documents.open", "SCHOOL", None),
    ))
    assert school_wide_capabilities(actor) == ["documents.open"]
