"""Pure monthly recovery counters, independent from SQL persistence.

Only positive obligations count as debtors. Non-cash settlements are
part of regularization, but must not be double-counted as cash.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class RecoveryLine:
    enrollment_id: str
    expected: Decimal
    paid: Decimal = Decimal("0")
    outside_cash: Decimal = Decimal("0")
    noncash: Decimal = Decimal("0")

def recovery_counts(lines: list[RecoveryLine]) -> dict[str, int]:
    """Group multiple charges per enrollment before classifying a debtor."""
    totals: dict[str, tuple[Decimal, Decimal]] = {}
    for line in lines:
        expected = Decimal(str(line.expected))
        paid = Decimal(str(line.paid))
        outside = Decimal(str(line.outside_cash))
        noncash = Decimal(str(line.noncash))
        if min(expected, paid, outside, noncash) < 0:
            raise ValueError("Negative recovery amount")
        previous = totals.get(line.enrollment_id, (Decimal(0), Decimal(0)))
        totals[line.enrollment_id] = (previous[0] + expected, previous[1] + paid + outside + noncash)
    debtors = [v for v in totals.values() if v[0] > 0]
    return {
        "debtors": len(debtors),
        "in_order": sum(1 for expected, settled in debtors if settled >= expected),
        "not_in_order": sum(1 for expected, settled in debtors if settled < expected),
    }
