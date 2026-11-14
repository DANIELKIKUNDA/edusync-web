"""Production Coolify — génère une fois les secrets d'EduSync dans deux volumes (docker-compose.coolify.yml, « secrets-init »).

Coolify v4 injecte toutes les variables d'une ressource dans tous ses conteneurs (coollabsio/coolify#7655) : aucun secret
généré ne passe donc par les variables Coolify. Ce script, lancé en root dans l'image backend certifiée :
  - crée chaque secret absent (jamais de remplacement d'un secret existant : les rôles PostgreSQL, les sessions et les
    secrets TOTP chiffrés en dépendent) ;
  - écrit l'identité S3 de SeaweedFS (s3.json) à partir des clés générées ;
  - pose les droits : mot de passe propriétaire lisible seulement par PostgreSQL (uid 70) et les services root qui
    montent « secrets_owner » ; les autres en lecture seule ;
  - n'affiche aucune valeur.

    python scripts/coolify_secrets.py [--owner-dir /run/edusync/owner] [--app-dir /run/edusync/app]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import string
from pathlib import Path

ALPHABET = string.ascii_letters + string.digits
POSTGRES_UID = POSTGRES_GID = 70           # utilisateur « postgres » de l'image postgres:16-alpine
OWNER_SECRETS = {"owner_password": 48}
APP_SECRETS = {"tenant_password": 40, "platform_password": 40, "worker_password": 40, "jwt_secret": 64,
               "document_link_secret": 64, "s3_access_key": 20, "s3_secret_key": 40}
MFA_KEY = "mfa_key"                       # 32 octets aléatoires en base64 (EDUSYNC_MFA_ENCRYPTION_KEY)
S3_CONFIG = "s3.json"


def _random(length: int) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def _write_once(path: Path, value: str) -> bool:
    if path.exists() and path.stat().st_size > 0:
        return False
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(value)
    os.replace(tmp, path)
    return True


def ensure(owner_dir: Path, app_dir: Path, *, chown: bool = True) -> dict[str, int]:
    owner_dir.mkdir(parents=True, exist_ok=True)
    app_dir.mkdir(parents=True, exist_ok=True)
    created = 0
    for name, length in OWNER_SECRETS.items():
        created += _write_once(owner_dir / name, _random(length))
    for name, length in APP_SECRETS.items():
        created += _write_once(app_dir / name, _random(length))
    created += _write_once(app_dir / MFA_KEY, base64.b64encode(secrets.token_bytes(32)).decode())
    # Identité S3 de SeaweedFS : toujours réécrite à partir des clés (elle ne contient rien d'autre).
    identity = {"identities": [{"name": "edusync-app", "credentials": [{
        "accessKey": (app_dir / "s3_access_key").read_text(encoding="utf-8"),
        "secretKey": (app_dir / "s3_secret_key").read_text(encoding="utf-8")}],
        "actions": ["Read", "Write", "List", "Tagging", "Admin"]}]}
    tmp = app_dir / (S3_CONFIG + ".tmp")
    tmp.write_text(json.dumps(identity), encoding="utf-8")
    os.replace(tmp, app_dir / S3_CONFIG)

    owner = owner_dir / "owner_password"
    if chown:
        os.chown(owner, POSTGRES_UID, POSTGRES_GID)
    os.chmod(owner, 0o400)
    for item in app_dir.iterdir():
        if item.is_file():
            os.chmod(item, 0o444)
    os.chmod(owner_dir, 0o755)
    os.chmod(app_dir, 0o755)
    return {"created": created}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner-dir", default="/run/edusync/owner")
    ap.add_argument("--app-dir", default="/run/edusync/app")
    a = ap.parse_args()
    result = ensure(Path(a.owner_dir), Path(a.app_dir), chown=os.geteuid() == 0 if hasattr(os, "geteuid") else False)
    print(f"secrets EduSync : présents ({result['created']} créé(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
