"""Settings fixes of 2026-10-24 (real administrator walkthrough):
- saving the school identity failed with HTTP 500 « droit refusé pour la table schools »: the tenant role had only SELECT.
  Migration 0086 grants UPDATE on the identity columns only, and the router saves through save_identity (never code/status);
- study options exist only in the Secondaire (Humanités); an option only applies to a Humanités class;
- a uniqueness violation is explained in the user's terms, never as raw SQL.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIG = (ROOT / "backend/migrations/0086_school_identity_tenant_update.sql").read_text(encoding="utf-8")
ROUTER = (ROOT / "backend/src/edusync/modules/settings/api/router.py").read_text(encoding="utf-8")
REPO = (ROOT / "backend/src/edusync/adapters/postgres_repositories.py").read_text(encoding="utf-8")
PROVISION = (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")


def test_tenant_may_update_identity_columns_only():
    grant = re.search(r"GRANT UPDATE \(([^)]*)\) ON schools TO edusync_tenant", MIG)
    assert grant, "column-level grant missing"
    cols = {c.strip() for c in grant.group(1).split(",")}
    assert cols == {"name", "logo_url", "email", "phone", "address", "city", "province", "updated_at", "version"}
    assert "code" not in cols and "status" not in cols                     # platform decisions stay platform decisions
    assert '("0086_school_identity_tenant_update", "0086_school_identity_tenant_update.sql")' in PROVISION


def test_identity_save_never_touches_code_or_status():
    body = REPO.split("def save_identity", 1)[1].split("@dataclass", 1)[0]
    sql = body.split('"""', 2)[1] if '"""' in body else body
    assert "UPDATE schools" in body and "code=" not in body.split("WHERE")[0] and "status=" not in body.split("WHERE")[0]
    assert "schools.save_identity(school)" in ROUTER and "schools.save(school)" not in ROUTER.split("def update_identity", 1)[1].split("@router", 1)[0]
    del sql


def test_options_only_in_the_secondaire_and_only_on_humanities_classes():
    assert "Les options n’existent qu’en Secondaire (Humanités)" in ROUTER and "!='SECONDAIRE'" in ROUTER
    assert "HUMANITIES_REFERENCES={'H1','H2','H3','H4'}" in ROUTER
    assert "Une option ne s’applique qu’aux classes des Humanités" in ROUTER


def test_integrity_errors_are_explained_without_raw_sql():
    error = ROUTER.split("def _error", 1)[1].split("def _audit_and_outbox", 1)[0]
    assert "Cet élément existe déjà" in error
    integrity = error.split("if isinstance(exc,IntegrityError):", 1)[1].split("if isinstance(exc,(ValueError", 1)[0]
    assert "str(exc)" not in integrity.split("raw=")[0] and "detail=msg" in integrity      # IntegrityError never echoes SQL
