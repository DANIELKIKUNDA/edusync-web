"""Owner, 2026-11-17: « l'interface ne doit jamais afficher une classe qui n'est pas de son périmètre » — for every role
given the finances with a section/class scope (préfet, directeur de section, directeur des études, de discipline…),
unless « toute l'école » is chosen in Accès & rôles."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from edusync.adapters import class_scope

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'backend/src/edusync'


class Cursor:
    def __init__(self, rows): self.rows, self.sql, self.args = rows, None, None
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, args): self.sql, self.args = sql, args
    def fetchall(self): return [(r,) for r in self.rows]


class Driver:
    def __init__(self, rows=()): self.cur = Cursor(list(rows))
    def cursor(self): return self.cur


def test_visible_class_ids_rule():
    sid = uuid4(); c1 = uuid4()
    assert class_scope.visible_class_ids(Driver(), sid, (('SCHOOL', None),)) is None
    assert class_scope.visible_class_ids(Driver(), sid, ()) is None            # same rule as the monthly recovery view
    assert class_scope.visible_class_ids(Driver(), sid, (('SECTION', None),)) == set()   # malformed grant: nothing
    d = Driver([c1])
    assert class_scope.visible_class_ids(d, sid, (('SECTION', 'secondaire'), ('CLASS', 'p1a'))) == {c1}
    assert d.cur.args == (sid, ['SECONDAIRE'], ['P1A'])


def test_scopes_union_only_counts_held_capabilities():
    actor = SimpleNamespace(permissions={'a'}, scopes_for=lambda c: (('SECTION', 'PRIMAIRE'),) if c == 'a' else (('SCHOOL', None),))
    assert class_scope.scopes_union(actor, 'a', 'b') == (('SECTION', 'PRIMAIRE'),)


def _services():
    @contextmanager
    def tx(**_): yield SimpleNamespace(connection=SimpleNamespace(driver_connection=Driver()))
    return SimpleNamespace(tenant_db=SimpleNamespace(tenant_transaction=tx))


def _actor(perms=('finance.analysis.by_fee.read', 'finance.checkout.balance.read')):
    return SimpleNamespace(school_id=uuid4(), user_id=uuid4(), permissions=set(perms), require=lambda c: None,
                           scopes_for=lambda c: (('SECTION', 'SECONDAIRE'),))


def test_fee_tracking_passes_the_visible_classes_everywhere(monkeypatch):
    from edusync.modules.finance_fee_tracking.api import router as R
    seen = {}
    allowed = {uuid4()}

    class Repo:
        def __init__(self, conn): pass
        def year(self, *a): return {'id': uuid4(), 'label': '2026-2027'}
        def scope_classes(self, school_id, scopes): return allowed
        def taxonomy(self, *a, class_ids=None): seen['taxonomy'] = class_ids; return []
        def overview(self, *a, class_ids=None): seen['overview'] = class_ids; return []
        def students_page(self, *a, class_ids=None, **k): seen['students'] = class_ids; self.last_totals = {}; return [], 0
        def student_summary(self, *a, class_ids=None): seen['student'] = class_ids; return {}
        def family_summary(self, *a, class_ids=None): seen['family'] = class_ids; return {}
    monkeypatch.setattr(R, 'PostgresFeeTrackingRepository', Repo)
    a, s = _actor(), _services()
    R.taxonomy(None, None, None, 'CDF', a, s); R.overview(None, 'CDF', None, None, None, None, a, s)
    R.students(None, 'CDF', None, None, None, None, None, None, 200, 0, a, s)
    R.student(uuid4(), 'CDF', a, s); R.family(uuid4(), 'CDF', a, s)
    assert seen == {k: allowed for k in ('taxonomy', 'overview', 'students', 'student', 'family')}


def test_fee_tracking_sql_filters_on_the_visible_classes():
    src = (SRC / 'adapters/postgres_fee_tracking.py').read_text(encoding='utf-8')
    assert src.count('e.class_id=ANY(%s)') == 2   # taxonomy + the student lines (overview, pages, pupil and family sheets)


def test_controls_registers_are_scoped():
    src = (SRC / 'modules/finance_controls/api/router.py').read_text(encoding='utf-8')
    for cap in ('finance.decisions.read', 'finance.responsibility.read', 'finance.credits.read'):
        assert f"**scope(c,actor,'{cap}')" in src
    assert "guard_student(c,actor,'finance.decisions.read',charge_id=charge_id)" in src
    assert "guard_student(c,actor,'finance.decisions.read',student_id=student_id)" in src
    assert "follow_up(actor.school_id,year_id,scope(c,actor,'finance.decisions.read'))" in src
    repo = (SRC / 'adapters/postgres_financial_decisions.py').read_text(encoding='utf-8')
    assert repo.count('CAST(:scope_all AS boolean) OR e.class_id=ANY(CAST(:scope_cids AS uuid[]))') == 2


def test_controls_guard_refuses_a_pupil_outside(monkeypatch):
    from edusync.modules.finance_controls.api import router as R
    monkeypatch.setattr(R, 'visible_class_ids', lambda *a: {uuid4()})
    conn = SimpleNamespace(connection=SimpleNamespace(driver_connection=None),
                           execute=lambda *a: SimpleNamespace(first=lambda: None))
    with pytest.raises(HTTPException) as e:
        R.guard_student(conn, _actor(), 'finance.decisions.read', student_id=uuid4())
    assert e.value.status_code == 403
    monkeypatch.setattr(R, 'visible_class_ids', lambda *a: None)
    R.guard_student(conn, _actor(), 'finance.decisions.read', student_id=uuid4())   # whole school: no refusal


def test_checkout_pupil_reads_are_scoped(monkeypatch):
    from edusync.modules.finance_checkout.api import router as R
    src = (SRC / 'modules/finance_checkout/api/router.py').read_text(encoding='utf-8')
    for fn in ('balance', 'registration_bundle', 'recommended_checkout', 'suggest_allocations', 'fee_bundle', 'anticipation', 'old_debts'):
        body = src.split(f'def {fn}(', 1)[1].split('\n@router', 1)[0]
        assert 'need_pupil(services,actor,' in body, fn
    assert 'class_ids=v' in src.split('def list_advance_funds(', 1)[1].split('\n@router', 1)[0]
    monkeypatch.setattr(R, '_pupil_in_scope', lambda *a, **k: False)
    with pytest.raises(HTTPException) as e:
        R.need_pupil(_services(), _actor(), 'finance.checkout.balance.read', enrollment_id=uuid4())
    assert e.value.status_code == 403


def test_class_picker_follows_the_capability_scope():
    src = (SRC / 'modules/settings/api/router.py').read_text(encoding='utf-8')
    body = src.split('def classes_selector(', 1)[1].split("@router.get('/classes')", 1)[0]
    assert 'visible_class_ids' in body and 'if capability not in actor.permissions:return []' in body
    ui = ROOT / 'frontend/src'
    assert "listClassSelector(token, yearId, 'finance.recovery.monthly.read')" in (ui / 'finance_followup.tsx').read_text(encoding='utf-8')
    assert "listClassSelector(token,undefined,'finance.analysis.by_fee.read')" in (ui / 'finance.tsx').read_text(encoding='utf-8')
    assert 'capability' in (ui / 'api.ts').read_text(encoding='utf-8').split('export async function listClassSelector', 1)[1].split('\n', 1)[0]
