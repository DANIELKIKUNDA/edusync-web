"""Production Coolify (docker-compose.coolify.yml, deploy/coolify/, scripts/coolify_*.py) : contrats vérifiés en CI.

Le détail des contrôles du fichier Compose est dans tools/ci/coolify_compose_check.py (aussi lancé à la main avant un
déploiement). Le staging (deploy/staging, docker-compose.yml, frontend/nginx.conf) n'est pas modifié par la production.
"""
import base64
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "tools/ci/coolify_compose_check.py"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "backend/scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_coolify_production_compose_passes_every_contract():
    args = [sys.executable, str(CHECK)] + (["--render"] if shutil.which("docker") else [])
    out = subprocess.run(args, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and "COOLIFY_COMPOSE_CHECK=PASS" in out.stdout, out.stdout[-3000:] + out.stderr[-1000:]


def test_secrets_are_generated_once_with_the_expected_shape_and_never_replaced(tmp_path):
    secrets_mod = _load("coolify_secrets")
    owner, app = tmp_path / "owner", tmp_path / "app"
    assert secrets_mod.ensure(owner, app, chown=False)["created"] == 9
    files = sorted(p.name for p in app.iterdir())
    assert files == ["document_link_secret", "jwt_secret", "mfa_key", "platform_password", "s3.json", "s3_access_key",
                     "s3_secret_key", "tenant_password", "worker_password"]
    read = lambda p: p.read_text(encoding="utf-8")
    assert len(read(app / "jwt_secret")) == 64 and len(read(app / "tenant_password")) == 40 and len(read(owner / "owner_password")) == 48
    assert len(base64.b64decode(read(app / "mfa_key"))) == 32                        # EDUSYNC_MFA_ENCRYPTION_KEY
    s3 = json.loads(read(app / "s3.json"))["identities"][0]["credentials"][0]
    assert s3 == {"accessKey": read(app / "s3_access_key"), "secretKey": read(app / "s3_secret_key")}
    before = {p.name: read(p) for p in app.iterdir()} | {"owner": read(owner / "owner_password")}
    for p in list(app.iterdir()) + [owner / "owner_password"]:
        os.chmod(p, 0o644)
    assert secrets_mod.ensure(owner, app, chown=False)["created"] == 0
    assert before == {p.name: read(p) for p in app.iterdir()} | {"owner": read(owner / "owner_password")}
    if os.name != "nt":
        assert stat.S_IMODE((owner / "owner_password").stat().st_mode) == 0o400
        assert stat.S_IMODE((app / "jwt_secret").stat().st_mode) == 0o444


def test_each_service_receives_only_its_own_secrets(tmp_path):
    secrets_mod, run = _load("coolify_secrets"), _load("coolify_run")
    owner, app = tmp_path / "owner", tmp_path / "app"
    secrets_mod.ensure(owner, app, chown=False)
    env = {role: run.environment_for(role, owner, app) for role in run.ROLES}
    assert set(env["api"]) == {"EDUSYNC_TENANT_DATABASE_URL", "EDUSYNC_PLATFORM_DATABASE_URL", "EDUSYNC_JWT_SECRET",
                               "EDUSYNC_MFA_ENCRYPTION_KEY", "EDUSYNC_DOCUMENT_LINK_SECRET",
                               "EDUSYNC_OBJECT_STORAGE_ACCESS_KEY", "EDUSYNC_OBJECT_STORAGE_SECRET_KEY"}
    assert set(env["outbox"]) == {"EDUSYNC_WORKER_DATABASE_URL", "EDUSYNC_JWT_SECRET"}
    assert set(env["communications"]) == {"EDUSYNC_WORKER_DATABASE_URL", "EDUSYNC_JWT_SECRET", "EDUSYNC_MFA_ENCRYPTION_KEY"}
    assert "EDUSYNC_OWNER_DATABASE_URL" in env["migrate"]
    assert all("EDUSYNC_OWNER_DATABASE_URL" not in env[r] for r in ("api", "outbox", "communications"))
    owner_pwd = (owner / "owner_password").read_text(encoding="utf-8")
    assert all(owner_pwd not in v for r in ("api", "outbox", "communications") for v in env[r].values())
    assert env["api"]["EDUSYNC_TENANT_DATABASE_URL"].startswith("postgresql+psycopg://edusync_tenant:")
    assert env["api"]["EDUSYNC_TENANT_DATABASE_URL"].endswith("@postgres:5432/edusync")
    assert env["outbox"]["EDUSYNC_WORKER_DATABASE_URL"].startswith("postgresql+psycopg://edusync_worker:")
    # Le jeu complet passe les contrôles de sûreté de production de l'application (comme au démarrage réel).
    from edusync.bootstrap.settings import Settings
    cfg = Settings(_env_file=None, env="production", cors_origins="https://app.myeducsync.com", platform_admin_password="",
                   trusted_hosts="app.myeducsync.com,localhost,127.0.0.1", **{k.removeprefix("EDUSYNC_").lower(): v
                                                                              for k, v in env["migrate"].items()})
    cfg.assert_provisioning_safe()
    os.chmod(app / "jwt_secret", 0o644)
    (app / "jwt_secret").unlink()
    with pytest.raises(run.MissingSecret, match="jwt_secret"):
        run.environment_for("api", owner, app)
    assert run.main(["coolify_run.py", "inconnu"]) == 2


@pytest.mark.skipif(not shutil.which("sh") or os.name == "nt", reason="sh POSIX requis")
def test_backup_reads_its_secrets_from_files(tmp_path):
    (tmp_path / "pg").write_text("motdepasse-du-fichier", encoding="utf-8")
    script = (ROOT / "deploy/backup/backup.sh").read_text(encoding="utf-8").split(': "${PGHOST:=postgres}"')[0]
    probe = script + 'printf %s "$PGPASSWORD"\n'
    out = subprocess.run(["sh", "-c", probe], capture_output=True, text=True, env={"PATH": os.environ["PATH"], "PGPASSWORD_FILE": str(tmp_path / "pg")})
    assert out.returncode == 0 and out.stdout == "motdepasse-du-fichier"
    missing = subprocess.run(["sh", "-c", probe], capture_output=True, text=True, env={"PATH": os.environ["PATH"], "PGPASSWORD_FILE": str(tmp_path / "absent")})
    assert missing.returncode != 0 and "secret manquant" in missing.stderr


def test_production_never_reuses_the_staging_entry_points():
    doc = yaml.safe_load((ROOT / "docker-compose.coolify.yml").read_text(encoding="utf-8"))
    used = yaml.safe_dump(doc["services"])          # sans les commentaires : ce que les services utilisent vraiment
    assert "deploy/staging" not in used and "staging" not in doc["services"]["backend"]["environment"]["EDUSYNC_ENV"]
    # Le staging garde sa configuration : Caddy, contrôleur à privilèges limités, nginx certifié de l'image.
    assert "tls-proxy" in (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "location ~ ^/api/v1/(notifications|platform/inbox)/stream$" in (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    assert "COPY nginx.conf /etc/nginx/conf.d/default.conf" in (ROOT / "frontend/Dockerfile").read_text(encoding="utf-8")


def test_release_gate_refuses_unvalidated_versions_without_network():
    out = subprocess.run([sys.executable, str(ROOT / "tools/ci/production_release_gate.py"), "pas-un-sha"],
                         capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 1 and "40 caractères" in out.stdout
    gate = (ROOT / "tools/ci/production_release_gate.py").read_text(encoding="utf-8")
    assert all(w in gate for w in ("ci.yml", "deploy-staging.yml", "e2e-staging.yml"))


def test_coolify_guide_covers_the_operator_steps():
    guide = (ROOT / "deploy/coolify/README.md").read_text(encoding="utf-8").replace("Retour arrière", "retour arrière")
    for needed in ("app.myeducsync.com", "ghcr.io", "EDUSYNC_RELEASE_SHA", "production_release_gate.py",
                   "secrets_app", "mfa_key", "EDUSYNC_BACKUP_OFFSITE", "SMTP", "FCM", "7655", "retour arrière"):
        assert needed in guide, needed
