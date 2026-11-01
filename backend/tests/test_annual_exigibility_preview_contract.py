"""Isolated preview contract tests; no database writes."""
from datetime import date
import pytest
from edusync.adapters.postgres_annual_exigibility_preview import preview_enrollment_monthly_schedules

class EmptySchedules:
    def execute(self, sql, params):
        assert "SELECT" in str(sql)
        class Rows:
            def mappings(self):
                return self
            def all(self):
                return []
        return Rows()

def test_empty_schedule_preview():
    result = preview_enrollment_monthly_schedules(
        EmptySchedules(), school_id="school", academic_year_id="year",
        class_id="class", financial_entry_date=date(2026, 10, 28),
    )
    assert result == []

def test_missing_entry_date_rejected():
    with pytest.raises(ValueError, match="Financial entry date"):
        preview_enrollment_monthly_schedules(
            EmptySchedules(), school_id="school", academic_year_id="year",
            class_id="class", financial_entry_date=None,
        )
