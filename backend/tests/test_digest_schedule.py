"""Owner, 2026-11-19: reports leave on their own — Saturday after the cash closure (20:00 at the latest), month and term ends."""
from datetime import date, datetime

from edusync.modules.finance_recovery.application.digest_schedule import due_kinds, month_report_day
from edusync.modules.finance_recovery.domain.digest import quarter_of, title, Digest


def at(y, m, d, h):
    return datetime(y, m, d, h, 0)


def test_saturday_after_all_desks_closed_or_at_20h():
    assert due_kinds(at(2026, 11, 21, 15), sessions_today=2, open_today=0) == ["WEEK"]      # all closed, afternoon
    assert due_kinds(at(2026, 11, 21, 15), sessions_today=2, open_today=1) == []            # a desk still open
    assert due_kinds(at(2026, 11, 21, 10), sessions_today=1, open_today=0) == []            # too early
    assert due_kinds(at(2026, 11, 21, 20), sessions_today=2, open_today=1) == ["WEEK"]      # 20:00 at the latest
    assert due_kinds(at(2026, 11, 21, 20), sessions_today=0, open_today=0) == ["WEEK"]      # no desk opened that day
    assert due_kinds(at(2026, 11, 20, 21), sessions_today=0, open_today=0) == []            # Friday: nothing


def test_month_and_term_ends():
    assert month_report_day(date(2026, 11, 3)) == date(2026, 11, 30)
    assert month_report_day(date(2027, 1, 5)) == date(2027, 1, 30)                         # 31/01/2027 is a Sunday
    assert due_kinds(at(2026, 11, 30, 20), sessions_today=0, open_today=0) == ["MONTH"]
    assert due_kinds(at(2026, 12, 31, 20), sessions_today=0, open_today=0) == ["MONTH", "QUARTER"]
    assert due_kinds(at(2027, 7, 31, 20), sessions_today=0, open_today=0) == ["WEEK"]       # holidays: no month report


def test_terms_and_title():
    assert quarter_of(date(2026, 10, 2)) == (date(2026, 9, 1), date(2026, 12, 31))
    assert quarter_of(date(2027, 2, 2)) == (date(2027, 1, 1), date(2027, 3, 31))
    d = Digest(kind="QUARTER", start=date(2026, 9, 1), end=date(2026, 12, 31), school_name="APN")
    assert title(d) == "Votre trimestre (septembre – décembre 2026) à APN"
