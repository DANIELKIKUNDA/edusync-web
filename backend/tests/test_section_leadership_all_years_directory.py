"""All-years directory cannot return a section-scoped pupil without an authorized enrollment."""
from uuid import uuid4
from unittest.mock import MagicMock
from edusync.adapters.postgres_schooling import PostgresSchoolingRepository


def test_all_years_section_directory_requires_authorized_enrollment():
    conn = MagicMock()
    conn.execute.return_value.all.return_value = []
    PostgresSchoolingRepository(conn).list_students(
        uuid4(), scopes=(("SECTION", "PRIMAIRE"),), all_years=True)
    statement, params = conn.execute.call_args.args
    sql = str(statement)
    assert "e.id IS NOT NULL" in sql
    assert "upper(ss1.code) IN :lateral_sections" in sql
    assert params["lateral_sections"] == ["PRIMAIRE"]


def test_all_years_schoolwide_directory_keeps_legacy_unenrolled_rows():
    conn = MagicMock()
    conn.execute.return_value.all.return_value = []
    PostgresSchoolingRepository(conn).list_students(
        uuid4(), scopes=(("SCHOOL", None),), all_years=True)
    statement, _ = conn.execute.call_args.args
    assert "e.id IS NOT NULL" not in str(statement)
