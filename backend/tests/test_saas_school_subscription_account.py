from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTER = (ROOT / "backend/src/edusync/modules/subscriptions/api/school_router.py").read_text(encoding="utf-8")
MIGRATION = (ROOT / "backend/migrations/0119_saas_school_subscription_account.sql").read_text(encoding="utf-8")
APP = (ROOT / "backend/src/edusync/bootstrap/app.py").read_text(encoding="utf-8")
PROJECTION = (ROOT / "backend/src/edusync/modules/access/application/projection.py").read_text(encoding="utf-8")
FRONT = (ROOT / "frontend/src/platform/school_subscription.tsx").read_text(encoding="utf-8")
CSS = (ROOT / "frontend/src/platform/school_subscription.css").read_text(encoding="utf-8")


def test_school_account_is_read_only_and_bound_to_the_token_school():
    assert ROUTER.count("@router.") == 1 and '@router.get("/account")' in ROUTER
    assert "Depends(require_school_actor)" in ROUTER
    assert 'actor.require("subscription.account.read")' in ROUTER
    assert "school_id = actor.school_id" in ROUTER
    assert "school_id:" not in ROUTER.split("def school_subscription_account(", 1)[1].split("):", 1)[0]
    assert ROUTER.count("school_id=:school") >= 3


def test_school_never_receives_commercial_mutation_capabilities():
    assert "platform.billing." not in ROUTER
    assert "INSERT INTO saas_" not in ROUTER and "UPDATE saas_" not in ROUTER and "DELETE FROM saas_" not in ROUTER


def test_capability_is_provisioned_for_the_four_accountable_roles():
    assert "0119_saas_school_subscription_account.sql" in (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")
    assert "subscription.account.read" in MIGRATION
    for role in ("ADMIN_SYSTEME_ECOLE", "PROMOTEUR", "GESTIONNAIRE", "RESPONSABLE_FINANCE"):
        assert role in MIGRATION
    assert 'school_subscription_router, prefix="/api/v1/subscription"' in APP


def test_navigation_is_server_projected_from_the_school_capability():
    assert '("subscription", "Mon abonnement", "receipt", ("subscription.account.read",))' in PROJECTION
    assert "module==='subscription'?<SchoolSubscriptionPage" in (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")


def test_mobile_account_explains_access_preservation_and_separation():
    for wording in ("Mon abonnement", "Fonctionnalités incluses", "Factures", "Paiements confirmés",
                    "Vos données sont conservées", "distinct des finances de l’école"):
        assert wording in FRONT
    assert "@media(max-width:650px)" in CSS and ".sa-table thead{display:none}" in CSS

