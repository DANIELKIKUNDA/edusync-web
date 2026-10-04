from pathlib import Path

import pytest

from edusync.bootstrap.settings import Settings
from edusync.shared.infrastructure.security import create_access_token, decode_access_token

ROOT = Path(__file__).parents[1]
SQL = (ROOT / "migrations" / "0003_g1_live_security.sql").read_text(encoding="utf-8")
PROVISION = (ROOT / "scripts" / "provision_database.py").read_text(encoding="utf-8")
FRONTEND_API = (ROOT.parent / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")


def test_rls_is_forced_and_platform_policy_is_role_bound():
    assert "FORCE ROW LEVEL SECURITY" in SQL
    assert "TO edusync_tenant" in SQL
    assert "TO edusync_platform" in SQL
    assert "current_user" not in SQL or "app.platform_mode" not in SQL
    assert "app.platform_mode" not in SQL
    assert "ALTER TABLE users ENABLE ROW LEVEL SECURITY" in SQL
    assert "membership_roles_tenant" in SQL


def test_application_roles_are_explicitly_non_privileged():
    assert "NOSUPERUSER" in PROVISION
    assert "NOBYPASSRLS" in PROVISION
    assert "NOCREATEROLE" in PROVISION
    assert "NOINHERIT" in PROVISION
    assert "REVOKE CREATE ON SCHEMA public FROM PUBLIC" in PROVISION


def test_owner_credentials_are_not_used_by_runtime_api_settings():
    s = Settings()
    assert "edusync_tenant" in s.tenant_database_url
    assert "edusync_platform" in s.platform_database_url
    assert "edusync_owner" in s.owner_database_url
    assert s.tenant_database_url != s.platform_database_url != s.owner_database_url


def test_production_rejects_default_secrets():
    s = Settings(env="production")
    with pytest.raises(RuntimeError):
        s.assert_production_safe()


def test_jwt_has_required_access_claims_and_scope_round_trip():
    secret = "x" * 40
    token = create_access_token(subject="00000000-0000-0000-0000-000000000001", secret=secret,
                                issuer="edusync-test", audience="web", minutes=5,
                                claims={"scope": "platform"})
    claims = decode_access_token(token, secret=secret, issuer="edusync-test", audience="web")
    assert claims["scope"] == "platform"
    assert claims["typ"] == "access"
    assert claims["jti"]


def test_frontend_no_longer_contains_web0a_dev_admin_bypass():
    assert "X-Platform-Admin" not in FRONTEND_API
    assert "Authorization" in FRONTEND_API
    assert "Idempotency-Key" in FRONTEND_API
    assert "crypto.randomUUID" in FRONTEND_API
