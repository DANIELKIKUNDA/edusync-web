from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
from uuid import uuid4

from edusync.shared.application.context import ActorContext

ROUTER=Path('src/edusync/modules/personnel/api/router.py').read_text(encoding='utf-8')
REPO=Path('src/edusync/adapters/postgres_personnel.py').read_text(encoding='utf-8')


def test_capability_bound_scopes_do_not_borrow_unrelated_school_scope():
    a=ActorContext(user_id=uuid4(),school_id=uuid4(),membership_id=uuid4(),permissions=frozenset({'personnel.read','finance.read'}),capability_scopes=(('finance.read','SCHOOL',None),('personnel.read','SECTION','SECONDAIRE')))
    assert a.scope_allows('finance.read','SECTION','PRIMAIRE')
    assert a.scope_allows('personnel.read','SECTION','SECONDAIRE')
    assert not a.scope_allows('personnel.read','SECTION','PRIMAIRE')


def test_personnel_repository_filters_section_leader_to_its_sections_only():
    # Amended by PR #27 (section isolation): a SCHOOL staff assignment no longer makes the agent visible to a
    # section / class leader. Owner decision 2026-10-28 (PR #27): leaders see only agents assigned to their sections;
    # transversal agents (Gestionnaire, Caissier…) are never visible automatically.
    assert "clauses: list[str] = []" in REPO and "A school-wide staff assignment must not implicitly widen section access." in REPO
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
    # N3-F (Desktop staff_finance.py): the payroll deduction is a NON-CASH settlement — never a payment, a receipt
    # or a cash operation.
    assert 'staff_children.finance_mode' in ROUTER
    assert "_need(actor,'personnel.payroll_deduction.confirm')" in ROUTER
    assert 'record_payment' not in ROUTER
    repo=(ROOT/'backend/src/edusync/adapters/postgres_staff_finance.py').read_text(encoding='utf-8')
    for forbidden in ('INSERT INTO finance_payments','next_receipt_number','finance_cash_'):
        assert forbidden not in repo, forbidden
