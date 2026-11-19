"""Owner, 2026-11-17: a préfet (section scope) saw the WHOLE school in « Registre des classes », « Synthèse par classe »
and « Synthèse par section ». Every recovery read must stay inside the actor's scope, on the server."""
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from edusync.adapters.postgres_finance_recovery import PostgresFinanceRecoveryRepository
from edusync.modules.finance_recovery.api import router as R

SEC, PRIM = uuid4(), uuid4()
C_SEC, C_PRIM = uuid4(), uuid4()
YEAR = {'id': uuid4(), 'label': '2026-2027'}


def _row(cid, sid, label, slabel):
    return {'class_id': cid, 'class_label': label, 'section_id': sid, 'section_label': slabel, 'debtors': 10, 'in_order': 6,
            'not_in_order': 4, 'expected': 100, 'cash_collected': 50, 'outside_cash': 10, 'regularized_total': 60, 'remaining': 40,
            'recovery_rate': 60}


class FakeRepo:
    def __init__(self, conn): self.visible = conn.visible
    def year(self, *_): return dict(YEAR)
    def school_identity(self, *_): return {'name': 'École'}
    def scope_classes(self, school_id, scopes): return self.visible
    def classes(self, *_):
        return [{'id': C_SEC, 'label': '3e SC', 'section_id': SEC, 'section_label': 'Secondaire'},
                {'id': C_PRIM, 'label': '1re primaire', 'section_id': PRIM, 'section_label': 'Primaire'}]
    def section_list(self, *_): return [{'id': SEC, 'label': 'Secondaire'}, {'id': PRIM, 'label': 'Primaire'}]
    def scope_summary(self, *a, **k): return [_row(C_SEC, SEC, '3e SC', 'Secondaire'), _row(C_PRIM, PRIM, '1re primaire', 'Primaire')]
    def class_monthly(self, *_): return []
    def class_register(self, *_): return {'class_label': 'x', 'columns': [], 'students': [], 'currency': 'CDF', 'footer': {}}


def _env(monkeypatch, visible):
    monkeypatch.setattr(R, 'PostgresFinanceRecoveryRepository', FakeRepo)

    @contextmanager
    def tx(**_): yield SimpleNamespace(visible=visible)
    services = SimpleNamespace(tenant_db=SimpleNamespace(tenant_transaction=tx))
    actor = SimpleNamespace(school_id=uuid4(), user_id=uuid4(), require=lambda c: None,
                            scopes_for=lambda c: (('SECTION', 'SECONDAIRE'),) if visible is not None else (('SCHOOL', None),))
    return actor, services


def test_prefet_sees_only_his_classes_and_section(monkeypatch):
    actor, services = _env(monkeypatch, {C_SEC})
    assert [c['id'] for c in R.recovery_classes(None, actor, services)['items']] == [C_SEC]
    assert [s['id'] for s in R.sections(None, actor, services)['items']] == [SEC]
    out = R.summary('school', actor=actor, services=services, year_id=None, class_id=None, section_id=None, fee_type_id=None,
                    period_order=None, currency='CDF')
    assert [r['label'] for r in out['items']] == ['Secondaire'] and 'PÉRIMÈTRE' in out['title']
    out = R.summary('section', actor=actor, services=services, year_id=None, class_id=None, section_id=None, fee_type_id=None,
                    period_order=None, currency='CDF')
    assert [r['label'] for r in out['items']] == ['3e SC']


def test_prefet_cannot_open_a_class_outside_his_section(monkeypatch):
    actor, services = _env(monkeypatch, {C_SEC})
    with pytest.raises(HTTPException) as e:
        R.class_register(C_PRIM, None, 'CDF', actor, services)
    assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:
        R.summary('class', actor=actor, services=services, year_id=None, class_id=C_PRIM, section_id=None, fee_type_id=None,
                  period_order=None, currency='CDF')
    assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:
        R.followup(C_PRIM, None, True, None, 'CDF', actor, services)
    assert e.value.status_code == 403
    assert R.class_register(C_SEC, None, 'CDF', actor, services)['class_label'] == 'x'


def test_school_wide_grant_still_sees_everything(monkeypatch):
    actor, services = _env(monkeypatch, None)
    assert len(R.recovery_classes(None, actor, services)['items']) == 2
    assert len(R.sections(None, actor, services)['items']) == 2
    out = R.summary('school', actor=actor, services=services, year_id=None, class_id=None, section_id=None, fee_type_id=None,
                    period_order=None, currency='CDF')
    assert len(out['items']) == 2 and out['title'] == "SYNTHÈSE GLOBALE DE L'ÉCOLE"


def test_scope_classes_follows_the_monthly_rule():
    repo = PostgresFinanceRecoveryRepository.__new__(PostgresFinanceRecoveryRepository)
    assert repo.scope_classes(uuid4(), (('SCHOOL', None),)) is None
    assert repo.scope_classes(uuid4(), ()) == set()


@pytest.mark.parametrize(("scopes", "condition", "section_args"), [
    ((("SECTION", "SECONDAIRE"),), "upper(ss.code)=ANY(%s)", (["SECONDAIRE"],)),
    ((("SECTION", "PRIMAIRE"), ("SECTION", "MATERNELLE")), "upper(ss.code)=ANY(%s)", (["PRIMAIRE", "MATERNELLE"],)),
    ((("SCHOOL", None),), "AND TRUE", ()),
    ((), "AND FALSE", ()),
])
def test_monthly_chart_uses_explicit_finance_scope(scopes, condition, section_args):
    class Cursor:
        def execute(self, sql, params):
            assert condition in sql
            assert params[3:] == section_args
            assert "GROUP BY ord,month_label,enrollment_id" in sql

        def fetchall(self):
            return []

    @contextmanager
    def cursor(**_):
        yield Cursor()

    repo = PostgresFinanceRecoveryRepository(SimpleNamespace(connection=SimpleNamespace(driver_connection=SimpleNamespace(cursor=cursor))))
    assert repo.monthly(uuid4(), YEAR["id"], "CDF", scopes=scopes) == []
