"""Pre-staging infrastructure contracts (STAGING_READINESS.md S1–S9). No business rule is tested here."""
import base64
from pathlib import Path

import pytest

from edusync.bootstrap.settings import Settings, is_protected_env

ROOT = Path(__file__).resolve().parents[2]
KEY = base64.b64encode(bytes(range(32))).decode()


def safe(env: str, **over):
    base = dict(_env_file=None, env=env, jwt_secret="p" * 48, cors_origins="https://staging.example.cd",
                trusted_hosts="staging.example.cd", mfa_encryption_key=KEY,
                tenant_database_url="postgresql+psycopg://edusync_tenant:Str0ng@db/edusync",
                platform_database_url="postgresql+psycopg://edusync_platform:Str0ng@db/edusync")
    return Settings(**{**base, **over})


# ---------------------------------------------------------------- S1: staging is a protected environment
def test_s1_staging_is_protected_like_production():
    assert is_protected_env("staging") and is_protected_env("Production") and is_protected_env("prod")
    assert not is_protected_env("dev") and not is_protected_env("") and not is_protected_env(None)
    safe("staging").assert_runtime_safe()
    for bad in (dict(jwt_secret="dev-only-change-me-dev-only-change-me"), dict(cors_origins="http://staging.example.cd"),
                dict(trusted_hosts="*"), dict(tenant_database_url="postgresql+psycopg://edusync_tenant:CHANGE_ME@db/edusync"),
                dict(mfa_platform_required=False), dict(push_provider="mock"), dict(mfa_encryption_key="")):
        with pytest.raises(RuntimeError):
            safe("staging", **bad).assert_runtime_safe()
    with pytest.raises(RuntimeError):
        safe("staging", platform_admin_password="CHANGE_ME_NOW_123!").assert_provisioning_safe()


def test_s1_simulated_sms_refused_and_secure_cookie_in_staging():
    from edusync.modules.communications.providers import provider_for
    assert provider_for(safe("staging"), "mock") is None and provider_for(safe("staging"), "sandbox") is None
    assert provider_for(Settings(_env_file=None), "mock") is not None
    iam = (ROOT / "backend/src/edusync/modules/iam/api/router.py").read_text(encoding="utf-8")
    assert "secure=is_protected_env(services.settings.env)" in iam


COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")


def block(name: str) -> str:
    return COMPOSE.split(f"\n  {name}:\n", 1)[1].split("\n\n", 1)[0]


# ---------------------------------------------------------------- S2: the API receives every runtime variable it needs
def test_s2_backend_receives_runtime_variables_without_owner_secrets():
    api = block("backend")
    for var in ("EDUSYNC_TRUSTED_HOSTS", "EDUSYNC_MFA_ENCRYPTION_KEY", "EDUSYNC_DOCUMENT_LINK_SECRET", "EDUSYNC_OBJECT_STORAGE_BACKEND", "EDUSYNC_PUSH_PROVIDER"):
        assert f"{var}:" in api, var
    assert "EDUSYNC_OWNER_DATABASE_URL" not in api and "POSTGRES_OWNER_PASSWORD" not in api and "PLATFORM_ADMIN_PASSWORD" not in api
    assert "env_file: ${EDUSYNC_ENV_FILE:-.env}" in block("migrator")


# ---------------------------------------------------------------- S3: private S3 storage is part of the stack
def test_s3_object_storage_service():
    s3 = block("object-storage")
    assert "image: chrislusf/seaweedfs:4.48" in s3 and "S3_SECRET_KEY:" in s3 and "ports:" not in s3   # never published
    entry = (ROOT / "deploy/seaweedfs/entrypoint.sh").read_text(encoding="utf-8")
    assert "umask 077" in entry and "-s3.config=/tmp/s3.json" in entry
