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
