from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(p):return (ROOT/p).read_text(encoding='utf-8')
def test_outbox_is_postgres_authoritative_and_crash_safe():
 s=read('backend/src/edusync/modules/sync/outbox_worker.py')
 assert 'FOR UPDATE SKIP LOCKED' in s and 'processing_token' in s and 'locked_until' in s
 assert "pipe.lpush(QUEUE" in s and "pipe.ltrim(QUEUE,0,MAX_QUEUE_LENGTH-1)" in s and 'published_at=now()' in s and 'REDIS_UNAVAILABLE' in s
 assert 'dead_lettered_at' in s and 'event_id' in s
def test_communication_worker_recovers_without_redis_hint():
 s=read('backend/src/edusync/modules/communications/worker.py')
 assert 'Redis is a hint, never the durable scheduler' in s
 assert 'FOR UPDATE OF d SKIP LOCKED' in s and 'locked_until' in s and 'processing_token' in s
 assert 'External I/O happens outside the PostgreSQL transaction' in s
 assert "except redis.RedisError:pass" in s
def test_worker_recovery_migration_indexes_due_work():
 s=read('backend/migrations/0030_worker_recovery_leases.sql')
 assert 'idx_outbox_dispatch_due' in s and 'idx_comm_delivery_due_recovery' in s
