from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def text(p):return (ROOT/p).read_text(encoding='utf-8')
def test_persistent_sessions_are_revocable_not_infinite_jwt():
 s=text('backend/src/edusync/shared/infrastructure/security.py');cfg=text('backend/src/edusync/bootstrap/settings.py');m=text('backend/migrations/0026_persistent_device_sessions.sql')
 assert '"exp"' in s and 'access_token_minutes: int = 15' in cfg
 assert 'user_device_sessions' in m and 'revoked_at' in m
def test_sync_admin_surface_exists():
 s=text('backend/src/edusync/modules/sync/api/router.py')
 for x in ["'/devices'","'/conflicts'","sync.device.revoke"]:assert x in s
def test_intendance_full_core_and_signed_adjustment():
 s=text('backend/src/edusync/modules/stewardship/api/router.py')
 for x in ["'/assets'","/history'","'/counts'","/validate'","adjustment_direction"]:assert x in s
def test_communications_has_real_adapter_contract_and_retries():
 # External messaging (2026-10): the documented Orange adapter lives behind SmsProviderPort; bounded retries with jitter.
 p=text('backend/src/edusync/shared/messaging/sms_orange.py');w=text('backend/src/edusync/modules/communications/worker.py')
 assert 'class OrangeSmsProvider' in p and 'httpx.AsyncClient' in p and '/oauth/v3/token' in p
 assert 'MAX_ATTEMPTS = 6' in w and 'attempts < MAX_ATTEMPTS' in w and '2 ** max(0, attempt - 1)' in w and 'random.uniform(0.8, 1.2)' in w
def test_no_direct_login_exception_leak():
 s=text('frontend/src/login.tsx');assert "e instanceof Error?e.message" not in s
def test_performance_and_security_gates_exist():
 assert (ROOT/'performance/api-k6.js').exists() and (ROOT/'performance/postgres-benchmark.sql').exists() and (ROOT/'security/SECURITY_TEST_PLAN.md').exists()
