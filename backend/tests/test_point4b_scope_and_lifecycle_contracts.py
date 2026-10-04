from pathlib import Path
from uuid import uuid4

from edusync.shared.application.context import ActorContext

ROUTER=Path('src/edusync/modules/personnel/api/router.py').read_text(encoding='utf-8')
REPO=Path('src/edusync/adapters/postgres_personnel.py').read_text(encoding='utf-8')


def test_capability_bound_scopes_do_not_borrow_unrelated_school_scope():
    a=ActorContext(user_id=uuid4(),school_id=uuid4(),membership_id=uuid4(),permissions=frozenset({'personnel.read','finance.read'}),capability_scopes=(('finance.read','SCHOOL',None),('personnel.read','SECTION','SECONDAIRE')))
    assert a.scope_allows('finance.read','SECTION','PRIMAIRE')
    assert a.scope_allows('personnel.read','SECTION','SECONDAIRE')
    assert not a.scope_allows('personnel.read','SECTION','PRIMAIRE')


def test_personnel_repository_includes_schoolwide_assignment_for_section_leader_but_filters_other_sections():
    assert "sa.scope_type='SCHOOL'" in REPO
    assert "upper(sa.scope_value) IN :scope_sections" in REPO
    assert 'school_classes sc JOIN school_sections ss' in REPO


def test_agent_exit_closes_assignments_disables_school_membership_and_keeps_user_global_account():
    assert "UPDATE staff_assignments SET end_date" in REPO
    assert "UPDATE school_memberships SET active=false" in REPO
    assert "UPDATE users SET active=false" not in REPO
    assert "INSERT INTO staff_status_history" in REPO


def test_reactivation_does_not_silently_reopen_old_assignments_or_membership():
    segment=REPO.split('def reactivate_staff',1)[1].split('def status_history',1)[0]
    assert "status='ACTIVE'" in segment
    assert 'UPDATE staff_assignments' not in segment
    assert 'UPDATE school_memberships' not in segment


def test_api_finance_payroll_confirmation_is_not_faked_inside_personnel():
    assert 'staff_children.finance_mode' in ROUTER
    assert 'payroll_deduction.confirm' not in ROUTER
    assert 'record_payment' not in ROUTER
