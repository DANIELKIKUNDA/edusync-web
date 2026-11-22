"""V2 lot 2 — pedagogical calendar and school programmes (owner, 2026-11-22). Rules without a database;
tools/ci/pedagogy_calendar_programmes_postgres_integration.py proves them over real HTTP + PostgreSQL."""
from datetime import date
from pathlib import Path

import pytest

from edusync.modules.pedagogy.domain import calendar as cal
from edusync.modules.pedagogy.domain import programme as prog

ROOT = Path(__file__).resolve().parents[2]
Y0, Y1 = date(2026, 9, 1), date(2027, 7, 2)


@pytest.mark.parametrize("structure,n", [("TRIMESTRIEL", 9), ("SEMESTRIEL", 6)])
def test_proposal_covers_the_whole_year_in_order_without_gap(structure, n):
    periods = cal.propose(structure, Y0, Y1)
    assert [p.code for p in periods] == list(cal.CODES[structure]) and len(periods) == n
    assert periods[0].starts_on == Y0 and periods[-1].ends_on == Y1
    assert cal.validate(structure, periods, Y0, Y1) == []                       # contiguous: no uncovered day
    assert all(p.is_exam == p.code.startswith("EX") for p in periods)
    assert all(5 <= (p.ends_on - p.starts_on).days + 1 <= 10 for p in periods if p.is_exam)


def test_labels_in_plain_french():
    assert cal.label("TRIMESTRIEL", "P1") == "1re période" and cal.label("TRIMESTRIEL", "P6") == "6e période"
    assert cal.label("TRIMESTRIEL", "EX3") == "Examen du 3e trimestre" and cal.label("SEMESTRIEL", "EX1") == "Examen du 1er semestre"
    assert [cal.term_of(c) for c in ("P1", "P2", "EX1", "P3", "EX2", "P6", "EX3")] == [1, 1, 1, 2, 2, 3, 3]


def test_blocking_rules_and_gaps():
    ps = cal.propose("SEMESTRIEL", Y0, Y1)
    with pytest.raises(cal.CalendarError, match="Périodes attendues"):
        cal.validate("SEMESTRIEL", ps[:-1], Y0, Y1)
    with pytest.raises(cal.CalendarError, match="P5"):
        cal.validate("SEMESTRIEL", ps + [cal.Period("P5", Y1, Y1)], Y0, Y1)
    late = [cal.Period(p.code, p.starts_on, p.ends_on if p.code != "EX2" else date(2027, 8, 1)) for p in ps]
    with pytest.raises(cal.CalendarError, match="en dehors de l’année scolaire"):
        cal.validate("SEMESTRIEL", late, Y0, Y1)
    overlap = [cal.Period(p.code, p.starts_on if p.code != "P2" else ps[0].ends_on, p.ends_on) for p in ps]
    with pytest.raises(cal.CalendarError, match="commence avant la fin"):
        cal.validate("SEMESTRIEL", overlap, Y0, Y1)
    holiday = [cal.Period(p.code, p.starts_on if p.code != "P3" else date(2027, 2, 15), p.ends_on) for p in ps]
    gaps = cal.validate("SEMESTRIEL", holiday, Y0, Y1)                          # a holiday is shown, never refused
    assert len(gaps) == 1 and gaps[0]["after"] == "EX1" and gaps[0]["days"] == 14


def test_grade_entry_state():
    p = cal.Period("P1", date(2026, 9, 1), date(2026, 10, 16))
    assert cal.entry_state(p, validated=False, closed=False, today=date(2026, 9, 10)) == "DRAFT"
    assert cal.entry_state(p, validated=True, closed=False, today=date(2026, 8, 30)) == "UPCOMING"
    assert cal.entry_state(p, validated=True, closed=False, today=date(2026, 9, 10)) == "ONGOING"
    assert cal.entry_state(p, validated=True, closed=False, today=date(2026, 11, 1)) == "OPEN"
    assert cal.entry_state(p, validated=True, closed=True, today=date(2026, 9, 10)) == "CLOSED"
    assert [cal.entry_allowed(s) for s in ("DRAFT", "UPCOMING", "ONGOING", "OPEN", "CLOSED")] == [False, False, True, True, False]


def test_one_number_per_term_gives_all_maxima_and_respects_the_owner_rules():
    assert prog.maxima_from_terms("SEMESTRIEL", [30, 40], True) == [30, 30, 60, 40, 40, 80, 0, 0, 0]
    assert prog.maxima_from_terms("TRIMESTRIEL", [10, 10, 20], True) == [10, 10, 20, 10, 10, 20, 20, 20, 40]
    assert prog.maxima_from_terms("SEMESTRIEL", [100, 100], False) == [100, 100, 0, 100, 100, 0, 0, 0, 0]
    assert prog.terms_from_maxima("SEMESTRIEL", [30, 30, 60, 40, 40, 80, 0, 0, 0]) == [30, 40]
    with pytest.raises(prog.ProgrammeError):
        prog.maxima_from_terms("SEMESTRIEL", [10, 10, 10], True)                 # semester: two numbers
    with pytest.raises(prog.ProgrammeError):
        prog.maxima_from_terms("SEMESTRIEL", [0, 0], True)
    prog.check("SEMESTRIEL", "X", [30, 30, 60, 40, 40, 80, 0, 0, 0], True)
    with pytest.raises(prog.ProgrammeError, match="double"):
        prog.check("SEMESTRIEL", "X", [30, 30, 50, 30, 30, 60, 0, 0, 0], True)
    with pytest.raises(prog.ProgrammeError, match="même chose"):
        prog.check("SEMESTRIEL", "X", [100, 100, 0, 200, 100, 0, 0, 0, 0], False)


def test_compulsory_official_course_cannot_be_removed():
    prog.can_remove({"source": "OFFICIEL", "mandatory": False})
    prog.can_remove({"source": "ECOLE", "mandatory": True})
    with pytest.raises(prog.ProgrammeError, match="obligatoire"):
        prog.can_remove({"source": "OFFICIEL", "mandatory": True})


def test_migration_routes_and_rights():
    sql = (ROOT / "backend/migrations/0125_pedagogy_calendar_programmes.sql").read_text(encoding="utf-8")
    for c in ("programme_line_exam_is_double", "programme_line_equal_periods", "programme_line_no_exam", "uq_pedagogy_programme_validated",
              "ENABLE ROW LEVEL SECURITY", "'PREFET_ETUDES','DIRECTEUR_ETUDES'"):
        assert c in sql, c
    assert "DROP TABLE" not in sql.upper() and (ROOT / "backend/migrations/rollback/0125_pedagogy_calendar_programmes.sql").exists()
    assert '("0125_pedagogy_calendar_programmes", "0125_pedagogy_calendar_programmes.sql")' in (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")
    for f in ("calendar.py", "programmes.py"):
        api = (ROOT / "backend/src/edusync/modules/pedagogy/api" / f).read_text(encoding="utf-8")
        routes = api.count("@router.")
        assert api.count("Depends(require_pedagogy)") == routes and api.count("Depends(require_school_actor)") == routes, f
        assert 'text(f"' not in api
