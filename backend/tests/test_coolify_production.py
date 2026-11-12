"""Production Coolify (docker-compose.coolify.yml, deploy/coolify/) : contrats vérifiés en CI.

Le détail des contrôles est dans tools/ci/coolify_compose_check.py (aussi lancé à la main avant un déploiement).
Le staging (deploy/staging, docker-compose.yml, frontend/nginx.conf) n'est pas modifié par la production.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "tools/ci/coolify_compose_check.py"


def test_coolify_production_compose_passes_every_contract():
    args = [sys.executable, str(CHECK)]
    if shutil.which("sh"):
        args.append("--shell")          # exécute réellement secrets-init et la lecture des secrets de chaque service
    if shutil.which("docker"):
        args.append("--render")         # docker compose config, comme Coolify lit le fichier
    out = subprocess.run(args, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and "COOLIFY_COMPOSE_CHECK=PASS" in out.stdout, out.stdout[-3000:] + out.stderr[-1000:]


def test_production_never_reuses_the_staging_entry_points():
    compose = (ROOT / "docker-compose.coolify.yml").read_text(encoding="utf-8")
    doc = yaml.safe_load(compose)
    used = yaml.safe_dump(doc["services"])          # sans les commentaires : ce que les services utilisent vraiment
    assert "deploy/staging" not in used and "staging" not in doc["services"]["backend"]["environment"]["EDUSYNC_ENV"]
    # Le staging garde sa configuration : Caddy, contrôleur à privilèges limités, nginx certifié de l'image.
    assert "tls-proxy" in (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "location ~ ^/api/v1/(notifications|platform/inbox)/stream$" in (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")


def test_release_gate_refuses_unvalidated_versions_without_network():
    out = subprocess.run([sys.executable, str(ROOT / "tools/ci/production_release_gate.py"), "pas-un-sha"],
                         capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 1 and "40 caractères" in out.stdout
    gate = (ROOT / "tools/ci/production_release_gate.py").read_text(encoding="utf-8")
    assert all(w in gate for w in ("ci.yml", "deploy-staging.yml", "e2e-staging.yml"))


def test_coolify_guide_covers_the_operator_steps():
    guide = (ROOT / "deploy/coolify/README.md").read_text(encoding="utf-8").replace("Retour arrière", "retour arrière")
    for needed in ("app.myeducsync.com", "Preserve repository", "ghcr.io", "EDUSYNC_RELEASE_SHA", "production_release_gate.py",
                   "secrets_app", "mfa_key", "EDUSYNC_BACKUP_OFFSITE", "SMTP", "FCM", "7655", "retour arrière"):
        assert needed in guide, needed
