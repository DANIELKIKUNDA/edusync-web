"""Rate limiting of sensitive operations (N0/N1 hardening 2026-10).

Fixed windows in Redis, keyed by the authenticated account (verified access token) or, before authentication,
by a digest of the client address. Keys never contain a raw e-mail, address or token.
Sign-in keeps its dedicated per-account/per-address guard (LoginAttemptGuard).

Availability choice (documented in N0_N1_THREAT_MODEL.md): if Redis is unreachable the limiter lets the request
through — every limited operation is already authenticated (except first-run setup), authorised and audited.
"""
from __future__ import annotations

import hashlib
import re
import time

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# (method, path regex, bucket, max requests, window seconds)
RULES: tuple[tuple[str, re.Pattern, str, int, int], ...] = tuple((m, re.compile(p), b, n, w) for m, p, b, n, w in (
    ("POST", r"^/api/v1/setup/first-manager$", "setup", 10, 3600),
    ("POST", r"^/api/v1/auth/(platform/)?password$", "password", 10, 3600),
    ("POST", r"^/api/v1/auth/refresh$", "refresh", 120, 600),
    ("POST", r"^/api/v1/platform/schools$", "school_create", 30, 3600),
    ("POST", r"^/api/v1/platform/schools/[^/]+/bootstrap-admin$", "school_admin", 30, 3600),
    ("POST", r"^/api/v1/platform/schools/[^/]+/(suspend|reactivate)$", "school_status", 30, 3600),
    ("POST", r"^/api/v1/platform/team/users$", "user_create", 30, 3600),
    ("POST", r"^/api/v1/platform/team/users/[^/]+/(suspend|reactivate|password-reset)$", "user_critical", 30, 3600),
    ("POST", r"^/api/v1/platform/team/users/[^/]+/roles(/[^/]+/revoke)?$", "role_assign", 60, 3600),
    ("POST|PUT", r"^/api/v1/platform/team/roles(/.*)?$", "role_manage", 60, 3600),
    ("POST", r"^/api/v1/platform/(notification-campaigns|system-notifications)$", "mass_notify", 20, 3600),
    ("POST", r"^/api/v1/platform/memberships/.+$", "access_manage", 120, 3600),
    ("GET", r"^/api/v1/platform/audit-log/export\.csv$", "audit_export", 20, 3600),
))


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        rule = next((r for r in RULES if request.method in r[0].split("|") and r[1].match(request.url.path)), None)
        if rule is None:
            return await call_next(request)
        _, _, bucket, limit, window = rule
        services = request.app.state.services
        limit = max(1, int(limit * max(1.0, float(getattr(services.settings, 'rate_limit_multiplier', 1.0) or 1.0))))
        who = None
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            try:
                from edusync.shared.infrastructure.security import decode_access_token
                cfg = services.settings
                claims = decode_access_token(auth.split(" ", 1)[1], secret=cfg.jwt_secret, issuer=cfg.jwt_issuer, audience=cfg.jwt_audience)
                who = "u:" + str(claims.get("sub"))
            except Exception:  # noqa: BLE001 — an invalid token is refused later by the route itself
                who = None
        if who is None:
            who = "ip:" + (request.client.host if request.client else "unknown")
        key = f"edusync:rl:{bucket}:{_digest(who)}:{int(time.time() // window)}"
        try:
            r = getattr(request.app.state, "_rl_redis", None)
            if r is None:
                import redis
                r = redis.Redis.from_url(services.settings.redis_url, socket_connect_timeout=.35, socket_timeout=.35)
                request.app.state._rl_redis = r
            pipe = r.pipeline()
            pipe.incr(key)
            pipe.expire(key, window + 5)
            count = int(pipe.execute()[0])
        except Exception:  # noqa: BLE001 — availability choice, see module docstring
            return await call_next(request)
        if count > limit:
            retry = window - int(time.time()) % window
            return JSONResponse(status_code=429, headers={"Retry-After": str(retry)},
                                content={"detail": "Trop de demandes pour cette opération. Réessayez dans quelques minutes."})
        return await call_next(request)
