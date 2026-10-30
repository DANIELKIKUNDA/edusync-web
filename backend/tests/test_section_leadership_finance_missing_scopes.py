"""Finance report endpoints must never infer school-wide rights from missing scopes."""
from uuid import uuid4
import pytest
from fastapi import HTTPException
from edusync.modules.finance_reports.api.router import need
from edusync.shared.application.context import ActorContext


def actor(scopes):
    return ActorContext(user_id=uuid4(), school_id=uuid4(), membership_id=uuid4(),
                        permissions=frozenset({"finance.reports.history.read"}),
                        capability_scopes=tuple(scopes))


@pytest.mark.parametrize("scopes", [
    (),
    (("finance.reports.history.read", "SECTION", "PRIMAIRE"),),
    (("finance.reports.history.read", "SECTION", "MATERNELLE"),),
    (("finance.reports.history.read", "SECTION", "SECONDAIRE"),),
])
def test_finance_report_denies_missing_or_section_scope(scopes):
    with pytest.raises(HTTPException) as exc:
        need(actor(scopes), "finance.reports.history.read")
    assert exc.value.status_code == 403


def test_finance_report_accepts_explicit_school_scope():
    need(actor((("finance.reports.history.read", "SCHOOL", None),)), "finance.reports.history.read")
