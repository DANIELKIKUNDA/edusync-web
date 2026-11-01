from unittest.mock import MagicMock
import pytest
from edusync.adapters.postgres_annual_policy_activation import activate_annual_policy

def test_missing_year_prevents_activation():
    db = MagicMock()
    db.execute.return_value.first.return_value = None
    with pytest.raises(ValueError, match="Academic year"):
        activate_annual_policy(db, school_id="s", academic_year_id="y",
                               policy_id="p", actor_id="a")
    assert db.execute.call_count == 1

def test_missing_draft_prevents_activation():
    db = MagicMock()
    db.execute.side_effect = [
        MagicMock(first=lambda: ("year",)),
        MagicMock(first=lambda: None),
    ]
    with pytest.raises(ValueError, match="Draft"):
        activate_annual_policy(db, school_id="s", academic_year_id="y",
                               policy_id="p", actor_id="a")
    assert db.execute.call_count == 2
