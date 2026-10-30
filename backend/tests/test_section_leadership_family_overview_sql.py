"""Family overview counts must use the caller's permitted pupil sections."""
from uuid import uuid4
from unittest.mock import MagicMock
import pytest
from edusync.adapters.postgres_schooling_parity import PostgresSchoolingParityRepository


@pytest.mark.parametrize("scopes,expected", [
    ((), None),
    ((("SECTION", "PRIMAIRE"),), ["PRIMAIRE"]),
    ((("SECTION", "MATERNELLE"),), ["MATERNELLE"]),
    ((("SECTION", "SECONDAIRE"),), ["SECONDAIRE"]),
    ((("SECTION", "PRIMAIRE"), ("SECTION", "MATERNELLE")), ["MATERNELLE", "PRIMAIRE"]),
    ((("SCHOOL", None),), "SCHOOL"),
])
def test_family_overview_all_counts_are_scoped(scopes, expected):
    conn = MagicMock()
    conn.execute.return_value.scalar_one_or_none.return_value = uuid4()
    conn.execute.return_value.scalar_one.return_value = 0
    repo = PostgresSchoolingParityRepository(conn)
    repo._large_min = lambda school_id, year: 5
    result = repo.family_overview_scoped(uuid4(), scopes=scopes)
    assert set(result) == {"families", "large_eligible", "beneficiaries",
                           "staff_children", "large_family_min_children"}
    assert result["large_family_min_children"] == 5
    for call in conn.execute.call_args_list[1:]:
        sql, params = str(call.args[0]), call.args[1]
        assert "s.school_id" in sql or "e.school_id" in sql or "sb.school_id" in sql or "l.school_id" in sql
        if expected is None:
            assert "AND FALSE" in sql
        elif expected == "SCHOOL":
            assert "AND TRUE" in sql
        else:
            assert params["scope_sections"] == expected
            assert "JOIN school_sections ss" in sql
