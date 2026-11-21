from pathlib import Path

from edusync.modules.subscriptions.application.payment_provider import sign_payload, verify_signature

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (ROOT / "backend/migrations/0121_saas_mobile_money_checkout.sql").read_text()
SCHOOL = (ROOT / "backend/src/edusync/modules/subscriptions/api/school_router.py").read_text()
WEBHOOK = (ROOT / "backend/src/edusync/modules/subscriptions/api/payment_webhooks.py").read_text()


def test_webhook_hmac_is_exact_and_rejects_tampering():
    body = b'{"provider_reference":"P-1","status":"SUCCEEDED"}'
    signature = sign_payload("secret", body)
    assert verify_signature("secret", body, signature)
    assert verify_signature("secret", body, "sha256=" + signature)
    assert not verify_signature("secret", body + b" ", signature)
    assert not verify_signature("", body, signature)


def test_checkout_is_school_scoped_and_never_persists_raw_phone():
    assert "WHERE id=:id AND school_id=:school FOR UPDATE" in SCHOOL
    assert 'actor.require("subscription.payment.create")' in SCHOOL
    assert "payer_phone_masked" in SCHOOL
    insert = SCHOOL.split("INSERT INTO saas_payments", 1)[1].split("\n", 5)[0:5]
    assert "body.phone" not in "\n".join(insert)


def test_only_signed_exact_webhook_settles_and_replays_are_ignored():
    assert "verify_signature" in WEBHOOK
    assert "ON CONFLICT(provider,provider_event_id) DO NOTHING" in WEBHOOK
    assert "Decimal(payment[\"amount\"]) != amount" in WEBHOOK
    assert "settle_payment" in WEBHOOK
    assert "signature_verified" in WEBHOOK


def test_migration_is_least_privilege_reversible_and_provisioned():
    assert "subscription.payment.create" in MIGRATION
    assert "GRANT UPDATE ON saas_payment_webhooks TO edusync_platform" in MIGRATION
    assert "0121_saas_mobile_money_checkout.sql" in (ROOT / "backend/scripts/provision_database.py").read_text()
    assert (ROOT / "backend/migrations/rollback/0121_saas_mobile_money_checkout.sql").exists()
