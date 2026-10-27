"""Personnel section scopes must never inherit school-wide assignments."""
from edusync.adapters.postgres_personnel import _scope_where


def test_section_scope_excludes_global_assignment():
    where, params = _scope_where((("SECTION", "primaire"),))
    assert "sa.scope_type='SCHOOL'" not in where
    assert "sa.scope_type='SECTION'" in where
    assert "sa.scope_type='CLASS'" in where
    assert params["scope_sections"] == ["PRIMAIRE"]


def test_class_scope_excludes_global_assignment():
    where, params = _scope_where((("CLASS", "7a"),))
    assert "sa.scope_type='SCHOOL'" not in where
    assert params["scope_classes"] == ["7A"]


def test_multiple_sections_are_unioned():
    where, params = _scope_where((("SECTION", "maternelle"), ("SECTION", "primaire")))
    assert " IN :scope_sections" in where
    assert params["scope_sections"] == ["MATERNELLE", "PRIMAIRE"]


def test_schoolwide_grant_is_explicit():
    assert _scope_where((("SCHOOL", None), ("SECTION", "PRIMAIRE"))) == ("TRUE", {})


def test_missing_scope_denied():
    assert _scope_where(()) == ("FALSE", {})
