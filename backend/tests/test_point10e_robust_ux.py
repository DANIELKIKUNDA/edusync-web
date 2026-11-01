from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def text(path): return (ROOT/path).read_text(encoding='utf-8')
def test_connectivity_is_not_binary_or_single_failure():
    s=text('frontend/src/platform/connectivity.ts')
    for state in ['DEGRADED','SUSPECTED_OFFLINE','OFFLINE','RECOVERING']: assert state in s
    # 2026-11-01: offline only after several failed probes over a grace period; recovery needs answers in a row.
    assert 'OFFLINE_GRACE_MS=10_000' in s and 'OFFLINE_AFTER_FAILURES=3' in s and 'RECOVER_SUCCESSES=2' in s

def test_retry_requires_safe_read_or_idempotency_key():
    s=text('frontend/src/platform/connectivity.ts')
    assert "method==='GET'||method==='HEAD'" in s and "Idempotency-Key" in s

def test_frontend_industrial_dependencies_declared():
    s=text('frontend/package.json')
    for dep in ['react-hook-form','zod','@hookform/resolvers','sonner']: assert dep in s

def test_security_and_observability_dependencies_declared():
    p=text('backend/pyproject.toml')
    for dep in ['PyJWT','argon2-cffi','redis','structlog']: assert dep in p

def test_user_error_boundary_and_no_native_alert():
    assert 'reportTechnical' in text('frontend/src/platform/ErrorBoundary.tsx')
    all_src='\n'.join(p.read_text(encoding='utf-8') for p in (ROOT/'frontend/src').rglob('*.tsx'))
    assert 'alert(' not in all_src
