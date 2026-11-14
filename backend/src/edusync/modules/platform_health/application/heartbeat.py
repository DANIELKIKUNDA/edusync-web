"""Signal de vie externe (owner, 2026-11-14): alerts that do NOT depend on the monitored server.

The incident e-mails of alerts.py leave from the server itself: if the VPS, PostgreSQL or the e-mail provider fail,
nobody is told. Here the API sends, about once a minute, a « dead man's switch » ping to an external service
(Healthchecks.io or any compatible endpoint): a plain GET when everything is fine, POST <url>/fail with the reasons when
a component has been « Hors service » for longer than the alert delay. When the server, the network or the API stop,
the pings stop and the EXTERNAL service alerts the owner (e-mail, Telegram, SMS… configured there, not here).

The state is kept in memory (no database needed: a database failure must still be reported). The URL holds a secret
identifier: it is never logged. Only https URLs are used. Every error is swallowed: the API keeps serving.
"""
from __future__ import annotations

import logging
import time
import urllib.request
from typing import Any

log = logging.getLogger("edusync.heartbeat")
_down_since: dict[str, float] = {}
_last_sent: dict[str, float] = {"at": float("-inf")}
_warned = {"bad_url": False}


def failing(body: dict, *, delay: float, now: float) -> list[dict]:
    """Components « Hors service » continuously for at least `delay` seconds (same rule as the incident e-mails)."""
    down = {c["key"]: c for c in body.get("components", []) if c.get("state") == "DOWN"}
    for key in list(_down_since):
        if key not in down:
            del _down_since[key]
    for key in down:
        _down_since.setdefault(key, now)
    return [down[k] for k in down if now - _down_since[k] >= delay]


def message(failed: list[dict]) -> str:
    return "\n".join(f"{c.get('label', c['key'])} : {c.get('detail', '')}"[:300] for c in failed)


def _http(url: str, data: bytes | None) -> None:
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET",
                                 headers={"User-Agent": "edusync-heartbeat", "Content-Type": "text/plain; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=10) as r:   # noqa: S310 — https enforced by beat()
        r.read(256)


def beat(settings: Any, body: dict | None, *, now: float | None = None, send=_http) -> str:
    """One heartbeat. Returns what was done: disabled / throttled / ok / fail / error."""
    url = (settings.heartbeat_url or "").strip()
    if not url:
        return "disabled"
    if not url.startswith("https://"):
        if not _warned["bad_url"]:
            log.warning("EDUSYNC_HEARTBEAT_URL ignorée : seule une adresse https est acceptée")
            _warned["bad_url"] = True
        return "disabled"
    now = time.time() if now is None else now
    failed = failing(body or {"components": [{"key": "api", "label": "Serveur d’application", "state": "DOWN",
                                              "detail": "Mesure de santé impossible"}]},
                     delay=settings.platform_alert_delay_seconds, now=now)
    if now - _last_sent["at"] < settings.heartbeat_interval_seconds and not failed:
        return "throttled"
    try:
        if failed:
            send(url.rstrip("/") + "/fail", message(failed).encode("utf-8"))
        else:
            send(url, None)
        _last_sent["at"] = now
        return "fail" if failed else "ok"
    except Exception as exc:  # noqa: BLE001 — never the URL in the logs
        log.warning("signal de vie externe non envoyé (%s)", type(exc).__name__)
        return "error"
