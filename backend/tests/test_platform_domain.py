import pytest
from edusync.modules.platform.domain.school import School, SchoolStatus

def test_school_code_normalized_and_status_transitions():
    s = School(name=" Collège Exemple ", code=" col-01 ")
    assert s.name == "Collège Exemple"
    assert s.code == "COL-01"
    assert s.status == SchoolStatus.ACTIVE
    s.suspend("Maintenance")
    assert s.status == SchoolStatus.SUSPENDED
    s.reactivate()
    assert s.status == SchoolStatus.ACTIVE

def test_suspend_requires_reason():
    s = School(name="A", code="AA")
    with pytest.raises(ValueError):
        s.suspend("")
