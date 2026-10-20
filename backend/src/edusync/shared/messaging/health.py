"""Real health checks of the messaging providers, run by the communications worker (the only process holding the
provider secrets). A check never sends a message:
  * e-mail (SMTP, e.g. Brevo): TCP connect + STARTTLS/TLS + AUTH, then QUIT;
  * push (FCM HTTP v1): an OAuth2 access token is obtained with the service account (proves the key and the project);
  * SMS (Orange): an OAuth2 token is obtained with the client credentials.
The snapshot (Redis `edusync:messaging:health`, 1 h) carries only non-secret facts: provider, environment, host, port,
security, whether a sender / username is configured, credential source, Firebase project id, outcome, latency,
sanitized error code. Never a password, a key, a token or a recipient.
The API reads it to tell CONFIGURED (secret present) from OPERATIONAL (a real check or a real send succeeded).
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone

from edusync.shared.messaging.ports import safe_error

KEY = "edusync:messaging:health"
REQUEST_KEY = "edusync:messaging:health:request"
TTL_SECONDS = 3600
INTERVAL_SECONDS = 300


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def describe(cfg) -> dict:
    """Non-secret description of the configuration as the WORKER sees it."""
    from edusync.shared.messaging.factory import _kind
    fcm_file = (cfg.fcm_service_account_file or "").strip()
    return {
        "env": cfg.env,
        "email": {"provider": _kind(cfg.email_provider), "host": cfg.smtp_host or None, "port": cfg.smtp_port or None,
                  "security": cfg.smtp_security or None, "username_configured": bool(cfg.smtp_username),
                  "password_configured": bool(cfg.smtp_password), "from_configured": bool(cfg.smtp_from_email),
                  "from_name": cfg.smtp_from_name or None},
        "push": {"provider": _kind(cfg.push_provider),
                 "credential_source": "json" if (cfg.fcm_service_account_json or "").strip() else "file" if fcm_file else None,
                 "credential_file_readable": bool(fcm_file) and os.path.isfile(fcm_file) and os.access(fcm_file, os.R_OK)},
        "sms": {"provider": _kind(cfg.sms_provider), "client_configured": bool(cfg.orange_sms_client_id and cfg.orange_sms_client_secret),
                "sender_configured": bool(cfg.orange_sms_sender_address)},
    }


async def _timed(coro) -> tuple[bool, int, str | None, dict]:
    t0 = time.perf_counter()
    try:
        extra = await asyncio.wait_for(coro, timeout=25)
        return True, int((time.perf_counter() - t0) * 1000), None, extra or {}
    except asyncio.TimeoutError:
        return False, int((time.perf_counter() - t0) * 1000), "TIMEOUT", {}
    except Exception as exc:  # noqa: BLE001 — classified, never the message (it may contain a host or an account name)
        return False, int((time.perf_counter() - t0) * 1000), safe_error(getattr(exc, "health_code", None) or type(exc).__name__), {}


async def check_all(cfg) -> dict:
    from edusync.shared.messaging.factory import build_email_provider, build_push_provider, build_sms_provider
    desc = describe(cfg)
    out = {"checked_at": _now(), "env": cfg.env, "channels": {}}
    for channel, builder in (("email", build_email_provider), ("push", build_push_provider), ("sms", build_sms_provider)):
        info = {"provider": desc[channel]["provider"], "config": desc[channel], "checked_at": _now()}
        if info["provider"] == "disabled":
            info.update(state="NOT_CONFIGURED", ok=None, error_code="CHANNEL_DISABLED")
        else:
            try:
                provider = builder(cfg)
            except Exception as exc:  # noqa: BLE001
                provider = None
                info["error_code"] = safe_error(type(exc).__name__)
            if provider is None:
                info.update(state="NOT_CONFIGURED", ok=False, error_code=info.get("error_code") or "PROVIDER_NOT_CONFIGURED")
            elif not hasattr(provider, "health_check"):
                info.update(state="CONFIGURED", ok=None, error_code="NO_HEALTH_CHECK")
            else:
                ok, ms, err, extra = await _timed(provider.health_check())
                info.update({**extra, "ok": ok, "latency_ms": ms, "error_code": err, "simulated": bool(getattr(provider, "simulated", False))})
        out["channels"][channel] = info
    return out


def run_and_store(cfg, r) -> dict:
    snap = asyncio.run(check_all(cfg))
    try:
        r.set(KEY, json.dumps(snap), ex=TTL_SECONDS)
        r.delete(REQUEST_KEY)
    except Exception:  # noqa: BLE001 — a lost snapshot only delays the cockpit
        pass
    return snap


def due(r, last_run: float) -> bool:
    """Every INTERVAL_SECONDS, or right away when the cockpit asked for a measure."""
    if time.monotonic() - last_run >= INTERVAL_SECONDS:
        return True
    try:
        return bool(r.exists(REQUEST_KEY))
    except Exception:  # noqa: BLE001
        return False


def read(r) -> dict | None:
    try:
        raw = r.get(KEY)
        return json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001
        return None
