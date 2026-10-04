from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def test_query_driven_index_migration_covers_hot_domains():
    sql=(ROOT/'backend/migrations/0028_scalability_query_indexes.sql').read_text(encoding='utf-8')
    for required in ('pg_trgm','btree_gin','students USING gin (school_id','staff_members USING gin (school_id',
                     'idx_enrollments_school_student_year_status','idx_audit_school_occurred',
                     'idx_inventory_asset_events_history','idx_schools_status_name'):
        assert required in sql

def test_performance_doctrine_requires_measurement_not_index_guessing():
    text=(ROOT/'performance/SCALABILITY_PERFORMANCE_DOCTRINE.md').read_text(encoding='utf-8')
    for required in ('EXPLAIN (ANALYZE, BUFFERS)','pg_stat_statements','p95','p99','school_id','k6'):
        assert required in text

def test_benchmark_targets_business_paths_not_only_health():
    sql=(ROOT/'performance/postgres-benchmark.sql').read_text(encoding='utf-8')
    for table in ('students','enrollments','finance_payments','outbox_events','audit_events','inventory_item_movements'):
        assert table in sql
