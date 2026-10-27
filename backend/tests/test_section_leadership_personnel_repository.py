"""Repository security invariants for assignment insertion."""
from unittest.mock import Mock
from uuid import uuid4

import pytest

from edusync.adapters.postgres_personnel import PostgresPersonnelRepository
from edusync.modules.personnel.domain.models import AssignmentScope, StaffAssignment


def assignment():
    return StaffAssignment(
        school_id=uuid4(),staff_id=uuid4(),function_id=uuid4(),
        scope_type=AssignmentScope.SECTION,scope_value="PRIMAIRE",
        section_id=uuid4(),start_date=__import__("datetime").date.today(),
    )


def test_foreign_school_or_disabled_function_rejected_before_insert():
    conn=Mock()
    conn.execute.return_value.first.side_effect=[(uuid4(),),None]
    with pytest.raises(ValueError,match="Fonction"):
        PostgresPersonnelRepository(conn).add_assignment(assignment())
    assert conn.execute.call_count==2
    assert "INSERT INTO staff_assignments" not in " ".join(
        str(call.args[0]) for call in conn.execute.call_args_list)


def test_nonexistent_staff_rejected_before_function_lookup():
    conn=Mock()
    conn.execute.return_value.first.return_value=None
    with pytest.raises(LookupError,match="Agent"):
        PostgresPersonnelRepository(conn).add_assignment(assignment())
    assert conn.execute.call_count==1
