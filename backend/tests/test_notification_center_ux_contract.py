from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_school_user_can_mark_own_notifications_read_with_read_capability():
    single = (ROOT / "backend/src/edusync/modules/notifications/api/router.py").read_text()
    center = (ROOT / "backend/src/edusync/modules/notifications_center/api/router.py").read_text()
    assert "need(actor,'notifications.internal.read')" in single
    read_all = center[center.index('def school_inbox_read_all'):center.index('@router.get("/notifications/push/config")')]
    assert 'notifications.internal.read' in read_all
    assert 'notifications.internal.dismiss' in read_all  # backward-compatible capability; read is sufficient
    assert "user_id=:u AND school_id=:s" in read_all


def test_notification_center_escapes_header_stacking_context_and_closes_cleanly():
    ui = (ROOT / "frontend/src/platform/notification_center.tsx").read_text()
    css = (ROOT / "frontend/src/platform/notification_center.css").read_text()
    assert "createPortal" in ui and "document.body" in ui
    assert "onPointerDown" in ui and "e.currentTarget === e.target" in ui
    assert "if (e.key === 'Escape') onClose()" in ui
    assert "setOpen(false);setCenter(false)" in ui
    assert "Tout marquer comme lu" in ui and "Marquer comme lue" in ui
    assert "height:min(760px,calc(100dvh - 32px))" in css
    assert "height:100dvh" in css


def test_notification_open_closes_panel_marks_read_and_routes_to_business_screen():
    ui = (ROOT / "frontend/src/platform/notification_center.tsx").read_text()
    assert "if(!n.read_at)void read(n)" in ui
    assert "edusync:navigate" in ui
    assert "edusync:finance-target" in ui
    assert "items.slice(0,4)" in ui
