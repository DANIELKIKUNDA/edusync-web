"""Owner, 2026-11-19: the real date of an abandon or a transfer, and each school sets whether the month of departure is owed."""
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from edusync.adapters.postgres_schooling import PostgresSchoolingRepository

ROOT = Path(__file__).resolve().parents[2]


def repo(day):
    r = PostgresSchoolingRepository.__new__(PostgresSchoolingRepository)
    r.connection = SimpleNamespace(execute=lambda *a, **k: SimpleNamespace(scalar=lambda: day))
    return r


def test_without_a_school_rule_the_month_of_departure_stays_owed():
    assert repo(None).departure_cutoff('s', 'ABANDON', date(2026, 9, 15)) == date(2026, 9, 15)


def test_school_day_frees_the_month_of_departure_up_to_that_day():
    assert repo(15).departure_cutoff('s', 'ABANDON', date(2026, 9, 15)) == date(2026, 9, 1)
    assert repo(15).departure_cutoff('s', 'TRANSFER', date(2026, 9, 3)) == date(2026, 9, 1)
    assert repo(15).departure_cutoff('s', 'ABANDON', date(2026, 9, 16)) == date(2026, 9, 16)


def test_a_suspension_keeps_the_default_rule():
    assert repo(31).departure_cutoff('s', 'SUSPEND', date(2026, 9, 5)) == date(2026, 9, 5)


def test_billing_policy_route_keeps_the_rule_when_an_older_screen_omits_it():
    src = (ROOT / 'backend/src/edusync/modules/settings/api/router.py').read_text(encoding='utf-8')
    assert "if 'departure_month_not_due_until_day' not in body.model_fields_set:data.pop('departure_month_not_due_until_day')" in src
    rep = (ROOT / 'backend/src/edusync/adapters/postgres_settings.py').read_text(encoding='utf-8')
    assert "departure_month_not_due_until_day is self.KEEP" in rep


def test_lifecycle_asks_the_real_date_and_refuses_the_future():
    ui = (ROOT / 'frontend/src/schooling.tsx').read_text(encoding='utf-8')
    assert "promptDate({title:type==='ABANDON'?'Date de l’abandon'" in ui and 'effective_date:effective' in ui and 'max:today()' in ui
    assert 'effective_date:today()' not in ui
    src = (ROOT / 'backend/src/edusync/adapters/postgres_schooling.py').read_text(encoding='utf-8')
    assert 'if effective_date>date.today():raise ValueError' in src
    mig = (ROOT / 'backend/migrations/0115_departure_month_rule.sql').read_text(encoding='utf-8')
    assert 'BETWEEN 1 AND 31' in mig
