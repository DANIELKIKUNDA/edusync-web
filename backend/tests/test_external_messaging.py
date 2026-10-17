"""External messaging contracts (EXTERNAL_MESSAGING_ARCHITECTURE.md): provider ports, documented Orange contract
(simulated HTTP transport, no network), SMTP and FCM outcome classification, notification policy, SMS units, retries,
fakes refused outside development, e-mail escaping, single-use account links."""
import asyncio
import base64
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from edusync.shared.messaging import ports
from edusync.shared.messaging.ports import SendResult

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "backend/src/edusync"


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- ports
def test_send_result_invariants():
    with pytest.raises(ValueError):
        SendResult("SENT")                      # no provider proof
    with pytest.raises(ValueError):
        SendResult("DELIVERED", provider_message_id="x")   # DELIVERED never comes from a send
    assert SendResult("SENT", provider_message_id="m").outcome == "SENT"
    assert ports.safe_error("x y/z") == "XYZ" and len(ports.safe_error("a" * 200)) == 64


def test_no_business_module_imports_a_provider():
    """Use cases never call Orange, Firebase or SMTP: only the shared messaging adapters and the worker do."""
    offenders = []
    for path in (SRC / "modules").rglob("*.py"):
        if "communications" in path.parts and path.name in {"worker.py", "webhooks.py"}:   # worker and provider callback entry
            continue
        s = path.read_text(encoding="utf-8")
        for needle in ("firebase_admin", "aiosmtplib", "api.orange.com", "sms_orange", "email_smtp", "push_fcm"):
            if needle in s:
                offenders.append(f"{path.relative_to(ROOT)}:{needle}")
    assert not offenders, offenders


# ---------------------------------------------------------------- Orange (documented contract, simulated transport)
def orange(handler, **kw):
    from edusync.shared.messaging.sms_orange import OrangeSmsProvider
    return OrangeSmsProvider(client_id="cid", client_secret="csecret", sender_address="tel:+2430000", sender_name=kw.pop("sender_name", ""),
                             api_base="https://api.orange.test", redis_url=None, transport=httpx.MockTransport(handler), **kw)


def created(request, mid="7f1d2c3a-0000-1111-2222-333344445555"):
    url = f"https://api.orange.test/smsmessaging/v1/outbound/tel:+2430000/requests/{mid}"
    return httpx.Response(201, json={"outboundSMSMessageRequest": {**json.loads(request.content)["outboundSMSMessageRequest"], "resourceURL": url}})


def test_orange_oauth_send_and_token_cache():
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        if request.url.path == "/oauth/v3/token":
            assert request.headers["Authorization"] == "Basic " + base64.b64encode(b"cid:csecret").decode()
            assert request.headers["Accept"] == "application/json"
            assert request.content == b"grant_type=client_credentials"
            return httpx.Response(200, json={"token_type": "Bearer", "access_token": "tok-1", "expires_in": "3600"})
        assert request.url.raw_path == b"/smsmessaging/v1/outbound/tel%3A%2B2430000/requests"
        assert request.headers["Authorization"] == "Bearer tok-1"
        body = json.loads(request.content)["outboundSMSMessageRequest"]
        assert body["address"] == "tel:+243810001234" and body["senderAddress"] == "tel:+2430000"
        assert body["outboundSMSTextMessage"]["message"] == "Bonjour" and body["senderName"] == "EduSync"
        return created(request)

    p = orange(handler, sender_name="EduSync")
    r1 = run(p.send_sms(to_e164="+243810001234", body="Bonjour"))
    r2 = run(p.send_sms(to_e164="+243810001234", body="Bonjour"))
    assert r1.outcome == r2.outcome == "SENT" and r1.provider_message_id == "7f1d2c3a-0000-1111-2222-333344445555"
    assert sum(1 for c in calls if c.url.path == "/oauth/v3/token") == 1       # token reused for its lifetime


def test_orange_expired_token_is_refreshed_once():
    tokens = iter(["old", "new"])

    def handler(request):
        if request.url.path == "/oauth/v3/token":
            return httpx.Response(200, json={"access_token": next(tokens), "expires_in": 3600})
        if request.headers["Authorization"] == "Bearer old":
            return httpx.Response(401, json={"code": 42, "message": "Expired credentials"})
        return created(request)

    assert run(orange(handler).send_sms(to_e164="+243810001234", body="x")).outcome == "SENT"


@pytest.mark.parametrize("status,payload,outcome,code", [
    (429, {"code": 53, "message": "Too many requests"}, "RETRYABLE", "PROVIDER_RATE_LIMITED"),
    (403, {"code": 53, "message": "Too many requests"}, "RETRYABLE", "PROVIDER_RATE_LIMITED"),
    (503, {"code": 5, "message": "temporarily unavailable"}, "RETRYABLE", "PROVIDER_HTTP_503"),
    (400, {"requestError": {"serviceException": {"messageId": "SVC0004", "text": "No valid addresses"}}}, "INVALID_DESTINATION", "INVALID_DESTINATION_SVC0004"),
    (400, {"requestError": {"serviceException": {"messageId": "SVC0280", "text": "Message too long"}}}, "PERMANENT", "MESSAGE_TOO_LONG"),
    (403, {"requestError": {"policyException": {"messageId": "POL0001", "text": "Policy error"}}}, "PERMANENT", "PROVIDER_HTTP_403_POL0001"),
])
def test_orange_error_classification(status, payload, outcome, code):
    def handler(request):
        if request.url.path == "/oauth/v3/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        return httpx.Response(status, json=payload)

    r = run(orange(handler).send_sms(to_e164="+243810001234", body="x"))
    assert (r.outcome, r.error_code) == (outcome, code)


def test_orange_timeout_bad_credentials_and_invalid_inputs():
    def timeout(request):
        raise httpx.ConnectTimeout("t")

    assert run(orange(timeout).send_sms(to_e164="+243810001234", body="x")).outcome == "RETRYABLE"

    def bad_creds(request):
        return httpx.Response(401, json={"error": "invalid_client"})

    r = run(orange(bad_creds).send_sms(to_e164="+243810001234", body="x"))
    assert r.outcome == "PERMANENT" and "csecret" not in (r.error_code or "")
    assert run(orange(timeout).send_sms(to_e164="0810001234", body="x")).outcome == "INVALID_DESTINATION"
    from edusync.shared.messaging.sms_orange import OrangeConfigurationError, OrangeSmsProvider
    for kw in ({"sender_address": "2430000"}, {"sender_name": "Nom beaucoup trop long"}, {"client_secret": ""}):
        with pytest.raises(OrangeConfigurationError):
            OrangeSmsProvider(**{"client_id": "c", "client_secret": "s", "sender_address": "tel:+2430000", **kw})


def test_orange_delivery_receipts_follow_documented_statuses():
    from edusync.shared.messaging.sms_orange import parse_delivery_receipt
    note = lambda s: {"deliveryInfoNotification": {"callbackData": "abc", "deliveryInfo": {"address": "tel:+243810001234", "deliveryStatus": s}}}  # noqa: E731
    assert parse_delivery_receipt(note("DeliveredToTerminal")).status == "DELIVERED"
    assert parse_delivery_receipt(note("DeliveryImpossible")).status == "FAILED"
    for s in ("DeliveredToNetwork", "DeliveryUncertain", "MessageWaiting"):
        assert parse_delivery_receipt(note(s)).status == "PENDING"       # never DELIVERED without handset proof
    assert parse_delivery_receipt({"x": 1}) is None


# ---------------------------------------------------------------- SMTP
def test_smtp_message_and_classification(monkeypatch):
    import aiosmtplib
    from edusync.shared.messaging.email_smtp import SmtpConfigurationError, SmtpEmailProvider
    from edusync.shared.messaging.ports import EmailContent
    with pytest.raises(SmtpConfigurationError):
        SmtpEmailProvider(host="smtp.test", port=25, username="", password="", from_email="noreply@edusync.test", security="none")
    p = SmtpEmailProvider(host="smtp.test", port=587, username="u", password="secret-pw", from_email="noreply@edusync.test")
    msg = p.build(to="parent@example.test", content=EmailContent("Sujet", "Texte", "<p>Texte</p>"))
    assert msg["From"].endswith("<noreply@edusync.test>") and msg["Message-ID"] and msg["Auto-Submitted"] == "auto-generated"
    sent = {}

    async def ok_send(message, **kw):
        sent.update(kw)
        return ({}, "250 OK")

    monkeypatch.setattr(aiosmtplib, "send", ok_send)
    r = run(p.send_email(to="parent@example.test", content=EmailContent("S", "T")))
    assert r.outcome == "SENT" and r.provider_message_id and sent["start_tls"] is True and sent["use_tls"] is False
    for exc, outcome in ((aiosmtplib.SMTPRecipientsRefused({}), "INVALID_DESTINATION"),
                         (aiosmtplib.SMTPResponseException(550, "no"), "PERMANENT"),
                         (aiosmtplib.SMTPResponseException(451, "later"), "RETRYABLE"),
                         (aiosmtplib.SMTPConnectError("down"), "RETRYABLE")):
        async def failing(message, _e=exc, **kw):
            raise _e
        monkeypatch.setattr(aiosmtplib, "send", failing)
        res = run(p.send_email(to="parent@example.test", content=EmailContent("S", "T")))
        assert res.outcome == outcome and "secret-pw" not in (res.error_code or "")
    assert run(p.send_email(to="a@b.c\r\nBcc: x@y.z", content=EmailContent("S", "T"))).outcome == "INVALID_DESTINATION"


# ---------------------------------------------------------------- FCM
def test_fcm_outcomes(monkeypatch):
    from firebase_admin import exceptions, messaging
    from edusync.shared.messaging.push_fcm import FcmPushProvider
    p = FcmPushProvider(app=object())
    captured = {}

    def ok(message, app=None):
        captured["m"] = message
        return "projects/p/messages/1"

    monkeypatch.setattr(messaging, "send", ok)
    r = run(p.send_push(token="tok", title="Titre", body="Ouvrez EduSync", link="/", data={"message_id": "m1"}))
    assert r.outcome == "SENT" and captured["m"].data["title"] == "Titre" and captured["m"].token == "tok"
    for exc, outcome in ((messaging.UnregisteredError("gone"), "INVALID_TOKEN"),
                         (exceptions.InvalidArgumentError("bad"), "INVALID_TOKEN"),
                         (messaging.QuotaExceededError("quota"), "RETRYABLE"),
                         (exceptions.UnavailableError("down"), "RETRYABLE")):
        def failing(message, app=None, _e=exc):
            raise _e
        monkeypatch.setattr(messaging, "send", failing)
        assert run(p.send_push(token="tok", title="T", body="B", link="/", data={})).outcome == outcome


# ---------------------------------------------------------------- policy, units, retries, factory
def test_notification_policy_decides_channels():
    from edusync.modules.communications.domain.policy import decide
    on = {"enabled": True, "sms_enabled": True, "email_enabled": True, "push_enabled": True}
    d = decide(channels=["SMS", "EMAIL", "PUSH"], kind="COMMUNIQUE", settings=on, phone="+243810001234", email="a@b.cd",
               sms_reserved=True, push_devices=["d1", "d2"], seen_phones=set())
    assert [(x.channel, x.send) for x in d] == [("SMS", True), ("EMAIL", True), ("PUSH", True), ("PUSH", True)]
    off = decide(channels=["SMS", "EMAIL"], kind="COMMUNIQUE", settings={**on, "sms_enabled": False, "email_enabled": False}, phone="+243810001234",
                 email="a@b.cd", sms_reserved=True, push_devices=[])
    assert [x.reason for x in off] == ["SMS_DISABLED_FOR_SCHOOL", "EMAIL_DISABLED_FOR_SCHOOL"]
    seen = {"+243810001234"}
    assert decide(channels=["SMS"], kind="COMMUNIQUE", settings=on, phone="+243810001234", email=None, sms_reserved=True,
                  push_devices=[], seen_phones=seen)[0].reason == "DUPLICATE_PHONE"
    assert decide(channels=["SMS"], kind="COMMUNIQUE", settings=on, phone="+243810001234", email=None, sms_reserved=False,
                  push_devices=[])[0].reason == "NO_SMS_CREDIT_RESERVED"
    acc = decide(channels=["SMS", "EMAIL"], kind="ACCOUNT", settings=None, phone="+243810001234", email="a@b.cd", sms_reserved=True, push_devices=[])
    assert [(x.channel, x.send) for x in acc] == [("SMS", False), ("EMAIL", True)]   # account e-mails do not depend on school switches


def test_sms_units_e164_and_bounded_backoff():
    from edusync.modules.communications.application.messaging import e164, sms_units
    from edusync.modules.communications.worker import MAX_ATTEMPTS, backoff_seconds
    assert sms_units("a" * 160) == 1 and sms_units("a" * 161) == 2 and sms_units("a" * 321) == 3 and sms_units("é" * 71) == 2
    assert e164("+243810001234") == "+243810001234" and e164("0810001234") is None and e164("+12") is None
    delays = [backoff_seconds(n) for n in range(1, 12)]
    assert all(1 <= d <= 3600 * 1.2 for d in delays) and MAX_ATTEMPTS <= 10
    assert backoff_seconds(1, retry_after=120) >= 96          # provider Retry-After respected (with jitter)


def test_fakes_refused_in_protected_environments():
    from edusync.shared.messaging.factory import build_email_provider, build_push_provider, build_sms_provider, channel_status
    base = dict(redis_url=None, sms_provider="fake", email_provider="fake", push_provider="fake")
    dev, staging = SimpleNamespace(env="dev", **base), SimpleNamespace(env="staging", **base)
    assert build_sms_provider(dev) and build_email_provider(dev) and build_push_provider(dev)
    assert build_sms_provider(staging) is None and build_email_provider(staging) is None and build_push_provider(staging) is None
    cfg = SimpleNamespace(env="staging", sms_provider="orange", email_provider="disabled", push_provider="disabled",
                          orange_sms_client_id="", orange_sms_client_secret="", orange_sms_sender_address="", orange_sms_sender_name="",
                          orange_sms_dr_secret="", smtp_host="", smtp_from_email="", fcm_service_account_file="", fcm_service_account_json="",
                          fcm_web_config_json="", fcm_vapid_public_key="")
    st = channel_status(cfg)
    assert st["sms"]["state"] == "INCOMPLETE" and st["email"]["state"] == "DISABLED"
    assert "secret" not in json.dumps(st).lower()


def test_email_templates_escape_and_never_carry_a_password():
    from edusync.modules.communications.domain.email_templates import render
    c = render("ACCOUNT_INVITATION", recipient_name="<script>x</script>", school_name="École <b>A</b>", subject=None, body="",
               link="https://app.test/#invitation=abc", ttl_label="48 heures")
    assert "<script>" not in c.html and "&lt;script&gt;" in c.html and "mot de passe provisoire" not in c.text
    assert "48 heures" in c.text and "https://app.test/#invitation=abc" in c.text
    s = render(None, recipient_name="Parent", school_name="École", subject=None, body="Ligne 1\n<img src=x onerror=alert(1)>", link=None)
    assert "<img" not in s.html


def test_account_links_are_hashed_single_use_and_in_fragment():
    src = (SRC / "modules/iam/application/account_links.py").read_text(encoding="utf-8")
    assert "secrets.token_urlsafe(32)" in src and "token_hash" in src and "FOR UPDATE OF t" in src and "used_at IS NULL" in src
    from edusync.modules.iam.application.account_links import INVITATION, PASSWORD_RESET, link
    cfg = SimpleNamespace(public_app_url="https://app.edusync.test/")
    assert link(cfg, PASSWORD_RESET, "T") == "https://app.edusync.test/#reset=T" and link(cfg, INVITATION, "T").endswith("/#invitation=T")
    mig = (ROOT / "backend/migrations/0076_external_messaging.sql").read_text(encoding="utf-8")
    assert "token_hash char(64) NOT NULL UNIQUE" in mig and "school_sms_ledger est en ajout seul" in mig
    assert "SMS_INSUFFICIENT_CREDIT" in mig and "CHECK (reserved <= balance)" in mig and "FOR UPDATE" in mig


def test_webhook_requires_secret_and_is_idempotent():
    s = (SRC / "modules/communications/api/webhooks.py").read_text(encoding="utf-8")
    assert "hmac.compare_digest" in s and "len(expected) < 24" in s and "ON CONFLICT (provider_code, provider_message_id, provider_status) DO NOTHING" in s
    w = (SRC / "modules/communications/worker.py").read_text(encoding="utf-8")
    assert "def process_receipts" in w and "FOR UPDATE SKIP LOCKED" in w
