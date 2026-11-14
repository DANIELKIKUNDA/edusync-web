"""Plateforme EduSync — system health with real measurements (N1 certification 2026-10, État du service lot 2026-10).

Every figure is measured at request time or read from a real signal; nothing is estimated or invented.
A component that is not configured is reported as such (never as healthy). States are the existing ones:
OK / DEGRADED / DOWN / NOT_CONFIGURED; the overall state is the worst configured component.
Freshness: each component carries measured_at (the instant of its own measurement) and, for the workers, the age of
their last heartbeat. Concurrent or repeated requests within MEASURE_TTL seconds share one measurement (no storm of
checks: 50 clicks or tabs cost one round of checks).
Diagnosable cockpit (lot 2026-10, signals.py): golden signals of the API (traffic, errors, latency, saturation), server
errors grouped by route template / status / type with first and last occurrence, CURRENT health (errors active within
the last 5 minutes) separated from HISTORY (1 h / 24 h / 7 d, which never degrades the current state), messaging
providers (state, last success, last failure), alerts derived from the components. Expected refusals (4xx: validation,
wrong password, 403, 404, bad file format) are counted apart and never degrade. Not available: uptime history,
planned maintenance, backup size. Alert e-mails: application/alerts.py.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

import uuid

from pydantic import BaseModel, Field

from edusync.bootstrap.dependencies import get_services, require_platform_actor, require_recent_mfa
from edusync.bootstrap.services import AppServices
from edusync.shared.application.context import ActorContext
from edusync.shared.infrastructure import signals
from edusync.shared.infrastructure.heartbeat import HEARTBEAT_PREFIX

router = APIRouter(tags=["Plateforme EduSync — santé"])
STARTED_AT = datetime.now(timezone.utc)
WORKERS = (("outbox", "Diffusion des événements"), ("communications", "Envoi des SMS"))
RANK = {"OK": 0, "NOT_CONFIGURED": 1, "DEGRADED": 2, "DOWN": 3}
MEASURE_TTL = 5.0
_cache: dict = {"at": 0.0, "body": None}
_lock = threading.Lock()
# What each component relies on (known architecture, not a guess about business impact).
DEPENDS = {"host": [], "api": ["database", "redis"], "worker_outbox": ["database", "redis"], "worker_communications": ["database", "redis"],
           "storage": [], "errors": ["redis"], "backup": ["database", "storage"], "database": [], "redis": [], "messaging": ["worker_communications"]}
P95_SLOW_MS = 2500        # p95 beyond the last latency bucket over 5 minutes: the API is slow (technical threshold, documented)
CHANNELS = (("SMS", "sms", "SMS"), ("EMAIL", "email", "E-mail"), ("PUSH", "push", "Notifications push"))
PROVIDER_LABEL = {"CONFIGURED": "Configuré", "SIMULATED": "Simulé (jamais certifié)", "DISABLED": "Désactivé", "INCOMPLETE": "Configuration incomplète",
                  "REFUSED": "Refusé (simulation interdite en production)"}


def _redis(services: AppServices):
    import redis
    return redis.Redis.from_url(services.settings.redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)


def _saturation(services: AppServices) -> dict | None:
    """Database connection pool of this API process (in use / capacity): the saturation signal."""
    try:
        eng = services.platform_db.engine
        eng = eng() if callable(eng) else eng
        pool = eng.pool
        size, used = int(pool.size()), int(pool.checkedout())
        cap = size + max(0, int(getattr(pool, "_max_overflow", 0) or 0))
        return {"db_pool_in_use": used, "db_pool_capacity": cap, "db_pool_ratio": round(used / cap, 2) if cap else None}
    except Exception:  # noqa: BLE001
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def _age(iso: str | None) -> int | None:
    if not iso:
        return None
    return int((datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds())


def _human_age(seconds: int | None) -> str:
    if seconds is None:
        return "aucun signal"
    if seconds < 90:
        return f"il y a {seconds} s"
    if seconds < 5400:
        return f"il y a {seconds // 60} min"
    return f"il y a {seconds // 3600} h"


def backup_component(services: AppServices) -> dict:
    """State of the last automatic backup (status file written by the backup service). Shared with the dashboard."""
    status_file = services.settings.backup_status_file or os.environ.get("EDUSYNC_BACKUP_STATUS_FILE", "")
    backup = {"key": "backup", "label": "Dernière sauvegarde", "state": "NOT_CONFIGURED",
              "detail": "Aucune sauvegarde automatique configurée sur ce serveur", "measured_ms": None, "measured_at": _now()}
    if status_file and Path(status_file).is_file():
        try:
            info = json.loads(Path(status_file).read_text(encoding="utf-8"))
            age = _age(info.get("finished_at"))
            if age is not None and age < -60:
                raise ValueError("date future")      # an invalid timestamp is never shown as a fresh backup
            ok = bool(info.get("ok")) and age is not None
            late = ok and age >= 26 * 3600           # the backup runs daily (deploy/backup): beyond 26 h it is late
            backup.update(state="OK" if ok and not late else "DEGRADED" if ok else "DOWN",
                          detail=(f"Réussie {_human_age(age)}" if ok else "Dernière tentative en échec") + (" · sauvegarde en retard" if late else "")
                          + (" · restauration vérifiée" if info.get("restore_verified") else ""),
                          backup={"finished_at": info.get("finished_at"), "ok": bool(info.get("ok")), "late": bool(late),
                                  "restore_verified": bool(info.get("restore_verified")), "offsite": bool(info.get("offsite")),
                                  "message": str(info.get("detail") or "")[:160],
                                  "duration_seconds": info.get("duration_seconds") if isinstance(info.get("duration_seconds"), int) else None,
                                  "restore_seconds": info.get("restore_seconds") if isinstance(info.get("restore_seconds"), int) else None})
        except Exception:  # noqa: BLE001
            backup.update(state="DOWN", detail="Rapport de sauvegarde illisible")
    return backup


@router.get("/health")
def system_health(actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require("platform.health.read")
    with _lock:   # concurrent requests wait for the measurement in progress and share it
        if _cache["body"] is not None and time.monotonic() - _cache["at"] < MEASURE_TTL:
            return {**_cache["body"], "shared": True}
        body = measure(services)
        _cache.update(at=time.monotonic(), body=body)
        return {**body, "shared": False}


def measure(services: AppServices) -> dict:
    components: list[dict] = []
    uptime = int((datetime.now(timezone.utc) - STARTED_AT).total_seconds())
    api = {"key": "api", "label": "Serveur d’application", "state": "OK",
           "detail": f"En service depuis {_human_age(uptime).replace('il y a ', '')}", "measured_ms": 0, "started_at": STARTED_AT.isoformat()}
    components.append(api)
    from edusync.modules.platform_health.application.host import host_component
    components.append(host_component(services.settings))

    # PostgreSQL: real round trip + a few real figures.
    queue = {}
    try:
        t0 = time.perf_counter()
        with services.platform_db.platform_transaction() as c:
            c.execute(text("SELECT 1")).scalar_one()
            latency = _ms(t0)
            queue = dict(c.execute(text("""SELECT
                (SELECT count(*) FROM outbox_events WHERE published_at IS NULL AND dead_lettered_at IS NULL) AS outbox_pending,
                (SELECT extract(epoch FROM now()-min(created_at))::int FROM outbox_events WHERE published_at IS NULL AND dead_lettered_at IS NULL) AS outbox_oldest_s,
                (SELECT count(*) FROM outbox_events WHERE published_at IS NULL AND dead_lettered_at IS NOT NULL) AS outbox_dead,
                (SELECT count(*) FROM communication_deliveries WHERE status IN ('PENDING','QUEUED')) AS sms_pending,
                (SELECT count(*) FROM communication_deliveries WHERE status='FAILED' AND attempts>=5) AS sms_dead,
                (SELECT count(*) FROM schools WHERE status='ACTIVE') AS schools_active,
                (SELECT count(*) FROM user_device_sessions WHERE revoked_at IS NULL) AS sessions_open""")).mappings().one())
        state = "OK" if latency < 250 else "DEGRADED"
        components.append({"key": "database", "label": "Base de données", "state": state,
                           "detail": f"Répond en {latency} ms" + (" (lente)" if state == "DEGRADED" else ""), "measured_ms": latency})
    except Exception:  # noqa: BLE001 — the health screen reports, it never fails
        components.append({"key": "database", "label": "Base de données", "state": "DOWN", "detail": "Injoignable", "measured_ms": None})

    # Redis: real PING, then worker heartbeats and server error counters.
    r = None
    try:
        import redis
        r = redis.Redis.from_url(services.settings.redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
        t0 = time.perf_counter()
        r.ping()
        latency = _ms(t0)
        components.append({"key": "redis", "label": "Cache et files rapides", "state": "OK" if latency < 100 else "DEGRADED",
                           "detail": f"Répond en {latency} ms", "measured_ms": latency})
    except Exception:  # noqa: BLE001
        r = None
        components.append({"key": "redis", "label": "Cache et files rapides", "state": "DOWN", "detail": "Injoignable", "measured_ms": None})

    for name, label in WORKERS:
        age = None
        if r is not None:
            try:
                age = _age(r.get(HEARTBEAT_PREFIX + name))
            except Exception:  # noqa: BLE001
                age = None
        state = "OK" if age is not None and age < 60 else "DEGRADED" if age is not None and age < 300 else "DOWN"
        detail = f"Dernier signal {_human_age(age)}"
        if name == "outbox" and queue:
            detail += f" · {queue['outbox_pending']} événement(s) en attente"
            if queue.get("outbox_oldest_s") and queue["outbox_oldest_s"] > 300:
                state = max(state, "DEGRADED", key=RANK.get)
                detail += f", le plus ancien {_human_age(queue['outbox_oldest_s'])}"
            if queue.get("outbox_dead"):
                state = max(state, "DEGRADED", key=RANK.get)
                detail += f" · {queue['outbox_dead']} en quarantaine (intervention requise)"
        if name == "communications" and queue:
            detail += f" · {queue['sms_pending']} SMS en attente, {queue['sms_dead']} définitivement non envoyé(s)"
        comp = {"key": f"worker_{name}", "label": label, "state": state, "detail": detail, "measured_ms": None, "age_seconds": age}
        if name == "outbox" and queue:
            comp["queue"] = {"pending": queue["outbox_pending"], "failed": queue["outbox_dead"], "oldest_seconds": queue.get("outbox_oldest_s")}
        if name == "communications" and queue:
            from edusync.shared.messaging.factory import channel_status
            sms = channel_status(services.settings)["sms"]
            comp["queue"] = {"pending": queue["sms_pending"], "failed": queue["sms_dead"], "oldest_seconds": None}
            comp["provider"] = {"state": sms["state"]}          # never a credential, never a token
            if sms["state"] in ("DISABLED", "INCOMPLETE", "REFUSED") and state != "DOWN":
                comp["detail"] += " · fournisseur SMS " + {"DISABLED": "désactivé", "INCOMPLETE": "incomplet", "REFUSED": "refusé (simulation en production)"}[sms["state"]]
        components.append(comp)

    # Object storage: a real signed HEAD request.
    storage = getattr(services, "object_storage", None)
    if storage is None:
        components.append({"key": "storage", "label": "Stockage des documents", "state": "NOT_CONFIGURED",
                           "detail": "Aucun stockage objet configuré : les documents ne sont pas archivés", "measured_ms": None})
    else:
        try:
            t0 = time.perf_counter()
            storage.exists("health/probe")
            latency = _ms(t0)
            components.append({"key": "storage", "label": "Stockage des documents", "state": "OK" if latency < 500 else "DEGRADED",
                               "detail": f"Répond en {latency} ms", "measured_ms": latency})
        except Exception:  # noqa: BLE001
            components.append({"key": "storage", "label": "Stockage des documents", "state": "DOWN", "detail": "Injoignable", "measured_ms": None})

    # Golden signals and grouped errors (signals.py). CURRENT health = errors active within the last 5 minutes;
    # the 24 h history informs and never degrades the current state.
    golden = groups = None
    if r is not None:
        try:
            golden = {"last_5m": signals.window(r, 5), "last_1h": signals.window(r, 60), "last_24h": signals.window(r, 60 * 24)}
            groups = signals.error_groups(r, since_hours=24)
        except Exception:  # noqa: BLE001
            golden = groups = None
    if golden is not None:
        w5 = golden["last_5m"]
        api["signals"] = {**golden, "saturation": _saturation(services)}
        if w5["latency_p95_over"]:
            api.update(state="DEGRADED", detail=api["detail"] + f" · lent : 95 % des requêtes au-delà de {P95_SLOW_MS / 1000:g} s sur 5 min")
        elif w5["requests"]:
            api["detail"] += f" · {w5['per_minute']:g} req/min · p95 ≤ {w5['latency_p95_ms']} ms"
    if groups is None:
        components.append({"key": "errors", "label": "Erreurs serveur", "state": "NOT_CONFIGURED",
                           "detail": "Compteur indisponible (cache injoignable)", "value": None})
    else:
        cur = signals.errors_state(groups, golden["last_1h"], golden["last_24h"])
        active = [g for g in groups if g["active"]]
        components.append({"key": "errors", "label": "Erreurs serveur", "state": cur["state"], "detail": cur["explain"],
                           "value": golden["last_24h"]["server_errors"],
                           "errors": {"current_state": cur["state"], "active_groups": cur["active_groups"],
                                      "last_hour": golden["last_1h"]["server_errors"], "last_24h": golden["last_24h"]["server_errors"],
                                      "refusals_24h": golden["last_24h"]["client_refusals"],
                                      "first_active_at": min((g["first_at"] for g in active), default=None),
                                      "last_at": max((g["last_at"] for g in groups), default=None),
                                      "active_window_seconds": signals.ACTIVE_WINDOW_S,
                                      "groups": [{k: g[k] for k in ("id", "method", "route", "status", "type", "active", "count_1h", "count_24h", "last_at")}
                                                 for g in groups[:8]]}})

    components.append(messaging_component(services))

    components.append(backup_component(services))

    checked = _now()
    for c in components:
        c.setdefault("measured_at", checked)
        c["depends_on"] = DEPENDS.get(c["key"], [])
    configured = [c for c in components if c["state"] != "NOT_CONFIGURED"]
    overall = max((c["state"] for c in configured), key=RANK.get, default="OK")
    # A degraded state is always explainable: every non-OK configured component becomes an alert with its reason.
    alerts = [{"key": c["key"], "severity": "critical" if c["state"] == "DOWN" else "warning", "title": c["label"], "explain": c["detail"],
               "since": (c.get("errors") or {}).get("first_active_at")} for c in configured if c["state"] != "OK"]
    return {"checked_at": checked, "overall": overall, "components": components, "refresh_seconds": 30, "measure_ttl_seconds": MEASURE_TTL,
            "alerts": alerts, "alert_delivery": "EMAIL",
            "summary": {"operational": sum(1 for c in configured if c["state"] == "OK"), "configured": len(configured),
                        "degraded": sum(1 for c in configured if c["state"] == "DEGRADED"), "down": sum(1 for c in configured if c["state"] == "DOWN"),
                        "not_configured": len(components) - len(configured)},
            "figures": {k: queue.get(k) for k in ("schools_active", "sessions_open")} if queue else {}}


def messaging_component(services: AppServices) -> dict:
    """Messaging providers: configuration state (never a credential), last real success and last failure per channel.
    A simulated provider is never shown as certified nor as operational: it is "not configured" for real sending."""
    from edusync.shared.messaging.factory import channel_status
    status = channel_status(services.settings)
    comp = {"key": "messaging", "label": "Fournisseurs de messagerie", "measured_ms": None, "providers": []}
    try:
        with services.platform_db.platform_transaction() as c:
            rows = {r["channel"]: dict(r) for r in c.execute(text("""SELECT channel,
                    max(coalesce(delivered_at, sent_at)) FILTER (WHERE status IN ('SENT','DELIVERED')) AS last_success,
                    max(failed_at) FILTER (WHERE status LIKE 'FAILED%') AS last_failure,
                    count(*) FILTER (WHERE status LIKE 'FAILED%' AND failed_at > now()-interval '15 minutes') AS failed_15m,
                    count(*) FILTER (WHERE status IN ('SENT','DELIVERED') AND coalesce(delivered_at, sent_at) > now()-interval '15 minutes') AS ok_15m,
                    (array_agg(last_error_code ORDER BY failed_at DESC) FILTER (WHERE status LIKE 'FAILED%'))[1] AS last_error_code
                FROM communication_deliveries WHERE created_at > now()-interval '7 days' GROUP BY channel""")).mappings()}
    except Exception:  # noqa: BLE001
        rows = None
    states = []
    for code, key, label in CHANNELS:
        st = status[key]["state"]
        row = (rows or {}).get(code, {})
        failing = bool(row.get("failed_15m")) and not row.get("ok_15m")
        state = "DOWN" if st == "REFUSED" else "DEGRADED" if st == "INCOMPLETE" or (st == "CONFIGURED" and failing) else \
            "OK" if st == "CONFIGURED" else "NOT_CONFIGURED"
        states.append(state)
        comp["providers"].append({"channel": code, "label": label, "config_state": st, "config_label": PROVIDER_LABEL.get(st, st), "state": state,
                                  "certified": False if st != "CONFIGURED" else None,
                                  "last_success_at": row["last_success"].isoformat() if row.get("last_success") else None,
                                  "last_failure_at": row["last_failure"].isoformat() if row.get("last_failure") else None,
                                  "last_error_code": row.get("last_error_code"), "failures_15m": int(row.get("failed_15m") or 0)})
    configured = [x for x in states if x != "NOT_CONFIGURED"]
    comp["state"] = max(configured, key=RANK.get) if configured else "NOT_CONFIGURED"
    if rows is None:
        comp["detail"] = "Historique des envois illisible (base injoignable)"
    elif not configured:
        comp["detail"] = "Aucun fournisseur réel configuré (simulation ou désactivé) : aucun envoi réel"
    else:
        bad = [p["label"] for p in comp["providers"] if p["state"] in ("DEGRADED", "DOWN")]
        comp["detail"] = ("En difficulté : " + ", ".join(bad)) if bad else "Fournisseurs configurés, aucun échec récent"
    return comp


def _signals_or_503(services: AppServices):
    try:
        r = _redis(services)
        r.ping()
        return r
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="Signaux indisponibles (cache injoignable). Réessayez dans un instant.")


@router.get("/health/errors")
def health_errors(window: str = Query("24h", pattern="^(1h|24h|7d)$"), actor: ActorContext = Depends(require_platform_actor),
                  services: AppServices = Depends(get_services)):
    """Error groups of the window (active first), with the 1 h / 24 h / 7 d counts. Redacted: no value, no identifier."""
    actor.require("platform.health.read")
    r = _signals_or_503(services)
    groups = signals.error_groups(r, since_hours={"1h": 1, "24h": 24, "7d": 24 * 7}[window])
    groups = [g for g in groups if g["active"]] + sorted([g for g in groups if not g["active"]], key=lambda g: g["last_at"] or "", reverse=True)
    return {"window": window, "groups": groups, "active_window_seconds": signals.ACTIVE_WINDOW_S, "measured_at": _now()}


@router.get("/health/errors/{group_id}")
def health_error_detail(group_id: str, actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require("platform.health.read")
    r = _signals_or_503(services)
    g = signals.error_group(r, group_id)
    if g is None:
        raise HTTPException(status_code=404, detail="Groupe d’erreurs introuvable ou expiré (conservation : 7 jours)")
    day = signals.window(r, 60 * 24)
    g["impact"] = {"share_of_errors_24h": round(g["count_24h"] / day["server_errors"], 2) if day["server_errors"] else None,
                   "requests_24h": day["requests"]}
    g["audit_link"] = "NOT_AVAILABLE"      # a server error is not an audited business action: no audit entry to open
    return {**g, "measured_at": _now()}


class RecipientInput(BaseModel):
    email: str = Field(min_length=6, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    label: str | None = Field(default=None, max_length=120)


@router.get("/health/incidents")
def health_incidents(actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    """Incidents (components « Hors service »), open first, then the 50 latest; and who receives the alerts."""
    actor.require("platform.health.read")
    with services.platform_db.platform_transaction() as conn:
        rows = conn.execute(text("""SELECT id, component_key, component_label, explain, opened_at, notified_at, resolved_at, resolution_notified_at
            FROM platform_incidents ORDER BY (resolved_at IS NULL) DESC, opened_at DESC LIMIT 50""")).mappings().all()
        extra = conn.execute(text("SELECT id, email, label, created_at FROM platform_alert_recipients WHERE active ORDER BY created_at")).mappings().all()
        managers = conn.execute(text("""SELECT count(DISTINCT u.id) FROM users u JOIN rbac_assignments a ON a.user_id=u.id AND a.school_id IS NULL AND a.active
            JOIN rbac_roles r ON r.id=a.role_id AND r.code='MANAGER_SYSTEME' AND r.status='ACTIVE' WHERE u.active AND u.email IS NOT NULL""")).scalar()
    can_manage = "platform.collaborators.manage" in actor.permissions
    iso = lambda v: v.isoformat() if v else None  # noqa: E731
    return {"incidents": [{**{k: str(r[k]) if k == "id" else r[k] for k in ("id", "component_key", "component_label", "explain")},
                           **{k: iso(r[k]) for k in ("opened_at", "notified_at", "resolved_at", "resolution_notified_at")},
                           "duration_seconds": int(((r["resolved_at"] or datetime.now(timezone.utc)) - r["opened_at"]).total_seconds())} for r in rows],
            "recipients": {"managers": int(managers or 0), "can_manage": can_manage,
                           "extra": [{"id": str(r["id"]), "email": r["email"] if can_manage else _mask(r["email"]), "label": r["label"],
                                      "created_at": iso(r["created_at"])} for r in extra]},
            "delay_seconds": services.settings.platform_alert_delay_seconds, "enabled": services.settings.platform_alerts_enabled,
            "measured_at": _now()}


def _mask(email: str) -> str:
    name, _, domain = email.partition("@")
    return (name[:2] + "…@" + domain) if domain else "…"


@router.post("/health/alert-recipients", status_code=201)
def add_alert_recipient(body: RecipientInput, actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    """A Manager adds an on-call address (step-up: it receives incident details)."""
    actor.require("platform.collaborators.manage")
    require_recent_mfa(services, actor, "platform.collaborators.manage")
    email = body.email.strip().lower()
    with services.platform_db.platform_transaction() as conn:
        if conn.execute(text("SELECT count(*) FROM platform_alert_recipients WHERE active")).scalar() >= 10:
            raise HTTPException(status_code=409, detail="10 adresses au maximum.")
        row = conn.execute(text("""INSERT INTO platform_alert_recipients(email, label, added_by_user_id) VALUES (:e, :l, :u)
            ON CONFLICT (lower(email)) WHERE active DO NOTHING RETURNING id"""), {"e": email, "l": (body.label or "").strip() or None, "u": str(actor.user_id)}).first()
        if row is None:
            raise HTTPException(status_code=409, detail="Cette adresse reçoit déjà les alertes.")
        _audit(conn, actor, "PLATFORM_ALERT_RECIPIENT_ADDED", row[0], {"email": _mask(email)})
    return {"id": str(row[0])}


@router.post("/health/alert-recipients/{recipient_id}/remove")
def remove_alert_recipient(recipient_id: str, actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require("platform.collaborators.manage")
    require_recent_mfa(services, actor, "platform.collaborators.manage")
    try:
        rid = str(uuid.UUID(recipient_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Adresse introuvable")
    with services.platform_db.platform_transaction() as conn:
        row = conn.execute(text("""UPDATE platform_alert_recipients SET active=false, removed_at=now(), removed_by_user_id=:u
            WHERE id=:id AND active RETURNING email"""), {"id": rid, "u": str(actor.user_id)}).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Adresse introuvable")
        _audit(conn, actor, "PLATFORM_ALERT_RECIPIENT_REMOVED", rid, {"email": _mask(row[0])})
    return {"status": "removed"}


@router.post("/health/alerts/test")
def test_alert(actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    """Sends a test e-mail to every recipient: proves the alert chain end to end (outbox → worker → provider)."""
    actor.require("platform.collaborators.manage")
    from edusync.modules.platform_health.application.alerts import recipients
    from edusync.modules.communications.application.messaging import Recipient, request_message
    with services.platform_db.platform_transaction() as conn:
        people = recipients(conn)
        if not people:
            raise HTTPException(status_code=409, detail="Aucun destinataire d’alerte.")
        request_message(conn, school_id=None, kind="PLATFORM", channels=["EMAIL"], template_code="PLATFORM_ALERT",
                        subject="[EduSync] Test des alertes", created_by=actor.user_id,
                        body="Ceci est un test : si vous lisez ce message, les alertes de la plateforme EduSync vous parviennent.",
                        recipients=[Recipient("USER", p["user_id"] or uuid.uuid5(uuid.NAMESPACE_URL, "alert:" + p["email"]), p["name"],
                                              email=p["email"], user_id=p["user_id"]) for p in people],
                        idempotency_key=f"platform-alert-test:{uuid.uuid4()}")
        _audit(conn, actor, "PLATFORM_ALERT_TEST_SENT", actor.user_id, {"recipients": len(people)})
    return {"recipients": len(people)}


def _audit(conn, actor, action: str, entity_id, detail: dict) -> None:
    conn.execute(text("""INSERT INTO audit_events(school_id, actor_user_id, action, entity_type, entity_id, source, result, new_json)
        VALUES (NULL, :a, :act, 'PlatformAlerts', :e, 'WEB', 'SUCCESS', CAST(:d AS jsonb))"""),
        {"a": str(actor.user_id), "act": action, "e": str(entity_id), "d": json.dumps(detail)})


@router.get("/health/history")
def health_history(span: str = Query("1h", pattern="^(1h|24h|7d)$"), actor: ActorContext = Depends(require_platform_actor),
                   services: AppServices = Depends(get_services)):
    """Short history of the golden signals: 1 h per minute, 24 h / 7 d per hour (kept 26 h / 8 days)."""
    actor.require("platform.health.read")
    r = _signals_or_503(services)
    return {"span": span, "points": signals.history(r, span), "measured_at": _now()}
