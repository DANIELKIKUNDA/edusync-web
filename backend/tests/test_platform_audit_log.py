"""Journal d'audit (lot 2026-10): contracts. Live behaviour (RBAC, immutability in the database, masking, search,
categories, filters, cursor pagination, sort, export = whole filtered set, export audited once, 100 000 events) is
proven by tools/local/audit_probe.py against a real database."""
from pathlib import Path

import pytest

from edusync.modules.platform_audit.api.router import CATEGORIES, _filters, _uuid_or_none, redact

ROOT = Path(__file__).resolve().parents[2]
ROUTER = (ROOT / "backend/src/edusync/modules/platform_audit/api/router.py").read_text(encoding="utf-8")
UI = (ROOT / "frontend/src/platform/audit.tsx").read_text(encoding="utf-8")


def test_sensitive_values_are_masked_counts_kept():
    out = redact({"password": "x", "temporary_password": "y", "totp_secret": "z", "access_token": "t", "refresh_token": "r", "api_key": "k",
                  "recovery_codes": ["A"], "recovery_codes_remaining": 7, "must_change_password": True, "nested": [{"cookie": "c"}], "note": "ok"})
    assert all(out[k] == "[masqué]" for k in ("password", "temporary_password", "totp_secret", "access_token", "refresh_token", "api_key", "recovery_codes"))
    assert out["recovery_codes_remaining"] == 7 and out["must_change_password"] is True and out["note"] == "ok"
    assert out["nested"][0]["cookie"] == "[masqué]"


def test_categories_are_derived_from_stored_data_only():
    assert CATEGORIES == ("FAILURES", "SECURITY", "PLATFORM", "SCHOOLS")
    for x in ("(:cat='FAILURES' AND a.result<>'SUCCESS')", "(:cat='SECURITY' AND a.entity_type='UserSecurity')",
              "(:cat='PLATFORM' AND a.school_id IS NULL)", "(:cat='SCHOOLS' AND a.school_id IS NOT NULL)"):
        assert x in ROUTER
    with pytest.raises(Exception):
        _filters(None, None, None, None, None, None, None, None, None, None, "INVENTED")


def test_identifier_search_is_exact_and_text_search_is_indexed():
    assert _uuid_or_none("5cbf447b-6e21-4cc7-b7f9-27336e0c4972") == "5cbf447b-6e21-4cc7-b7f9-27336e0c4972"
    assert _uuid_or_none("code refusé") is None
    assert "edusync_search_key(a.action || ' ' || a.entity_type || ' ' || coalesce(a.reason, ''))" in ROUTER
    mig = (ROOT / "backend/migrations/0082_audit_log_search.sql").read_text(encoding="utf-8")
    assert "idx_audit_search_trgm" in mig and "gin_trgm_ops" in mig and "trg_audit_no_update" in mig
    assert "0082_audit_log_search.sql" in (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")


def test_read_only_capabilities_and_bounded_streamed_export():
    assert '@router.put' not in ROUTER and '@router.patch' not in ROUTER and '@router.delete' not in ROUTER and '@router.post' not in ROUTER
    assert ROUTER.count('actor_ctx.require("platform.audit.read")') >= 2 and 'actor_ctx.require("platform.audit.export")' in ROUTER
    export = ROUTER[ROUTER.index("def audit_export("):ROUTER.index('@router.get("/{event_id}")')]
    assert "StreamingResponse(stream()" in export and "PLATFORM_AUDIT_EXPORTED" in export and "EXPORT_MAX_ROWS" in export
    assert "category" in export and "_filters(action, school, scope, actor, result, date_from, date_to, correlation_id, entity_id, q, category)" in export
    assert "('=', '+', '-', '@', '\\t', '\\r')" in export or '("=", "+", "-", "@", "\\t", "\\r")' in export


def test_detail_redacts_and_describes_existing_resources():
    detail = ROUTER[ROUTER.index("def audit_event("):]
    assert 'redact(out["old_json"])' in detail and 'out.pop("idempotency_key", None)' in detail
    assert "entity_is_campaign" in detail and "actor_is_member" in detail and "school_exists" in detail


def test_frontend_mobile_first_read_only_audit():
    for x in ("Toutes les actions tracées de la plateforme et des écoles, selon vos autorisations.", "Échecs", "Sécurité", "Charger la suite",
              "Voir les occurrences", "Réinitialiser", "Appliquer", "Copier l’identifiant de corrélation", "Voir l’école", "Voir la notification",
              "Résumé", "Contexte", "Ressource", "Technique", "Changements", "aucun événement ne peut être modifié ni supprimé"):
        assert x in UI, x
    assert "Modifier" not in UI and "Supprimer" not in UI and "Rechercher</button>" not in UI
    assert "window.setTimeout(() => set({q: qInput}), 300)" in UI and "writeUrl(f, event)" in UI and "scrollY.current" in UI
    assert "GROUP_GAP_MS" in UI and "last.action === r.action && last.actor_user_id === r.actor_user_id && last.school_id === r.school_id" in UI
