"""Regression: signed document links must re-check live authorization.

These tests deliberately assert the server-side guard rather than treating the
signed token as an irrevocable grant.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER = (ROOT / "src/edusync/modules/documents/api/router.py").read_text(encoding="utf-8")


def test_document_link_revalidates_live_permissions():
    method = ROUTER.split("def open_signed_document(", 1)[1]
    assert '"documents.open" not in permissions' in method
    assert "PostgresMembershipRepository(conn).permissions" in method
    assert "effective_capability_grants(" in method
    assert 'doc["required_capability"] not in object_store.school_wide_capabilities(current_actor)' in method


def test_document_link_does_not_exempt_document_creator():
    method = ROUTER.split("def open_signed_document(", 1)[1]
    assert method.index('if "documents.open" not in permissions:') < method.index('if str(doc["generated_by"]) != claim["user_id"]')
    assert "with services.tenant_db.tenant_transaction" in method
    assert "if not member or not doc:" in method


def test_section_only_archive_is_denied_before_owner_history_lookup():
    method = ROUTER.split("def document_history(", 1)[1].split("@router.post", 1)[0]
    assert 'actor.scopes_for("documents.history.read")' in method
    assert method.index("Historique documentaire sans provenance") < method.index("if scope == \"mine\"")


def test_section_only_signed_link_is_denied_before_owner_lookup():
    method = ROUTER.split("def document_link(", 1)[1].split("@router.get", 1)[0]
    assert 'actor.scopes_for("documents.open")' in method
    assert method.index("Document sans provenance de section") < method.index("found = conn.execute")


def test_signed_link_requires_current_schoolwide_open_grant():
    method = ROUTER.split("def open_signed_document(", 1)[1]
    assert 'current_actor.scopes_for("documents.open")' in method
    assert method.index('current_actor.scopes_for("documents.open")') < method.index('if str(doc["generated_by"])')
