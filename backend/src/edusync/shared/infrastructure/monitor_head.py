"""HEAD on the monitoring addresses only (owner, 2026-11-21).

Free uptime monitors (UptimeRobot) probe with HEAD. FastAPI answers 405 to HEAD on a GET route, so the monitors
reported the site DOWN while it was up. HEAD is answered like GET, without the body, but ONLY for the read-only
monitoring addresses: some GET routes have effects (an export archives the generated document) and a probe must never
trigger them.
"""
from __future__ import annotations

MONITOR_HEAD_PATHS = frozenset({"/health", "/api/v1/setup/status"})


class MonitorHeadMiddleware:
    def __init__(self, app, *, paths: frozenset[str] = MONITOR_HEAD_PATHS):
        self.app = app
        self.paths = paths

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "HEAD" or scope.get("path") not in self.paths:
            await self.app(scope, receive, send)
            return

        async def send_without_body(message):
            if message["type"] == "http.response.body":
                if message.get("more_body", False):
                    return                                   # swallow every body chunk
                message = {"type": "http.response.body", "body": b"", "more_body": False}
            await send(message)

        await self.app({**scope, "method": "GET"}, receive, send_without_body)
