from datetime import date
from uuid import uuid4
import pytest

from edusync.modules.personnel.domain.models import AssignmentScope, StaffAssignment, StaffCategory, StaffFunction, StaffMember, StaffStatus


def member(**kw):
    base=dict(school_id=uuid4(),employee_no=' ag-001 ',last_name=' Kikunda ',first_name='Daniel',category=StaffCategory.ENSEIGNANT,hire_date=date(2024,9,1))
    base.update(kw);return StaffMember(**base)

def test_staff_normalizes_identity_and_preserves_category_separate_from_function():
    m=member();assert m.employee_no=='AG-001';assert m.last_name=='Kikunda';assert m.category==StaffCategory.ENSEIGNANT

def test_staff_requires_number_and_name():
    with pytest.raises(ValueError): member(employee_no=' ')
    with pytest.raises(ValueError): member(last_name=' ')

def test_staff_gender_is_constrained():
    with pytest.raises(ValueError): member(gender='Z')

def test_staff_left_requires_effective_date():
    with pytest.raises(ValueError): member(status=StaffStatus.LEFT)

def test_leave_requires_reason_and_date_after_hire():
    m=member()
    with pytest.raises(ValueError): m.leave(effective_date=date(2024,8,1),reason='départ')
    with pytest.raises(ValueError): m.leave(effective_date=date(2025,1,1),reason=' ')

def test_leave_preserves_identity_but_changes_lifecycle_state():
    m=member();m.leave(effective_date=date(2025,6,30),reason='Fin de service');assert m.status==StaffStatus.LEFT;assert m.exit_date==date(2025,6,30);assert m.employee_no=='AG-001'

def test_reactivate_only_left_staff_and_does_not_model_assignment_reopen():
    m=member()
    with pytest.raises(ValueError): m.reactivate()
    m.leave(effective_date=date(2025,6,30),reason='Départ');m.reactivate();assert m.status==StaffStatus.ACTIVE;assert m.exit_date is None

def test_function_normalization():
    f=StaffFunction(school_id=uuid4(),code=' directeur études ',label=' Directeur des études ');assert f.code=='DIRECTEUR_ÉTUDES';assert f.label=='Directeur des études'

def test_school_assignment_has_no_embedded_scope_value():
    a=StaffAssignment(school_id=uuid4(),staff_id=uuid4(),function_id=uuid4(),start_date=date.today())
    assert a.scope_type==AssignmentScope.SCHOOL
    with pytest.raises(ValueError): StaffAssignment(school_id=a.school_id,staff_id=a.staff_id,function_id=a.function_id,start_date=date.today(),scope_value='SECONDAIRE')

def test_section_assignment_requires_section_identity():
    with pytest.raises(ValueError): StaffAssignment(school_id=uuid4(),staff_id=uuid4(),function_id=uuid4(),start_date=date.today(),scope_type=AssignmentScope.SECTION,scope_value='SECONDAIRE')
    a=StaffAssignment(school_id=uuid4(),staff_id=uuid4(),function_id=uuid4(),start_date=date.today(),scope_type=AssignmentScope.SECTION,scope_value='SECONDAIRE',section_id=uuid4());assert a.scope_value=='SECONDAIRE'

def test_titulariat_is_explicit_and_separate():
    base=dict(school_id=uuid4(),staff_id=uuid4(),function_id=uuid4(),start_date=date.today())
    with pytest.raises(ValueError): StaffAssignment(**base,is_titular=True)
    cid=uuid4();a=StaffAssignment(**base,is_titular=True,titular_class_id=cid);assert a.is_titular and a.titular_class_id==cid

def test_assignment_end_requires_reason_and_valid_date():
    a=StaffAssignment(school_id=uuid4(),staff_id=uuid4(),function_id=uuid4(),start_date=date(2026,9,1))
    with pytest.raises(ValueError): a.end(effective_date=date(2026,8,31),reason='mutation')
    with pytest.raises(ValueError): a.end(effective_date=date(2026,9,2),reason=' ')
    a.end(effective_date=date(2026,9,2),reason='Réaffectation');assert a.end_date==date(2026,9,2)
