from datetime import date
from uuid import uuid4
import pytest

from edusync.modules.schooling.domain.models import Student, Family, ContactStatus, generate_family_label, normalized_phone


def test_student_birth_fields_are_optional_but_gender_is_required():
    s=Student(school_id=uuid4(),family_id=uuid4(),matricule='elv-00001',last_name='Kikunda',middle_name='Ngwej',first_name='Daniel',gender='M')
    assert s.birth_date is None
    assert s.birth_place is None
    assert s.display_name == 'Kikunda Ngwej Daniel'
    assert s.matricule == 'ELV-00001'

@pytest.mark.parametrize('field', ['last_name','middle_name','first_name'])
def test_student_core_name_parts_cannot_be_blank(field):
    kwargs=dict(school_id=uuid4(),family_id=uuid4(),matricule='ELV-1',last_name='A',middle_name='B',first_name='C',gender='M')
    kwargs[field]=' '
    with pytest.raises(ValueError): Student(**kwargs)


def test_family_label_is_generated_from_guardian_then_student():
    assert generate_family_label(guardian_name='  Espérance   Ilunga ', student_name='A B C')[0] == 'Foyer de Espérance Ilunga'
    assert generate_family_label(guardian_name=None, student_name='Kikunda Ngwej Daniel')[0] == 'Foyer Kikunda Ngwej Daniel'


def test_shared_phone_is_normalized_for_search_not_identity_merge():
    assert normalized_phone('099 123 45 67') == '+243991234567'
    assert normalized_phone('+243 991 234 567') == '+243991234567'


def test_student_gender_is_mandatory():
    with pytest.raises(ValueError,match='Sexe obligatoire'):
        Student(school_id=uuid4(),family_id=uuid4(),matricule='ELV-2',last_name='A',middle_name='B',first_name='C')
