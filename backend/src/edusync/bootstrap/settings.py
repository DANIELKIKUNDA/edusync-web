from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EDUSYNC_", env_file=".env", extra="ignore")

    env: str = "dev"
    tenant_database_url: str = "postgresql+psycopg://edusync_tenant:tenant-change-me@localhost:5432/edusync"
    platform_database_url: str = "postgresql+psycopg://edusync_platform:platform-change-me@localhost:5432/edusync"
    owner_database_url: str = "postgresql+psycopg://edusync_owner:owner-change-me@localhost:5432/edusync"
    # Background workers (outbox, SMS). Never the owner/migrator credentials.
    worker_database_url: str = ""
    # JSON report written by the backup job ({"finished_at", "ok", "restore_verified"}); empty = not configured.
    backup_status_file: str = ""
    # Push notifications: "disabled" (default) or "mock" (local certification). Real providers: BLOCKED_EXTERNAL.
    push_provider: str = "disabled"
    # Multiplies every sensitive-operation rate limit (1 in production; raised only for local certification runs).
    rate_limit_multiplier: float = 1.0
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "dev-only-change-me-dev-only-change-me"
    jwt_issuer: str = "edusync"
    jwt_audience: str = "edusync-web"
    access_token_minutes: int = 15
    persistent_session_cookie: str = "edusync_session"
    # Persistent device session (owner decision 2026-10-07): no periodic re-authentication.
    # 0 = disabled (default). Rotation at every renewal + reuse detection + per-device revocation stay on.
    session_absolute_days: int = 0
    session_idle_days: int = 0
    session_rotation_grace_seconds: int = 60
    # Browsers cap cookie lifetimes (about 400 days); the cookie is re-issued at every renewal.
    session_cookie_max_age_days: int = 400

    offline_finance_enabled: bool = False
    offline_finance_certified: bool = False

    platform_admin_email: str = "admin@example.com"
    platform_admin_password: str = "CHANGE_ME_NOW_123!"
    platform_admin_name: str = "Administrateur Atelier Pro"

    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    trusted_hosts: str = "localhost,127.0.0.1,testserver"
    login_max_attempts: int = 7
    login_window_seconds: int = 900
    login_lock_seconds: int = 900
    api_max_body_bytes: int = 2_097_152
    api_max_query_bytes: int = 8_192
    sms_provider: str = "disabled"
    orange_sms_endpoint: str = ""
    orange_sms_bearer_token: str = ""

    # Object storage (S3-compatible). Empty endpoint + backend "auto" = documents storage disabled (503, clear message).
    object_storage_backend: str = "auto"  # auto | s3 | local
    object_storage_endpoint: str = ""
    object_storage_access_key: str = ""
    object_storage_secret_key: str = ""
    object_storage_bucket: str = "edusync-documents"
    object_storage_region: str = "us-east-1"
    object_storage_path_style: bool = True
    object_storage_local_root: str = ".local/object-storage"
    # Secret for short-lived download links issued by the API. Defaults to a key derived from the JWT secret.
    document_link_secret: str = ""
    document_link_seconds: int = 300

    # First Manager Système from the login page. Allowed only while no platform manager exists, and only
    # from loopback in dev; staging/production additionally require this one-time setup token.
    setup_token: str = ""

    # Second factor (MFA_PROPOSAL.md, option B, owner decision 2026-10-13): mandatory TOTP to open the platform console.
    # The key (32 bytes, base64) encrypts TOTP secrets at rest; it must differ from the JWT secret. School accounts are
    # not concerned. Disabling the policy is refused outside development (assert_runtime_safe).
    mfa_platform_required: bool = True
    mfa_encryption_key: str = ""
    mfa_challenge_seconds: int = 300
    mfa_max_attempts: int = 5
    mfa_lock_seconds: int = 900
    # Step-up (owner decision 2026-10-13): sensitive platform actions need a code confirmed within this delay.
    mfa_stepup_seconds: int = 300

    @field_validator("jwt_secret")
    @classmethod
    def _secret_strength(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("EDUSYNC_JWT_SECRET doit contenir au moins 32 caractères")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [x.strip() for x in self.trusted_hosts.split(",") if x.strip()]

    @staticmethod
    def _url_has_placeholder(url: str) -> bool:
        low = url.lower()
        return any(marker in low for marker in ("change_me", "change-", "change_", "change%", "password@"))

    def assert_runtime_safe(self) -> None:
        if self.env.lower() not in {"prod", "production"}:
            return
        if self.jwt_secret == "dev-only-change-me-dev-only-change-me":
            raise RuntimeError("Secret JWT de développement interdit en production")
        for url in (self.tenant_database_url, self.platform_database_url):
            if self._url_has_placeholder(url):
                raise RuntimeError("Mots de passe PostgreSQL applicatifs de démonstration interdits en production")
        if self.offline_finance_enabled and not self.offline_finance_certified:
            raise RuntimeError("Finance offline activée sans certification G2")
        origins = self.cors_origin_list
        if not origins or any(origin == "*" or not origin.startswith("https://") for origin in origins):
            raise RuntimeError("CORS production doit contenir uniquement des origines HTTPS explicites")
        hosts = self.trusted_host_list
        if not hosts or "*" in hosts:
            raise RuntimeError("TrustedHost production doit contenir des hôtes explicites")
        if self.api_max_body_bytes <= 0 or self.api_max_body_bytes > 10 * 1024 * 1024:
            raise RuntimeError("Limite de corps API production invalide")
        if self.api_max_query_bytes <= 0 or self.api_max_query_bytes > 32768:
            raise RuntimeError("Limite de query-string API production invalide")
        if not self.mfa_platform_required:
            raise RuntimeError("Le second facteur des comptes plateforme ne peut pas être désactivé en production")
        from edusync.shared.infrastructure.mfa import load_mfa_key
        key = load_mfa_key(self.mfa_encryption_key, jwt_secret=self.jwt_secret, env=self.env)
        if key == self.jwt_secret.encode("utf-8")[:32]:
            raise RuntimeError("EDUSYNC_MFA_ENCRYPTION_KEY doit être distincte du secret JWT")

    def assert_provisioning_safe(self) -> None:
        self.assert_runtime_safe()
        if self.env.lower() not in {"prod", "production"}:
            return
        if self.platform_admin_password == "CHANGE_ME_NOW_123!":
            raise RuntimeError("Mot de passe bootstrap Atelier Pro de développement interdit en production")
        if self._url_has_placeholder(self.owner_database_url):
            raise RuntimeError("Mot de passe PostgreSQL owner de démonstration interdit en production")

    # Compatibility name for existing foundation tests/scripts. Provisioning is the stricter profile.
    def assert_production_safe(self) -> None:
        self.assert_provisioning_safe()


def worker_url(cfg: Settings) -> str:
    """Background workers connect with the dedicated least-privilege role, never the owner/migrator."""
    url = cfg.worker_database_url
    if not url:
        raise RuntimeError("EDUSYNC_WORKER_DATABASE_URL obligatoire : les workers n'utilisent jamais le compte propriétaire")
    if "edusync_worker" not in url.split("@", 1)[0]:
        raise RuntimeError("EDUSYNC_WORKER_DATABASE_URL doit utiliser le rôle edusync_worker")
    return url
