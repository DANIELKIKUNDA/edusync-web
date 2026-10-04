from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
APP=(ROOT/'frontend/src/App.tsx').read_text(encoding='utf-8')
LOGIN=(ROOT/'frontend/src/login.tsx').read_text(encoding='utf-8')
PERSONNEL=(ROOT/'frontend/src/personnel.tsx').read_text(encoding='utf-8')
SCHOOLING=(ROOT/'frontend/src/schooling.tsx').read_text(encoding='utf-8')
DIALOGS=(ROOT/'frontend/src/platform/dialogs.ts').read_text(encoding='utf-8')
IAM=(ROOT/'backend/src/edusync/modules/iam/api/router.py').read_text(encoding='utf-8')

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
    assert "fetch('/api/v1/auth/refresh'" in APP
    assert "credentials:'include'" in APP

def test_refresh_restores_authoritative_school_context():
    assert "'user':dict(user_row)" in IAM
    assert "'school':dict(school_row)" in IAM
    assert "'permissions':sorted(permissions)" in IAM
    assert 'user_device_sessions' in IAM
