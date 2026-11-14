"""Platform alerts (lot 2026-10): a component « Hors service » for more than `platform_alert_delay_seconds` (5 min)
opens an incident and sends ONE e-mail to the recipients; its recovery sends ONE resolution e-mail. Every incident is
kept (État du service → Incidents récents).

Recipients: every active Manager Système (role MANAGER_SYSTEME, active, not suspended) plus the extra addresses a
Manager added in État du service (platform_alert_recipients). No address lives in the code or the configuration.

Runs inside the API (one evaluation per minute, a PostgreSQL advisory lock elects one process at a time: several API
processes never send the same alert twice). The e-mail goes through the transactional outbox (communications worker).
Limits, documented: when PostgreSQL itself is down nothing can be recorded nor queued here; the external heartbeat
(heartbeat.py, sent after every evaluation, independent of the database and of the e-mails) and the external probes
(deploy/coolify/README.md §9) cover that case and an unreachable server.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

log = logging.getLogger("edusync.alerts")
LOCK_KEY = 7_202_610_001          # pg_try_advisory_xact_lock key of the alert evaluator
_started = False


def recipients(conn) -> list[dict]:
    rows = conn.execute(text("""SELECT DISTINCT u.id, u.full_name, lower(u.email) AS email FROM users u
        JOIN rbac_assignments a ON a.user_id=u.id AND a.school_id IS NULL AND a.active
             AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now())
        JOIN rbac_roles r ON r.id=a.role_id AND r.code='MANAGER_SYSTEME' AND r.status='ACTIVE'
        WHERE u.active AND u.email IS NOT NULL""")).mappings().all()
    out = {r["email"]: {"user_id": r["id"], "name": r["full_name"], "email": r["email"]} for r in rows}
    try:
        from edusync.bootstrap.dependencies import platform_account_suspended
        out = {e: v for e, v in out.items() if not platform_account_suspended(conn, v["user_id"])}
    except Exception:  # noqa: BLE001
        pass
    for r in conn.execute(text("SELECT lower(email) AS email, label FROM platform_alert_recipients WHERE active")).mappings():
        out.setdefault(r["email"], {"user_id": None, "name": r["label"], "email": r["email"]})
    return list(out.values())


def _send(conn, cfg, incident: dict, kind: str) -> int:
    from edusync.modules.communications.application.messaging import Recipient, request_message
    people = recipients(conn)
    if not people:
        return 0
    if kind == "OPEN":
        subject = f"[EduSync] Incident : {incident['component_label']} hors service"
        body = (f"Le service « {incident['component_label']} » est hors service depuis le "
                f"{incident['opened_at'].astimezone(timezone.utc):%d/%m/%Y à %H:%M} UTC.\n"
                f"Raison mesurée : {incident['explain']}\n\n"
                "Ouvrez EduSync → État du service pour le détail. Un second message sera envoyé à la résolution.")
    else:
        mins = int((incident['resolved_at'] - incident['opened_at']).total_seconds() // 60)
        subject = f"[EduSync] Résolu : {incident['component_label']}"
        body = (f"Le service « {incident['component_label']} » fonctionne de nouveau "
                f"(incident ouvert le {incident['opened_at'].astimezone(timezone.utc):%d/%m/%Y à %H:%M} UTC, durée : {mins} min).")
    recips = [Recipient("USER", p["user_id"] or uuid.uuid5(uuid.NAMESPACE_URL, "alert:" + p["email"]), p["name"], email=p["email"],
                        user_id=p["user_id"]) for p in people]
    request_message(conn, school_id=None, kind="PLATFORM", channels=["EMAIL"], body=body, subject=subject, template_code="PLATFORM_ALERT",
                    recipients=recips, idempotency_key=f"platform-incident:{incident['id']}:{kind}", created_by=None)
    return len(recips)


def evaluate(services, *, body: dict | None = None, now: datetime | None = None) -> dict:
    """One evaluation: open / notify / resolve incidents from a fresh measurement. Returns what happened."""
    from edusync.modules.platform_health.api.router import measure
    cfg = services.settings
    body = body or measure(services)
    now = now or datetime.now(timezone.utc)
    down = {c["key"]: c for c in body["components"] if c["state"] == "DOWN"}
    out = {"opened": [], "notified": [], "resolved": [], "skipped": False}
    with services.platform_db.platform_transaction() as conn:
        if not conn.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": LOCK_KEY}).scalar():
            out["skipped"] = True
            return out
        open_rows = {r["component_key"]: dict(r) for r in conn.execute(text(
            "SELECT * FROM platform_incidents WHERE resolved_at IS NULL FOR UPDATE")).mappings()}
        for key, comp in down.items():
            if key not in open_rows:
                row = conn.execute(text("""INSERT INTO platform_incidents(component_key, component_label, explain, opened_at, last_seen_at)
                    VALUES (:k, :l, :e, :t, :t) RETURNING *"""), {"k": key, "l": comp["label"], "e": comp["detail"][:500], "t": now}).mappings().one()
                open_rows[key] = dict(row)
                out["opened"].append(key)
            else:
                conn.execute(text("UPDATE platform_incidents SET last_seen_at=:t, explain=:e WHERE id=:id"),
                             {"t": now, "e": comp["detail"][:500], "id": open_rows[key]["id"]})
            inc = open_rows[key]
            if inc["notified_at"] is None and (now - inc["opened_at"]).total_seconds() >= cfg.platform_alert_delay_seconds:
                inc["explain"] = comp["detail"][:500]
                _send(conn, cfg, inc, "OPEN")
                conn.execute(text("UPDATE platform_incidents SET notified_at=:t WHERE id=:id"), {"t": now, "id": inc["id"]})
                out["notified"].append(key)
        for key, inc in open_rows.items():
            if key in down:
                continue
            inc["resolved_at"] = now
            conn.execute(text("UPDATE platform_incidents SET resolved_at=:t WHERE id=:id"), {"t": now, "id": inc["id"]})
            if inc["notified_at"] is not None:        # an incident nobody was told about is closed silently
                _send(conn, cfg, inc, "RESOLVED")
                conn.execute(text("UPDATE platform_incidents SET resolution_notified_at=:t WHERE id=:id"), {"t": now, "id": inc["id"]})
            out["resolved"].append(key)
    return out


def start_alert_loop(services) -> None:
    """Background evaluator of this API process (daemon thread, one evaluation per interval). Never raises."""
    global _started
    if _started or not services.settings.platform_alerts_enabled:
        return
    _started = True

    def loop():
        time.sleep(15)
        from edusync.modules.platform_health.api.router import measure
        from edusync.modules.platform_health.application.heartbeat import beat
        while True:
            body = None
            try:
                body = measure(services)
                evaluate(services, body=body)
            except Exception:  # noqa: BLE001 — an evaluation failure is logged, the API keeps serving
                log.exception("platform alert evaluation failed")
            # External heartbeat (heartbeat.py): sent even when the database or the e-mails are down.
            beat(services.settings, body)
            time.sleep(max(15, services.settings.platform_alert_interval_seconds))

    threading.Thread(target=loop, name="edusync-platform-alerts", daemon=True).start()
