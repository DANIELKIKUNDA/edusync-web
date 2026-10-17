"""Fake providers — development and automated tests ONLY (refused in staging/production by the factory and by
Settings.assert_runtime_safe). They exercise every outcome deterministically and record what would have been sent
in a Redis list (edusync:messaging:fake:<channel>, last 200 entries) so local probes can follow a link end to end.
A fake success is never a provider certification.

SMS (by the last digits of the number): 0000 permanent refusal, 1111 invalid number, 9999 timeout (retryable),
7777 rate limited (retryable); everything else is accepted.
E-mail (by the local part): bounce@ permanent refusal, invalid@ refused recipient, slow@ unavailable (retryable).
Push (by token prefix): dead- unregistered token, slow- provider unavailable (retryable).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from edusync.shared.messaging.ports import (INVALID_DESTINATION, INVALID_TOKEN, PERMANENT, RETRYABLE, SENT, EmailContent,
                                            SendResult)

FAKE_KEY = "edusync:messaging:fake:{channel}"


def _record(redis_url: str | None, channel: str, entry: dict) -> None:
    if not redis_url:
        return
    try:
        import redis
        r = redis.Redis.from_url(redis_url, decode_responses=True, socket_timeout=1, socket_connect_timeout=1)
        key = FAKE_KEY.format(channel=channel)
        pipe = r.pipeline()
        pipe.lpush(key, json.dumps({"at": datetime.now(timezone.utc).isoformat(), **entry}, ensure_ascii=False))
        pipe.ltrim(key, 0, 199)
        pipe.execute()
    except Exception:  # noqa: BLE001 — the fake sink is a convenience for local probes
        pass


def _id(prefix: str, *parts: str) -> str:
    return prefix + hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]


class FakeSmsProvider:
    code = "fake"

    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url

    async def send_sms(self, *, to_e164: str, body: str) -> SendResult:
        digits = "".join(ch for ch in to_e164 if ch.isdigit())
        if digits.endswith("1111") or len(digits) < 9:
            return SendResult(INVALID_DESTINATION, error_code="INVALID_DESTINATION")
        if digits.endswith("0000"):
            return SendResult(PERMANENT, error_code="PROVIDER_HTTP_403_POL0001")
        if digits.endswith("9999"):
            return SendResult(RETRYABLE, error_code="PROVIDER_TIMEOUT")
        if digits.endswith("7777"):
            return SendResult(RETRYABLE, error_code="PROVIDER_RATE_LIMITED", retry_after_seconds=1)
        mid = _id("fake-sms-", to_e164, body, datetime.now(timezone.utc).isoformat())
        _record(self.redis_url, "sms", {"to": to_e164, "body": body, "id": mid})
        return SendResult(SENT, provider_message_id=mid)


class FakeEmailProvider:
    code = "fake"

    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url

    async def send_email(self, *, to: str, content: EmailContent) -> SendResult:
        local = to.split("@", 1)[0].lower()
        if local.startswith("invalid"):
            return SendResult(INVALID_DESTINATION, error_code="SMTP_RECIPIENT_REFUSED")
        if local.startswith("bounce"):
            return SendResult(PERMANENT, error_code="SMTP_550")
        if local.startswith("slow"):
            return SendResult(RETRYABLE, error_code="SMTP_UNAVAILABLE")
        mid = _id("fake-mail-", to, content.subject, datetime.now(timezone.utc).isoformat())
        _record(self.redis_url, "email", {"to": to, "subject": content.subject, "text": content.text, "id": mid})
        return SendResult(SENT, provider_message_id=mid)


class FakePushProvider:
    code = "fake"

    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url

    async def send_push(self, *, token: str, title: str, body: str, link: str | None, data: dict[str, str]) -> SendResult:
        if token.startswith("dead-"):
            return SendResult(INVALID_TOKEN, error_code="PUSH_TOKEN_UNREGISTERED")
        if token.startswith("slow-"):
            return SendResult(RETRYABLE, error_code="PUSH_PROVIDER_UNAVAILABLE")
        mid = _id("fake-push-", token, title, datetime.now(timezone.utc).isoformat())
        # The token itself is never recorded, only a short fingerprint.
        _record(self.redis_url, "push", {"token_fp": hashlib.sha256(token.encode()).hexdigest()[:12], "title": title,
                                         "link": link, "id": mid})
        return SendResult(SENT, provider_message_id=mid)
