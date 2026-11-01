"""Preview monthly schedule obligations without mutating certified charges.

An explicit financial entry date is required. The active school/year policy
must exist for the fee type. Non-monthly schedules are intentionally rejected.
"""
from datetime import date
from decimal import Decimal
from sqlalchemy import text
from edusync.adapters.postgres_annual_exigibility import PostgresAnnualExigibilityRepository


def preview_enrollment_monthly_schedules(connection, *, school_id, academic_year_id,
                                         class_id, financial_entry_date: date):
    if not isinstance(financial_entry_date, date):
        raise ValueError("Financial entry date required")
    schedules = connection.execute(text("""
        SELECT s.id AS schedule_id,s.fee_type_id,s.period_code,s.due_date,
               s.amount,s.currency
        FROM fee_schedules s
        JOIN fee_types f ON f.id=s.fee_type_id AND f.school_id=s.school_id
        WHERE s.school_id=:school AND s.academic_year_id=:year
          AND s.class_id=:class_id AND s.active AND f.periodicity='MONTHLY'
        ORDER BY s.due_date,s.id
    """), {"school": school_id, "year": academic_year_id, "class_id": class_id}).mappings().all()
    repo = PostgresAnnualExigibilityRepository(connection)
    results = []
    for schedule in schedules:
        due_date = schedule["due_date"]
        if due_date is None or schedule["period_code"] != f"{due_date.month:02d}":
            raise ValueError("Invalid monthly schedule period")
        assessment = repo.preview_month(
            school_id=school_id, academic_year_id=academic_year_id,
            fee_type_id=schedule["fee_type_id"], financial_entry_date=financial_entry_date,
            period_year=due_date.year, period_month=due_date.month,
            tariff=Decimal(str(schedule["amount"])),
        )
        results.append({
            "schedule_id": str(schedule["schedule_id"]),
            "period_code": schedule["period_code"],
            "currency": schedule["currency"],
            **assessment,
        })
    return results
