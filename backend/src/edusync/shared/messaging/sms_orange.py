"""Orange Developer SMS API adapter (SMS_ORANGE_INTEGRATION.md).

Contract taken from the official Orange Developer documentation (generic "SMS API" getting-started page, valid for
every country of the Africa & Middle East offer, and the DR Congo Swagger), not from memory:
  * OAuth v3 client credentials: POST {base}/oauth/v3/token, header "Authorization: Basic base64(client_id:client_secret)",
    "Accept: application/json", form body grant_type=client_credentials; access token valid 3600 s, reused until it
    expires (a 401 code 42 "Expired credentials" forces a refresh). Token endpoint limited to 50 requests/minute.
  * Send: POST {base}/smsmessaging/v1/outbound/{URL-encoded senderAddress}/requests with
    {"outboundSMSMessageRequest": {"address": "tel:+...", "senderAddress": "tel:+...", ["senderName": ...],
     "outboundSMSTextMessage": {"message": ...}}} -> 201 Created; the message id is the last segment of resourceURL.
  * Errors: {"code","message","description"} (401 40/41/42, 403 50-53, 429 53, 5xx) and, for sending,
    {"requestError": {"serviceException"|"policyException": {"messageId": "SVC0004"...}}}.
  * Sending limited to 5 SMS per second (enforced by the worker).
  * Delivery receipts: Orange POSTs {"deliveryInfoNotification": {"callbackData": <id>, "deliveryInfo":
    {"address", "deliveryStatus"}}} to a callback declared through Orange's form (see parse_delivery_receipt).
The access token is cached (Redis when available, else in memory) for its real lifetime and never logged or stored
as configuration. Credentials never appear in an error code, a log line or an API response.
"""
from __future__ import annotations

import base64
import json
import time
from urllib.parse import quote

import httpx

from edusync.shared.messaging.ports import (INVALID_DESTINATION, PERMANENT, RETRYABLE, SENT, DeliveryReceipt,
                                            SendResult, safe_error)

TOKEN_CACHE_KEY = "edusync:orange_sms:access_token"
# Documented deliveryStatus values. Only DeliveredToTerminal proves delivery to the handset.
FINAL_DELIVERED = {"DeliveredToTerminal"}
FINAL_FAILED = {"DeliveryImpossible"}          # may still be followed by a delivery: a later receipt can upgrade it
INTERMEDIATE = {"DeliveredToNetwork", "DeliveryUncertain", "MessageWaiting"}


class OrangeConfigurationError(RuntimeError):
    pass


class OrangeSmsProvider:
    code = "orange"

    def __init__(self, *, client_id: str, client_secret: str, sender_address: str, sender_name: str = "",
                 api_base: str = "https://api.orange.com", redis_url: str | None = None, timeout_seconds: float = 15.0,
                 transport: httpx.AsyncBaseTransport | None = None):
        if not (client_id and client_secret and sender_address):
            raise OrangeConfigurationError("Orange SMS : client_id, client_secret et adresse d'expéditeur obligatoires")
        if not sender_address.startswith("tel:+") or not sender_address[5:].isdigit():
            raise OrangeConfigurationError("Orange SMS : l'adresse d'expéditeur doit avoir la forme tel:+<indicatif><numéro>")
        if sender_name and (len(sender_name) > 11 or not all(ch.isalnum() or ch == " " for ch in sender_name)):
            raise OrangeConfigurationError("Orange SMS : nom d'expéditeur de 11 caractères alphanumériques au plus")
        self._client_id, self._client_secret = client_id, client_secret
        self.sender_address, self.sender_name = sender_address, sender_name
        self.api_base = api_base.rstrip("/")
        self._redis_url = redis_url
        self._timeout = timeout_seconds
        self._transport = transport
        self._memory_token: tuple[str, float] | None = None

    # ------------------------------------------------------------------ OAuth token (cached for its real lifetime)
    def _cache_get(self) -> str | None:
        if self._redis_url:
            try:
                import redis
                value = redis.Redis.from_url(self._redis_url, decode_responses=True, socket_timeout=1, socket_connect_timeout=1).get(TOKEN_CACHE_KEY)
                if value:
                    return value
            except Exception:  # noqa: BLE001 — Redis is an optimisation; the memory cache still applies
                pass
        if self._memory_token and self._memory_token[1] > time.monotonic():
            return self._memory_token[0]
        return None

    def _cache_put(self, token: str, lifetime: int) -> None:
        ttl = max(30, lifetime - 120)        # refresh two minutes before Orange's expiry
        self._memory_token = (token, time.monotonic() + ttl)
        if self._redis_url:
            try:
                import redis
                redis.Redis.from_url(self._redis_url, socket_timeout=1, socket_connect_timeout=1).set(TOKEN_CACHE_KEY, token, ex=ttl)
            except Exception:  # noqa: BLE001
                pass

    def _cache_drop(self) -> None:
        self._memory_token = None
        if self._redis_url:
            try:
                import redis
                redis.Redis.from_url(self._redis_url, socket_timeout=1, socket_connect_timeout=1).delete(TOKEN_CACHE_KEY)
            except Exception:  # noqa: BLE001
                pass

    async def _token(self, client: httpx.AsyncClient, *, force: bool = False) -> str:
        if not force:
            cached = self._cache_get()
            if cached:
                return cached
        basic = base64.b64encode(f"{self._client_id}:{self._client_secret}".encode()).decode()
        r = await client.post(f"{self.api_base}/oauth/v3/token", data={"grant_type": "client_credentials"},
                              headers={"Authorization": f"Basic {basic}", "Accept": "application/json",
                                       "Content-Type": "application/x-www-form-urlencoded"})
        if r.status_code != 200:
            raise _OrangeHttpError(r.status_code, "OAUTH")
        data = r.json()
        token = data.get("access_token")
        if not token:
            raise _OrangeHttpError(502, "OAUTH")
        try:
            lifetime = int(data.get("expires_in", 3600))     # documented as "3600" (string) or 3600 (number)
        except (TypeError, ValueError):
            lifetime = 3600
        self._cache_put(token, lifetime)
        return token

    # ------------------------------------------------------------------ send
    async def send_sms(self, *, to_e164: str, body: str) -> SendResult:
        if not (to_e164.startswith("+") and to_e164[1:].isdigit() and 9 <= len(to_e164) <= 16):
            return SendResult(INVALID_DESTINATION, error_code="INVALID_DESTINATION")
        request = {"address": f"tel:{to_e164}", "senderAddress": self.sender_address, "outboundSMSTextMessage": {"message": body}}
        if self.sender_name:
            request["senderName"] = self.sender_name
        url = f"{self.api_base}/smsmessaging/v1/outbound/{quote(self.sender_address, safe='')}/requests"
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                for attempt in (1, 2):                       # one immediate retry after a token refresh
                    token = await self._token(client, force=attempt == 2)
                    r = await client.post(url, json={"outboundSMSMessageRequest": request},
                                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                                   "Accept": "application/json"})
                    if r.status_code == 401 and attempt == 1:
                        self._cache_drop()
                        continue
                    return classify_send_response(r)
        except _OrangeHttpError as exc:
            if exc.status in (401, 400):
                return SendResult(PERMANENT, error_code=f"OAUTH_HTTP_{exc.status}")     # wrong credentials: fix configuration
            return SendResult(RETRYABLE, error_code=f"OAUTH_HTTP_{exc.status}", retry_after_seconds=60 if exc.status == 429 else None)
        except httpx.TimeoutException:
            return SendResult(RETRYABLE, error_code="PROVIDER_TIMEOUT")
        except httpx.HTTPError:
            return SendResult(RETRYABLE, error_code="PROVIDER_NETWORK")
        return SendResult(RETRYABLE, error_code="PROVIDER_ERROR")


class _OrangeHttpError(Exception):
    def __init__(self, status: int, stage: str):
        super().__init__(f"{stage} HTTP {status}")
        self.status = status


def _json(r: httpx.Response) -> dict:
    try:
        data = r.json()
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def classify_send_response(r: httpx.Response) -> SendResult:
    status = r.status_code
    data = _json(r)
    if status == 201:
        res = (data.get("outboundSMSMessageRequest") or {}).get("resourceURL") or r.headers.get("Location") or ""
        message_id = res.rstrip("/").rsplit("/", 1)[-1] if "/requests/" in res else ""
        if not message_id:
            return SendResult(RETRYABLE, error_code="NO_PROVIDER_PROOF")
        return SendResult(SENT, provider_message_id=message_id)
    retry_after = None
    if r.headers.get("Retry-After", "").isdigit():
        retry_after = int(r.headers["Retry-After"])
    code = data.get("code")
    exc = (data.get("requestError") or {})
    detail = (exc.get("serviceException") or exc.get("policyException") or {}).get("messageId", "")
    if status == 429 or (status == 403 and code == 53):
        return SendResult(RETRYABLE, error_code="PROVIDER_RATE_LIMITED", retry_after_seconds=retry_after or 30)
    if status in (408, 500, 502, 503, 504):
        return SendResult(RETRYABLE, error_code=f"PROVIDER_HTTP_{status}", retry_after_seconds=retry_after)
    if status == 400 and detail in ("SVC0004", "SVC0002"):
        return SendResult(INVALID_DESTINATION, error_code=safe_error(f"INVALID_DESTINATION_{detail}"))
    if status == 400 and detail == "SVC0280":
        return SendResult(PERMANENT, error_code="MESSAGE_TOO_LONG")
    if status == 401:
        return SendResult(PERMANENT, error_code=f"PROVIDER_CREDENTIALS_{code or status}")
    if 400 <= status < 500:
        return SendResult(PERMANENT, error_code=safe_error(f"PROVIDER_HTTP_{status}_{detail or code or ''}"))
    return SendResult(RETRYABLE, error_code=f"PROVIDER_HTTP_{status}")


def parse_delivery_receipt(payload: dict) -> DeliveryReceipt | None:
    """Orange deliveryInfoNotification -> receipt. Only DeliveredToTerminal is DELIVERED; DeliveryImpossible is
    FAILED (a later receipt may still prove delivery); network-level states stay PENDING (SENT)."""
    note = (payload or {}).get("deliveryInfoNotification") or {}
    message_id = str(note.get("callbackData") or "").strip()
    status = str((note.get("deliveryInfo") or {}).get("deliveryStatus") or "").strip()
    if not message_id or len(message_id) > 180 or not status:
        return None
    if status in FINAL_DELIVERED:
        return DeliveryReceipt(message_id, "DELIVERED", status)
    if status in FINAL_FAILED:
        return DeliveryReceipt(message_id, "FAILED", status, "UNDELIVERABLE")
    if status in INTERMEDIATE:
        return DeliveryReceipt(message_id, "PENDING", status)
    return DeliveryReceipt(message_id, "PENDING", safe_error(status))
