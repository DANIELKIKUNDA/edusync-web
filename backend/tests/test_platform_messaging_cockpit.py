"""Messagerie plateforme (lot 2026-10): provider state machine (current vs history), masking, health checks, RBAC
contracts, templates. Behaviour against the real stack: tools/local/messaging_cockpit_probe.py and
tools/local/account_flows_probe.py; real Brevo: SMTP health check against smtp-relay.brevo.com (see the certification)."""
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from edusync.modules.communications.api.platform_router import channel_state, mask
from edusync.modules.communications.domain.email_templates import render
from edusync.shared.messaging.email_smtp import SmtpEmailProvider
from edusync.shared.messaging.health import _timed

ROOT = Path(__file__).resolve().parents[2]
ROUTER = (ROOT / "backend/src/edusync/modules/communications/api/platform_router.py").read_text(encoding="utf-8")
WORKER = (ROOT / "backend/src/edusync/modules/communications/worker.py").read_text(encoding="utf-8")
MIG = (ROOT / "backend/migrations/0084_platform_messaging_cockpit.sql").read_text(encoding="utf-8")
UI = (ROOT / "frontend/src/platform/messaging.tsx").read_text(encoding="utf-8")
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
CFG = {"provider": "smtp", "state": "CONFIGURED"}


def snap(ok, minutes_ago=1, state=None, key="email", provider="smtp", **extra):
    ch = {"provider": provider, "checked_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(), "ok": ok, "latency_ms": 120,
          "error_code": None if ok else "SMTP_AUTHENTICATION", "config": {"host": "smtp-relay.brevo.com"}, **({"state": state} if state else {})}
    ch.update(extra)
    return {"env": "staging", "channels": {key: ch}}


def test_operational_only_with_a_real_proof():
    assert channel_state("email", CFG, None, {}, NOW)["state"] == "CONFIGURED"                         # a secret alone proves nothing
    assert channel_state("email", CFG, snap(True), {}, NOW)["state"] == "OPERATIONAL"                  # fresh real check
    assert channel_state("email", CFG, snap(None, minutes_ago=60), {"last_success": NOW - timedelta(hours=2)}, NOW)["state"] == "OPERATIONAL"
    assert channel_state("email", CFG, snap(True, minutes_ago=40), {}, NOW)["state"] == "CONFIGURED"   # stale check
    assert channel_state("email", {"provider": "fake", "state": "SIMULATED"}, snap(True), {}, NOW)["state"] == "NOT_CONFIGURED"


def test_current_failure_vs_history():
    old = {"last_failure": NOW - timedelta(days=2), "failed_15m": 0, "sent_15m": 0, "last_success": NOW - timedelta(hours=1)}
    assert channel_state("email", CFG, snap(True), old, NOW)["state"] == "OPERATIONAL"                 # an old error never degrades
    now_failing = {"failed_15m": 3, "sent_15m": 0}
    st = channel_state("email", CFG, snap(True), now_failing, NOW)
    assert st["state"] == "DEGRADED" and "15 min" in st["reasons"][0]
    assert channel_state("email", CFG, snap(True), {"failed_15m": 3, "sent_15m": 2}, NOW)["state"] == "OPERATIONAL"
    assert channel_state("email", CFG, snap(True), {"oldest_due_seconds": 1200}, NOW)["state"] == "DEGRADED"
    assert channel_state("email", CFG, snap(False), {}, NOW)["state"] == "UNAVAILABLE"
    assert channel_state("email", CFG, snap(False, minutes_ago=40), {}, NOW)["state"] == "CONFIGURED"  # stale failure = history
    assert channel_state("email", {"provider": "fake", "state": "REFUSED"}, None, {}, NOW)["state"] == "UNAVAILABLE"
    st = channel_state("email", CFG, snap(False, state="NOT_CONFIGURED", checks=[{"name": "EDUSYNC_SMTP_PASSWORD", "ok": False, "detail": "absent dans ce processus"}]), {}, NOW)
    assert st["state"] == "NOT_CONFIGURED" and "EDUSYNC_SMTP_PASSWORD" in st["reasons"][0]          # the failing variable is named


def test_push_operational_only_after_a_real_accepted_push_and_api_worker_consistency():
    cfg = {"provider": "fcm", "state": "CONFIGURED"}
    ok = snap(True, key="push", provider="fcm", project_id="edusync-staging")
    st = channel_state("push", cfg, ok, {}, NOW)
    assert st["state"] == "CONFIGURED" and "push de test" in st["reasons"][0]                       # credentials alone are not enough
    assert channel_state("push", cfg, ok, {"last_success": NOW - timedelta(days=3)}, NOW)["state"] == "OPERATIONAL"
    st = channel_state("push", cfg, ok, {"last_success": NOW - timedelta(days=3)}, NOW, None, "autre-projet")
    assert st["state"] == "DEGRADED" and "Projet Firebase différent" in st["reasons"][-1]
    api = [{"name": "EDUSYNC_FCM_WEB_CONFIG_JSON", "ok": False, "detail": "absente"}]
    st = channel_state("push", {"provider": "disabled", "state": "DISABLED"}, None, {}, NOW, api)
    assert st["state"] == "NOT_CONFIGURED" and any("EDUSYNC_FCM_WEB_CONFIG_JSON" in r for r in st["reasons"])


def test_service_account_json_base64_file_and_codes(tmp_path):
    import base64, json as _j
    from edusync.shared.messaging.diagnose import CredentialError, load_service_account
    pem = "-" * 5 + "BEGIN " + "PRIVATE KEY" + "-" * 5 + "x"        # built at run time: no key-shaped literal in the repository
    sa = {"type": "service_account", "project_id": "p", "private" + "_key": pem, "client_email": "a@p.iam.gserviceaccount.com"}
    assert load_service_account("", _j.dumps(sa))["project_id"] == "p"
    assert load_service_account("", base64.b64encode(_j.dumps(sa).encode()).decode())["project_id"] == "p"   # one line, env-file safe
    f = tmp_path / "sa.json"; f.write_text(_j.dumps(sa), encoding="utf-8")
    assert load_service_account(str(f), "")["client_email"].endswith("gserviceaccount.com")
    for args, code in ((("", ""), "PUSH_CREDENTIAL_MISSING"), (("/nope/sa.json", ""), "PUSH_CREDENTIAL_FILE_MISSING"),
                       (("", "{pas du json"), "PUSH_CREDENTIAL_JSON_INVALID"), (("", _j.dumps({"type": "user"})), "PUSH_CREDENTIAL_NOT_SERVICE_ACCOUNT")):
        try:
            load_service_account(*args); raise AssertionError(code)
        except CredentialError as exc:
            assert exc.code == code and "BEGIN" not in exc.detail


def test_diagnosis_names_variables_never_values():
    from types import SimpleNamespace
    from edusync.shared.messaging.diagnose import all_checks
    cfg = SimpleNamespace(env="staging", email_provider="disabled", smtp_host="smtp-relay.brevo.com", smtp_port=587, smtp_security="starttls",
                          smtp_from_email="ops@example.test", smtp_username="u", smtp_password="tres-secret", public_app_url="http://x",
                          push_provider="fcm", fcm_service_account_file="", fcm_service_account_json="", fcm_web_config_json="", fcm_vapid_public_key="")
    w = all_checks(cfg, "worker"); a = all_checks(cfg, "api")
    names = {c["name"]: c for c in w["email"]}
    assert names["EDUSYNC_EMAIL_PROVIDER"]["ok"] is False and "smtp" in names["EDUSYNC_EMAIL_PROVIDER"]["detail"]
    assert names["EDUSYNC_PUBLIC_APP_URL"]["ok"] is False and names["EDUSYNC_SMTP_PASSWORD"]["ok"] is True
    assert "tres-secret" not in str(w) + str(a)
    assert any(c["name"] == "Compte de service Firebase" and "PUSH_CREDENTIAL_MISSING" in c["detail"] for c in w["push"])
    assert {c["name"] for c in a["push"]} >= {"EDUSYNC_FCM_WEB_CONFIG_JSON", "EDUSYNC_FCM_VAPID_PUBLIC_KEY"}


def test_destination_masking():
    assert mask("EMAIL", "danielle.dupont@gmail.com") == "da•••@gmail.com"
    assert mask("SMS", "+243810000099") == "+243•••••••99"
    assert mask("PUSH", "0b7c3f0e-1111-4c2a-9e55-0123456789ab") == "Appareil …89ab"
    assert mask("EMAIL", "skip:abc") == "—" and mask("SMS", None) == "—"


def test_smtp_health_check_classifies_without_secret():
    p = SmtpEmailProvider(host="127.0.0.1", port=2, username="u", password="secret-value", from_email="x@example.test", timeout_seconds=2)
    ok, ms, err, extra = asyncio.run(_timed(p.health_check()))
    assert ok is False and err in ("SMTP_UNAVAILABLE", "TIMEOUT") and "secret-value" not in repr((ok, err, extra))   # refused (Linux) or timed out (Windows)


def test_worker_health_never_blocks_deliveries_and_records_first_attempt():
    assert "provider_health.run_and_store(cfg, r)" in WORKER and "log.exception('provider health check failed')" in WORKER
    assert "first_attempt_at=coalesce(first_attempt_at, now())" in WORKER


def test_rbac_capabilities_and_retry_rules():
    for cap in ("platform.messaging.retry", "platform.sms_wallet.adjust"):
        assert cap in MIG
    assert "USING (channel IN ('EMAIL','PUSH'))" in MIG                     # the platform role can never touch an SMS row
    assert "_need(actor, RETRY)" in ROUTER and "require_recent_mfa(services, actor, RETRY)" in ROUTER
    assert "_need(actor, ADJUST)" in ROUTER and "_need(actor, CREDIT)" in ROUTER
    assert "class RetryBody" in ROUTER and "reason: str = Field(min_length=5" in ROUTER
    assert "paid_on: date\n" in ROUTER and "commercial_price: float = Field(gt=0)" in ROUTER
    assert "LEFT JOIN communication_messages m" in ROUTER and "'SCHOOL_MESSAGE'" in ROUTER   # school messages stay private


def test_email_templates_have_text_html_and_signature():
    for code in ("ACCOUNT_INVITATION", "ACCOUNT_PASSWORD_RESET", "ACCOUNT_SECURITY_ALERT", "PLATFORM_ALERT", None):
        c = render(code, recipient_name="<i>Ana</i>", school_name="École", subject="Sujet", body="Corps <b>", link="https://app.example/#reset=x", ttl_label="30 minutes")
        assert c.subject and c.text and c.html and "From Volcano Tech" in c.text and "From Volcano Tech" in c.html
        assert "<i>Ana</i>" not in c.html and "<b>" not in c.html.split("<td style=\"font-size:15px")[1].split("</td>")[0]


def test_ui_contract():
    for x in ("Contrôler les fournisseurs", "Échecs actifs", "Rechercher dans tous les envois", "Recharge payée", "Ajustement", "Relancer",
              "Notifications sur cet appareil", "Hors connexion", "Distribué (preuve)", "contenu et destinataires privés"):
        assert x in UI or x in (ROOT / "frontend/src/platform/messaging_api.ts").read_text(encoding="utf-8"), x
    assert "key = useRef(crypto.randomUUID())" in UI           # one idempotency key per form: a double click never credits twice


# ---------------------------------------------------------------- Push: precise Firebase mapping, provider ≠ delivery health
class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def _fb(cls, status, google_status, reason=None, fcm=None, message="refused"):
    details = ([{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": reason}] if reason else []) +               ([{"@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError", "errorCode": fcm}] if fcm else [])
    return cls(message, http_response=_Resp(status, {"error": {"code": status, "status": google_status, "message": message, "details": details}}))


def test_firebase_errors_are_mapped_precisely_never_a_catch_all():
    from firebase_admin import exceptions, messaging
    from edusync.shared.messaging.fcm_errors import classify, scope_of
    cases = (
        (_fb(exceptions.PermissionDeniedError, 403, "PERMISSION_DENIED", reason="SERVICE_DISABLED"), "PUSH_FCM_API_DISABLED", "PROVIDER"),
        (_fb(exceptions.PermissionDeniedError, 403, "PERMISSION_DENIED", reason="IAM_PERMISSION_DENIED"), "PUSH_IAM_PERMISSION_MISSING", "PROVIDER"),
        (_fb(exceptions.PermissionDeniedError, 403, "PERMISSION_DENIED"), "PUSH_PROJECT_PERMISSION_DENIED", "PROVIDER"),
        (_fb(messaging.SenderIdMismatchError, 403, "PERMISSION_DENIED", fcm="SENDER_ID_MISMATCH"), "PUSH_SENDER_ID_MISMATCH", "DEVICE"),
        (_fb(messaging.UnregisteredError, 404, "NOT_FOUND", fcm="UNREGISTERED"), "PUSH_TOKEN_UNREGISTERED", "DEVICE"),
        (_fb(exceptions.InvalidArgumentError, 400, "INVALID_ARGUMENT"), "PUSH_TOKEN_INVALID", "DEVICE"),
        (_fb(messaging.ThirdPartyAuthError, 401, "UNAUTHENTICATED", fcm="THIRD_PARTY_AUTH_ERROR"), "PUSH_WEBPUSH_AUTH", "PROVIDER"),
        (_fb(exceptions.UnauthenticatedError, 401, "UNAUTHENTICATED"), "PUSH_CREDENTIALS", "PROVIDER"),
        (_fb(exceptions.UnavailableError, 503, "UNAVAILABLE"), "PUSH_PROVIDER_UNAVAILABLE", "TRANSIENT"),
    )
    for exc, code, scope in cases:
        outcome, got, detail = classify(exc)
        assert got == code and scope_of(got) == scope, (code, got)
        assert "HTTP" in detail and "token" not in detail.lower()
    assert all(classify(c[0])[1] != "PUSH_PERMISSION_DENIED" for c in cases)        # the old catch-all is gone


def test_provider_health_is_the_send_permission_dry_run():
    from unittest.mock import patch
    from firebase_admin import exceptions, messaging
    from edusync.shared.messaging.push_fcm import FcmPushProvider

    class Cred:
        def get_access_token(self):
            return type("T", (), {"access_token": "x"})()
    app = type("App", (), {"credential": Cred(), "project_id": "edusync-staging"})()
    p = FcmPushProvider(app=app)
    with patch.object(messaging, "send", side_effect=_fb(exceptions.InvalidArgumentError, 400, "INVALID_ARGUMENT")) as send:
        assert p._health_blocking() == {"project_id": "edusync-staging", "send_authorized": True}     # token refused AFTER auth/API/IAM
        assert send.call_args.kwargs["dry_run"] is True                                           # nothing is delivered
    with patch.object(messaging, "send", side_effect=_fb(exceptions.PermissionDeniedError, 403, "PERMISSION_DENIED", reason="SERVICE_DISABLED")):
        try:
            p._health_blocking(); raise AssertionError("must fail")
        except RuntimeError as exc:
            assert exc.health_code == "PUSH_FCM_API_DISABLED" and "SERVICE_DISABLED" in exc.health_detail
    with patch.object(messaging, "send", side_effect=_fb(exceptions.PermissionDeniedError, 403, "PERMISSION_DENIED", reason="SERVICE_DISABLED")):
        r = p._send_blocking("device-token", "t", "b", "/", {})
        assert r.outcome == "RETRYABLE" and r.error_code == "PUSH_FCM_API_DISABLED" and r.retry_after_seconds == 900
    with patch.object(messaging, "send", side_effect=_fb(messaging.UnregisteredError, 404, "NOT_FOUND", fcm="UNREGISTERED")):
        r = p._send_blocking("device-token", "t", "b", "/", {})
        assert r.outcome == "INVALID_TOKEN" and r.error_code == "PUSH_TOKEN_UNREGISTERED"
    with patch.object(messaging, "send", return_value="projects/edusync-staging/messages/0:123"):
        assert p._send_blocking("device-token", "t", "b", "/", {}).outcome == "SENT"


def test_one_device_failing_never_degrades_a_healthy_provider():
    cfg = {"provider": "fcm", "state": "CONFIGURED"}
    ok = snap(True, key="push", provider="fcm", project_id="p", send_authorized=True)
    st = channel_state("push", cfg, ok, {"failed_15m": 0, "failed_15m_recipient": 4, "sent_15m": 0, "last_success": NOW - timedelta(days=1),
                                         "last_failure_code": "PUSH_TOKEN_UNREGISTERED"}, NOW)
    assert st["state"] == "OPERATIONAL" and st["delivery_health"]["last_failure_scope"] == "DEVICE"
    assert channel_state("push", cfg, ok, {"failed_15m": 1, "sent_15m": 0, "last_success": NOW - timedelta(days=1)}, NOW)["state"] == "OPERATIONAL"
    st = channel_state("push", cfg, ok, {"failed_15m": 3, "sent_15m": 0, "last_failure_code": "PUSH_PROVIDER_UNAVAILABLE"}, NOW)
    assert st["state"] == "DEGRADED"                                                               # repeated systemic failures only
    bad = snap(False, key="push", provider="fcm", error_code="PUSH_IAM_PERMISSION_MISSING", error_detail="HTTP 403 PERMISSION_DENIED")
    st = channel_state("push", cfg, bad, {}, NOW)
    assert st["state"] == "UNAVAILABLE" and any("Firebase Cloud Messaging API Admin" in r for r in st["reasons"])
    assert st["provider_health"]["ok"] is False and "delivery_health" in st
