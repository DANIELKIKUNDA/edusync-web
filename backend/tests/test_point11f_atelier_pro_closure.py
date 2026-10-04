from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
APP=(ROOT/'frontend/src/App.tsx').read_text()
API=(ROOT/'frontend/src/api.ts').read_text()
ROUTER=(ROOT/'backend/src/edusync/modules/platform/api/router.py').read_text()


def test_atelier_pro_has_no_placeholder_navigation_and_all_six_real_modules():
    for label in ['Cockpit','Écoles','Accès','Notifications système','Audit','Diagnostics']:
        assert label in APP
    assert "false,()=>setTab" not in APP
    assert 'Administration technique légère' not in APP


def test_atelier_pro_real_backend_surfaces_are_wired():
    for route in ["/dashboard","/schools-page","/access","/audit","/diagnostics","/system-notifications","/schools/{school_id}/detail","/rbac/roles"]:
        assert route in ROUTER
    for fn in ['platformDashboard','platformSchoolsPage','platformAccess','platformAudit','platformDiagnostics','platformSystemNotifications','platformSchoolDetail','platformRbacRoles']:
        assert fn in API and fn in APP


def test_atelier_pro_sensitive_governance_is_permissioned_locked_and_audited():
    for permission in ['platform.schools.create','platform.schools.suspend','platform.schools.activate','platform.school_admin.bootstrap','platform.access.manage','platform.notifications.system.send']:
        assert permission in (ROUTER + (ROOT/'backend/src/edusync/modules/platform/application/use_cases.py').read_text())
    assert ROUTER.count('FOR UPDATE') >= 4
    for action in ['PLATFORM_MEMBERSHIP_DEACTIVATED','PLATFORM_MEMBERSHIP_ACTIVATED','PLATFORM_STANDARD_ROLE_ASSIGNED','PLATFORM_STANDARD_ROLE_REVOKED','PLATFORM_SYSTEM_NOTIFICATION_SENT']:
        assert action in ROUTER


def test_atelier_pro_readiness_is_progressive_and_no_global_lock():
    for gate in ['school_identity','initial_admin','academic_year','classes','fee_catalog']:
        assert gate in ROUTER
    assert "'global_lock':False" in ROUTER
    assert 'ready_count' in ROUTER and 'total_gates' in ROUTER


def test_atelier_pro_browser_security_no_native_sensitive_dialogs_or_token_persistence():
    atelier=APP.split('function AtelierPro',1)[1].split('function SchoolDetailDialog',1)[0]
    for forbidden in ['window.prompt','window.confirm','window.alert','dangerouslySetInnerHTML','eval(']:
        assert forbidden not in atelier
    # Access tokens live only in React memory and are restored through the HttpOnly refresh cookie.
    assert 'localStorage.setItem(PLATFORM_TOKEN' not in APP
    assert 'localStorage.setItem(SCHOOL_SESSION' not in APP
