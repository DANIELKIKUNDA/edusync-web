"""Precise classification of Firebase Cloud Messaging (HTTP v1) errors — lot 2026-10.

`messages:send` answers an HTTP status, a google.rpc `status` and details: an ErrorInfo `reason` (for example
SERVICE_DISABLED when the « Firebase Cloud Messaging API » is not enabled in the Google Cloud project, or
IAM_PERMISSION_DENIED when the service account lacks `cloudmessaging.messages.create`) and an FcmError `errorCode`
(UNREGISTERED, SENDER_ID_MISMATCH, THIRD_PARTY_AUTH_ERROR…). A 403 PERMISSION_DENIED is a refusal of the SEND API
by Google Cloud — never the browser notification permission — and is no longer reported as a catch-all code.

Scope of each code (drives retries and the channel state):
  DEVICE     the targeted device / token only: the device is deactivated, the channel stays healthy;
  PROVIDER   the project / credentials / API configuration: every send fails until an operator fixes it;
  TRANSIENT  temporary (network, quota, Firebase unavailable): retried with backoff.
Only sanitized codes and a redacted reason leave this module: never a token, a key, an e-mail of service account.
"""
from __future__ import annotations

import json

DEVICE_CODES = frozenset({"PUSH_TOKEN_UNREGISTERED", "PUSH_TOKEN_INVALID", "PUSH_SENDER_ID_MISMATCH", "PUSH_DEVICE_REVOKED"})
PROVIDER_CODES = frozenset({"PUSH_FCM_API_DISABLED", "PUSH_IAM_PERMISSION_MISSING", "PUSH_PROJECT_PERMISSION_DENIED", "PUSH_CREDENTIALS",
                            "PUSH_WEBPUSH_AUTH", "PUSH_PROJECT_NOT_FOUND"})
OPERATOR_HINT = {
    "PUSH_FCM_API_DISABLED": "Activer « Firebase Cloud Messaging API » (V1) dans Google Cloud Console pour ce projet",
    "PUSH_IAM_PERMISSION_MISSING": "Donner au compte de service le rôle « Firebase Cloud Messaging API Admin » (cloudmessaging.messages.create)",
    "PUSH_PROJECT_PERMISSION_DENIED": "Le projet Google Cloud refuse l’envoi : vérifier le projet du compte de service et ses droits",
    "PUSH_CREDENTIALS": "Clé du compte de service refusée par Google (révoquée ou d’un autre projet)",
    "PUSH_WEBPUSH_AUTH": "Clé Web Push (VAPID) refusée : utiliser la paire générée dans Firebase → Cloud Messaging → Web Push",
    "PUSH_PROJECT_NOT_FOUND": "Projet Firebase introuvable pour ce compte de service",
    "PUSH_SENDER_ID_MISMATCH": "Appareil enregistré avec un autre projet Firebase : il doit réactiver les notifications",
    "PUSH_TOKEN_UNREGISTERED": "Appareil désinscrit (application désinstallée, notifications coupées) : appareil désactivé",
    "PUSH_TOKEN_INVALID": "Jeton d’appareil invalide : appareil désactivé",
}


def scope_of(code: str | None) -> str:
    if code in DEVICE_CODES:
        return "DEVICE"
    if code in PROVIDER_CODES:
        return "PROVIDER"
    return "TRANSIENT"


def _google_error(exc) -> tuple[str | None, str | None, str | None, int | None]:
    """(status, ErrorInfo reason, FcmError errorCode, http status) read from the Firebase HTTP response, if any."""
    resp = getattr(exc, "http_response", None)
    http = getattr(resp, "status_code", None)
    try:
        body = resp.json() if resp is not None else {}
    except (ValueError, json.JSONDecodeError, AttributeError):
        body = {}
    err = (body or {}).get("error") or {}
    reason = fcm_code = None
    for d in err.get("details") or []:
        t = d.get("@type", "")
        if t.endswith("google.rpc.ErrorInfo"):
            reason = d.get("reason")
        elif t.endswith("google.firebase.fcm.v1.FcmError"):
            fcm_code = d.get("errorCode")
    return err.get("status"), reason, fcm_code, http


def classify(exc) -> tuple[str, str, str]:
    """(outcome, code, detail) for a firebase_admin exception. outcome ∈ ports outcomes (string)."""
    from firebase_admin import exceptions, messaging
    status, reason, fcm_code, http = _google_error(exc)
    tail = f"HTTP {http or '?'} {status or getattr(exc, 'code', '') or ''}".strip() + (f" · {reason}" if reason else "") + (f" · {fcm_code}" if fcm_code else "")
    if isinstance(exc, messaging.UnregisteredError) or fcm_code == "UNREGISTERED":
        return "INVALID_TOKEN", "PUSH_TOKEN_UNREGISTERED", tail
    if isinstance(exc, messaging.SenderIdMismatchError) or fcm_code == "SENDER_ID_MISMATCH":
        return "INVALID_TOKEN", "PUSH_SENDER_ID_MISMATCH", tail
    if isinstance(exc, messaging.ThirdPartyAuthError) or fcm_code == "THIRD_PARTY_AUTH_ERROR":
        return "RETRYABLE", "PUSH_WEBPUSH_AUTH", tail
    if isinstance(exc, exceptions.PermissionDeniedError):
        if reason in ("SERVICE_DISABLED", "API_DISABLED"):
            return "RETRYABLE", "PUSH_FCM_API_DISABLED", tail
        if reason == "ACCESS_TOKEN_SCOPE_INSUFFICIENT":
            return "RETRYABLE", "PUSH_CREDENTIALS", tail
        if reason in ("IAM_PERMISSION_DENIED",) or "cloudmessaging.messages.create" in str(exc):
            return "RETRYABLE", "PUSH_IAM_PERMISSION_MISSING", tail
        if "has not been used in project" in str(exc) or "is disabled" in str(exc):
            return "RETRYABLE", "PUSH_FCM_API_DISABLED", tail
        return "RETRYABLE", "PUSH_PROJECT_PERMISSION_DENIED", tail
    if isinstance(exc, exceptions.UnauthenticatedError):
        return "RETRYABLE", "PUSH_CREDENTIALS", tail
    if isinstance(exc, exceptions.InvalidArgumentError):
        return "INVALID_TOKEN", "PUSH_TOKEN_INVALID", tail
    if isinstance(exc, exceptions.NotFoundError):
        return ("INVALID_TOKEN", "PUSH_TOKEN_UNREGISTERED", tail) if fcm_code else ("RETRYABLE", "PUSH_PROJECT_NOT_FOUND", tail)
    if isinstance(exc, messaging.QuotaExceededError) or isinstance(exc, exceptions.ResourceExhaustedError):
        return "RETRYABLE", "PUSH_QUOTA_EXCEEDED", tail
    if isinstance(exc, (exceptions.UnavailableError, exceptions.InternalError, exceptions.DeadlineExceededError)):
        return "RETRYABLE", "PUSH_PROVIDER_UNAVAILABLE", tail
    return "RETRYABLE", "PUSH_PROVIDER_ERROR", tail
