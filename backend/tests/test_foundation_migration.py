from pathlib import Path

SQL = (Path(__file__).parents[1] / "migrations" / "0001_foundation.sql").read_text(encoding="utf-8")

def test_migration_contains_tenant_rls_and_append_only_audit():
    assert "ENABLE ROW LEVEL SECURITY" in SQL
    assert "current_setting('app.current_school_id'" in SQL
    assert "forbid_audit_mutation" in SQL
    assert "UNIQUE (school_id, idempotency_key)" in SQL
    assert "OR school_id IS NULL" not in SQL

def test_intendant_is_role_not_hardcoded_permission_if():
    assert "('INTENDANT','Intendant')" in SQL
    assert "stewardship.manage" in SQL
