from decimal import Decimal
import pytest
from edusync.modules.finance_fee_tracking.domain.annual_policy_validation import validate_policy_rules

def rule(fee="tuition", bands=None, mode="NOT_APPLICABLE", prior=None):
    if bands is None:
        bands = [
            {"first_day": 1, "last_day": 15, "percent": "100"},
            {"first_day": 16, "last_day": 24, "percent": "50"},
            {"first_day": 25, "last_day": None, "percent": "0"},
        ]
    return {"fee_type_id": fee, "prior_mode": mode, "prior_percent": prior, "bands": bands}

def test_valid_rule():
    assert validate_policy_rules([rule()]) == 1

def test_two_fee_types():
    assert validate_policy_rules([rule(), rule("registration")]) == 2

@pytest.mark.parametrize("rules", [
    [],
    [rule(), rule()],
    [rule(bands=[{"first_day": 1, "last_day": 15, "percent": "100"}])],
    [rule(bands=[{"first_day": 1, "last_day": None, "percent": "101"}])],
    [rule(mode="CUSTOM")],
    [rule(mode="FULL", prior="50")],
])
def test_reject_invalid_policy(rules):
    with pytest.raises(ValueError):
        validate_policy_rules(rules)

def test_string_day_bounds():
    bands = [
        {"first_day": "1", "last_day": "15", "percent": "100"},
        {"first_day": "16", "last_day": "24", "percent": "50"},
        {"first_day": "25", "last_day": None, "percent": "0"},
    ]
    assert validate_policy_rules([rule(bands=bands)]) == 1
