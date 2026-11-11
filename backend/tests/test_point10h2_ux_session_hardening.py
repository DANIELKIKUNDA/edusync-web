from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
APP=(ROOT/'frontend/src/App.tsx').read_text(encoding='utf-8')
LOGIN=(ROOT/'frontend/src/login.tsx').read_text(encoding='utf-8')
PERSONNEL=(ROOT/'frontend/src/personnel.tsx').read_text(encoding='utf-8')
SCHOOLING=(ROOT/'frontend/src/schooling.tsx').read_text(encoding='utf-8')
DIALOGS=(ROOT/'frontend/src/platform/dialogs.ts').read_text(encoding='utf-8')
IAM=(ROOT/'backend/src/edusync/modules/iam/api/router.py').read_text(encoding='utf-8')
CONNECTIVITY=(ROOT/'frontend/src/platform/connectivity.ts').read_text(encoding='utf-8')

def test_no_native_prompt_confirm_alert_remains_in_business_ui():
    text='\n'.join([APP,LOGIN,PERSONNEL,SCHOOLING])
    assert 'window.prompt' not in text
    assert 'window.confirm' not in text
    assert 'window.alert' not in text
    assert 'promptText' in PERSONNEL and 'promptText' in SCHOOLING
    assert "role','dialog'" in DIALOGS and "aria-modal','true'" in DIALOGS

def test_access_jwt_is_not_persisted_in_browser_storage():
    text=APP+'\n'+LOGIN
    assert "localStorage.setItem('edusync.platform.token'" not in text
    assert "localStorage.setItem('edusync.school.session'" not in text
    assert "refreshAccessSession(ctl.signal)" in APP
    assert "credentials:'include'" in CONNECTIVITY

def test_refresh_restores_authoritative_school_context():
    assert "'user':dict(user_row)" in IAM
    assert "'school':dict(school_row)" in IAM
    assert "'permissions':sorted(permissions)" in IAM
    assert 'user_device_sessions' in IAM

def test_chrome_wake_refresh_is_serialised_and_retried_without_revocation():
    assert "navigator.locks" in CONNECTIVITY
    assert "edusync-session-refresh" in CONNECTIVITY
    assert "X-EduSync-Session" in CONNECTIVITY and "STALE_REFRESH" in CONNECTIVITY
    assert "visibilitychange" in CONNECTIVITY and "void renewAccess()" in CONNECTIVITY
    assert "no\n    # longer emitted" in IAM
