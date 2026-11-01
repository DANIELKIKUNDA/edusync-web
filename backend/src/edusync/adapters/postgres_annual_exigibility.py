"""Read-only policy preview; no charge/payment mutation.

This adapter deliberately fails closed if no active annual policy exists.
The caller must pass a tenant-scoped school and year. Draft policies are
never used for financial assessments.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from edusync.modules.finance_fee_tracking.domain.annual_exigibility import (
    DayBand, EntryPolicy, PriorPeriodMode, resolve_monthly_obligation,
)


class PostgresAnnualExigibilityRepository:
    def __init__(self, connection: Connection):
        self.connection = connection

    def active_policy_for_fee(self, school_id: UUID, academic_year_id: UUID, fee_type_id: UUID):
        row = self.connection.execute(text("""
            SELECT p.id AS policy_id, p.version, p.effective_from, r.id AS rule_id,
                   r.prior_mode, r.prior_percent
            FROM finance_exigibility_policies p
            JOIN finance_exigibility_rules r
              ON r.policy_id=p.id AND r.school_id=p.school_id
            JOIN fee_types f ON f.id=r.fee_type_id AND f.school_id=p.school_id
            WHERE p.school_id=:school AND p.academic_year_id=:year
              AND p.status='ACTIVE' AND r.fee_type_id=:fee
        """), {"school": school_id, "year": academic_year_id, "fee": fee_type_id}).mappings().one_or_none()
        if row is None:
            return None
        bands = self.connection.execute(text("""
            SELECT b.first_day, b.last_day, b.percent
            FROM finance_exigibility_day_bands b
            WHERE b.school_id=:school AND b.rule_id=:rule
            ORDER BY b.first_day
        """), {"school": school_id, "rule": row["rule_id"]}).mappings().all()
        policy = EntryPolicy(
            PriorPeriodMode(row["prior_mode"]),
            tuple(DayBand(int(b["first_day"]), int(b["last_day"]) if b["last_day"] is not None else None,
                          Decimal(str(b["percent"]))) for b in bands),
            Decimal(str(row["prior_percent"])) if row["prior_percent"] is not None else None,
        )
        return {"id": row["policy_id"], "version": row["version"], "effective_from": row["effective_from"],
                "policy": policy}

    def preview_month(self, *, school_id: UUID, academic_year_id: UUID, fee_type_id: UUID,
                      financial_entry_date: date, period_year: int, period_month: int, tariff: Decimal):
        configured = self.active_policy_for_fee(school_id, academic_year_id, fee_type_id)
        if configured is None:
            raise ValueError("Aucune politique annuelle active pour ce type de frais")
        result = resolve_monthly_obligation(
            tariff=tariff, period_year=period_year, period_month=period_month,
            financial_entry_date=financial_entry_date, policy=configured["policy"],
        )
        return {"policy_id": configured["id"], "policy_version": configured["version"],
                "status": result.status.value, "tariff": result.tariff,
                "exigible": result.exigible, "percent": result.policy_percent}
