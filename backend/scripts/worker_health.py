"""Docker healthcheck of an EduSync worker (owner, 2026-11-21: Coolify showed « Running (no healthcheck) »).

A worker is healthy when its own heartbeat (edusync:heartbeat:<worker>, written by every loop turn, see
shared/infrastructure/heartbeat.py) is younger than 5 minutes — the same rule as the « État du service » screen.
Reads Redis only; no secret is needed or printed. Exit 0 = healthy, 1 = unhealthy.

    python scripts/worker_health.py outbox|communications
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

MAX_AGE_SECONDS = 300


def age_seconds(value: str | None, now: datetime | None = None) -> float | None:
    if not value:
        return None
    try:
        seen = datetime.fromisoformat(value)
    except ValueError:
        return None
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    return ((now or datetime.now(timezone.utc)) - seen).total_seconds()


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in {"outbox", "communications"}:
        print("Usage : python scripts/worker_health.py outbox|communications", file=sys.stderr)
        return 2
    import redis
    url = os.environ.get("EDUSYNC_REDIS_URL", "redis://redis:6379/0")
    try:
        value = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2).get(
            "edusync:heartbeat:" + argv[1])
    except Exception:  # noqa: BLE001 — Redis down: the worker cannot work either
        print("Redis injoignable", file=sys.stderr)
        return 1
    age = age_seconds(value)
    if age is None or age > MAX_AGE_SECONDS:
        print(f"{argv[1]} : aucun signal récent", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
