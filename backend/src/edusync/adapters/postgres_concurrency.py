from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from edusync.shared.domain.concurrency import OptimisticConcurrencyError


@dataclass(slots=True)
class OptimisticWriter:
    connection: Connection

    def update_school(self, *, school_id: UUID, expected_version: int, patch: dict[str, Any]) -> int:
        allowed = {"name", "logo_url", "email", "phone", "status"}
        values = {k: v for k, v in patch.items() if k in allowed}
        if not values:
            return expected_version
        sets = ", ".join(f"{k}=:{k}" for k in values)
        params = dict(values, school_id=str(school_id), expected=expected_version)
        row = self.connection.execute(text(f"""
            UPDATE schools SET {sets}, version=version+1, updated_at=now()
             WHERE id=:school_id AND version=:expected
             RETURNING version
        """), params).first()
        if row is None:
            raise OptimisticConcurrencyError(
                f"School {school_id} a été modifiée par une autre session (version attendue {expected_version})"
            )
        return int(row[0])

    def lock_rows_for_financial_mutation(self, *, table: str, ids: list[UUID]) -> None:
        """Foundation hook for later Finance port.

        Only an allow-list is accepted. The Finance bounded context will call this inside the SAME
        transaction as balance recomputation, allocations, receipt, cash, audit and outbox.
        """
        allowed = {"charges", "cash_days", "advance_funds"}
        if table not in allowed:
            raise ValueError("Table non autorisée pour verrou financier")
        if not ids:
            return
        self.connection.execute(
            text(f"SELECT id FROM {table} WHERE id = ANY(:ids) ORDER BY id FOR UPDATE"),
            {"ids": [str(x) for x in ids]},
        ).all()
