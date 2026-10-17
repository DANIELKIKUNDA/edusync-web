"""Builds the configured provider of each channel. Returns None when the channel is disabled or not configured:
deliveries then fail cleanly (PROVIDER_NOT_CONFIGURED) instead of being reported as sent. Fake providers are
refused in every protected environment (staging, production), whatever the configuration says."""
from __future__ import annotations

import logging

from edusync.bootstrap.settings import is_protected_env

log = logging.getLogger("edusync.messaging")


def _kind(value: str | None) -> str:
    return (value or "disabled").strip().lower()


def build_sms_provider(cfg):
    kind = _kind(cfg.sms_provider)
    if kind in {"fake", "mock", "sandbox"}:
        if is_protected_env(cfg.env):
            return None
        from edusync.shared.messaging.fakes import FakeSmsProvider
        return FakeSmsProvider(cfg.redis_url)
    if kind == "orange":
        from edusync.shared.messaging.sms_orange import OrangeConfigurationError, OrangeSmsProvider
        try:
            return OrangeSmsProvider(client_id=cfg.orange_sms_client_id, client_secret=cfg.orange_sms_client_secret,
                                     sender_address=cfg.orange_sms_sender_address, sender_name=cfg.orange_sms_sender_name,
                                     api_base=cfg.orange_sms_api_base, redis_url=cfg.redis_url)
        except OrangeConfigurationError as exc:
            log.warning("sms provider not configured: %s", exc)
    return None


def build_email_provider(cfg):
    kind = _kind(cfg.email_provider)
    if kind == "fake":
        if is_protected_env(cfg.env):
            return None
        from edusync.shared.messaging.fakes import FakeEmailProvider
        return FakeEmailProvider(cfg.redis_url)
    if kind == "smtp":
        from edusync.shared.messaging.email_smtp import SmtpConfigurationError, SmtpEmailProvider
        try:
            return SmtpEmailProvider(host=cfg.smtp_host, port=cfg.smtp_port, username=cfg.smtp_username, password=cfg.smtp_password,
                                     from_email=cfg.smtp_from_email, from_name=cfg.smtp_from_name, security=cfg.smtp_security,
                                     timeout_seconds=cfg.smtp_timeout_seconds, allow_plaintext=not is_protected_env(cfg.env))
        except SmtpConfigurationError as exc:
            log.warning("email provider not configured: %s", exc)
    return None


def build_push_provider(cfg):
    kind = _kind(cfg.push_provider)
    if kind in {"fake", "mock"}:
        if is_protected_env(cfg.env):
            return None
        from edusync.shared.messaging.fakes import FakePushProvider
        return FakePushProvider(cfg.redis_url)
    if kind == "fcm":
        from edusync.shared.messaging.push_fcm import FcmConfigurationError, FcmPushProvider
        try:
            return FcmPushProvider(service_account_file=cfg.fcm_service_account_file, service_account_json=cfg.fcm_service_account_json)
        except (FcmConfigurationError, ValueError, OSError) as exc:
            log.warning("push provider not configured: %s", type(exc).__name__)
    return None


def channel_status(cfg) -> dict[str, dict]:
    """Operational status of each channel for Atelier Pro / school settings: never a credential, never a token."""
    def state(kind: str, configured: bool) -> str:
        if kind == "disabled":
            return "DISABLED"
        if kind in {"fake", "mock", "sandbox"}:
            return "SIMULATED" if not is_protected_env(cfg.env) else "REFUSED"
        return "CONFIGURED" if configured else "INCOMPLETE"
    sms, email, push = _kind(cfg.sms_provider), _kind(cfg.email_provider), _kind(cfg.push_provider)
    return {
        "sms": {"provider": sms, "state": state(sms, bool(cfg.orange_sms_client_id and cfg.orange_sms_client_secret and cfg.orange_sms_sender_address)),
                "sender_name_configured": bool(cfg.orange_sms_sender_name), "delivery_receipts": bool(cfg.orange_sms_dr_secret)},
        "email": {"provider": email, "state": state(email, bool(cfg.smtp_host and cfg.smtp_from_email)), "from_email": cfg.smtp_from_email or None},
        "push": {"provider": push, "state": state(push, bool(cfg.fcm_service_account_file or cfg.fcm_service_account_json)),
                 "web_config": bool(cfg.fcm_web_config_json and cfg.fcm_vapid_public_key)},
    }
