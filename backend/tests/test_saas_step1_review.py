"""Owner, 2026-11-21: subscription step 1 — merged without activation; review fixes on top of the original branch."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = (ROOT / "backend/src/edusync/modules/subscriptions/api/payment_webhooks.py").read_text(encoding="utf-8")


def test_event_identity_comes_from_the_signed_body_only():
    assert 'alias="X-Provider-Event-Id"' not in HOOK                       # the unsigned header is no longer read
    assert 'json.loads(raw).get("event_id")' in HOOK


def test_unsigned_requests_write_nothing_and_rejections_are_committed():
    head = HOOK.split("if not verified:", 1)[1].split("raise HTTPException(401", 1)[0]
    assert "INSERT" not in head and "log.warning" in head
    assert "outcome = _process(" in HOOK and "if outcome[0] != 200:" in HOOK      # raised after the commit


def test_read_only_roles_do_not_pay_by_default_but_each_school_may_decide():
    import json
    reg = json.loads((ROOT / "contracts/CAPABILITY_REGISTRY.json").read_text(encoding="utf-8"))
    who = sorted(r for r, v in reg["standard_roles"].items() if "subscription.payment.create" in v["capabilities"])
    assert who == ["ADMIN_SYSTEME_ECOLE", "GESTIONNAIRE"]
    cap = {c["code"]: c for c in reg["capabilities"]}["subscription.payment.create"]
    assert cap["school_adjustable"] is True
    sql = (ROOT / "backend/migrations/0121_saas_mobile_money_checkout.sql").read_text(encoding="utf-8")
    assert "r.code IN ('ADMIN_SYSTEME_ECOLE','GESTIONNAIRE')" in sql and "school_adjustable=true" in sql


def test_migrations_follow_family_merge_and_ci_runs_the_integration():
    prov = (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")
    order = [prov.index(f'"{m}"') for m in ("0118_family_merge", "0119_saas_subscriptions_foundation",
                                            "0120_saas_school_subscription_account", "0121_saas_mobile_money_checkout")]
    assert order == sorted(order)
    assert "tools/ci/saas_subscription_postgres_integration.py" in (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
