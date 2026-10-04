from datetime import date
from uuid import uuid4

import pytest

from edusync.modules.settings.domain.models import AcademicYear, AcademicYearStatus, compute_readiness


def year(status=AcademicYearStatus.PREPARED):
    return AcademicYear(
        school_id=uuid4(), code="2026-2027", label="2026-2027",
        start_date=date(2026, 9, 1), end_date=date(2027, 7, 31), status=status,
    )


def test_academic_year_lifecycle_is_explicit_and_no_closed_direct_activation():
    y=year(); y.activate(); assert y.status == AcademicYearStatus.ACTIVE
    y.close(); assert y.status == AcademicYearStatus.CLOSED
    with pytest.raises(ValueError): y.activate()
    y.reopen(); assert y.status == AcademicYearStatus.PREPARED
    y.activate(); y.close(); y.archive(); assert y.status == AcademicYearStatus.ARCHIVED
    y.reopen(); assert y.status == AcademicYearStatus.PREPARED


def test_readiness_is_progressive_not_global_lock():
    sid=uuid4()
    snap=compute_readiness(
        school_id=sid,has_identity=True,active_years=0,enabled_sections=0,enabled_classes=0,
        active_fee_types=0,active_tariffs=0,internal_notifications_enabled=True,external_sms_enabled=False,
    )
    assert snap.percent < 100
    by_code={x.code:x for x in snap.items}
    assert by_code['ACADEMIC_YEAR'].blocking_only_for == ('ENROLL_STUDENT','GENERATE_FEES')
    assert by_code['EXTERNAL_SMS'].state == 'NOT_APPLICABLE'
    assert by_code['IDENTITY'].state == 'READY'
