from decimal import Decimal
import pytest
from edusync.modules.finance_recovery.domain.exigibility_counters import RecoveryLine, recovery_counts

def test_zero_net_is_not_a_debtor_or_paid():
    assert recovery_counts([RecoveryLine("late", Decimal(0))]) == {
        "debtors": 0, "in_order": 0, "not_in_order": 0}

def test_multiple_charges_same_student_aggregate_before_classification():
    lines = [RecoveryLine("a", Decimal(100), Decimal(100)),
             RecoveryLine("a", Decimal(100), Decimal(0)),
             RecoveryLine("b", Decimal(0)),
             RecoveryLine("c", Decimal(50), Decimal(20), noncash=Decimal(30))]
    assert recovery_counts(lines) == {"debtors": 2, "in_order": 1, "not_in_order": 1}

def test_negative_rejected():
    with pytest.raises(ValueError):
        recovery_counts([RecoveryLine("a", Decimal(-1))])
