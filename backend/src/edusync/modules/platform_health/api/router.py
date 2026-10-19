"""Plateforme EduSync — system health with real measurements (N1 certification 2026-10, État du service lot 2026-10).

Every figure is measured at request time or read from a real signal; nothing is estimated or invented.
A component that is not configured is reported as such (never as healthy). States are the existing ones:
OK / DEGRADED / DOWN / NOT_CONFIGURED; the overall state is the worst configured component.
Freshness: each component carries measured_at (the instant of its own measurement) and, for the workers, the age of
their last heartbeat. Concurrent or repeated requests within MEASURE_TTL seconds share one measurement (no storm of
checks: 50 clicks or tabs cost one round of checks). Not available (no history is stored): uptime, short history,
incidents, planned maintenance, backup size.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import text

from edusync.bootstrap.dependencies import get_services, require_platform_actor
from edusync.bootstrap.services import AppServices
from edusync.shared.application.context import ActorContext
from edusync.shared.infrastructure.heartbeat import HEARTBEAT_PREFIX, server_errors_last_24h

router = APIRouter(tags=["Plateforme EduSync — santé"])
STARTED_AT = datetime.now(timezone.utc)
WORKERS = (("outbox", "Diffusion des événements"), ("communications", "Envoi des SMS"))
RANK = {"OK": 0, "NOT_CONFIGURED": 1, "DEGRADED": 2, "DOWN": 3}
MEASURE_TTL = 5.0
_cache: dict = {"at": 0.0, "body": None}
_lock = threading.Lock()
# What each component relies on (known architecture, not a guess about business impact).
DEPENDS = {"api": ["database", "redis"], "worker_outbox": ["database", "redis"], "worker_communications": ["database", "redis"],
           "storage": [], "errors": ["redis"], "backup": ["database", "storage"], "database": [], "redis": []}


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
                                  "message": str(info.get("detail") or "")[:160]})
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
    components.append({"key": "api", "label": "Serveur d’application", "state": "OK",
                       "detail": f"En service depuis {_human_age(uptime).replace('il y a ', '')}", "measured_ms": 0, "started_at": STARTED_AT.isoformat()})

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

    errors = None
    if r is not None:
        try:
            errors = server_errors_last_24h(r)
        except Exception:  # noqa: BLE001
            errors = None
    components.append({"key": "errors", "label": "Erreurs serveur (24 h)",
                       "state": "NOT_CONFIGURED" if errors is None else "OK" if errors == 0 else "DEGRADED" if errors < 20 else "DOWN",
                       "detail": "Compteur indisponible (cache injoignable)" if errors is None else f"{errors} erreur(s) inattendue(s)", "value": errors})

    components.append(backup_component(services))

    checked = _now()
    for c in components:
        c.setdefault("measured_at", checked)
        c["depends_on"] = DEPENDS.get(c["key"], [])
    configured = [c for c in components if c["state"] != "NOT_CONFIGURED"]
    overall = max((c["state"] for c in configured), key=RANK.get, default="OK")
    return {"checked_at": checked, "overall": overall, "components": components, "refresh_seconds": 30, "measure_ttl_seconds": MEASURE_TTL,
            "summary": {"operational": sum(1 for c in configured if c["state"] == "OK"), "configured": len(configured),
                        "degraded": sum(1 for c in configured if c["state"] == "DEGRADED"), "down": sum(1 for c in configured if c["state"] == "DOWN"),
                        "not_configured": len(components) - len(configured)},
            "figures": {k: queue.get(k) for k in ("schools_active", "sessions_open")} if queue else {}}
