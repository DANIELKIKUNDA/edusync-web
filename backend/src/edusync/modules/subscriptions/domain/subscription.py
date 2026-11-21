from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from enum import StrEnum
from uuid import UUID


class BillingCycle(StrEnum):
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUAL = "ANNUAL"


class SubscriptionStatus(StrEnum):
    TRIAL = "TRIAL"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    GRACE = "GRACE"
    LIMITED = "LIMITED"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class TransitionDenied(ValueError):
    pass


_ALLOWED: dict[SubscriptionStatus, frozenset[SubscriptionStatus]] = {
    SubscriptionStatus.TRIAL: frozenset({SubscriptionStatus.PENDING_PAYMENT, SubscriptionStatus.ACTIVE,
                                         SubscriptionStatus.EXPIRED, SubscriptionStatus.CANCELLED}),
    SubscriptionStatus.PENDING_PAYMENT: frozenset({SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELLED,
                                                   SubscriptionStatus.EXPIRED}),
    SubscriptionStatus.ACTIVE: frozenset({SubscriptionStatus.PAST_DUE, SubscriptionStatus.CANCELLED,
                                          SubscriptionStatus.EXPIRED}),
    SubscriptionStatus.PAST_DUE: frozenset({SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE,
                                            SubscriptionStatus.LIMITED, SubscriptionStatus.CANCELLED}),
    SubscriptionStatus.GRACE: frozenset({SubscriptionStatus.ACTIVE, SubscriptionStatus.LIMITED,
                                         SubscriptionStatus.CANCELLED}),
    SubscriptionStatus.LIMITED: frozenset({SubscriptionStatus.ACTIVE, SubscriptionStatus.SUSPENDED,
                                           SubscriptionStatus.CANCELLED}),
    SubscriptionStatus.SUSPENDED: frozenset({SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELLED}),
    SubscriptionStatus.CANCELLED: frozenset(),
    SubscriptionStatus.EXPIRED: frozenset({SubscriptionStatus.PENDING_PAYMENT, SubscriptionStatus.ACTIVE}),
}


def period_end(start: date, cycle: BillingCycle) -> date:
    """Exclusive end date without external date libraries; end-of-month is clamped."""
    months = {BillingCycle.MONTHLY: 1, BillingCycle.QUARTERLY: 3, BillingCycle.ANNUAL: 12}[cycle]
    target_month = start.month - 1 + months
    year = start.year + target_month // 12
    month = target_month % 12 + 1
    first_after = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    last_day = (first_after - timedelta(days=1)).day
    return date(year, month, min(start.day, last_day))


@dataclass(frozen=True, slots=True)
class Subscription:
    id: UUID
    school_id: UUID
    plan_version_id: UUID
    cycle: BillingCycle
    status: SubscriptionStatus
    current_period_start: date
    current_period_end: date
    grace_days: int
    auto_renew: bool
    version: int = 1

    def __post_init__(self) -> None:
        if self.grace_days < 0 or self.grace_days > 90:
            raise ValueError("La période de grâce doit être comprise entre 0 et 90 jours")
        if self.current_period_end <= self.current_period_start:
            raise ValueError("La fin de période doit suivre son début")
        if self.version < 1:
            raise ValueError("La version doit être positive")

    @property
    def grace_ends_on(self) -> date:
        return self.current_period_end + timedelta(days=self.grace_days)

    @property
    def commercially_usable(self) -> bool:
        return self.status in {SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE,
                               SubscriptionStatus.PAST_DUE, SubscriptionStatus.GRACE}

    def transition(self, target: SubscriptionStatus, *, reason: str) -> "Subscription":
        if len(reason.strip()) < 5:
            raise TransitionDenied("Un motif d'au moins 5 caractères est obligatoire")
        if target == self.status:
            raise TransitionDenied("L'abonnement est déjà dans cet état")
        if target not in _ALLOWED[self.status]:
            raise TransitionDenied(f"Transition interdite : {self.status} vers {target}")
        return replace(self, status=target, version=self.version + 1)

    def renew(self, *, paid_through: date, reason: str) -> "Subscription":
        if len(reason.strip()) < 5:
            raise TransitionDenied("Un motif d'au moins 5 caractères est obligatoire")
        if self.status in {SubscriptionStatus.CANCELLED}:
            raise TransitionDenied("Un abonnement résilié ne peut pas être renouvelé")
        start = max(self.current_period_end, paid_through)
        end = period_end(start, self.cycle)
        return replace(self, status=SubscriptionStatus.ACTIVE, current_period_start=start,
                       current_period_end=end, version=self.version + 1)

    def evaluate(self, today: date) -> SubscriptionStatus:
        """Pure daily decision. Persistence/audit remains an application concern."""
        if self.status in {SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED,
                           SubscriptionStatus.SUSPENDED, SubscriptionStatus.LIMITED}:
            return self.status
        if today <= self.current_period_end:
            return self.status
        if today <= self.grace_ends_on:
            return SubscriptionStatus.GRACE
        return SubscriptionStatus.LIMITED

