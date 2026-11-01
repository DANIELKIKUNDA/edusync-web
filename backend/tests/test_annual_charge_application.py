from decimal import Decimal
import pytest
from edusync.modules.finance_fee_tracking.domain.annual_exigibility import Obligation, ObligationStatus
from edusync.modules.finance_fee_tracking.domain.annual_charge_application import plan_charge_application

def obligation(status, amount):
    return Obligation(status, Decimal("100"), Decimal(amount), Decimal("100"))

@pytest.mark.parametrize("status", [ObligationStatus.NOT_APPLICABLE, ObligationStatus.NOT_EXIGIBLE])
def test_no_charge_for_no_obligation(status):
    assert plan_charge_application(obligation(status, "0"), existing_charge=False).action == "SKIP"

def test_new_due_charge():
    result = plan_charge_application(obligation(ObligationStatus.DUE, "50"), existing_charge=False)
    assert (result.action, result.proposed_amount) == ("CREATE", Decimal("50"))

def test_existing_charge_kept_when_equal():
    result = plan_charge_application(obligation(ObligationStatus.DUE, "50"),
                                     existing_charge=True, existing_net_amount=Decimal("50"))
    assert result.action == "KEEP"

@pytest.mark.parametrize("paid", ["0", "25", "100"])
def test_existing_charge_mismatch_never_silently_updated(paid):
    result = plan_charge_application(obligation(ObligationStatus.NOT_APPLICABLE, "0"),
                                     existing_charge=True, existing_net_amount=Decimal("100"),
                                     paid_amount=Decimal(paid))
    assert result.action == "REVIEW_REQUIRED"

def test_existing_charge_lower_than_paid_rejected():
    with pytest.raises(ValueError):
        plan_charge_application(obligation(ObligationStatus.DUE, "10"),
                                existing_charge=True, existing_net_amount=Decimal("20"),
                                paid_amount=Decimal("30"))

def test_missing_existing_amount_rejected():
    with pytest.raises(ValueError):
        plan_charge_application(obligation(ObligationStatus.DUE, "10"), existing_charge=True)

def test_orphan_payment_rejected():
    with pytest.raises(ValueError):
        plan_charge_application(obligation(ObligationStatus.DUE, "10"), existing_charge=False,
                                paid_amount=Decimal("5"))
