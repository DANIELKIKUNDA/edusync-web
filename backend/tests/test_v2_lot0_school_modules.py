"""V2 lot 0 — modules of a school (owner, 2026-11-22).

« Chaque école n'aura pas la V2 : on va la vendre séparément » ; « il faut permettre aux écoles existantes qui n'ont pas de
module de leur donner des modules ». Rules tested here without a database; tools/ci/school_modules_postgres_integration.py
proves them over real HTTP + PostgreSQL.
"""
from pathlib import Path

import pytest

from edusync.modules.school_modules.domain.catalog import (ENFORCED, PEDAGOGY, SWITCHABLE, V1_MODULES, ModuleRuleError,
                                                           check_activation, check_withdrawal, clean_reason)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "backend/src/edusync"
KNOWN = set(V1_MODULES) | {PEDAGOGY, "GRADES", "REPORT_CARDS"}
DEPS = {PEDAGOGY: ["CORE_SCHOOL"], "GRADES": [PEDAGOGY], "REPORT_CARDS": ["GRADES"], "FINANCE": ["CORE_SCHOOL"]}


def test_one_pedagogy_module_switchable_and_enforced_v1_only_recorded():
    assert V1_MODULES == ("CORE_SCHOOL", "ENROLLMENT", "FINANCE", "RECOVERY", "REPORTS", "PERSONNEL", "DOCUMENTS", "COMMUNICATIONS")
    assert SWITCHABLE == {PEDAGOGY} == ENFORCED and PEDAGOGY == "ACADEMIC"


def test_activation_rules():
    v1 = set(V1_MODULES)
    check_activation(PEDAGOGY, known=KNOWN, active=v1, dependencies=DEPS[PEDAGOGY], school_status="ACTIVE")
    with pytest.raises(ModuleRuleError, match="déjà actif"):
        check_activation(PEDAGOGY, known=KNOWN, active=v1 | {PEDAGOGY}, dependencies=DEPS[PEDAGOGY], school_status="ACTIVE")
    with pytest.raises(ModuleRuleError, match="requis manquants : CORE_SCHOOL"):
        check_activation(PEDAGOGY, known=KNOWN, active=set(), dependencies=DEPS[PEDAGOGY], school_status="ACTIVE")
    with pytest.raises(ModuleRuleError, match="suspendue"):
        check_activation(PEDAGOGY, known=KNOWN, active=v1, dependencies=DEPS[PEDAGOGY], school_status="SUSPENDED")
    with pytest.raises(ModuleRuleError, match="V1"):
        check_activation("FINANCE", known=KNOWN, active=set(), dependencies=["CORE_SCHOOL"], school_status="ACTIVE")
    with pytest.raises(LookupError):
        check_activation("INCONNU", known=KNOWN, active=v1, dependencies=[], school_status="ACTIVE")


def test_withdrawal_rules():
    v1 = set(V1_MODULES)
    check_withdrawal(PEDAGOGY, known=KNOWN, active=v1 | {PEDAGOGY}, dependents=DEPS)
    with pytest.raises(ModuleRuleError, match="pas actif"):
        check_withdrawal(PEDAGOGY, known=KNOWN, active=v1, dependents=DEPS)
    with pytest.raises(ModuleRuleError, match="ne se retirent pas"):
        check_withdrawal("FINANCE", known=KNOWN, active=v1, dependents=DEPS)
    with pytest.raises(ModuleRuleError, match="dépendent : GRADES"):            # a later module needing the pedagogy blocks it
        check_withdrawal(PEDAGOGY, known=KNOWN, active=v1 | {PEDAGOGY, "GRADES"}, dependents=DEPS)


def test_reason_is_required():
    assert clean_reason("  Contrat   signé le 22/11  ") == "Contrat signé le 22/11"
    with pytest.raises(ModuleRuleError):
        clean_reason("ok")


def test_migration_records_v1_modules_for_every_existing_school_and_is_additive():
    sql = (ROOT / "backend/migrations/0123_school_modules.sql").read_text(encoding="utf-8")
    for code in V1_MODULES:
        assert f"('{code}')" in sql
    assert "FROM schools s" in sql and "'MIGRATION', 'ACTIVE'" in sql and "WHERE NOT EXISTS" in sql   # twice → no duplicate
    assert "ACADEMIC" in sql and "'ACADEMIC'," not in sql.split("INSERT INTO saas_entitlements")[1].split(";")[0]  # nobody gets V2
    upper = sql.upper()
    assert "DROP " not in upper and "DELETE FROM" not in upper and "TRUNCATE" not in upper
    assert (ROOT / "backend/migrations/rollback/0123_school_modules.sql").exists()
    assert '("0123_school_modules", "0123_school_modules.sql")' in (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")


def test_new_school_gets_v1_modules_and_subscription_keeps_a_module_in_service():
    platform = (SRC / "modules/platform/api/router.py").read_text(encoding="utf-8")
    assert "grant_v1_modules(conn, school.id)" in platform
    billing = (SRC / "modules/subscriptions/api/router.py").read_text(encoding="utf-8")
    assert "ON CONFLICT (school_id,module_code) WHERE status='ACTIVE' DO NOTHING" in billing


def test_platform_routes_are_guarded_audited_and_step_up():
    api = (SRC / "modules/school_modules/api/platform_router.py").read_text(encoding="utf-8")
    assert 'actor.require(READ)' in api and 'actor.require(MANAGE)' in api and "require_recent_mfa(services, actor, MANAGE)" in api
    assert "SCHOOL_MODULE_ACTIVATED" in api and "SCHOOL_MODULE_WITHDRAWN" in api and "Idempotency-Key" in api
    service = (SRC / "modules/school_modules/application/service.py").read_text(encoding="utf-8")
    assert "DELETE FROM" not in service.upper() and "status='REVOKED'" in service   # a withdrawal keeps the history
    guard = (SRC / "modules/school_modules/api/guard.py").read_text(encoding="utf-8")
    assert "MODULE_NOT_ACTIVE" in guard and "platform_transaction" in guard


def test_school_sees_its_modules_and_v2_route_is_behind_the_gate():
    access = (SRC / "modules/access/api/router.py").read_text(encoding="utf-8")
    assert '"modules": school_module_codes(services, actor.school_id)' in access
    pedagogy = (SRC / "modules/school_modules/api/pedagogy_router.py").read_text(encoding="utf-8")
    assert "Depends(require_pedagogy)" in pedagogy
    app = (SRC / "bootstrap/app.py").read_text(encoding="utf-8")
    assert 'prefix="/api/v1/pedagogy"' in app
