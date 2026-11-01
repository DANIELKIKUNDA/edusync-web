from unittest.mock import Mock
import pytest
from edusync.adapters.postgres_annual_policy_activation import activate_annual_policy


def test_activation_rejects_missing_year_without_writes():
    connection = Mock()
    connection.execute.return_value.first.return_value = None
    with pytest.raises(ValueError, match="Academic year"):
        activate_annual_policy(connection, school_id="school", academic_year_id="year",
                               policy_id="policy", actor_id="actor")
    assert connection.execute.call_count == 1


def test_activation_rejects_missing_draft_without_writes():
    connection = Mock()
    connection.execute.side_effect = [
        Mock(first=Mock(return_value=("year",))),
        Mock(first=Mock(return_value=None)),
    ]
    with pytest.raises(ValueError, match="Draft policy"):
        activate_annual_policy(connection, school_id="school", academic_year_id="year",
                               policy_id="policy", actor_id="actor")
    assert connection.execute.call_count == 2


def test_activation_rejects_empty_rules_before_update():
    connection = Mock()
    connection.execute.side_effect = [
        Mock(first=Mock(return_value=("year",))),
        Mock(first=Mock(return_value=("draft",))),
        Mock(mappings=Mock(return_value=Mock(all=Mock(return_value=[])))),
    ]
    with pytest.raises(ValueError, match="No fee rules"):
        activate_annual_policy(connection, school_id="school", academic_year_id="year",
                               policy_id="policy", actor_id="actor")
    assert connection.execute.call_count == 3
