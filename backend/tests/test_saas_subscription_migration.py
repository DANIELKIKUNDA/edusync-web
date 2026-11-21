from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SQL = (ROOT / "backend/migrations/0119_saas_subscriptions_foundation.sql").read_text(encoding="utf-8")
ROLLBACK = (ROOT / "backend/migrations/rollback/0119_saas_subscriptions_foundation.sql").read_text(encoding="utf-8")
PROVISION = (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")


def test_commercial_billing_is_separate_and_complete():
    for table in (
        "saas_modules", "saas_plans", "saas_plan_versions", "saas_plan_modules",
        "saas_subscriptions", "saas_subscription_events", "saas_entitlements",
        "saas_invoices", "saas_invoice_lines", "saas_payments", "saas_payment_webhooks",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in SQL
    assert "finance_charges" not in SQL and "finance_payments" not in SQL


def test_subscription_and_money_invariants_are_database_enforced():
    for fragment in (
        "uq_saas_school_current_subscription",
        "current_period_end > current_period_start",
        "grace_days BETWEEN 0 AND 90",
        "paid_total <= total",
        "total = subtotal - discount_total + fee_total",
        "UNIQUE(provider,provider_event_id)",
        "UNIQUE(provider,provider_reference)",
    ):
        assert fragment in SQL


def test_future_modules_cannot_be_sold_as_active():
    for code in ("ACADEMIC", "GRADES", "REPORT_CARDS", "PARENT_PORTAL", "MULTI_SCHOOL"):
        assert f"('{code}'" in SQL
    draft_block = SQL[SQL.index("('ACADEMIC'"):SQL.index("ON CONFLICT (code) DO NOTHING")]
    assert draft_block.count("'DRAFT'") >= 5


def test_least_privilege_and_owner_capabilities_are_provisioned():
    assert "REVOKE ALL ON saas_modules" in SQL
    assert "TO edusync_platform" in SQL
    assert "TO edusync_tenant" not in SQL
    assert "r.code='MANAGER_SYSTEME'" in SQL
    assert "platform.billing.payments.reconcile" in SQL
    assert "platform.billing.overrides.grant" in SQL


def test_migration_is_provisioned_and_reversible():
    assert "0119_saas_subscriptions_foundation.sql" in PROVISION
    for table in ("saas_payment_webhooks", "saas_invoices", "saas_subscriptions", "saas_modules"):
        assert f"DROP TABLE IF EXISTS {table}" in ROLLBACK
