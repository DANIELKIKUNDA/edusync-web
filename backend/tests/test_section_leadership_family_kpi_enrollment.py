"""KPI queries must filter the enrollment being reported, not another school year."""
from pathlib import Path


def test_family_overview_joins_section_of_counted_enrollment():
    source = (Path(__file__).resolve().parents[1] /
              "src/edusync/adapters/postgres_schooling_parity.py").read_text(encoding="utf-8")
    method = source.split("    def family_overview_scoped(", 1)[1].split("    def family_kpi_details(", 1)[0]
    assert "JOIN school_classes sc ON sc.id=e.class_id" in method
    assert "JOIN school_sections ss ON ss.id=sc.section_id" in method
    assert "_section_class_where(sections, classes, schoolwide=schoolwide)" in method
    assert "_student_scope_where(scopes" not in method
    helper = source.split("def _section_class_where(", 1)[1].split("CENT = ", 1)[0]
    # only non-empty lists are bound (empty expanding list -> « text = integer », HTTP 500 for a section-only Préfet)
    assert "upper(ss.code) IN :scope_sections" in helper and "upper(sc.code) IN :scope_classes" in helper
    assert "if sections:" in helper and "if classes:" in helper


def test_all_family_kpi_metrics_scope_reported_enrollment():
    source = (Path(__file__).resolve().parents[1] /
              "src/edusync/adapters/postgres_schooling_parity.py").read_text(encoding="utf-8")
    method = source.split("    def family_kpi_details_scoped(", 1)[1].split("    def product_sales_report(", 1)[0]
    assert method.count("JOIN school_sections ss ON ss.id=sc.section_id") == 3
    assert "_section_class_where(sections, classes, schoolwide=schoolwide)" in method
