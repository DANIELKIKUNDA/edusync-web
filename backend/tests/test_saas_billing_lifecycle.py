from datetime import date
from decimal import Decimal

from edusync.modules.subscriptions.application.lifecycle import expected_status, invoice_status
from edusync.modules.subscriptions.domain.subscription import SubscriptionStatus


def test_subscription_stays_usable_through_the_paid_period():
    assert expected_status(current=SubscriptionStatus.ACTIVE, period_end=date(2026, 11, 30), grace_days=10,
                           today=date(2026, 11, 30)) == SubscriptionStatus.ACTIVE


def test_subscription_enters_grace_after_due_date():
    assert expected_status(current=SubscriptionStatus.ACTIVE, period_end=date(2026, 11, 30), grace_days=10,
                           today=date(2026, 12, 5)) == SubscriptionStatus.GRACE


def test_subscription_becomes_limited_after_grace_not_deleted():
    assert expected_status(current=SubscriptionStatus.GRACE, period_end=date(2026, 11, 30), grace_days=10,
                           today=date(2026, 12, 11)) == SubscriptionStatus.LIMITED


def test_manual_suspension_and_cancellation_are_never_overridden():
    for state in (SubscriptionStatus.SUSPENDED, SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED):
        assert expected_status(current=state, period_end=date(2026, 1, 1), grace_days=0,
                               today=date(2026, 12, 1)) == state


def test_invoice_state_is_exact_and_never_float_based():
    assert invoice_status(total=Decimal("10.00"), paid_total=Decimal("10.00"), due_on=date(2026, 11, 1), today=date(2026, 11, 20)) == "PAID"
    assert invoice_status(total=Decimal("10.00"), paid_total=Decimal("2.50"), due_on=date(2026, 11, 1), today=date(2026, 11, 20)) == "PARTIALLY_PAID"
    assert invoice_status(total=Decimal("10.00"), paid_total=Decimal("0.00"), due_on=date(2026, 11, 1), today=date(2026, 11, 20)) == "OVERDUE"


def test_lifecycle_is_single_runner_and_started_with_the_api():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    src = (root / "backend/src/edusync/modules/subscriptions/application/lifecycle.py").read_text(encoding="utf-8")
    app = (root / "backend/src/edusync/bootstrap/app.py").read_text(encoding="utf-8")
    assert "pg_try_advisory_xact_lock" in src
    assert "start_billing_loop(app.state.services)" in app
    assert "time.sleep(900)" in src
