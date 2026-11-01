"""School live changes (owner, 2026-11-01): after every SUCCESSFUL school write — through any route, including the
offline replays of the devices — a signal naming the touched domains is published on the school channel (see
realtime.py). One place for the whole API: no route has to remember to publish. Best effort, never blocks the answer."""
from __future__ import annotations

import asyncio

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from edusync.shared.infrastructure.realtime import live_domains, publish_school_changed


class LiveChangesMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, redis_url: str | None):
        super().__init__(app)
        self.redis_url = redis_url

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if not self.redis_url or not 200 <= response.status_code < 300:
            return response
        school_id = getattr(request.state, "live_school_id", None)
        domains = live_domains(request.method, request.url.path) if school_id else ()
        if domains:
            asyncio.get_running_loop().run_in_executor(None, publish_school_changed, self.redis_url, school_id, domains)
        return response
