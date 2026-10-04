from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(p): return (ROOT/p).read_text(encoding='utf-8')
def test_platform_notification_contract_is_durable_audited_and_targeted():
 r=read('backend/src/edusync/modules/platform/api/router.py'); m=read('backend/migrations/0031_platform_system_notifications.sql')
 assert "platform.notifications.system.send" in r
 assert "PLATFORM_SYSTEM_NOTIFICATION_SENT" in r
 assert "school_memberships" in r and "s.status='ACTIVE'" in r and "u.active=true" in r
 assert 'platform_system_notifications' in m and 'recipient_count' in m
 assert "target_scope='SCHOOL'" in m and "target_scope='ALL_ACTIVE_SCHOOLS'" in m
def test_platform_notification_frontend_is_real_module():
 a=read('frontend/src/App.tsx'); api=read('frontend/src/api.ts')
 assert "Notifications système" in a and "PlatformNotificationDialog" in a
 assert 'sendPlatformSystemNotification' in a and 'platformSystemNotifications' in api
 assert "Aucun SMS ou WhatsApp" in a
def test_diagnostics_exposes_operational_signals():
 r=read('backend/src/edusync/modules/platform/api/router.py')
 for x in ('active_schools','active_device_sessions','dead_letter_deliveries','sync_conflicts','outbox_pending'): assert x in r
