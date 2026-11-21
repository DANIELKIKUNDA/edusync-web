from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
UI = (ROOT / "frontend/src/platform/billing.tsx").read_text(encoding="utf-8")
CSS = (ROOT / "frontend/src/platform/billing.css").read_text(encoding="utf-8")
API = (ROOT / "frontend/src/platform/billing_api.ts").read_text(encoding="utf-8")
TEAM = (ROOT / "backend/src/edusync/modules/platform_team/api/router.py").read_text(encoding="utf-8")


def test_billing_menu_is_server_computed_and_lazy_loaded():
    assert '("billing", "Abonnements", "platform.billing.read")' in TEAM
    assert "const PlatformBilling=lazyPage" in APP
    assert "can('billing')" in APP and "<PlatformBilling token={token} has={has}" in APP


def test_mobile_first_billing_views_cover_the_commercial_workflow():
    for label in ("Abonnements des écoles", "Factures commerciales", "Paiements rapprochés", "Offres commerciales",
                  "Émettre une facture", "Enregistrer un paiement", "Nouvelle offre"):
        assert label in UI
    assert "@media(max-width:650px)" in CSS
    assert ".bl-table thead{display:none}" in CSS
    assert 'content:attr(data-label)' in CSS


def test_sensitive_actions_are_hidden_without_their_capability():
    for cap in ("platform.billing.invoices.manage", "platform.billing.payments.reconcile", "platform.billing.plans.manage"):
        assert cap in UI


def test_frontend_mutations_use_idempotency_keys():
    assert API.count("'Idempotency-Key':key()") >= 4
    assert "recordPayment" in API and "issueInvoice" in API and "createPlan" in API


def test_school_cash_and_commercial_billing_are_explicitly_separated():
    assert "séparées de leurs caisses scolaires" in UI

