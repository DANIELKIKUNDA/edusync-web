"""Historical arrears never disclose balances of a student outside section scope."""
from uuid import uuid4
from unittest.mock import MagicMock
import pytest
from edusync.adapters.postgres_schooling_parity import PostgresSchoolingParityRepository


@pytest.mark.parametrize("scopes,expected", [
    ((), None),
    ((("SECTION", "PRIMAIRE"),), "PRIMAIRE"),
    ((("SECTION", "MATERNELLE"),), "MATERNELLE"),
    ((("SECTION", "SECONDAIRE"),), "SECONDAIRE"),
    ((("SCHOOL", None),), "SCHOOL"),
])
def test_historical_arrears_query_respects_student_section(scopes, expected):
    conn = MagicMock()
    conn.execute.return_value.scalar_one_or_none.return_value = uuid4()
    conn.execute.return_value.mappings.return_value.all.return_value = []
    PostgresSchoolingParityRepository(conn).historical_arrears(uuid4(), uuid4(), scopes=scopes)
    statement, params = conn.execute.call_args.args
    sql = str(statement)
    assert "JOIN students s ON s.id=e.student_id" in sql
    assert "e.school_id=:s" in sql
    if expected is None:
        assert "AND FALSE" in sql
    elif expected == "SCHOOL":
        assert "AND TRUE" in sql
    else:
        assert params["scope_sections"] == [expected]
        assert "JOIN school_sections ss" in sql
