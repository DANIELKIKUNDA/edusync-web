"""Automatic commercial lifecycle, deliberately independent from school fee collection."""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import text

from edusync.modules.subscriptions.domain.subscription import SubscriptionStatus

log = logging.getLogger("edusync.subscriptions")
LOCK_KEY = 8_311_202_611
_started = False


def expected_status(*, current: SubscriptionStatus, period_end: date, grace_days: int, today: date) -> SubscriptionStatus:
    """Return the policy state for a non-terminal subscription on a given day."""
    if current in {SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED, SubscriptionStatus.SUSPENDED}:
        return current
    if today <= period_end:
        return current
    if today <= period_end + timedelta(days=grace_days):
        return SubscriptionStatus.GRACE
    return SubscriptionStatus.LIMITED


def invoice_status(*, total: Decimal, paid_total: Decimal, due_on: date | None, today: date) -> str:
    if paid_total >= total:
        return "PAID"
    if paid_total > 0:
        return "PARTIALLY_PAID"
    if due_on is not None and due_on < today:
        return "OVERDUE"
    return "ISSUED"


def run_once(services, *, today: date | None = None) -> dict:
    """Evaluate all commercial subscriptions once. An advisory lock elects one API process."""
    today = today or date.today()
    out = {"skipped": False, "subscriptions": 0, "invoices": 0, "payments_expired": 0, "transitions": []}
    with services.platform_db.platform_transaction() as conn:
        if not conn.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": LOCK_KEY}).scalar():
            out["skipped"] = True
            return out
        invoices = conn.execute(text("""UPDATE saas_invoices SET status='OVERDUE',version=version+1,updated_at=now()
            WHERE status='ISSUED' AND paid_total=0 AND due_at::date<:today RETURNING id"""), {"today": today}).all()
        out["invoices"] = len(invoices)
        expired = conn.execute(text("""UPDATE saas_payments SET status='EXPIRED',failure_code='TIMEOUT',
            failure_message='Délai de confirmation dépassé',last_provider_update_at=now(),version=version+1,updated_at=now()
            WHERE status IN ('CREATED','PENDING') AND expires_at IS NOT NULL AND expires_at<now() RETURNING id""")).all()
        out["payments_expired"] = len(expired)
        rows = conn.execute(text("""SELECT id,school_id,status,current_period_end,grace_days,version
            FROM saas_subscriptions WHERE status NOT IN ('CANCELLED','EXPIRED','SUSPENDED') FOR UPDATE""")).mappings().all()
        out["subscriptions"] = len(rows)
        for row in rows:
            old = SubscriptionStatus(row["status"])
            target = expected_status(current=old, period_end=row["current_period_end"], grace_days=row["grace_days"], today=today)
            if target == old:
                continue
            conn.execute(text("""UPDATE saas_subscriptions SET status=:status,version=version+1,updated_at=now()
                WHERE id=:id AND version=:version"""), {"status": target.value, "id": row["id"], "version": row["version"]})
            entitlement = "ACTIVE" if target in {SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE} else "SUSPENDED"
            conn.execute(text("""UPDATE saas_entitlements SET status=:status,version=version+1,updated_at=now(),
                reason=:reason WHERE subscription_id=:id AND status IN ('ACTIVE','SUSPENDED')"""),
                {"status": entitlement, "reason": "Politique automatique d’échéance", "id": row["id"]})
            conn.execute(text("""INSERT INTO saas_subscription_events(subscription_id,school_id,from_status,to_status,reason)
                VALUES(:id,:school,:old,:new,'Politique automatique d’échéance')"""),
                {"id": row["id"], "school": row["school_id"], "old": old.value, "new": target.value})
            out["transitions"].append({"subscription_id": str(row["id"]), "from": old.value, "to": target.value})
    return out


def start_billing_loop(services) -> None:
    global _started
    if _started:
        return
    _started = True

    def loop() -> None:
        time.sleep(120)
        while True:
            try:
                run_once(services)
            except Exception:  # one pass must never stop the API
                log.exception("commercial subscription lifecycle pass failed")
            time.sleep(900)

    threading.Thread(target=loop, name="edusync-subscriptions", daemon=True).start()
