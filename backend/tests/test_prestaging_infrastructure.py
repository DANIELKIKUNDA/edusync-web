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
    for var in ("EDUSYNC_TRUSTED_HOSTS", "EDUSYNC_MFA_ENCRYPTION_KEY", "EDUSYNC_DOCUMENT_LINK_SECRET", "EDUSYNC_BACKUP_STATUS_FILE",
                "EDUSYNC_OBJECT_STORAGE_BACKEND", "EDUSYNC_PUSH_PROVIDER"):
        assert f"{var}:" in api, var
    assert "EDUSYNC_OWNER_DATABASE_URL" not in api and "POSTGRES_OWNER_PASSWORD" not in api and "PLATFORM_ADMIN_PASSWORD" not in api
    assert "backup_status:/backup-status:ro" in api
    assert "env_file: ${EDUSYNC_ENV_FILE:-.env}" in block("migrator")


# ---------------------------------------------------------------- S3: private S3 storage is part of the stack
def test_s3_object_storage_service():
    s3 = block("object-storage")
    assert "image: chrislusf/seaweedfs:4.48" in s3 and "S3_SECRET_KEY:" in s3 and "ports:" not in s3   # never published
    entry = (ROOT / "deploy/seaweedfs/entrypoint.sh").read_text(encoding="utf-8")
    assert "umask 077" in entry and "-s3.config=/tmp/s3.json" in entry


# ---------------------------------------------------------------- S4: nginx accepts the 10 MiB imports
def test_s4_nginx_import_size():
    nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    assert "client_max_body_size 11m;" in nginx
    from edusync.modules.migration_import.api.router import MAX_IMPORT_BYTES
    assert MAX_IMPORT_BYTES <= 11 * 1024 * 1024


# ---------------------------------------------------------------- S5: server-sent events unbuffered and kept open
def test_s5_nginx_streams():
    nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    sse = nginx.split("location ~ ^/api/v1/(notifications|platform/inbox)/stream$", 1)[1].split("}", 1)[0]
    assert "proxy_buffering off;" in sse and "proxy_read_timeout 1h;" in sse
    assert nginx.index("(notifications|platform/inbox)/stream") < nginx.index("location /api/ {")
    assert "proxy_set_header Host $host;" in nginx.split("location /health-api", 1)[1].split("}", 1)[0]


# ---------------------------------------------------------------- S6: reproducible frontend image
def test_s6_frontend_image_uses_lockfile():
    docker = (ROOT / "frontend/Dockerfile").read_text(encoding="utf-8")
    assert "COPY package.json package-lock.json" in docker and "RUN npm ci" in docker and "npm install" not in docker
    assert "node_modules" in (ROOT / "frontend/.dockerignore").read_text(encoding="utf-8")


# ---------------------------------------------------------------- S7: public TLS + HSTS
def test_s7_tls_terminator_with_hsts():
    tls = block("tls-proxy")
    assert 'profiles: ["tls"]' in tls and '"443:443"' in tls and "ipv4_address: 172.30.57.11" in tls
    caddy = (ROOT / "deploy/caddy/Caddyfile").read_text(encoding="utf-8")
    assert 'Strict-Transport-Security "max-age=31536000"' in caddy and "flush_interval -1" in caddy
    assert "includeSubDomains" not in caddy and "preload" not in caddy   # owner decision: no subdomains / preload yet
    assert '"127.0.0.1:8080:80"' in block("frontend")      # plain HTTP only on loopback


# ---------------------------------------------------------------- S8: forwarded headers trusted only from the proxies
def test_s8_forwarded_ips_restricted_to_proxies():
    assert "FORWARDED_ALLOW_IPS: ${EDUSYNC_FORWARDED_ALLOW_IPS:-172.30.57.10,172.30.57.11}" in block("backend")
    assert "ipv4_address: 172.30.57.10" in block("frontend") and "subnet: 172.30.57.0/24" in COMPOSE
    assert "EDUSYNC_FORWARDED_ALLOW_IPS=*" not in (ROOT / ".env.example").read_text(encoding="utf-8")


# ---------------------------------------------------------------- S9: scheduled backup with verified restore
def test_s9_backup_service_verifies_restore_and_reports_status():
    bk = block("backup")
    assert "build: ./deploy/backup" in bk and "backup_status:/backup-status" in bk and "BACKUP_OFFSITE:" in bk
    script = (ROOT / "deploy/backup/backup.sh").read_text(encoding="utf-8")
    for contract in ("pg_dump -Fc", "pg_restore --exit-on-error", "CHECK_DB=edusync_restore_check", "SHA256SUMS",
                     '"restore_verified"', '[ "$r" -lt "$b" ] || [ "$r" -gt "$a" ]', "-mtime \"+$KEEP_DAYS\""):
        assert contract in script, contract
    assert "FROM postgres:16-alpine" in (ROOT / "deploy/backup/Dockerfile").read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in (ROOT / ".gitattributes").read_text(encoding="utf-8")
