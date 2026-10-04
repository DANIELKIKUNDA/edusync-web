from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(p): return (ROOT/p).read_text(encoding='utf-8')
def test_sync_frontend_consumes_keyset_and_outbox():
 a=read('frontend/src/api.ts'); u=read('frontend/src/sync_admin.tsx')
 assert 'syncPendingOutbox' in a and 'cursor_at' in a and 'cursor_id' in a
 assert 'Charger plus' in u and 'Outbox durable en attente' in u
 assert 'window.prompt' not in u and 'window.confirm' not in u and 'window.alert' not in u
def test_sync_conflict_resolution_is_permissioned_tenant_scoped_and_audited():
 s=read('backend/src/edusync/modules/sync/api/router.py')
 assert "need(actor,'sync.conflicts.resolve')" in s
 assert "school_id=:sid FOR UPDATE" in s
 assert "status!='OPEN'" in s
 assert "sync.conflict.resolved" in s
 assert 'PostgresAuditRepository(c).append' in s
def test_sync_review_uses_real_conflict_registry():
 s=read('backend/src/edusync/modules/sync/api/router.py')
 assert "@router.get('/review-conflicts')" in s
 assert "FROM sync_conflicts WHERE school_id=:sid AND status='OPEN'" in s
