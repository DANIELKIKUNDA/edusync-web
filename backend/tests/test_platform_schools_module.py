"""Platform Schools module (lot 2026-10): directory, school sheet, creation, administrator continuity, export.

Pure helpers are tested directly; routes and UI are checked as contracts (the live behaviour is exercised end to end
by tools/local/schools_module_probe.py against a real stack)."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from edusync.modules.platform.application.schools_directory import (
    CONFIG_STATES, PROVINCE_CAPITALS, RDC_PROVINCES, SORTS, _search_sql, decode_cursor, encode_cursor, format_phone,
    normalize_phone, normalize_province)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "backend/src/edusync/modules/platform"
FRONT = ROOT / "frontend/src/platform"
ROUTER = (SRC / "api/router.py").read_text(encoding="utf-8")
DIRECTORY = (SRC / "application/schools_directory.py").read_text(encoding="utf-8")
MIGRATION = (ROOT / "backend/migrations/0078_schools_directory.sql").read_text(encoding="utf-8")


def section(src: str, start: str, end: str) -> str:
    return src[src.index(start):src.index(end, src.index(start))]


# ------------------------------------------------------------------ reference data and normalisation
def test_the_26_provinces_of_the_drc_with_their_capitals():
    assert len(RDC_PROVINCES) == 26 and len(set(RDC_PROVINCES)) == 26
    assert set(PROVINCE_CAPITALS) == set(RDC_PROVINCES)
    assert PROVINCE_CAPITALS["Kinshasa"] == "Kinshasa" and PROVINCE_CAPITALS["Nord-Kivu"] == "Goma"
    front = (FRONT / "schools_api.ts").read_text(encoding="utf-8")
    for p in RDC_PROVINCES:   # one reference list on both sides
        assert f"'{p}'" in front, p


@pytest.mark.parametrize("typed,expected", [("kasai central", "Kasaï-Central"), ("KINSHASA", "Kinshasa"), ("nord kivu", "Nord-Kivu"),
                                            ("Equateur", "Équateur"), ("  ", None), (None, None)])
def test_province_is_canonicalised(typed, expected):
    assert normalize_province(typed) == expected


def test_unknown_province_is_refused():
    with pytest.raises(ValueError):
        normalize_province("Katanga")   # former province, not one of the 26


@pytest.mark.parametrize("typed", ["0812345678", "081 234 5678", "+243 81 234 5678", "243812345678", "00243812345678", "081.234.56.78"])
def test_drc_phone_numbers_are_normalised_to_e164(typed):
    assert normalize_phone(typed) == "+243812345678"
    assert format_phone("+243812345678") == "+243 81 234 5678"


@pytest.mark.parametrize("typed", ["12345", "0712345678", "+243 81 234 567", "abc"])
def test_invalid_phone_numbers_are_refused(typed):
    with pytest.raises(ValueError):
        normalize_phone(typed)


def test_foreign_numbers_keep_their_prefix():
    assert normalize_phone("+33 6 12 34 56 78") == "+33612345678"
    assert format_phone("+33612345678") == "+33612345678"
    assert normalize_phone("") is None


# ------------------------------------------------------------------ search and keyset pagination
def test_search_requires_every_word_and_binds_parameters():
    sql, params = _search_sql("sainte-thérèse  2af6ba")
    assert params == {"w0": "sainte", "w1": "thérèse", "w2": "2af6ba"}
    assert sql.count(" AND ") == 2 and "edusync_search_key(CAST(:w0 AS text))" in sql
    assert "thérèse" not in sql   # values are never spliced into SQL
    assert _search_sql("   ") == ("TRUE", {})
    assert len(_search_sql("a b c d e f g h")[1]) == 5   # bounded


@pytest.mark.parametrize("sort", SORTS)
def test_cursor_round_trip(sort):
    row = {"id": uuid4(), "name": "Collège Sainte-Thérèse", "created_at": datetime(2026, 10, 18, tzinfo=timezone.utc), "status_rank": 1}
    k = decode_cursor(sort, encode_cursor(sort, row))
    assert k["kid"] == str(row["id"])
    assert decode_cursor(sort, None) is None


@pytest.mark.parametrize("cursor", ["%%%", "eyJzIjoibmFtZSJ9", "eyJzIjoibmFtZSIsImsiOltudWxsLCJ4Iiwibm90LWEtdXVpZCJdfQ"])
def test_forged_cursor_is_refused(cursor):
    with pytest.raises(ValueError):
        decode_cursor("name", cursor)


def test_cursor_of_another_sort_is_refused():
    row = {"id": uuid4(), "name": "A", "created_at": datetime.now(timezone.utc), "status_rank": 0}
    with pytest.raises(ValueError):
        decode_cursor("created", encode_cursor("name", row))


def test_directory_states_and_definitions():
    assert CONFIG_STATES == ("COMPLETE", "INCOMPLETE", "ADMIN_PENDING", "ADMIN_MISSING")
    # same "sans administrateur" definition as the dashboard item; counts in one query (no N+1)
    assert "r2.code='ADMIN_SYSTEME_ECOLE'" in DIRECTORY and "CROSS JOIN LATERAL platform_school_setup(b.id)" in DIRECTORY
    assert "ORDER BY {order} LIMIT :lim" in DIRECTORY


# ------------------------------------------------------------------ migration
def test_migration_is_provisioned_indexed_and_least_privilege():
    assert "0078_schools_directory.sql" in (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")
    for x in ("CREATE SEQUENCE IF NOT EXISTS school_code_seq", "idx_schools_search_trgm", "gin_trgm_ops", "idx_schools_created_id",
              "idx_schools_name_id", "SECURITY DEFINER", "SET search_path = public, pg_temp"):
        assert x in MIGRATION, x
    assert "GRANT EXECUTE ON FUNCTION platform_school_setup(uuid) TO edusync_platform" in MIGRATION


# ------------------------------------------------------------------ routes: permissions, validation, audit
def test_create_generates_the_code_server_side_and_never_accepts_one():
    create = section(ROUTER, "class SchoolCreate(", "\nclass ")
    assert "code:" not in create and "code =" not in create
    route = section(ROUTER, "def create_school(", "\n@router")
    assert "actor.require" in route or "platform.schools.create" in ROUTER
    assert "next_school_code(" in route


def test_directory_routes_are_permissioned_and_bounded():
    page = section(ROUTER, "def platform_schools_page(", "\n@router")
    assert "actor.require('platform.schools.read')" in page and "100" in page
    export = section(ROUTER, "def platform_schools_export(", "\n@router")
    assert "actor.require('platform.schools.read')" in export and "10000" in export and "PLATFORM_SCHOOLS_EXPORTED" in export
    assert "needs_admin=needs_admin" in export   # the export follows the same filters as the list
    assert "('=', '+', '-', '@', '\\t', '\\r')" in export   # spreadsheet formula injection neutralised


def test_update_is_permissioned_versioned_and_audited():
    upd = section(ROUTER, "def platform_update_school(", "\n@router")
    assert "actor.require('platform.schools.update')" in upd and "409" in upd and "PLATFORM_SCHOOL_UPDATED" in upd
    assert "DISABLED" in upd


def test_admin_bootstrap_never_takes_a_password_and_never_replays_it():
    boot = section(ROUTER, "class AdminBootstrap(", "\nclass ")
    assert "password:" not in boot and "password =" not in boot
    route = section(ROUTER, "def bootstrap_admin(", "\n@router")
    assert "new_temporary_password()" in route and 'issued.get("temporary_password")' in route
    assert "no-store" in route


def test_admin_access_reset_is_scoped_step_up_and_audited():
    route = section(ROUTER, "def platform_reset_admin_access(", "\n@router")
    for x in ("platform.school_admin.bootstrap", "require_recent_mfa", "PLATFORM_SCHOOL_ADMIN_ACCESS_RESET", "SCHOOL_ADMIN_ROLE"):
        assert x in route, x


def test_platform_does_not_manage_local_business_roles():
    for name in ("def platform_assign_standard_role(", "def platform_revoke_standard_role("):
        route = section(ROUTER, name, "\n@router")
        assert "SCHOOL_ADMIN_ROLE" in route and "403" in route, name


def test_no_dynamic_select_sql_in_the_router():
    assert 'text(f"SELECT' not in ROUTER and "text(f'SELECT" not in ROUTER


# ------------------------------------------------------------------ frontend contracts
def test_frontend_list_is_instant_cancellable_and_url_driven():
    ui = (FRONT / "schools.tsx").read_text(encoding="utf-8")
    assert "300" in ui and "AbortController" in ui and "Rechercher</button>" not in ui
    for x in ("history.pushState", "popstate", "Charger la suite", "role=\"row\"", "stopPropagation", "Toutes", "Actives", "Suspendues", "Désactivées"):
        assert x in ui, x


def test_frontend_sheet_and_dialogs():
    ui = (FRONT / "school_sheet.tsx").read_text(encoding="utf-8")
    for x in ("Écoles", "Général", "Promoteur / contact principal", "Administrateurs / accès", "Configuration", "Historique de gouvernance",
              "Dernière activité", "Créer l’administrateur initial", "Réinitialiser l’accès", "affiché une seule fois"):
        assert x in ui, x
    assert "type=\"password\"" not in ui   # the manager never types an administrator password
    api = (FRONT / "schools_api.ts").read_text(encoding="utf-8")
    assert "STATUS_LABEL" in api and "ACTIVE: 'Actif', SUSPENDED: 'Suspendu', DISABLED: 'Désactivé'" in api
