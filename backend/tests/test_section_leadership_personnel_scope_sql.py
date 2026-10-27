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


def test_section_directory_redacts_unrelated_assignments_and_global_flags():
    from unittest.mock import Mock
    from uuid import uuid4
    from edusync.adapters.postgres_personnel import PostgresPersonnelRepository

    school_id, staff_id = uuid4(), uuid4()
    connection = Mock()
    row = Mock()
    row._mapping = {
        "id": staff_id,
        "assignments": [{"scope_type": "SECTION", "scope_value": "SECONDAIRE"}],
        "active_assignment_count": 3,
        "has_linked_access": True,
        "staff_children_count": 2,
    }
    connection.execute.return_value.all.return_value = [row]
    repo = PostgresPersonnelRepository(connection)
    repo.list_assignments = Mock(return_value=[
        {"scope_type": "SECTION", "scope_value": "PRIMAIRE"}
    ])
    result = repo.list_staff(school_id, scopes=(("SECTION", "PRIMAIRE"),))
    assert len(result) == 1
    assert result[0]["assignments"] == [{"scope_type": "SECTION", "scope_value": "PRIMAIRE"}]
    assert result[0]["active_assignment_count"] == 1
    assert result[0]["has_linked_access"] is False
    assert result[0]["staff_children_count"] == 0
    repo.list_assignments.assert_called_once_with(
        school_id, staff_id, scopes=(("SECTION", "PRIMAIRE"),)
    )
