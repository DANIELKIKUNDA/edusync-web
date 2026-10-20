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


def snap(ok, minutes_ago=1, state=None):
    return {"channels": {"email": {"checked_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(), "ok": ok, "latency_ms": 120,
                                   "error_code": None if ok else "SMTP_AUTHENTICATION", "config": {"host": "smtp-relay.brevo.com"}, **({"state": state} if state else {})}}}


def test_operational_only_with_a_real_proof():
    assert channel_state("email", CFG, None, {}, NOW)["state"] == "CONFIGURED"                         # a secret alone proves nothing
    assert channel_state("email", CFG, snap(True), {}, NOW)["state"] == "OPERATIONAL"                  # fresh real check
    assert channel_state("email", CFG, None, {"last_success": NOW - timedelta(hours=2)}, NOW)["state"] == "OPERATIONAL"
    assert channel_state("email", CFG, snap(True, minutes_ago=40), {}, NOW)["state"] == "CONFIGURED"   # stale check
    assert channel_state("email", {"provider": "fake", "state": "SIMULATED"}, snap(True), {}, NOW)["state"] == "NOT_CONFIGURED"


def test_current_failure_vs_history():
    old = {"last_failure": NOW - timedelta(days=2), "failed_15m": 0, "sent_15m": 0, "last_success": NOW - timedelta(hours=1)}
    assert channel_state("email", CFG, snap(True), old, NOW)["state"] == "OPERATIONAL"                 # an old error never degrades
    now_failing = {"failed_15m": 3, "sent_15m": 0}
    st = channel_state("email", CFG, snap(True), now_failing, NOW)
    assert st["state"] == "DEGRADED" and "15 dernières minutes" in st["reasons"][0]
    assert channel_state("email", CFG, snap(True), {"failed_15m": 3, "sent_15m": 2}, NOW)["state"] == "OPERATIONAL"
    assert channel_state("email", CFG, snap(True), {"oldest_due_seconds": 1200}, NOW)["state"] == "DEGRADED"
    assert channel_state("email", CFG, snap(False), {}, NOW)["state"] == "UNAVAILABLE"
    assert channel_state("email", CFG, snap(False, minutes_ago=40), {}, NOW)["state"] == "CONFIGURED"  # stale failure = history
    assert channel_state("email", {"provider": "fake", "state": "REFUSED"}, None, {}, NOW)["state"] == "UNAVAILABLE"
    assert channel_state("email", CFG, snap(None, state="NOT_CONFIGURED"), {}, NOW)["state"] == "NOT_CONFIGURED"


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
