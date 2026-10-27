"""Personnel section scopes must never inherit school-wide assignments."""
from edusync.adapters.postgres_personnel import _scope_where


def test_section_scope_excludes_global_assignment():
    where, params = _scope_where((("SECTION", "primaire"),))
    assert "sa.scope_type='SCHOOL'" not in where
    assert "sa.scope_type='SECTION'" in where
    assert "sa.scope_type='CLASS'" in where
    assert params["scope_sections"] == ["PRIMAIRE"]


def test_class_scope_excludes_global_assignment():
    where, params = _scope_where((("CLASS", "7a"),))
    assert "sa.scope_type='SCHOOL'" not in where
    assert params["scope_classes"] == ["7A"]


def test_multiple_sections_are_unioned():
    where, params = _scope_where((("SECTION", "maternelle"), ("SECTION", "primaire")))
    assert " IN :scope_sections" in where
    assert params["scope_sections"] == ["MATERNELLE", "PRIMAIRE"]


def test_schoolwide_grant_is_explicit():
    assert _scope_where((("SCHOOL", None), ("SECTION", "PRIMAIRE"))) == ("TRUE", {})


def test_missing_scope_denied():
    assert _scope_where(()) == ("FALSE", {})


def test_section_directory_batches_assignments_and_redacts_global_flags():
    from unittest.mock import Mock
    from uuid import uuid4
    from edusync.adapters.postgres_personnel import PostgresPersonnelRepository

    school_id, staff_id, second_id = uuid4(), uuid4(), uuid4()
    connection = Mock()
    def row(data):
        result = Mock()
        result._mapping = data
        return result
    connection.execute.return_value.all.side_effect = [
        [
            row({"id": staff_id, "assignments": [{"scope_type": "SCHOOL"}],
                 "active_assignment_count": 3, "has_linked_access": True,
                 "staff_children_count": 2}),
            row({"id": second_id, "assignments": [{"scope_type": "SCHOOL"}],
                 "active_assignment_count": 2, "has_linked_access": True,
                 "staff_children_count": 1}),
        ],
        [row({"staff_id": staff_id, "scope_type": "SECTION",
              "scope_value": "PRIMAIRE"})],
    ]
    repo = PostgresPersonnelRepository(connection)
    result = repo.list_staff(school_id, scopes=(("SECTION", "PRIMAIRE"),))
    assert connection.execute.call_count == 2  # one directory + one batch, not per agent
    assert result[0]["assignments"][0]["scope_value"] == "PRIMAIRE"
    assert result[0]["active_assignment_count"] == 1
    assert result[1]["assignments"] == []
    assert result[1]["active_assignment_count"] == 0
    assert all(item["has_linked_access"] is False for item in result)
    assert all(item["staff_children_count"] == 0 for item in result)
    batch_sql = str(connection.execute.call_args_list[1].args[0])
    assert "a.staff_id IN" in batch_sql
    assert "a.scope_type='SECTION'" in batch_sql
    assert "a.school_id=:sid" in batch_sql


def test_section_directory_empty_page_does_not_query_assignments():
    from unittest.mock import Mock
    from uuid import uuid4
    from edusync.adapters.postgres_personnel import PostgresPersonnelRepository

    conn = Mock()
    conn.execute.return_value.all.return_value = []
    assert PostgresPersonnelRepository(conn).list_staff(
        uuid4(), scopes=(("SECTION", "PRIMAIRE"),)) == []
    assert conn.execute.call_count == 1
