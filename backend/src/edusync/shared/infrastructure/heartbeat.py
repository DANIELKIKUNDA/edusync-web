"""Operational signals kept in Redis for the platform health screen (best effort, never blocks business work).

* worker heartbeats: `edusync:heartbeat:<worker>` = ISO timestamp, refreshed at most every 10 s, expires after 10 min;
Server errors, traffic and latency live in signals.py (grouped errors, golden signals).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

HEARTBEAT_PREFIX = "edusync:heartbeat:"
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
