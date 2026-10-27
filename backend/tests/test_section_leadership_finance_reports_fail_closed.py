"""Finance reports must not turn section-limited permissions into school-wide SQL."""
from uuid import uuid4

import pytest
from fastapi import HTTPException

from edusync.modules.finance_reports.api.router import need
from edusync.shared.application.context import ActorContext


@pytest.mark.parametrize("capability", [
    "finance.reports.periodic.generate",
    "finance.reports.history.read",
    "finance.analysis.by_fee.read",
    "finance.recovery.monthly.read",
    "students.account.read",
])
@pytest.mark.parametrize("section", ["SECONDAIRE", "PRIMAIRE", "MATERNELLE"])
def test_section_limited_finance_report_denied_before_schoolwide_query(capability, section):
    actor = ActorContext(
        user_id=uuid4(), school_id=uuid4(), membership_id=uuid4(),
        permissions=frozenset({capability}),
        capability_scopes=((capability, "SECTION", section),),
    )
    with pytest.raises(HTTPException) as exc:
        need(actor, capability)
    assert exc.value.status_code == 403
    assert "périmètre de section" in str(exc.value.detail)


def test_schoolwide_finance_grant_remains_available():
    capability = "finance.reports.periodic.generate"
    actor = ActorContext(
        user_id=uuid4(), school_id=uuid4(), membership_id=uuid4(),
        permissions=frozenset({capability}),
        capability_scopes=((capability, "SCHOOL", None),),
    )
    need(actor, capability)


def test_unrelated_schoolwide_capability_cannot_widen_finance():
    capability = "finance.analysis.by_fee.read"
    actor = ActorContext(
        user_id=uuid4(), school_id=uuid4(), membership_id=uuid4(),
        permissions=frozenset({capability, "personnel.read"}),
        capability_scopes=(
            (capability, "SECTION", "SECONDAIRE"),
            ("personnel.read", "SCHOOL", None),
        ),
    )
    with pytest.raises(HTTPException) as exc:
        need(actor, capability)
    assert exc.value.status_code == 403


def test_missing_capability_remains_forbidden():
    actor = ActorContext(
        user_id=uuid4(), school_id=uuid4(), membership_id=uuid4(),
        permissions=frozenset(),
    )
    with pytest.raises(HTTPException) as exc:
        need(actor, "finance.reports.periodic.generate")
    assert exc.value.status_code == 403
