from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(p):return (ROOT/p).read_text(encoding='utf-8')
def test_transversal_routers_are_mounted():
    s=read('backend/src/edusync/bootstrap/app.py')
    for p in ['/api/v1/audit','/api/v1/notifications','/api/v1/sync']:assert p in s
def test_audit_is_read_only_and_permission_gated():
    s=read('backend/src/edusync/modules/audit/api/router.py')
    assert 'audit.school.read' in s and 'audit.entity.history.read' in s
    assert '@router.post' not in s and '@router.delete' not in s and '@router.patch' not in s
def test_notifications_are_personal_by_default():
    s=read('backend/src/edusync/modules/notifications/api/router.py')
    assert 'user_id=:uid' in s and 'notifications.internal.read' in s and 'notifications.internal.dismiss' in s
def test_sync_status_does_not_weaken_finance_offline_doctrine():
    s=read('backend/src/edusync/modules/sync/api/router.py')+read('backend/src/edusync/modules/sync/domain/contracts.py')
    assert 'sync.status.read' in s and 'AUTHORIZED_PARTITIONED_CASH_V2' in s and 'NO_AUTOMATIC_FINANCIAL_MERGE' in s
def test_school_direction_finance_remains_explicit_permission_only():
    # 2026-10-23: widgets are declared server-side with their capabilities; the home only renders what is listed.
    s=read('backend/src/edusync/modules/access/application/projection.py')
    assert '"finance.recovery.monthly.read"' in s and '"finance.analysis.by_fee.read"' in s
    assert 'modelOf' not in read('frontend/src/home.tsx')
