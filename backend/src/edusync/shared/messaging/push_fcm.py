"""Firebase Cloud Messaging adapter (official firebase-admin SDK) — PUSH_FCM_INTEGRATION.md.

The service account is a backend secret: a mounted file (EDUSYNC_FCM_SERVICE_ACCOUNT_FILE) or JSON injected by the
deployment (EDUSYNC_FCM_SERVICE_ACCOUNT_JSON). It is never sent to the browser, logged or returned by the API.
Messages are data-only web push: the existing EduSync service worker (public/sw.js) displays them and opens the
EduSync route on click, so no second service worker competes with the PWA. A push carries a title, a short text
and an internal link — never personal or financial data. Tokens reported unregistered are deactivated.
"""
from __future__ import annotations

import asyncio
import json
import warnings

from edusync.shared.messaging.fcm_errors import classify, scope_of
from edusync.shared.messaging.ports import RETRYABLE, SENT, SendResult

APP_NAME = "edusync-fcm"


class FcmConfigurationError(RuntimeError):
    pass


def _credentials(service_account_file: str, service_account_json: str):
    """Service account from JSON, base64 JSON (one line, safe in an env file) or a file mounted in the container."""
    from firebase_admin import credentials
    from edusync.shared.messaging.diagnose import CredentialError, load_service_account
    try:
        return credentials.Certificate(load_service_account(service_account_file, service_account_json))
    except CredentialError as exc:
        raise FcmConfigurationError(exc.code) from None


class FcmPushProvider:
    code = "fcm"

    def __init__(self, *, service_account_file: str = "", service_account_json: str = "", app=None):
        import firebase_admin
        if app is not None:
            self._app = app
        else:
            try:
                self._app = firebase_admin.get_app(APP_NAME)
            except ValueError:
                self._app = firebase_admin.initialize_app(_credentials(service_account_file, service_account_json), name=APP_NAME)

    def _send_blocking(self, token: str, title: str, body: str, link: str | None, data: dict[str, str]) -> SendResult:
        from firebase_admin import exceptions, messaging
        payload = {"title": title[:120], "body": body[:240], "link": link or "/", **{k: str(v)[:200] for k, v in data.items()}}
        # firebase-admin 7.7 marks Message.token as deprecated in favour of fid (installation id). The web SDK getToken()
        # value is sent as a registration token, still supported; which field it maps to is verified by the real FCM
        # certification (PUSH_FCM_INTEGRATION.md, point to check), never assumed here.
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)
            message = messaging.Message(token=token, data=payload,
                                        webpush=messaging.WebpushConfig(headers={"Urgency": "normal", "TTL": "86400"},
                                                                        fcm_options=messaging.WebpushFCMOptions(link=link) if link and link.startswith("https://") else None))
        try:
            message_id = messaging.send(message, app=self._app)
        except exceptions.FirebaseError as exc:
            # Precise mapping (fcm_errors.py): device-scope errors deactivate the device only; project / credential /
            # API errors are retried with a long delay (an operator fix in Google Cloud recovers the queued pushes).
            outcome, code, detail = classify(exc)
            retry = 300 if code == "PUSH_QUOTA_EXCEEDED" else 900 if scope_of(code) == "PROVIDER" else None
            return SendResult(outcome, error_code=code, retry_after_seconds=retry, error_detail=detail)
        except Exception:  # noqa: BLE001 — network errors surface as transport exceptions
            return SendResult(RETRYABLE, error_code="PUSH_NETWORK", error_detail="transport")
        return SendResult(SENT, provider_message_id=str(message_id)[:180])

    HEALTH_TOKEN = "edusync-health-check-not-a-device-token"

    def _health_blocking(self) -> dict:
        """PROVIDER health = the SEND permission, not only an OAuth token: a validate-only (dry_run) send to a token that
        is not a device. Google checks credentials, the « Firebase Cloud Messaging API » and IAM BEFORE the token, so
        « token invalid » proves the project can send; PERMISSION_DENIED / UNAUTHENTICATED prove it cannot. No push
        is delivered (dry_run)."""
        from firebase_admin import exceptions, messaging
        info = self._app.credential.get_access_token()          # OAuth2 with the service account key
        if not getattr(info, "access_token", None):
            raise RuntimeError("no access token")
        project = getattr(self._app, "project_id", None)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', DeprecationWarning)
                messaging.send(messaging.Message(token=self.HEALTH_TOKEN, data={"health": "1"}), dry_run=True, app=self._app)
        except exceptions.FirebaseError as exc:
            outcome, code, detail = classify(exc)
            if scope_of(code) == "DEVICE":
                return {"project_id": project, "send_authorized": True}
            err = RuntimeError("fcm health")
            err.health_code, err.health_detail = code, detail
            raise err from None
        return {"project_id": project, "send_authorized": True}

    async def health_check(self) -> dict:
        try:
            return await asyncio.to_thread(self._health_blocking)
        except RuntimeError as exc:
            if getattr(exc, "health_code", None):
                raise
            err = RuntimeError("fcm health")
            err.health_code = "PUSH_PROVIDER_UNAVAILABLE"
            raise err from None
        except Exception as exc:  # noqa: BLE001 — google-auth errors may echo the account e-mail: only a code leaves here
            err = RuntimeError("fcm health")
            err.health_code = "PUSH_CREDENTIALS" if "RefreshError" in type(exc).__name__ else "PUSH_PROVIDER_UNAVAILABLE"
            raise err from None

    async def send_push(self, *, token: str, title: str, body: str, link: str | None, data: dict[str, str]) -> SendResult:
        return await asyncio.to_thread(self._send_blocking, token, title, body, link, data)
