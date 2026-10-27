"""Historical debt is authorized by the charge enrollment's own section."""
from pathlib import Path


def test_historical_arrears_scopes_debt_enrollment_not_any_student_enrollment():
    source = (Path(__file__).resolve().parents[1] /
              "src/edusync/adapters/postgres_schooling_parity.py").read_text(encoding="utf-8")
    method = source.split("    def historical_arrears(", 1)[1].split("    def family_contact_diagnostics(", 1)[0]
    assert "JOIN school_classes sc ON sc.id=e.class_id" in method
    assert "JOIN school_sections ss ON ss.id=sc.section_id" in method
    assert "upper(ss.code) IN :scope_sections" in method
    assert "upper(sc.code) IN :scope_classes" in method
    assert "AND {scope_where} AND e.status='VALIDATED'" in method
    assert '_student_scope_where(scopes, alias="s")' not in method
