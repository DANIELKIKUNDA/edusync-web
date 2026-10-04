from pathlib import Path
from edusync.bootstrap.settings import Settings

ROOT=Path(__file__).resolve().parents[1]

def text(p): return (ROOT/p).read_text(encoding='utf-8')

def test_api_guard_bounds_request_shape_and_disables_api_cache():
    s=text('src/edusync/shared/infrastructure/api_guard.py')
    assert 'status_code=413' in s and 'status_code=414' in s
    assert 'Cache-Control' in s and 'no-store' in s and 'Pragma' in s
    app=text('src/edusync/bootstrap/app.py')
    assert 'ApiGuardMiddleware' in app and 'api_max_body_bytes' in app and 'api_max_query_bytes' in app

def test_production_rejects_wildcard_or_insecure_cors_and_hosts():
    base=dict(env='prod', jwt_secret='x'*40,
              tenant_database_url='postgresql://u:strong@db/tenant',
              platform_database_url='postgresql://u:strong@db/platform',
              owner_database_url='postgresql://u:strong@db/owner',
              platform_admin_password='StrongBootstrapPassword!')
    for cors,hosts in [('*','api.example.com'),('http://example.com','api.example.com'),('https://example.com','*')]:
        cfg=Settings(**base,cors_origins=cors,trusted_hosts=hosts)
        try: cfg.assert_runtime_safe()
        except RuntimeError: pass
        else: raise AssertionError('configuration réseau permissive acceptée en production')

def test_school_actor_revalidates_tenant_membership_and_versions_server_side():
    s=text('src/edusync/bootstrap/dependencies.py')
    for contract in ['membership.user_id != user_id','membership.school_id != school_id','membership_version','user_version','tenant_transaction(school_id=school_id']:
        assert contract in s
    assert 'permissions = memberships.permissions(membership.id)' in s
    assert 'effective_capability_grants(user_id, school_id)' in s

def test_sql_hot_routes_are_tenant_parameterized_not_interpolated():
    # Static regression gate for the most security-sensitive school APIs.
    for rel in ['modules/personnel/api/router.py','modules/schooling/api/router.py','modules/stewardship/api/router.py','modules/finance_checkout/api/router.py']:
        s=text('src/edusync/'+rel)
        assert 'tenant_transaction(school_id=actor.school_id' in s
        assert 'f"SELECT' not in s and "f'SELECT" not in s
