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
    """Owner review 2026-11-21: every server action reachable, no horizontal overflow (bars no longer slide)."""
    for label in ("Abonnements des écoles", "Attribuer une offre", "Ajouter un tarif", "Publier ce tarif", "Émettre une facture",
                  "Enregistrer un paiement", "Nouvelle offre", "Changer l’état", "Exporter"):
        assert label in UI
    for call in ("createSubscription", "transitionSubscription", "createPlanVersion", "publishPlanVersion", "exportBillingCsv"):
        assert call in UI and call in API
    assert ".bl>*,.bl .ui-page-head,.bl .ui-page-head>*{min-width:0;max-width:100%}" in CSS      # nothing wider than the screen
    assert "<table" not in UI                                                                         # cards, never a wide table
    assert ".bl .ui-btn-sm,.bl-dialog .ui-btn{min-height:44px}" in CSS                               # touch targets
    assert "var(--es-border)" not in CSS and "var(--es-line)" in CSS                                  # real design tokens (dark mode)


def test_only_legal_subscription_moves_are_offered():
    from edusync.modules.subscriptions.domain.subscription import _ALLOWED
    block = UI.split("const MOVES: Record<string, string[]> = {", 1)[1].split("};", 1)[0]
    for state, targets in _ALLOWED.items():
        if state.value == "EXPIRED" or not targets:
            continue
        line = block.split(f"{state.value}: [", 1)[1].split("]", 1)[0]
        offered = {x.strip(" '") for x in line.split(",") if x.strip()}
        assert offered <= {t.value for t in targets}, (state, offered)


def test_sensitive_actions_are_hidden_without_their_capability():
    for cap in ("platform.billing.invoices.manage", "platform.billing.payments.reconcile", "platform.billing.plans.manage"):
        assert cap in UI


def test_frontend_mutations_use_idempotency_keys():
    assert API.count("'Idempotency-Key':key()") >= 4
    assert "recordPayment" in API and "issueInvoice" in API and "createPlan" in API


def test_school_cash_and_commercial_billing_are_explicitly_separated():
    assert "séparées des caisses des écoles" in UI

