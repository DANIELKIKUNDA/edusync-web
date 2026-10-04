from pathlib import Path

SQL = (Path(__file__).parents[1] / "migrations" / "0002_idempotency_concurrency.sql").read_text(encoding="utf-8")


def test_idempotency_registry_has_database_uniqueness():
    assert "idempotency_registry" in SQL
    assert "UNIQUE (scope_key, idempotency_key)" in SQL
    assert "request_hash" in SQL
    assert "PROCESSING" in SQL and "SUCCEEDED" in SQL


def test_optimistic_versions_and_conflicts_present():
    assert "ADD COLUMN IF NOT EXISTS version bigint" in SQL
    assert "sync_conflicts" in SQL
    assert "expected_version" in SQL and "actual_version" in SQL


def test_new_tenant_tables_have_rls():
    assert "ALTER TABLE idempotency_registry ENABLE ROW LEVEL SECURITY" in SQL
    assert "ALTER TABLE sync_conflicts ENABLE ROW LEVEL SECURITY" in SQL
    assert "current_setting('app.current_school_id'" in SQL


def test_outbox_and_sync_deduplication_are_enforced():
    assert "deduplication_key" in SQL
    assert "uq_outbox_scope_dedup" in SQL
    assert "uq_sync_inbox_school_operation" in SQL
