"""Legacy schooling parity reads cannot silently widen SECTION permissions."""
from uuid import uuid4

import pytest
from fastapi import HTTPException

from edusync.modules.schooling.api import router as schooling
from edusync.shared.application.context import ActorContext


def actor(capability, section):
    return ActorContext(
        user_id=uuid4(), school_id=uuid4(), membership_id=uuid4(),
        permissions=frozenset({capability}),
        capability_scopes=((capability, "SECTION", section),),
    )


@pytest.mark.parametrize("capability", [
    "students.read", "students.account.read", "families.read",
])
@pytest.mark.parametrize("section", ["SECONDAIRE", "PRIMAIRE", "MATERNELLE"])
def test_unscoped_parity_reader_denies_section_permission(capability, section):
    with pytest.raises(HTTPException) as exc:
        schooling._require_schoolwide_parity(actor(capability, section), capability)
    assert exc.value.status_code == 403


@pytest.mark.parametrize("capability", [
    "students.read", "students.account.read", "families.read",
])
def test_school_grant_can_read_legacy_parity(capability):
    a = ActorContext(
        user_id=uuid4(), school_id=uuid4(), membership_id=uuid4(),
        permissions=frozenset({capability}),
        capability_scopes=((capability, "SCHOOL", None),),
    )
    schooling._require_schoolwide_parity(a, capability)


def test_other_school_capability_does_not_expand_family_read():
    a = ActorContext(
        user_id=uuid4(), school_id=uuid4(), membership_id=uuid4(),
        permissions=frozenset({"families.read", "personnel.read"}),
        capability_scopes=(
            ("families.read", "SECTION", "SECONDAIRE"),
            ("personnel.read", "SCHOOL", None),
        ),
    )
    with pytest.raises(HTTPException) as exc:
        schooling._require_schoolwide_parity(a, "families.read")
    assert exc.value.status_code == 403
