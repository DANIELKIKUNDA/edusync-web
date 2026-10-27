"""Student details must not reveal enrollment rows from other sections."""
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src/edusync/adapters/postgres_schooling.py"


def test_student_detail_filters_enrollment_history_independently():
    source = SOURCE.read_text(encoding="utf-8")
    method = source.split("    def get_student(", 1)[1].split("    def update_student(", 1)[0]
    assert "history_where" in method
    assert "upper(ss.code) IN :history_sections" in method
    assert "upper(sc.code) IN :history_classes" in method
    assert "AND {history_where}" in method
    assert "bindparam(\"history_sections\", expanding=True)" in method
    assert "schoolwide = any(t==\"SCHOOL\"" in method
