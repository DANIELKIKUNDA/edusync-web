"""School-wide migration is distinct from daily section supervision."""
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException

from edusync.shared.application.context import ActorContext
from edusync.modules.migration_import.api.router import need, import_contract_registry

CAP = 'migration.finance_history.analyze'


def actor(scopes, permissions=(CAP,)):
    return ActorContext(user_id=uuid4(), school_id=uuid4(), membership_id=uuid4(),
                        permissions=frozenset(permissions), capability_scopes=tuple(scopes))


@pytest.mark.parametrize('scopes', [(), ((CAP, 'SECTION', 'SECONDAIRE'),),
    ((CAP, 'CLASS', '7A'),), ((CAP, 'SECTION', 'SECONDAIRE'), ('students.read', 'SCHOOL', None))])
def test_global_import_denies_missing_or_partial_scope(scopes):
    a = actor(scopes)
    with pytest.raises(HTTPException) as error:
        need(a, CAP)
    assert error.value.status_code == 403
    assert import_contract_registry(a)['contracts'] == []


def test_explicit_school_delegation_remains_available():
    a = actor(((CAP, 'SCHOOL', None),))
    need(a, CAP)
    assert [c['kind'] for c in import_contract_registry(a)['contracts']] == ['FINANCE_HISTORY']


def test_school_scope_without_permission_is_insufficient():
    with pytest.raises(HTTPException) as error:
        need(actor(((CAP, 'SCHOOL', None),), permissions=()), CAP)
    assert error.value.status_code == 403


@pytest.mark.parametrize('role', ['PREFET_ETUDES', 'DIRECTION_SECTION'])
def test_section_leadership_has_no_import_by_default(role):
    registry = json.loads((Path(__file__).resolve().parents[2] / 'contracts/CAPABILITY_REGISTRY.json').read_text())
    assert not any(c.startswith('migration.') for c in registry['standard_roles'][role]['capabilities'])


@pytest.mark.parametrize('cap,path', [
    ('migration.students.analyze', '/students/batches'),
    ('migration.staff.analyze', '/staff/template.xlsx'),
    ('migration.finance_history.analyze', '/finance-history/template.xlsx'),
])
def test_partial_import_scope_is_refused_by_http_before_database(cap, path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from edusync.bootstrap.dependencies import require_school_actor, get_services
    from edusync.modules.migration_import.api.router import router
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_school_actor] = lambda: actor(((cap, 'SECTION', 'SECONDAIRE'),), (cap,))
    # Any access to a database would fail: authorization must happen first.
    app.dependency_overrides[get_services] = lambda: object()
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 403, response.text
