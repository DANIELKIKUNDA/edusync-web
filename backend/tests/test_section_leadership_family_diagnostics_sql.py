"""Family diagnostics must aggregate only families visible to each section."""
from uuid import uuid4
from unittest.mock import MagicMock
import pytest
from edusync.adapters.postgres_schooling_parity import PostgresSchoolingParityRepository


@pytest.mark.parametrize("scopes,section", [
    ((), None),
    ((("SECTION", "PRIMAIRE"),), "PRIMAIRE"),
    ((("SECTION", "MATERNELLE"),), "MATERNELLE"),
    ((("SECTION", "SECONDAIRE"),), "SECONDAIRE"),
    ((("SECTION", "PRIMAIRE"), ("SECTION", "MATERNELLE")), "DUAL"),
    ((("SCHOOL", None),), "SCHOOL"),
])
def test_family_diagnostics_queries_are_scoped(scopes, section):
    conn = MagicMock()
    conn.execute.return_value.scalar_one.return_value = 0
    result = PostgresSchoolingParityRepository(conn).family_contact_diagnostics_scoped(uuid4(), scopes=scopes)
    assert set(result) == {"without_responsible", "multiple_primary",
                           "responsible_without_phone", "shared_phones"}
    assert conn.execute.call_count == 4
    for call in conn.execute.call_args_list:
        statement, params = call.args
        sql = str(statement)
        assert "f.school_id=:sid" in sql
        if section is None:
            assert "AND FALSE" in sql
        elif section == "SCHOOL":
            assert "AND TRUE" in sql
        else:
            assert "JOIN school_sections ss" in sql
            assert params["scope_sections"] == (["MATERNELLE", "PRIMAIRE"] if section == "DUAL" else [section])
