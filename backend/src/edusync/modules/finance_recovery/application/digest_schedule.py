"""Automatic weekly / monthly / term reports (owner, 2026-11-19 — étape 3).

« La semaine se termine samedi » : the weekly report leaves on Saturday as soon as the day's cash desks are all closed
(from noon), at the latest at 20:00 school time — then with a mention that a desk is still open if so. The monthly one
leaves the same way on the last day of the month (on Saturday when the month ends on a Sunday), the term one at the
end of December, March and June. July and August (holidays): no monthly / term report.

Safe by construction: one pass at a time across API processes (advisory lock), and a report already sent for a period
(automatically or with the button) is never sent again (idempotent messages per person and period).
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import text

log = logging.getLogger("edusync.reports")
LOCK_KEY = 8_710_119_2026
_started = False


def month_report_day(day: date) -> date:
    nxt = (day.replace(year=day.year + 1, month=1, day=1) if day.month == 12 else day.replace(month=day.month + 1, day=1))
    last = nxt - timedelta(days=1)
    return last - timedelta(days=1) if last.weekday() == 6 else last


def due_kinds(now: datetime, *, sessions_today: int, open_today: int) -> list[str]:
    """Pure: which reports are due at `now` (school local time) given today's cash desks."""
    today = now.date()
    closed = sessions_today > 0 and open_today == 0 and now.hour >= 12
    if not (closed or now.hour >= 20):
        return []
    kinds = []
    if today.weekday() == 5:
        kinds.append("WEEK")
    if today.month not in (7, 8) and today == month_report_day(today):
        kinds.append("MONTH")
        if today.month in (12, 3, 6):
            kinds.append("QUARTER")
    return kinds


def already_sent(conn, school_id, kind: str, start: date) -> bool:
    return conn.execute(text("""SELECT 1 FROM communication_messages WHERE school_id=:s AND kind='REPORT'
        AND idempotency_key LIKE :k LIMIT 1"""), {"s": str(school_id), "k": f"digest:{kind}:{start.isoformat()}:%"}).first() is not None


def run_school(services, school_id, now: datetime) -> list[str]:
    from edusync.modules.finance_recovery.api.router import _digest_load
    from edusync.modules.finance_recovery.application.digest_send import send_digest
    from edusync.modules.finance_recovery.domain.digest import period_of
    with services.tenant_db.tenant_transaction(school_id=school_id) as conn:
        row = conn.execute(text("""SELECT count(*) n, count(*) FILTER (WHERE status='OPEN') o FROM finance_cash_sessions
            WHERE school_id=:s AND business_date=:d"""), {"s": str(school_id), "d": now.date()}).mappings().one()
        kinds = [k for k in due_kinds(now, sessions_today=row["n"], open_today=row["o"])
                 if not already_sent(conn, school_id, k, period_of(k, now.date())[0])]
    done = []
    system = SimpleNamespace(school_id=school_id, user_id=None)
    for k in kinds:
        out = send_digest(services, system, kind=k, as_of=now.date(), currency="CDF", load=_digest_load)
        log.info("scheduled report %s school=%s sent=%s", k, school_id, len(out["sent"]))
        done.append(k)
    return done


def run_all(services, now: datetime | None = None) -> dict:
    zone = ZoneInfo(getattr(services.settings, "school_timezone", "Africa/Lubumbashi"))
    now = now or datetime.now(zone)
    with services.platform_db.engine.connect() as pc:
        if not pc.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar():
            return {"skipped": True}
        try:
            schools = [r[0] for r in pc.execute(text("SELECT id FROM schools WHERE status='ACTIVE' ORDER BY id"))]
            out = {"skipped": False, "schools": len(schools), "sent": {}}
            for sid in schools:
                try:
                    done = run_school(services, sid, now)
                    if done:
                        out["sent"][str(sid)] = done
                except Exception:  # one school never blocks the others
                    log.exception("scheduled report failed school=%s", sid)
            return out
        finally:
            pc.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})


def start_report_loop(services) -> None:
    global _started
    if _started or not getattr(services.settings, "scheduled_reports_enabled", True):
        return
    _started = True

    def loop():
        time.sleep(90)
        while True:
            try:
                run_all(services)
            except Exception:
                log.exception("scheduled reports pass failed")
            time.sleep(600)
    threading.Thread(target=loop, name="edusync-reports", daemon=True).start()
