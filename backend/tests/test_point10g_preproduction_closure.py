from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def test_account_password_endpoint_invalidates_old_tokens():
    s=(ROOT/'backend/src/edusync/modules/iam/api/router.py').read_text()
    assert '@router.post("/password")' in s
    assert 'version=version+1' in s
    assert 'verify_password(body.current_password' in s
    assert 'hash_password(body.new_password)' in s

def test_frontend_has_no_raw_technical_error_rendering_contract():
    src=ROOT/'frontend/src'
    text='\n'.join(p.read_text() for p in src.glob('*.tsx'))
    assert 'setError(String(e))' not in text
    assert 'setError(e instanceof Error?e.message:String(e))' not in text
    assert 'window.alert(' not in text

def test_release_versions_are_normalized():
    assert '0.52.0-point17-environment-closure' in (ROOT/'frontend/package.json').read_text()
    assert 'version = "0.52.0"' in (ROOT/'backend/pyproject.toml').read_text()
    assert '0.52.0-point17-environment-closure' in (ROOT/'backend/src/edusync/bootstrap/app.py').read_text()
