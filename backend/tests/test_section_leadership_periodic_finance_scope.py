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


def test_frontend_hides_official_pdf_for_section_only_grants():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    ui = (root / "frontend/src/reports_ui.tsx").read_text()
    api = (root / "backend/src/edusync/modules/finance_reports/api/router.py").read_text()
    assert "official_pdf_available" in api
    assert "generated_history_available" in api
    assert "officialAllowed && can('finance.reports.periodic.generate')" in ui
    assert "historyAllowed && can('finance.reports.history.read')" in ui


def test_all_three_analytics_have_sql_scope_and_route_forwarding():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    adapter = (root / "src/edusync/adapters/postgres_periodic_reports.py").read_text()
    router = (root / "src/edusync/modules/finance_reports/api/router.py").read_text()
    cases = (
        ("analysis_by_fee_type", "finance.analysis.by_fee.read"),
        ("analysis_by_cashier", "finance.analysis.by_cashier.read"),
        ("analysis_advance_funds", "finance.analysis.advance.read"),
    )
    for method, capability in cases:
        body = adapter.split("def " + method + "(", 1)[1].split("\n    def ", 1)[0]
        assert "scope_where, scope_params = self._scope_clause(scopes)" in body
        assert "JOIN school_sections ss_scope" in body
        assert "AND {scope_where}" in body
        assert method + "(actor.school_id, year_id, scopes=actor.scopes_for('" + capability + "'))" in router


def test_student_account_uses_enrollment_scope_for_read_and_pdf():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    adapter = (root / "src/edusync/adapters/postgres_periodic_reports.py").read_text()
    router = (root / "src/edusync/modules/finance_reports/api/router.py").read_text()
    body = adapter.split("def student_account(", 1)[1]
    assert "AND {scope_where} ORDER BY" in body
    assert "JOIN school_sections ss_scope" in body
    assert "scope_params" in body
    assert "student_account(actor.school_id, student_id, scopes=actor.scopes_for('students.account.read'))" in router
    assert "student_account(actor.school_id, student_id, scopes=actor.scopes_for('students.account.export'))" in router


def test_official_periodic_pdf_denies_section_only_before_report_replay():
    from pathlib import Path
    router = (Path(__file__).resolve().parents[1] /
              "src/edusync/modules/finance_reports/api/router.py").read_text()
    body = router.split("def periodic_pdf(", 1)[1].split("@router.get('/periodic.xlsx')", 1)[0]
    assert "t == 'SCHOOL'" in body
    assert body.index("Rapport officiel réservé au périmètre école") < body.index("prior = c.execute")


def test_product_sales_filter_and_history_fail_closed():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    adapter = (root / "src/edusync/adapters/postgres_schooling_parity.py").read_text()
    router = (root / "src/edusync/modules/finance_reports/api/router.py").read_text()
    sales = adapter.split("def product_sales_report(", 1)[1].split("def contribution_register(", 1)[0]
    assert "upper(ss_scope.code) IN :scope_sections" in sales
    assert "upper(sc_scope.code) IN :scope_classes" in sales
    assert "AND {scope_where}" in sales
    assert "scopes=actor.scopes_for('finance.products.sales_report.read')" in router
    history = router.split("def generated_reports(", 1)[1].split("@router.get('/analysis/fees')", 1)[0]
    assert "Historique des rapports sans provenance de section vérifiable" in history
    assert history.index("t == 'SCHOOL'") < history.index("tenant_transaction")


class _EmptyMappings:
    def mappings(self):
        return self

    def all(self):
        return []


class _RecordingConnection:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((statement, params))
        return _EmptyMappings()


def test_real_sql_statement_uses_expanding_section_parameters():
    """Exercise query construction, not only static source-code assertions."""
    conn = _RecordingConnection()
    repo = PostgresPeriodicReportsRepository(conn)
    repo._allocations(uuid4(), start_date=None, end_date=date(2026, 10, 27),
                      year_id=None, scopes=(("SECTION", "PRIMAIRE"), ("SECTION", "MATERNELLE")))
    stmt, params = conn.calls[0]
    assert "AND (upper(ss_scope.code) IN" in str(stmt)
    assert params["scope_sections"] == ["MATERNELLE", "PRIMAIRE"]
    assert stmt._bindparams["scope_sections"].expanding
    assert "scope_classes" not in params


def test_real_sales_query_class_only_excludes_unassigned_sales():
    conn = _RecordingConnection()
    repo = PostgresPeriodicReportsRepository(conn)
    assert repo._sales(uuid4(), start_date=date(2026, 10, 1),
                       end_date=date(2026, 10, 27), year_id=None,
                       scopes=(("CLASS", "P1A"),)) == []
    stmt, params = conn.calls[0]
    assert "upper(sc_scope.code) IN" in str(stmt)
    assert params["scope_classes"] == ["P1A"]
    assert stmt._bindparams["scope_classes"].expanding
    assert "scope_sections" not in params


def test_no_grant_uses_false_sql_predicate():
    conn = _RecordingConnection()
    repo = PostgresPeriodicReportsRepository(conn)
    repo._allocations(uuid4(), start_date=None, end_date=date(2026, 10, 27),
                      year_id=None, scopes=())
    stmt, params = conn.calls[0]
    assert "AND FALSE" in str(stmt)
    assert "scope_sections" not in params
    assert "scope_classes" not in params


def test_template_preview_applies_cashier_and_section_filters():
    from pathlib import Path
    router = (Path(__file__).resolve().parents[1] /
              "src/edusync/modules/finance_reports/api/router.py").read_text()
    preview = router.split("def preview(", 1)[1].split("# ---------------------------------------------------------------- N3-G", 1)[0]
    assert "_need_periodic_scope(actor, 'finance.reports.periodic.generate')" in preview
    assert "_scope_clause(scopes)" in preview
    assert "JOIN school_sections ss_scope" in preview
    assert 'scope_where+where+" GROUP BY' in preview
    assert "p.update(scope_params)" in preview


def test_scoped_student_account_missing_enrollment_is_not_disclosed():
    """A student outside the grant must not expose even account metadata."""
    from unittest.mock import Mock
    from sqlalchemy.sql.elements import TextClause
    conn = Mock()
    conn.execute.return_value.mappings.return_value.first.return_value = None
    repo = PostgresPeriodicReportsRepository(conn)
    import pytest
    with pytest.raises(LookupError, match="Élève introuvable"):
        repo.student_account(uuid4(), uuid4(), scopes=(("SECTION", "PRIMAIRE"),))
    stmt, params = conn.execute.call_args.args
    assert isinstance(stmt, TextClause)
    assert stmt._bindparams["scope_sections"].expanding
    assert params["scope_sections"] == ["PRIMAIRE"]
    assert "AND (upper(ss_scope.code) IN :scope_sections)" in str(stmt)


def test_analytics_scope_queries_are_executable_and_bound():
    from unittest.mock import Mock
    from sqlalchemy.sql.elements import TextClause
    for method in ("analysis_by_fee_type", "analysis_by_cashier", "analysis_advance_funds"):
        conn = Mock()
        conn.execute.return_value.mappings.return_value.all.return_value = []
        repo = PostgresPeriodicReportsRepository(conn)
        repo._year = lambda school_id, year_id: uuid4()
        assert getattr(repo, method)(uuid4(), scopes=(("SECTION", "MATERNELLE"), ("CLASS", "M1A"))) == []
        stmt, params = conn.execute.call_args.args
        assert isinstance(stmt, TextClause)
        assert "AND (upper(ss_scope.code) IN :scope_sections OR upper(sc_scope.code) IN :scope_classes)" in str(stmt)
        assert stmt._bindparams["scope_sections"].expanding
        assert stmt._bindparams["scope_classes"].expanding
        assert params["scope_sections"] == ["MATERNELLE"]
        assert params["scope_classes"] == ["M1A"]


def test_schoolwide_finance_joins_remain_optional_but_section_grants_fail_closed():
    """Unassigned section rows remain visible schoolwide, never to section users."""
    from pathlib import Path
    adapter = (Path(__file__).resolve().parents[1] /
               "src/edusync/adapters/postgres_periodic_reports.py").read_text()
    for method in ("_allocations", "_sales", "analysis_by_fee_type",
                   "analysis_by_cashier", "analysis_advance_funds"):
        body = adapter.split("def " + method + "(", 1)[1].split("\n    def ", 1)[0]
        assert "LEFT JOIN school_sections ss_scope ON ss_scope.id=sc_scope.section_id" in body
        assert "AND {scope_where}" in body
    assert PostgresPeriodicReportsRepository._scope_clause(()) == ("FALSE", {})
    assert PostgresPeriodicReportsRepository._scope_clause((("SCHOOL", None),)) == ("TRUE", {})
