"""Production Coolify — démarre un service EduSync avec SES secrets seulement (docker-compose.coolify.yml).

Lit les fichiers créés par scripts/coolify_secrets.py, construit les URL PostgreSQL à moindre privilège, exporte
uniquement ce dont le rôle a besoin, puis remplace le processus (os.execvp : signaux et code de sortie conservés).
Un secret absent arrête le service avec un message clair : jamais de démarrage sans lui. Aucune valeur affichée.

    python scripts/coolify_run.py migrate|api|outbox|communications
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

OWNER_DIR = Path(os.environ.get("EDUSYNC_SECRETS_OWNER_DIR", "/run/edusync/owner"))
APP_DIR = Path(os.environ.get("EDUSYNC_SECRETS_APP_DIR", "/run/edusync/app"))
DB_HOST = "postgres:5432"
DB_NAME = "edusync"

ROLES = {
    "migrate": {"needs": ("owner", "tenant", "platform", "worker", "jwt", "mfa"),
                "argv": ["sh", "-c", "python scripts/provision_database.py && python scripts/bootstrap_platform_admin.py"]},
    "api": {"needs": ("tenant", "platform", "jwt", "mfa", "doclink", "s3"),
            "argv": ["uvicorn", "edusync.bootstrap.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000",
                     "--proxy-headers", "--no-server-header"]},
    "outbox": {"needs": ("worker", "jwt"), "argv": ["python", "-m", "edusync.modules.sync.outbox_worker"]},
    "communications": {"needs": ("worker", "jwt", "mfa"), "argv": ["python", "-m", "edusync.modules.communications.worker"]},
}


class MissingSecret(RuntimeError):
    pass


def _read(directory: Path, name: str) -> str:
    path = directory / name
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        value = ""
    if not value:
        raise MissingSecret(f"secret manquant : {name} (le service secrets-init doit réussir avant)")
    return value


def _db(role: str, password: str) -> str:
    return f"postgresql+psycopg://{role}:{password}@{DB_HOST}/{DB_NAME}"


def environment_for(role: str, owner_dir: Path = OWNER_DIR, app_dir: Path = APP_DIR) -> dict[str, str]:
    """Variables exportées pour ce rôle seulement."""
    needs = ROLES[role]["needs"]
    env: dict[str, str] = {}
    if "owner" in needs:
        env["EDUSYNC_OWNER_DATABASE_URL"] = _db("edusync_owner", _read(owner_dir, "owner_password"))
    if "tenant" in needs:
        env["EDUSYNC_TENANT_DATABASE_URL"] = _db("edusync_tenant", _read(app_dir, "tenant_password"))
    if "platform" in needs:
        env["EDUSYNC_PLATFORM_DATABASE_URL"] = _db("edusync_platform", _read(app_dir, "platform_password"))
    if "worker" in needs:
        env["EDUSYNC_WORKER_DATABASE_URL"] = _db("edusync_worker", _read(app_dir, "worker_password"))
    if "jwt" in needs:
        env["EDUSYNC_JWT_SECRET"] = _read(app_dir, "jwt_secret")
    if "mfa" in needs:
        env["EDUSYNC_MFA_ENCRYPTION_KEY"] = _read(app_dir, "mfa_key")
    if "doclink" in needs:
        env["EDUSYNC_DOCUMENT_LINK_SECRET"] = _read(app_dir, "document_link_secret")
    if "s3" in needs:
        env["EDUSYNC_OBJECT_STORAGE_ACCESS_KEY"] = _read(app_dir, "s3_access_key")
        env["EDUSYNC_OBJECT_STORAGE_SECRET_KEY"] = _read(app_dir, "s3_secret_key")
    return env


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in ROLES:
        print(f"Usage : python scripts/coolify_run.py {'|'.join(ROLES)}", file=sys.stderr)
        return 2
    role = argv[1]
    try:
        env = environment_for(role)
    except MissingSecret as exc:
        print(str(exc), file=sys.stderr)
        return 1
    # Les secrets générés viennent des fichiers, jamais des variables Coolify : une valeur homonyme injectée est remplacée.
    os.environ.update(env)
    argv_ = ROLES[role]["argv"]
    os.execvp(argv_[0], argv_)
    return 0  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main(sys.argv))
