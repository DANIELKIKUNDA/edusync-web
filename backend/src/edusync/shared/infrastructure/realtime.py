"""Real-time signals (Server-Sent Events over Redis Pub/Sub), N1 2026-10.

A signal only says "your inbox changed": it carries no title, body or personal data. The client then re-reads
its inbox through the normal authorised API, so authorisation and tenant isolation stay where they are.
Channels: `edusync:rt:<user_id>:<school_id|platform>` (one per inbox).
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterator

STREAM_MAX_SECONDS = 300   # the client reconnects with a fresh access token; a revoked session stops within 5 min
HEARTBEAT_SECONDS = 20


def channel(user_id, school_id=None) -> str:
    return f"edusync:rt:{user_id}:{school_id or 'platform'}"


def publish_inbox_changed(redis_url: str, recipients: list[tuple[str, str | None]]) -> int:
    """Best effort: a lost signal only delays the update until the next periodic refresh."""
    if not recipients:
        return 0
    try:
        import redis
        r = redis.Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=2)
        pipe = r.pipeline(transaction=False)
        msg = json.dumps({"type": "inbox_changed"})
        for user_id, school_id in recipients:
            pipe.publish(channel(user_id, school_id), msg)
        pipe.execute()
        return len(recipients)
    except Exception:  # noqa: BLE001
        return 0


async def inbox_events(redis_url: str, user_id, school_id, is_disconnected) -> AsyncIterator[bytes]:
    import redis.asyncio as aioredis
    r = aioredis.Redis.from_url(redis_url, socket_connect_timeout=2)
    pubsub = r.pubsub()
    try:
        await pubsub.subscribe(channel(user_id, school_id))
        yield b"retry: 5000\nevent: ready\ndata: {}\n\n"
        started, last_beat = time.monotonic(), time.monotonic()
        while time.monotonic() - started < STREAM_MAX_SECONDS:
            if await is_disconnected():
                break
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg.get("type") == "message":
                yield b"event: inbox\ndata: {\"type\":\"inbox_changed\"}\n\n"
            if time.monotonic() - last_beat >= HEARTBEAT_SECONDS:
                yield b": ping\n\n"
                last_beat = time.monotonic()
            await asyncio.sleep(0)
        yield b"event: reconnect\ndata: {}\n\n"
    finally:
        try:
            await pubsub.unsubscribe()
            await pubsub.aclose()
            await r.aclose()
        except Exception:  # noqa: BLE001
            pass


# ------------------------------------------------------------------ school-wide live changes (owner, 2026-11-01)
# « Quand un caissier encaisse, après la validation, automatiquement tout le monde voit sans recharger » — for every school
# role. A signal names only the DOMAINS that changed (finance, students, headcounts…): no amount, no name, no identifier.
# Each screen then re-reads its own data through the normal API, with the reader's own rights: nobody can receive through
# this channel anything their role may not see. Channel: `edusync:rt:school:<school_id>`.
LIVE_DOMAINS = ("finance", "students", "headcounts", "personnel", "stock", "settings", "communications", "access", "documents")
_LIVE_PREFIXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("/api/v1/schooling/enrollments", ("students", "headcounts", "finance")),     # an enrollment creates charges
    ("/api/v1/schooling", ("students", "headcounts")),
    ("/api/v1/finance", ("finance",)),
    ("/api/v1/effectifs", ("headcounts",)),
    ("/api/v1/personnel", ("personnel",)),
    ("/api/v1/stewardship", ("stock",)),
    ("/api/v1/settings", ("settings", "finance")),                                # tariffs and fees change balances
    ("/api/v1/communications", ("communications",)),
    ("/api/v1/access", ("access",)),
    ("/api/v1/documents", ("documents",)),
    ("/api/v1/import/students", ("students", "headcounts", "finance")),
    ("/api/v1/import/staff", ("personnel",)),
    ("/api/v1/import/finance-history", ("finance",)),
)
NL = bytes([10])
_NOT_A_CHANGE = ("/preview", "/analyze", "/print", "/pdf", "/xlsx", "/export")   # reads sent as POST


def school_channel(school_id) -> str:
    return f"edusync:rt:school:{school_id}"


def live_domains(method: str, path: str) -> tuple[str, ...]:
    """Domains touched by a successful school write (empty for reads and for POSTs that only compute or print)."""
    if method not in ("POST", "PUT", "PATCH", "DELETE") or any(m in path for m in _NOT_A_CHANGE):
        return ()
    return next((d for prefix, d in _LIVE_PREFIXES if path.startswith(prefix)), ())


def publish_school_changed(redis_url: str, school_id, domains: tuple[str, ...]) -> bool:
    """Best effort: a lost signal is caught up when the screen reconnects (it reloads everything on reconnection)."""
    if not domains or not redis_url:
        return False
    try:
        import redis
        r = redis.Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=2)
        r.publish(school_channel(school_id), json.dumps({"type": "changed", "domains": list(domains), "at": time.time()}))
        return True
    except Exception:  # noqa: BLE001
        return False


async def school_events(redis_url: str, school_id, is_disconnected) -> AsyncIterator[bytes]:
    import redis.asyncio as aioredis
    r = aioredis.Redis.from_url(redis_url, socket_connect_timeout=2)
    pubsub = r.pubsub()
    try:
        await pubsub.subscribe(school_channel(school_id))
        yield b"retry: 3000" + NL + b"event: ready" + NL + b"data: {}" + NL + NL
        started, last_beat = time.monotonic(), time.monotonic()
        while time.monotonic() - started < STREAM_MAX_SECONDS:
            if await is_disconnected():
                break
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg.get("type") == "message":
                try:
                    domains = [d for d in json.loads(msg["data"]).get("domains", []) if d in LIVE_DOMAINS]
                except Exception:  # noqa: BLE001
                    domains = []
                if domains:
                    yield b"event: change" + NL + b"data: " + json.dumps({"domains": domains}).encode() + NL + NL
            if time.monotonic() - last_beat >= HEARTBEAT_SECONDS:
                yield b": ping" + NL + NL
                last_beat = time.monotonic()
            await asyncio.sleep(0)
        yield b"event: reconnect" + NL + b"data: {}" + NL + NL
    finally:
        try:
            await pubsub.unsubscribe()
            await pubsub.aclose()
            await r.aclose()
        except Exception:  # noqa: BLE001
            pass
