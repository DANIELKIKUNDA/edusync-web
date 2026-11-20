from datetime import date
from uuid import uuid4

import pytest

from edusync.modules.subscriptions.domain.subscription import (
    BillingCycle,
    Subscription,
    SubscriptionStatus,
    TransitionDenied,
    period_end,
)


def subscription(status=SubscriptionStatus.ACTIVE, end=date(2026, 12, 1), grace=10):
    return Subscription(uuid4(), uuid4(), uuid4(), BillingCycle.MONTHLY, status,
                        date(2026, 11, 1), end, grace, True)


@pytest.mark.parametrize(("start", "cycle", "expected"), [
    (date(2026, 1, 31), BillingCycle.MONTHLY, date(2026, 2, 28)),
    (date(2024, 1, 31), BillingCycle.MONTHLY, date(2024, 2, 29)),
    (date(2026, 11, 20), BillingCycle.QUARTERLY, date(2027, 2, 20)),
    (date(2026, 11, 20), BillingCycle.ANNUAL, date(2027, 11, 20)),
])
def test_period_end_clamps_calendar(start, cycle, expected):
    assert period_end(start, cycle) == expected


def test_grace_and_limited_are_deterministic():
    item = subscription()
    assert item.evaluate(date(2026, 12, 1)) == SubscriptionStatus.ACTIVE
    assert item.evaluate(date(2026, 12, 2)) == SubscriptionStatus.GRACE
    assert item.evaluate(date(2026, 12, 11)) == SubscriptionStatus.GRACE
    assert item.evaluate(date(2026, 12, 12)) == SubscriptionStatus.LIMITED


def test_transition_matrix_and_reason_are_enforced():
    item = subscription()
    assert item.transition(SubscriptionStatus.PAST_DUE, reason="Facture échue").version == 2
    with pytest.raises(TransitionDenied):
        item.transition(SubscriptionStatus.SUSPENDED, reason="Impayé confirmé")
    with pytest.raises(TransitionDenied):
        item.transition(SubscriptionStatus.PAST_DUE, reason="non")


def test_cancelled_subscription_cannot_be_renewed():
    item = subscription(SubscriptionStatus.CANCELLED)
    with pytest.raises(TransitionDenied):
        item.renew(paid_through=date(2026, 12, 1), reason="Paiement reçu")


def test_invariants_reject_invalid_grace_and_period():
    with pytest.raises(ValueError):
        subscription(grace=91)
    with pytest.raises(ValueError):
        Subscription(uuid4(), uuid4(), uuid4(), BillingCycle.MONTHLY, SubscriptionStatus.ACTIVE,
                     date(2026, 11, 1), date(2026, 11, 1), 10, True)
