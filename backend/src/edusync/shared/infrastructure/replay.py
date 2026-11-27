"""When was an operation really made? (owner, 2026-11-27 — protections of the cash desk.)

An operation made offline is sent later by the device's outbox (header « X-EduSync-Replay: outbox ») with the moment it
was really made on the device (« X-EduSync-Made-At », ISO 8601). The cash rules use it so that a payment made offline
yesterday evening still goes into yesterday's session this morning, while a payment made this morning into yesterday's
forgotten session is refused. A device that does not send the moment yet (older version) is never refused for it.
"""
from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime

_replay: ContextVar[bool] = ContextVar("edusync_replay", default=False)
_made_at: ContextVar[datetime | None] = ContextVar("edusync_replay_made_at", default=None)


def is_replay() -> bool:
    return _replay.get()


def made_at() -> datetime | None:
    return _made_at.get()


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else None                 # a moment without its zone cannot be placed in a day


class ReplayContextMiddleware:
    """Pure ASGI: sets the two values for the request (copied into the worker thread of a sync endpoint)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        t1 = _replay.set(headers.get("x-edusync-replay", "").strip().lower() == "outbox")
        t2 = _made_at.set(_parse(headers.get("x-edusync-made-at")) if t1 and _replay.get() else None)
        try:
            await self.app(scope, receive, send)
        finally:
            _made_at.reset(t2)
            _replay.reset(t1)
