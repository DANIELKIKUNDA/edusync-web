"""Annuaire « Utilisateurs & accès » (lot 2026-10): read-only directory of platform and school identities.

Pure helpers are tested directly; routes and UI are checked as contracts (live behaviour: tools/local/identities_probe.py,
scale: tools/local/identities_scale_probe.py)."""
from pathlib import Path
from uuid import uuid4

import pytest

from edusync.modules.platform.application.identities_directory import (
    SCOPES, STATUSES, _filters, _search, decode_cursor, encode_cursor)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "backend/src/edusync/modules"
ROUTER = (SRC / "platform/api/router.py").read_text(encoding="utf-8")
DIRECTORY = (SRC / "platform/application/identities_directory.py").read_text(encoding="utf-8")
UI = (ROOT / "frontend/src/platform/identities.tsx").read_text(encoding="utf-8")
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")


def section(src: str, start: str, end: str) -> str:
    return src[src.index(start):src.index(end, src.index(start))]


def test_search_binds_every_word_and_is_bounded():
    where, params = _search("Ilunga  béatrice@école")
    assert params == {"w0": "Ilunga", "w1": "béatrice@école"} and len(where) == 2
    assert all("edusync_search_key(CAST(:w" in w for w in where) and "Ilunga" not in " ".join(where)
    assert len(_search("a b c d e f g")[1]) == 5
    assert _search("  ") == ([], {})


def test_cursor_round_trip_and_forgery():
    row = {"id": uuid4(), "full_name": "Agent Support"}
    assert decode_cursor(encode_cursor(row)) == {"k1": "agent support", "kid": str(row["id"])}
    assert decode_cursor(None) is None
    for forged in ("%%%", "Zm9yZ2Vk", "WyJhIiwibm90LWEtdXVpZCJd"):
        with pytest.raises(ValueError):
            decode_cursor(forged)


def test_filters_are_parameterised():
    where, params = _filters("x", "SCHOOL", "DISABLED", uuid4(), "CAISSIER", True)
    sql = " ".join(where)
    assert ":school" in sql and ":role" in sql and "CAISSIER" not in sql and params["role"] == "CAISSIER"
    assert "NOT u.active" in sql and "sm.active" in sql
    assert SCOPES == ("PLATFORM", "SCHOOL") and STATUSES == ("ACTIVE", "PENDING", "SUSPENDED", "DISABLED")


def test_active_accesses_filter_has_the_dashboard_definition():
    dash = (SRC / "platform/application/dashboard.py").read_text(encoding="utf-8")
    assert "EXISTS (SELECT 1 FROM school_memberships m WHERE m.user_id=u.id AND m.active)" in dash
    where, _ = _filters(None, None, None, None, None, True)
    assert where == ["u.active AND EXISTS (SELECT 1 FROM school_memberships sm WHERE sm.user_id=u.id AND sm.active)"]


def test_page_details_are_computed_for_the_page_only():
    # one count + one page query; per-row details are LATERAL joins on the LIMITed page (no N+1)
    assert "WITH page AS (" in DIRECTORY and "LIMIT :lim" in DIRECTORY and DIRECTORY.count("LEFT JOIN LATERAL") >= 4
    assert "ORDER BY lower(u.full_name), u.id" in DIRECTORY


def test_migration_indexes_search_and_order():
    m = (ROOT / "backend/migrations/0079_identities_directory.sql").read_text(encoding="utf-8")
    assert "idx_users_search_trgm" in m and "gin_trgm_ops" in m and "idx_users_name_id ON users(lower(full_name), id)" in m
    assert "0079_identities_directory.sql" in (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")


def test_routes_are_read_only_permissioned_and_validated():
    for name in ("def platform_identities(", "def platform_identity_filters(", "def platform_identity_detail("):
        route = section(ROUTER, name, "\n@router")
        assert "actor.require('platform.schools.read')" in route, name
    assert "@router.post('/identities" not in ROUTER and "@router.patch('/identities" not in ROUTER and "@router.delete('/identities" not in ROUTER
    listing = section(ROUTER, "def platform_identities(", "\n@router")
    assert "422" in listing and "min(limit, 100)" in listing and "len(q) > 80" in listing


def test_security_signals_follow_the_team_capability():
    detail = section(ROUTER, "def platform_identity_detail(", "\n@router")
    assert "can_security='platform.collaborators.manage' in actor.permissions" in detail
    assert "password_hash" not in DIRECTORY.split("def identity_detail", 1)[1]


def test_screen_is_named_and_read_only():
    assert "['access','lock','Utilisateurs & accès']" in APP and "Accès écoles" not in APP
    team = (SRC / "platform_team/api/router.py").read_text(encoding="utf-8")
    assert '("access", "Utilisateurs & accès", "platform.schools.read")' in team
    for x in ("Utilisateurs & accès", "Tous", "Plateforme", "Écoles", "Charger la suite", "AbortController", "300", "role=\"row\"",
              "Dernière activité", "Rattachements école", "Gérer dans Équipe plateforme", "Fiche école"):
        assert x in UI, x
    assert "Rechercher</button>" not in UI
    # no new mutation: the only write is the existing collaborator action, unchanged (same API functions)
    assert UI.count("await platform") == 2 and "platformGrantCollaborator" in UI and "platformRevokeCollaborator" in UI


def test_url_keys_do_not_collide_with_the_schools_screen():
    assert "ACCESS_URL_KEYS.test(window.location.search)?'access'" in APP
    assert "/[?&](user|iq|scope|istatus|ischool|role|ipage|iactive)=/" in UI
