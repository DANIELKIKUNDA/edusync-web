"""Contract tests: activation must reject an unknown school/year before writes."""
import pytest
from edusync.adapters.postgres_annual_policy_activation import activate_annual_policy

class NoYearConnection:
    def __init__(self):
        self.queries = []
    def execute(self, statement, params):
        self.queries.append(str(statement))
        class Result:
            def first(self):
                return None
        return Result()

def test_unknown_year_fails_without_policy_mutation():
    connection = NoYearConnection()
    with pytest.raises(ValueError, match="Academic year not found"):
        activate_annual_policy(connection, school_id="school", academic_year_id="year",
                               policy_id="policy", actor_id="actor")
    assert len(connection.queries) == 1
    assert "FOR UPDATE" in connection.queries[0]
