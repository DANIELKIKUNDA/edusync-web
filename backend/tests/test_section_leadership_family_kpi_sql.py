"""All family KPI detail variants enforce student section scope in SQL."""
from uuid import uuid4
from unittest.mock import MagicMock
import pytest
from edusync.adapters.postgres_schooling_parity import PostgresSchoolingParityRepository


@pytest.mark.parametrize("metric", ["LARGE_ELIGIBLE", "BENEFICIARIES", "STAFF_CHILDREN"])
@pytest.mark.parametrize("scopes,expected", [
    ((), None),
    ((("SECTION", "PRIMAIRE"),), ["PRIMAIRE"]),
    ((("SECTION", "MATERNELLE"),), ["MATERNELLE"]),
    ((("SECTION", "SECONDAIRE"),), ["SECONDAIRE"]),
    ((("SECTION", "PRIMAIRE"), ("SECTION", "MATERNELLE")), ["MATERNELLE", "PRIMAIRE"]),
    ((("SCHOOL", None),), "SCHOOL"),
])
def test_family_kpi_sql_enforces_section(metric, scopes, expected):
    conn = MagicMock()
    conn.execute.return_value.scalar_one_or_none.return_value = uuid4()
    conn.execute.return_value.mappings.return_value.all.return_value = []
    repo = PostgresSchoolingParityRepository(conn)
    repo._large_min = lambda school_id, year: 5
    assert repo.family_kpi_details_scoped(uuid4(), metric=metric, scopes=scopes) == []
    statement, params = conn.execute.call_args.args
    sql = str(statement)
    assert "JOIN students s" in sql
    if expected is None:
        assert "AND FALSE" in sql
    elif expected == "SCHOOL":
        assert "AND TRUE" in sql
    else:
        assert params["scope_sections"] == expected
        assert "JOIN school_sections ss" in sql


def test_unknown_family_kpi_fails_closed():
    repo = PostgresSchoolingParityRepository(MagicMock())
    with pytest.raises(ValueError):
        repo.family_kpi_details_scoped(uuid4(), metric="INVALID", scopes=())
