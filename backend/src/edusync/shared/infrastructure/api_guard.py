from __future__ import annotations

from starlette.responses import JSONResponse


class ApiGuardMiddleware:
    """Bound request shapes before FastAPI parses personal/financial payloads.

    The middleware deliberately buffers request bodies because EduSync currently has no
    streaming business endpoint. This also closes the chunked-transfer loophole where a
    missing Content-Length could previously bypass the generic size guard.

    Normal API mutations keep the strict configured limit. The three official XLSX
    analysis endpoints receive a narrowly-scoped 10 MiB ceiling matching the import
    contract; their own parser applies the same limit and row-count limits afterwards.
    """

    IMPORT_MAX_BODY_BYTES = 10 * 1024 * 1024
    IMPORT_ANALYZE_PATHS = frozenset({
        "/api/v1/import/students/analyze",
        "/api/v1/import/staff/analyze",
        "/api/v1/import/finance-history/analyze",
    })

    def __init__(self, app, *, max_body_bytes: int = 2_097_152, max_query_bytes: int = 8_192):
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.max_query_bytes = max_query_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if len(scope.get("query_string", b"")) > self.max_query_bytes:
            await JSONResponse(status_code=414, content={"detail": "Requête trop longue"})(scope, receive, send)
            return

        path = scope.get("path", "")
        effective_limit = self.IMPORT_MAX_BODY_BYTES if path in self.IMPORT_ANALYZE_PATHS else self.max_body_bytes
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        raw_length = headers.get(b"content-length")
        if raw_length:
            try:
                if int(raw_length) > effective_limit:
                    await JSONResponse(status_code=413, content={"detail": "Corps de requête trop volumineux"})(scope, receive, send)
                    return
            except ValueError:
                await JSONResponse(status_code=400, content={"detail": "Content-Length invalide"})(scope, receive, send)
                return

        # Pre-read body-bearing requests with a hard byte counter. This bounds chunked
        # requests too; no downstream JSON/XLSX parser can allocate an unbounded body.
        if scope.get("method", "GET").upper() in {"POST", "PUT", "PATCH"}:
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                if message["type"] != "http.request":
                    continue
                body.extend(message.get("body", b""))
                if len(body) > effective_limit:
                    await JSONResponse(status_code=413, content={"detail": "Corps de requête trop volumineux"})(scope, receive, send)
                    return
                if not message.get("more_body", False):
                    break
            replayed = False
            async def replay_receive():
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return {"type": "http.disconnect"}
            receive = replay_receive

        async def secure_send(message):
            if message["type"] == "http.response.start" and path.startswith("/api/"):
                headers_list = list(message.get("headers", []))
                headers_list = [(k, v) for k, v in headers_list if k.lower() not in {b"cache-control", b"pragma"}]
                headers_list.extend([(b"Cache-Control", b"no-store"), (b"Pragma", b"no-cache")])
                message["headers"] = headers_list
            await send(message)

        await self.app(scope, receive, secure_send)
