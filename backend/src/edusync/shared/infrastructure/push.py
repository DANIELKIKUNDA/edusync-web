"""Push notification abstraction (N1 certification 2026-10).

No real provider is wired: real Web Push / Firebase delivery needs external accounts and keys (BLOCKED_EXTERNAL).
* `disabled` (default): nothing is sent; the in-app notification remains the source of truth.
* `mock`: records what would be sent in Redis (`edusync:push:mock`, last 200 entries) for local certification.
A push carries only a title, a severity and an internal link: never the body, never personal data.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

MOCK_KEY = "edusync:push:mock"


@dataclass(frozen=True)
class PushResult:
    accepted: bool
    reason: str = ""


class PushProvider(Protocol):
    name: str

    def send(self, subscription: dict, payload: dict) -> PushResult: ...


class DisabledPushProvider:
    name = "disabled"

    def send(self, subscription: dict, payload: dict) -> PushResult:
        return PushResult(False, "PUSH_DISABLED")


class MockPushProvider:
    name = "mock"

    def __init__(self, redis_url: str):
        import redis
        self._r = redis.Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)

    def send(self, subscription: dict, payload: dict) -> PushResult:
        entry = {"at": datetime.now(timezone.utc).isoformat(), "subscription_id": str(subscription["id"]),
                 "user_id": str(subscription["user_id"]), "title": payload.get("title", "")[:180],
                 "severity": payload.get("severity", "INFO"), "link": payload.get("link")}
        try:
            pipe = self._r.pipeline()
            pipe.lpush(MOCK_KEY, json.dumps(entry, ensure_ascii=False))
            pipe.ltrim(MOCK_KEY, 0, 199)
            pipe.execute()
            return PushResult(True)
        except Exception:  # noqa: BLE001 — push is best effort; the in-app notification already exists
            return PushResult(False, "MOCK_UNAVAILABLE")


def build_push_provider(settings) -> PushProvider:
    if (getattr(settings, "push_provider", "") or "disabled").lower() == "mock":
        return MockPushProvider(settings.redis_url)
    return DisabledPushProvider()
