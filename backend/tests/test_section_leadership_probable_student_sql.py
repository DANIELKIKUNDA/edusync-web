"""Section isolation in probable-student search, including empty scope."""
from uuid import uuid4
from unittest.mock import MagicMock
import pytest
from edusync.adapters.postgres_schooling_parity import PostgresSchoolingParityRepository


@pytest.mark.parametrize("scopes,expected", [
    ((), "FALSE"),
    ((("students.read", "SECTION", "PRIMAIRE"),), "PRIMAIRE"),
    ((("students.read", "SECTION", "MATERNELLE"),), "MATERNELLE"),
    ((("students.read", "SECTION", "SECONDAIRE"),), "SECONDAIRE"),
    ((("students.read", "SCHOOL", None),), "TRUE"),
])
def test_probable_student_search_sql_restricts_scope(scopes, expected):
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.all.return_value = []
    repo = PostgresSchoolingParityRepository(conn)
    repo.probable_students(uuid4(), last_name="KIKUNDA",
                           scopes=tuple((kind, value) for _, kind, value in scopes))
    statement, params = conn.execute.call_args.args
    sql = str(statement)
    assert "s.school_id=:sid" in sql
    assert "LIMIT 8" in sql
    if expected == "FALSE":
        assert "AND FALSE" in sql
    elif expected == "TRUE":
        assert "AND TRUE" in sql
    else:
        assert "scope_sections" in params
        assert params["scope_sections"] == [expected]
        assert "JOIN school_sections ss" in sql


def test_probable_student_search_does_not_mix_sections():
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.all.return_value = []
    PostgresSchoolingParityRepository(conn).probable_students(
        uuid4(), last_name="MULUMBA", scopes=(("SECTION", "PRIMAIRE"),))
    _, params = conn.execute.call_args.args
    assert params["scope_sections"] == ["PRIMAIRE"]
