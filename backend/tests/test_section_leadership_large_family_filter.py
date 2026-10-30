"""The large-family filter cannot count children from another section."""
from pathlib import Path


def test_large_family_filter_uses_scoped_students():
    source = (Path(__file__).resolve().parents[1] /
              "src/edusync/adapters/postgres_schooling.py").read_text(encoding="utf-8")
    method = source.split("    def list_families(", 1)[1].split("    def get_family(", 1)[0]
    assert 'if large_family_only:conditions.append(f"' in method
    assert 'AND {child_scope})>=5' in method
    assert 'FROM students sx WHERE sx.family_id=f.id' not in method
