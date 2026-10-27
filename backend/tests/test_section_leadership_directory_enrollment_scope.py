"""Regression checks for section-safe directory and export enrollment selection."""
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] /
          "src/edusync/adapters/postgres_schooling.py").read_text(encoding="utf-8")


def test_student_directory_lateral_enrollment_is_section_scoped():
    method = SOURCE.split("    def list_students(", 1)[1].split("    def get_student(", 1)[0]
    assert 'JOIN school_classes sc1 ON sc1.id=e1.class_id' in method
    assert 'JOIN school_sections ss1 ON ss1.id=sc1.section_id' in method
    assert method.count("AND {lateral_scope}") == 3
    assert 'lateral_sections' in method and 'lateral_classes' in method
    assert 'bindparam("lateral_sections",expanding=True)' in method


def test_enrolled_family_filter_uses_visible_children():
    method = SOURCE.split("    def list_families(", 1)[1].split("    def get_family(", 1)[0]
    assert "child_scope.replace('s.', 'se.')" in method
    assert "AND {child_scope.replace('s.', 'se.')}" in method
