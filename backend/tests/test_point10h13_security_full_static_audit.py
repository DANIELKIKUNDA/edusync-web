from pathlib import Path
import ast, re

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'/'edusync'
# setup_status/create_first_manager: first-run setup, public by design but locked (see test_local_closure_20261006).
# open_signed_document: authenticated by a short-lived HMAC link, re-checks membership and tenant ownership.
# logout_all: authenticated by the device-session cookie like logout (CSRF origin check, audited).
# mfa_verify/mfa_enroll_start/mfa_enroll_confirm (option B, 2026-10-13): second step of a platform sign-in, authenticated
# by the single-use step token issued after the password (hashed server-side, 5 min, attempt-limited, CSRF origin check).
PUBLIC_AUTH={'login','refresh_session','logout','logout_all','setup_status','create_first_manager','open_signed_document',
             'mfa_verify','mfa_enroll_start','mfa_enroll_confirm'}
HTTP={'get','post','put','patch','delete'}

def _routes(path:Path):
    source=path.read_text(encoding='utf-8'); tree=ast.parse(source)
    for node in tree.body:
        if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)): continue
        dec=[d for d in node.decorator_list if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.func.attr in HTTP]
        if dec: yield node, ast.get_source_segment(source,node) or ''

def test_every_non_public_api_route_has_server_side_actor_dependency():
    missing=[]
    for path in sorted((SRC/'modules').glob('*/api/router.py')):
        for node,text in _routes(path):
            if node.name in PUBLIC_AUTH: continue
            if 'require_school_actor' not in text and 'require_platform_actor' not in text:
                missing.append(f'{path.relative_to(ROOT)}:{node.lineno}:{node.name}')
    assert not missing, 'Routes sans contexte serveur: '+', '.join(missing)

def test_platform_mutations_are_permission_checked_in_application_layer():
    s=(SRC/'modules/platform/application/use_cases.py').read_text(encoding='utf-8')
    for cap in ('platform.schools.create','platform.schools.suspend','platform.schools.activate','platform.school_admin.bootstrap'):
        assert f'actor.require("{cap}")' in s

def test_all_router_sql_avoids_interpolated_select_update_delete_insert():
    bad=[]
    pattern=re.compile(r'''f[\"\']\s*(?:SELECT|UPDATE|DELETE|INSERT)''',re.I)
    for path in sorted((SRC/'modules').glob('*/api/router.py')):
        s=path.read_text(encoding='utf-8')
        if pattern.search(s): bad.append(str(path.relative_to(ROOT)))
    assert not bad, 'SQL interpolé dans routes: '+', '.join(bad)

def test_frontend_has_no_known_raw_html_or_dynamic_code_sinks_and_no_token_storage():
    bad=[]
    patterns=('dangerouslySetInnerHTML','document.write(','eval(','new Function(')
    for path in sorted((ROOT.parent/'frontend/src').rglob('*')):
        if path.suffix not in {'.ts','.tsx','.js','.jsx'}: continue
        s=path.read_text(encoding='utf-8')
        if any(p in s for p in patterns): bad.append(str(path.relative_to(ROOT.parent)))
        if re.search(r'(localStorage|sessionStorage)\.(?:setItem|getItem)\([^\n]*(?:access[_-]?token|session[_-]?token)',s,re.I):
            bad.append(str(path.relative_to(ROOT.parent))+':token-storage')
    assert not bad, 'Sink frontend sensible: '+', '.join(bad)

def test_access_jwt_is_algorithm_pinned_and_claims_required():
    s=(SRC/'shared/infrastructure/security.py').read_text(encoding='utf-8')
    assert 'algorithms=["HS256"]' in s
    for claim in ('sub','iss','aud','iat','nbf','exp','jti','typ'):
        assert f'"{claim}"' in s
    assert 'payload.get("typ") != "access"' in s

def test_persistent_cookie_is_httponly_lax_and_secure_in_production():
    s=(SRC/'modules/iam/api/router.py').read_text(encoding='utf-8')
    assert 'httponly=True' in s and 'samesite="lax"' in s
    assert 'secure=services.settings.env.lower() in {"prod","production"}' in s

def test_school_context_reloads_permissions_and_checks_membership_identity():
    s=(SRC/'bootstrap/dependencies.py').read_text(encoding='utf-8')
    for contract in ('membership.user_id != user_id','membership.school_id != school_id','memberships.permissions(membership.id)','effective_capability_grants(user_id, school_id)'):
        assert contract in s
