"""Operational signals kept in Redis for the platform health screen (best effort, never blocks business work).

* worker heartbeats: `edusync:heartbeat:<worker>` = ISO timestamp, refreshed at most every 10 s, expires after 10 min;
* server errors: `edusync:errors:5xx:<YYYYMMDDHH>` hourly counters, kept 3 days.
Nothing sensitive is stored: no path parameters, no user, no payload.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

HEARTBEAT_PREFIX = "edusync:heartbeat:"
ERRORS_PREFIX = "edusync:errors:5xx:"
_last_beat: dict[str, float] = {}


def beat(r, worker: str) -> None:
    now = time.monotonic()
    if now - _last_beat.get(worker, 0.0) < 10:
        return
    try:
        r.set(HEARTBEAT_PREFIX + worker, datetime.now(timezone.utc).isoformat(), ex=600)
        _last_beat[worker] = now
    except Exception:  # noqa: BLE001 — a heartbeat must never stop a worker
        pass


def record_server_error(r) -> None:
    key = ERRORS_PREFIX + datetime.now(timezone.utc).strftime("%Y%m%d%H")
    try:
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, 3 * 24 * 3600)
        pipe.execute()
    except Exception:  # noqa: BLE001 — observability is best effort
        pass


def server_errors_last_24h(r) -> int:
    now = datetime.now(timezone.utc)
    keys = [ERRORS_PREFIX + datetime.fromtimestamp(now.timestamp() - h * 3600, timezone.utc).strftime("%Y%m%d%H") for h in range(24)]
    return sum(int(v or 0) for v in r.mget(keys))
