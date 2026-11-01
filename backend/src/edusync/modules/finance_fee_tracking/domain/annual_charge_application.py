"""Safety gates for applying annual exigibility to existing finance charges.

The policy engine computes a proposed amount. This module decides whether an
existing charge may be created, retained, or requires explicit reconciliation.
It never silently rewrites payments or previously issued obligations.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from edusync.modules.finance_fee_tracking.domain.annual_exigibility import (
    Obligation, ObligationStatus,
)


@dataclass(frozen=True)
class ChargeDecision:
    action: str
    proposed_amount: Decimal
    reason: str


def plan_charge_application(
    obligation: Obligation, *,
    existing_charge: bool,
    paid_amount: Decimal = Decimal("0"),
    existing_net_amount: Decimal | None = None,
) -> ChargeDecision:
    paid = Decimal(str(paid_amount))
    if not paid.is_finite() or paid < 0:
        raise ValueError("Invalid paid amount")
    if existing_charge:
        if existing_net_amount is None:
            raise ValueError("Existing charge amount is required")
        current = Decimal(str(existing_net_amount))
        if not current.is_finite() or current < 0 or paid > current:
            raise ValueError("Invalid existing charge state")
        if current != obligation.exigible:
            return ChargeDecision("REVIEW_REQUIRED", obligation.exigible,
                                  "Existing charge differs from policy assessment")
        return ChargeDecision("KEEP", current, "Existing obligation is unchanged")
    if paid:
        raise ValueError("Payments cannot exist without a charge")
    if obligation.status in (ObligationStatus.NOT_APPLICABLE, ObligationStatus.NOT_EXIGIBLE):
        return ChargeDecision("SKIP", Decimal("0.00"), obligation.status.value)
    if obligation.exigible <= 0:
        raise ValueError("Positive due amount required for a new charge")
    return ChargeDecision("CREATE", obligation.exigible, "New obligation")
