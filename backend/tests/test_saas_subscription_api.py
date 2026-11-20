"""S2 contracts for the platform subscription workshop API."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTER = (ROOT / "backend/src/edusync/modules/subscriptions/api/router.py").read_text(encoding="utf-8")
APP = (ROOT / "backend/src/edusync/bootstrap/app.py").read_text(encoding="utf-8")


def section(start: str, end: str = "\n@router") -> str:
    offset = ROUTER.index(start)
    stop = ROUTER.find(end, offset)
    return ROUTER[offset:] if stop < 0 else ROUTER[offset:stop]


def test_router_is_mounted_only_in_platform_billing_space():
    assert 'subscriptions_router, prefix="/api/v1/platform/billing"' in APP
    assert "Depends(require_platform_actor)" in ROUTER


def test_every_catalog_read_requires_billing_read_capability():
    for name in ("def catalog(", "def list_subscriptions("):
        assert 'platform.billing.read' in section(name)


def test_sensitive_mutations_require_capability_mfa_and_audit():
    expectations = {
        "def create_plan(": ("platform.billing.plans.manage", "SAAS_PLAN_CREATED"),
        "def create_plan_version(": ("platform.billing.plans.manage", "SAAS_PLAN_VERSION_CREATED"),
        "def publish_plan_version(": ("platform.billing.plans.manage", "SAAS_PLAN_VERSION_PUBLISHED"),
        "def create_subscription(": ("platform.billing.subscriptions.manage", "SAAS_SUBSCRIPTION_CREATED"),
        "def transition_subscription(": ("platform.billing.subscriptions.manage", "SAAS_SUBSCRIPTION_TRANSITIONED"),
    }
    for name, (capability, event) in expectations.items():
        route = section(name)
        assert capability in route and "require_recent_mfa" in route and event in route


def test_plan_creation_is_persistently_idempotent():
    route = section("def create_plan(")
    assert "Idempotency-Key" in route
    assert "IdempotentExecutor(PostgresIdempotencyRepository(conn))" in route
    assert 'operation="SAAS_PLAN_CREATE"' in route


def test_only_active_modules_can_be_sold_and_only_published_plans_assigned():
    version = section("def create_plan_version(")
    subscription = section("def create_subscription(")
    assert "status='ACTIVE'" in version and "Modules indisponibles" in version
    assert 'version["status"] != "PUBLISHED"' in subscription


def test_subscription_transition_uses_domain_rules_and_optimistic_locking():
    route = section("def transition_subscription(")
    for token in ("FOR UPDATE", 'current["version"]', "aggregate.transition", "saas_subscription_events", "saas_entitlements"):
        assert token in route


def test_list_is_filtered_and_hard_bounded():
    route = section("def list_subscriptions(")
    assert "le=200" in route and "school_id" in route and "status" in route and "LIMIT :limit" in route


def test_invoice_and_payment_reads_are_bounded_and_permissioned():
    route = section("def list_invoices(")
    assert "platform.billing.read" in route and "le=200" in route and "LIMIT :limit" in route


def test_invoice_issue_is_idempotent_mfa_protected_and_audited():
    route = section("def issue_invoice(")
    for token in ("platform.billing.invoices.manage", "require_recent_mfa", "IdempotentExecutor",
                  "SAAS_INVOICE_ISSUED", "saas_invoice_number_seq", "bill_to_snapshot"):
        assert token in route


def test_manual_payment_is_exact_locked_and_reactivates_subscription():
    route = section("def record_manual_payment(")
    for token in ("platform.billing.payments.reconcile", "require_recent_mfa", "FOR UPDATE", "body.amount > remaining",
                  "PARTIALLY_PAID", "SAAS_PAYMENT_RECONCILED", "status='ACTIVE'", "Paiement intégral confirmé"):
        assert token in route


def test_payment_never_accepts_a_currency_mismatch_or_overpayment():
    route = section("def record_manual_payment(")
    assert "La devise du paiement doit être celle de la facture" in route
    assert "Le paiement dépasse le solde restant" in route

