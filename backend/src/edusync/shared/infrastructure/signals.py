"""Golden signals and grouped server errors for the « État du service » cockpit (lot 2026-10).

Kept in Redis, best effort (a lost write never breaks a response, nothing blocks the request: the API middleware hands
the write to a thread). Nothing sensitive is stored: the route TEMPLATE (never the concrete path, so no identifier),
the method, the status, the error type, a redacted first line of the error message, the correlation id. No user, no
payload, no header, no query string, no stack trace.

Keys (UTC):
* ``edusync:obs:m:<YYYYMMDDHHMM>``  per-minute hash, kept 26 h: ``req`` requests, ``e5`` unexpected server errors
  (5xx), ``e4`` expected client refusals (4xx, never an incident), ``ls`` latency sum (ms), ``b0``..``b6`` latency buckets;
* ``edusync:obs:h:<YYYYMMDDHH>``    the same per hour, kept 8 days (7-day history);
* ``edusync:obs:eg:<gid>``          one error group (method + route template + status + error type): first/last
  occurrence, count, redacted message; ``edusync:obs:egz`` sorted set of groups by last occurrence;
* ``edusync:obs:egm:<gid>``         per-minute counts of the group (26 h), ``edusync:obs:egh:<gid>`` per hour (8 days);
* ``edusync:obs:eo:<gid>``          its 20 latest occurrences (instant, correlation id, status, duration).

Current health vs history: an error group is ACTIVE while it occurred within ACTIVE_WINDOW_S; only active groups
degrade the current state. The 24 h / 7 d counts are history: they inform, they never degrade the current state.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone

PREFIX = "edusync:obs:"
ACTIVE_WINDOW_S = 300               # an error is "active" (current incident) for 5 minutes after its last occurrence
BUCKETS_MS = (50, 100, 250, 500, 1000, 2500)   # b0 <= 50 ms … b5 <= 2.5 s, b6 above
MINUTE_TTL = 26 * 3600
HOUR_TTL = 8 * 24 * 3600
OCCURRENCES = 20

_REDACT = (
    (re.compile(r"\[SQL:.*", re.S), ""),
    (re.compile(r"\(Background on this error.*", re.S), ""),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "<e-mail>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<id>"),
    (re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|authorization|cookie|otp|code)\b\s*[=:]\s*\S+"), r"\1=<masqué>"),
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]+"), r"\1 <masqué>"),
    (re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s'\"]+", re.I), "<adresse>"),
    (re.compile(r"(?:[A-Za-z]:\\|/)(?:[\w.-]+[\\/])+[\w.-]+"), "<chemin>"),
    (re.compile(r"'[^']{0,200}'|\"[^\"]{0,200}\""), "'…'"),
    (re.compile(r"\b\d{4,}\b"), "<n>"),
)


def redact(message: str) -> str:
    """First line of an error message without values: no identifier, address, path, secret or quoted value."""
    text = (message or "").strip().splitlines()[0] if (message or "").strip() else ""
    for rx, repl in _REDACT:
        text = rx.sub(repl, text)
    return re.sub(r"\s+", " ", text).strip()[:160]


def group_id(method: str, route: str, status: int, error_type: str) -> str:
    return hashlib.sha1(f"{method}|{route}|{status}|{error_type}".encode()).hexdigest()[:12]


def _bucket(ms: int) -> str:
    for i, edge in enumerate(BUCKETS_MS):
        if ms <= edge:
            return f"b{i}"
    return f"b{len(BUCKETS_MS)}"


def record_request(r, *, method: str, route: str, status: int, duration_ms: int, correlation_id: str,
                   error_type: str | None = None, message: str = "", now: datetime | None = None) -> None:
    """One request: traffic, latency, refusals (4xx) and, for an unexpected server error (5xx), its group."""
    now = now or datetime.now(timezone.utc)
    minute, hour = now.strftime("%Y%m%d%H%M"), now.strftime("%Y%m%d%H")
    try:
        pipe = r.pipeline(transaction=False)
        for key, ttl in ((PREFIX + "m:" + minute, MINUTE_TTL), (PREFIX + "h:" + hour, HOUR_TTL)):
            pipe.hincrby(key, "req", 1)
            pipe.hincrby(key, "ls", int(duration_ms))
            pipe.hincrby(key, _bucket(duration_ms), 1)
            if status >= 500:
                pipe.hincrby(key, "e5", 1)
            elif status >= 400:
                pipe.hincrby(key, "e4", 1)
            pipe.expire(key, ttl)
        if status >= 500:
            etype = error_type or f"HTTP {status}"
            gid = group_id(method, route, status, etype)
            g = PREFIX + "eg:" + gid
            ts = now.isoformat()
            pipe.hsetnx(g, "first", ts)
            pipe.hset(g, mapping={"method": method, "route": route, "status": status, "type": etype, "message": redact(message), "last": ts})
            pipe.hincrby(g, "count", 1)
            pipe.expire(g, HOUR_TTL)
            pipe.zadd(PREFIX + "egz", {gid: now.timestamp()})
            pipe.hincrby(PREFIX + "egm:" + gid, minute, 1)
            pipe.expire(PREFIX + "egm:" + gid, MINUTE_TTL)
            pipe.hincrby(PREFIX + "egh:" + gid, hour, 1)
            pipe.expire(PREFIX + "egh:" + gid, HOUR_TTL)
            pipe.lpush(PREFIX + "eo:" + gid, json.dumps({"at": ts, "correlation_id": correlation_id[:64], "status": status, "duration_ms": int(duration_ms)}))
            pipe.ltrim(PREFIX + "eo:" + gid, 0, OCCURRENCES - 1)
            pipe.expire(PREFIX + "eo:" + gid, HOUR_TTL)
        pipe.execute()
    except Exception:  # noqa: BLE001 — observability is best effort
        pass


def _minutes(now: datetime, n: int) -> list[str]:
    return [(now - timedelta(minutes=i)).strftime("%Y%m%d%H%M") for i in range(n)]


def _hours(now: datetime, n: int) -> list[str]:
    return [(now - timedelta(hours=i)).strftime("%Y%m%d%H") for i in range(n)]


def _sum(rows: list[dict]) -> dict:
    out = {"req": 0, "e5": 0, "e4": 0, "ls": 0, **{f"b{i}": 0 for i in range(len(BUCKETS_MS) + 1)}}
    for row in rows:
        for k, v in (row or {}).items():
            k = k.decode() if isinstance(k, bytes) else k
            if k in out:
                out[k] += int(v)
    return out


def _percentile(agg: dict, q: float) -> int | None:
    """Upper edge of the bucket holding the q-quantile (honest resolution: the bucket, not a fake precise figure)."""
    total = agg["req"]
    if not total:
        return None
    seen = 0
    for i in range(len(BUCKETS_MS) + 1):
        seen += agg[f"b{i}"]
        if seen >= q * total:
            return BUCKETS_MS[i] if i < len(BUCKETS_MS) else None
    return None


def window(r, minutes: int, now: datetime | None = None) -> dict:
    """Golden signals over the last `minutes` minutes (traffic, errors, latency)."""
    now = now or datetime.now(timezone.utc)
    pipe = r.pipeline(transaction=False)
    for m in _minutes(now, minutes):
        pipe.hgetall(PREFIX + "m:" + m)
    agg = _sum(pipe.execute())
    return _signals(agg, minutes)


def _signals(agg: dict, minutes: int) -> dict:
    req = agg["req"]
    p95 = _percentile(agg, .95)
    return {"minutes": minutes, "requests": req, "per_minute": round(req / minutes, 1) if minutes else None,
            "server_errors": agg["e5"], "client_refusals": agg["e4"],
            "error_rate": round(agg["e5"] / req, 4) if req else 0.0,
            "latency_avg_ms": int(agg["ls"] / req) if req else None,
            "latency_p50_ms": _percentile(agg, .5), "latency_p95_ms": p95, "latency_p95_over": req > 0 and p95 is None}


def history(r, span: str, now: datetime | None = None) -> list[dict]:
    """Short history: 1h per minute (60 points), 24h per hour (24 points), 7d per hour (168 points)."""
    now = now or datetime.now(timezone.utc)
    if span == "1h":
        keys = list(reversed(_minutes(now, 60))); prefix = "m:"; fmt = "%Y%m%d%H%M"
    else:
        keys = list(reversed(_hours(now, 24 if span == "24h" else 168))); prefix = "h:"; fmt = "%Y%m%d%H"
    pipe = r.pipeline(transaction=False)
    for k in keys:
        pipe.hgetall(PREFIX + prefix + k)
    out = []
    for k, row in zip(keys, pipe.execute()):
        agg = _sum([row])
        out.append({"at": datetime.strptime(k, fmt).replace(tzinfo=timezone.utc).isoformat(), "requests": agg["req"],
                    "server_errors": agg["e5"], "client_refusals": agg["e4"], "latency_p95_ms": _percentile(agg, .95)})
    return out


def _dec(d: dict) -> dict:
    return {(k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v) for k, v in (d or {}).items()}


def error_groups(r, now: datetime | None = None, since_hours: int = 24 * 7) -> list[dict]:
    """Error groups seen within `since_hours`, most recent first, with active flag and 1 h / 24 h / 7 d counts."""
    now = now or datetime.now(timezone.utc)
    floor = (now - timedelta(hours=since_hours)).timestamp()
    r.zremrangebyscore(PREFIX + "egz", 0, (now - timedelta(days=8)).timestamp())
    gids = [g.decode() if isinstance(g, bytes) else g for g in r.zrevrangebyscore(PREFIX + "egz", "+inf", floor)]
    if not gids:
        return []
    minutes, hours = _minutes(now, 60), _hours(now, 24)
    pipe = r.pipeline(transaction=False)
    for gid in gids:
        pipe.hgetall(PREFIX + "eg:" + gid)
        pipe.hmget(PREFIX + "egm:" + gid, minutes)
        pipe.hmget(PREFIX + "egh:" + gid, hours)
        pipe.hgetall(PREFIX + "egh:" + gid)
    res = pipe.execute()
    out = []
    for i, gid in enumerate(gids):
        g, m, h, allh = _dec(res[4 * i]), res[4 * i + 1], res[4 * i + 2], _dec(res[4 * i + 3])
        if not g:
            continue
        last = datetime.fromisoformat(g["last"])
        week_floor = (now - timedelta(days=7)).strftime("%Y%m%d%H")
        out.append({"id": gid, "method": g.get("method"), "route": g.get("route"), "status": int(g.get("status") or 0), "type": g.get("type"),
                    "message": g.get("message") or "", "first_at": g.get("first"), "last_at": g.get("last"),
                    "active": (now - last).total_seconds() <= ACTIVE_WINDOW_S,
                    "count_1h": sum(int(x or 0) for x in m), "count_24h": sum(int(x or 0) for x in h),
                    "count_7d": sum(int(v) for k, v in allh.items() if k >= week_floor), "count_total": int(g.get("count") or 0)})
    return out


def error_group(r, gid: str, now: datetime | None = None) -> dict | None:
    if not re.fullmatch(r"[0-9a-f]{12}", gid or ""):
        return None
    group = next((g for g in error_groups(r, now) if g["id"] == gid), None)
    if group is None:
        return None
    group["occurrences"] = [json.loads(x) for x in r.lrange(PREFIX + "eo:" + gid, 0, OCCURRENCES - 1)]
    return group


def errors_state(groups: list[dict], last_hour: dict, day: dict) -> dict:
    """CURRENT_HEALTH from the active groups only; HISTORICAL_ERRORS_24H informs and never degrades."""
    active = [g for g in groups if g["active"]]
    state = "DEGRADED" if active else "OK"
    if active:
        n = sum(g["count_1h"] for g in active)
        explain = f"{len(active)} erreur(s) inattendue(s) en cours (dernière occurrence il y a moins de {ACTIVE_WINDOW_S // 60} min)"
    elif day["server_errors"]:
        n = 0
        explain = f"Aucune erreur en cours · {day['server_errors']} erreur(s) résolue(s) sur 24 h (historique)"
    else:
        n = 0
        explain = "Aucune erreur inattendue sur 24 h"
    return {"state": state, "explain": explain, "active_groups": len(active), "active_occurrences_1h": n}
