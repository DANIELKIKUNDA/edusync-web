"""V2 lot 3b — grade entry and conduct facts (owner, 2026-11-22: « les enseignants ne doivent pas se plaindre »).
Rules without a database; tools/ci/pedagogy_grades_postgres_integration.py proves them over real HTTP + PostgreSQL."""
from datetime import date
from pathlib import Path

import pytest

from edusync.modules.pedagogy.domain import grades as gd

ROOT = Path(__file__).resolve().parents[2]


def test_what_the_teacher_types():
    assert gd.parse_cell("14", 20) == ("NOTE", 14) and gd.parse_cell(" 0 ", 20) == ("NOTE", 0)
    assert gd.parse_cell("a", 20) == ("ABSENT", None) and gd.parse_cell("ABS", 20) == ("ABSENT", None)
    assert gd.parse_cell("d", 20) == ("DISPENSE", None) and gd.parse_cell("", 20) == (None, None)
    with pytest.raises(gd.GradeError, match="Maximum 20"):
        gd.parse_cell("21", 20)
    for bad in ("12.5", "-1", "douze", "1 2"):
        with pytest.raises(gd.GradeError):
            gd.parse_cell(bad, 20)


def test_parent_rules_on_a_mark():
    gd.check("NOTE", 20, 20, has_exam=True, period="P1")
    gd.check(None, None, 20, has_exam=True, period="P1")                       # emptied, never deleted
    with pytest.raises(gd.GradeError, match="pas d’examen"):
        gd.check("NOTE", 10, 40, has_exam=False, period="EX1")
    with pytest.raises(gd.GradeError):
        gd.check("ABSENT", 5, 20, has_exam=True, period="P1")
    assert gd.is_failing(9, 20) and not gd.is_failing(10, 20) and not gd.is_failing(None, 20)


def test_pasted_column_from_excel_whatsapp_or_notes():
    assert gd.parse_pasted("12\n15/20\na\n\n18\n\n", 20) == [("NOTE", 12), ("NOTE", 15), ("ABSENT", None), (None, None), ("NOTE", 18)]
    assert gd.parse_pasted("KABILA Jean\t14\nMBUYI Anne;9", 20) == [("NOTE", 14), ("NOTE", 9)]
    with pytest.raises(gd.GradeError, match="Ligne 2 : Maximum 20"):
        gd.parse_pasted("12\n25", 20)


def test_conduct_fact_goes_to_the_simple_period_of_its_day():
    periods = [{"code": c, "sort_order": i, "starts_on": a, "ends_on": b} for i, (c, a, b) in enumerate([
        ("P1", date(2026, 9, 1), date(2026, 10, 15)), ("P2", date(2026, 10, 16), date(2026, 11, 30)),
        ("EX1", date(2026, 12, 1), date(2026, 12, 10)), ("P3", date(2026, 12, 11), date(2027, 1, 24))], start=1)]
    assert gd.conduct_period(periods, date(2026, 9, 20)) == "P1"
    assert gd.conduct_period(periods, date(2026, 12, 5)) == "P2"               # exam session → the period before
    assert gd.conduct_period(periods, date(2026, 8, 1)) is None


def test_routes_rights_and_safety():
    sql = (ROOT / "backend/migrations/0127_pedagogy_grades_conduct_facts.sql").read_text(encoding="utf-8")
    assert "grade_value_coherent" in sql and "UNIQUE (class_id, student_id, course_code, period_code)" in sql
    assert "GRANT SELECT, INSERT, UPDATE ON pedagogy_grades, pedagogy_conduct_facts" in sql            # no DELETE grant
    assert "DROP TABLE" not in sql.upper() and "ENABLE ROW LEVEL SECURITY" in sql
    for f in ("grades.py", "conduct_facts.py"):
        api = (ROOT / "backend/src/edusync/modules/pedagogy/api" / f).read_text(encoding="utf-8")
        routes = api.count("@router.")
        assert api.count("Depends(require_pedagogy)") == routes and api.count("Depends(require_school_actor)") == routes, f
        assert 'text(f"' not in api and "DELETE FROM" not in api.upper()
    grades = (ROOT / "backend/src/edusync/modules/pedagogy/api/grades.py").read_text(encoding="utf-8")
    assert "GRADE_CONFLICT" in grades and "never overwrite a mark already there" in grades
    rt = (ROOT / "backend/src/edusync/shared/infrastructure/realtime.py").read_text(encoding="utf-8")
    assert '("/api/v1/pedagogy", ("pedagogy",))' in rt                          # live for the directors


def test_pupils_who_left_are_kept_apart():
    """Owner 2026-11-22: « un élève qui a déjà abandonné, comment la liste le gère ? » — at the end, read-only, his marks
    kept, no more mark nor fact, not counted, not in the pasted order; a suspended pupil stays (flagged)."""
    grades = (ROOT / "backend/src/edusync/modules/pedagogy/api/grades.py").read_text(encoding="utf-8")
    assert "ORDER BY (st.status IN ('ABANDON','TRANSFERRED'))" in grades and "plus de cote à saisir pour cet élève" in grades
    assert 'pupils = [p for p in _pupils(conn, actor, ctx) if not p["departed"]]' in grades
    assert "st.status NOT IN ('ABANDON','TRANSFERRED')" in grades                      # directors' follow-up
    conduct = (ROOT / "backend/src/edusync/modules/pedagogy/api/conduct_facts.py").read_text(encoding="utf-8")
    assert "plus de fait à signaler" in conduct
