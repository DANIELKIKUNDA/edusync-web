"""Scope isolation for periodic finance reports."""
from datetime import date
from uuid import uuid4

from edusync.adapters.postgres_periodic_reports import PostgresPeriodicReportsRepository


def test_section_union_and_class_grant():
    clause, params = PostgresPeriodicReportsRepository._scope_clause(
        (("SECTION", "PRIMAIRE"), ("SECTION", "MATERNELLE"), ("CLASS", "P1A")))
    assert " OR " in clause
    assert params["scope_sections"] == ["MATERNELLE", "PRIMAIRE"]
    assert params["scope_classes"] == ["P1A"]
    stmt = PostgresPeriodicReportsRepository._scoped_sql(
        "SELECT 1 WHERE " + clause, params)
    assert "scope_sections" in stmt._bindparams
    assert stmt._bindparams["scope_sections"].expanding
    assert stmt._bindparams["scope_classes"].expanding


def test_no_grant_fails_closed():
    assert PostgresPeriodicReportsRepository._scope_clause(()) == ("FALSE", {})
    assert PostgresPeriodicReportsRepository._scope_clause(
        (("SECTION", None),)) == ("FALSE", {})


def test_schoolwide_grant_does_not_require_arrays():
    assert PostgresPeriodicReportsRepository._scope_clause(
        (("SCHOOL", None),)) == ("TRUE", {})


def test_section_only_and_class_only_do_not_bind_empty_arrays():
    for grant, expected in (
        (("SECTION", "SECONDAIRE"), "scope_sections"),
        (("CLASS", "CI-P1"), "scope_classes"),
    ):
        clause, params = PostgresPeriodicReportsRepository._scope_clause((grant,))
        assert list(params) == [expected]
        stmt = PostgresPeriodicReportsRepository._scoped_sql(
            "SELECT 1 WHERE " + clause, params)
        assert set(stmt._bindparams) == {expected}


def test_periodic_routes_forward_exact_capability_scopes():
    from pathlib import Path
    router = (Path(__file__).resolve().parents[1] /
              "src/edusync/modules/finance_reports/api/router.py").read_text()
    preview = router.split("def periodic(", 1)[1].split("class PeriodicPdfBody", 1)[0]
    excel = router.split("def periodic_xlsx(", 1)[1].split("@router.get('/generated')", 1)[0]
    assert "scopes=actor.scopes_for('finance.reports.periodic.generate')" in preview
    assert "scopes=actor.scopes_for('finance.reports.periodic.export')" in excel
    assert "_need_periodic_scope(actor, 'finance.reports.periodic.export')" in excel
