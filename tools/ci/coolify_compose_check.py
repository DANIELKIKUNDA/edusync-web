"""Contrôle de la configuration de PRODUCTION Coolify (docker-compose.coolify.yml + deploy/coolify/nginx.conf).

Vérifie, sans rien déployer :
  - images certifiées seulement (aucun build sur le VPS) : applicatives = ghcr.io/danielkikunda/edusync-* au SHA validé,
    infrastructure = les mêmes empreintes que le contrôleur du staging ;
  - une seule variable obligatoire (EDUSYNC_RELEASE_SHA), aucun env_file, aucun port publié, pas de Caddy ;
  - aucun secret généré dans les variables Coolify (injectées dans tous les conteneurs, coollabsio/coolify#7655) ;
    le mot de passe propriétaire PostgreSQL n'est monté que là où il sert ;
  - HTTPS : CORS, hôtes, adresse publique ; journaux bornés ; nginx de production = nginx certifié + 3 écarts permis ;
  - --render : `docker compose config` sur le fichier (clés propres à Coolify retirées), comme Coolify le lit ;
  - --shell  : exécute réellement les scripts shell des services (secrets-init, lecture des secrets) dans un dossier
    temporaire, avec des secrets factices, et vérifie les variables obtenues (aucune valeur affichée).

    python tools/ci/coolify_compose_check.py [--render] [--shell]
Code de sortie 1 au premier écart.
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.coolify.yml"
NGINX_PROD = ROOT / "deploy/coolify/nginx.conf"
NGINX_BASE = ROOT / "frontend/nginx.conf"
CONTROLLER = ROOT / "deploy/staging/privileged/deploy_controller.py"
APP_IMAGE = re.compile(r"^ghcr\.io/danielkikunda/edusync-(backend|frontend|backup):\$\{EDUSYNC_RELEASE_SHA:\?[^}]+\}$")
HSTS = 'add_header Strict-Transport-Security "max-age=31536000" always;'
# Générés par secrets-init : ne doivent JAMAIS figurer dans une variable Coolify.
GENERATED = re.compile(r"(JWT_SECRET|MFA_ENCRYPTION_KEY|DOCUMENT_LINK_SECRET|DATABASE_URL|POSTGRES_PASSWORD$|PGPASSWORD|"
                       r"OBJECT_STORAGE_(ACCESS|SECRET)_KEY|SRC_(ACCESS_KEY_ID|SECRET_ACCESS_KEY)|S3_(ACCESS|SECRET)_KEY)")
# Secrets de fournisseurs saisis par le propriétaire le jour où le canal est activé (risque résiduel documenté).
PROVIDER_SECRETS = {"EDUSYNC_SMTP_PASSWORD", "EDUSYNC_SMTP_USERNAME", "EDUSYNC_ORANGE_SMS_CLIENT_SECRET",
                    "EDUSYNC_ORANGE_SMS_DR_SECRET", "EDUSYNC_SETUP_TOKEN", "RCLONE_CONFIG_OFFSITE_SECRET_ACCESS_KEY",
                    "RCLONE_CONFIG_OFFSITE_ACCESS_KEY_ID"}
OWNER_MOUNTS = {"secrets-init", "postgres", "migrator", "backup"}
COOLIFY_ONLY_KEYS = ("exclude_from_hc",)

failures: list[str] = []


def check(cond: bool, message: str) -> None:
    print(("PASS  " if cond else "FAIL  ") + message)
    if not cond:
        failures.append(message)


def controller_infra_images() -> dict[str, str]:
    tree = ast.parse(CONTROLLER.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "INFRA_IMAGES" for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit("INFRA_IMAGES introuvable dans le contrôleur du staging")


def load() -> tuple[str, dict]:
    raw = COMPOSE.read_text(encoding="utf-8")
    return raw, yaml.safe_load(raw)


def static_checks() -> None:
    raw, doc = load()
    services = doc["services"]
    infra = controller_infra_images()
    certified = {infra["postgres"], infra["redis"], infra["object-storage"]}

    required = sorted(set(re.findall(r"\$\{([A-Z0-9_]+):?\?", raw)))
    check(required == ["EDUSYNC_RELEASE_SHA"], f"une seule variable obligatoire (EDUSYNC_RELEASE_SHA) — trouvé {required}")
    check("env_file" not in raw.replace("# ", ""), "aucun env_file")
    check("tls-proxy" not in services and "caddy" not in raw.lower().split("services:", 1)[1],
          "pas de Caddy : Traefik (Coolify) termine le HTTPS")
    for name, svc in services.items():
        check("build" not in svc, f"{name} : aucune compilation sur le VPS")
        image = svc.get("image", "")
        check(bool(APP_IMAGE.match(image)) or image in certified, f"{name} : image certifiée ({image.split('@')[0]})")
        check("ports" not in svc, f"{name} : aucun port publié (Traefik seul entre)")
        log = svc.get("logging", {})
        check(log.get("driver") == "json-file" and log.get("options", {}).get("max-size") == "10m",
              f"{name} : journaux bornés")
        env = svc.get("environment", {}) or {}
        leaked = [k for k in env if GENERATED.search(k) and k not in PROVIDER_SECRETS]
        check(not leaked, f"{name} : aucun secret généré dans les variables Coolify {leaked or ''}".rstrip())
        command = "\n".join(svc.get("command", []) if isinstance(svc.get("command"), list) else [svc.get("command") or ""])
        check("${" not in command and "$${" not in command, f"{name} : commande sans expression « ${{ » lue par Coolify")
        vols = [str(v) for v in svc.get("volumes", [])]
        if any(v.startswith("secrets_owner:") for v in vols):
            check(name in OWNER_MOUNTS, f"{name} : autorisé à voir le mot de passe propriétaire")
        for v in vols:
            if v.startswith("secrets_") and name != "secrets-init":
                check(v.endswith(":ro"), f"{name} : secrets montés en lecture seule ({v})")
    for name in ("backend", "migrator", "outbox-worker", "communications-worker", "backup"):
        check(not any(str(v).startswith("secrets_owner:") for v in services[name].get("volumes", [])) or name in OWNER_MOUNTS,
              f"{name} : pas d'accès propriétaire hors du nécessaire")
    check(not any(str(v).startswith("secrets_owner:") for v in services["backend"]["volumes"]),
          "l'API ne voit jamais le mot de passe propriétaire")
    for name in ("secrets-init", "migrator"):
        check(services[name].get("restart") == "no" and services[name].get("exclude_from_hc") is True,
              f"{name} : tâche ponctuelle exclue du contrôle de santé Coolify")
    check(services["backend"]["depends_on"]["migrator"]["condition"] == "service_completed_successfully",
          "l'API attend la fin des migrations")
    env = services["backend"]["environment"]
    check(env["EDUSYNC_ENV"] == "production", "EDUSYNC_ENV=production (contrôles de sûreté actifs)")
    check(env["EDUSYNC_CORS_ORIGINS"].startswith("https://") and "," not in env["EDUSYNC_CORS_ORIGINS"], "CORS : une origine HTTPS")
    check(env["EDUSYNC_PUBLIC_APP_URL"].startswith("https://"), "adresse publique HTTPS (liens des e-mails)")
    check("*" not in env["EDUSYNC_TRUSTED_HOSTS"] and "localhost" in env["EDUSYNC_TRUSTED_HOSTS"],
          "hôtes de confiance explicites (+ localhost pour le contrôle de santé)")
    check(env["FORWARDED_ALLOW_IPS"] == "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
          "X-Forwarded-For cru seulement depuis les réseaux Docker privés")
    check("app.myeducsync.com" in raw, "domaine app.myeducsync.com")
    check(any("deploy/coolify/nginx.conf:/etc/nginx/conf.d/default.conf:ro" in str(v) for v in services["frontend"]["volumes"]),
          "nginx de production monté sur le frontend")
    check(services["backup"]["environment"]["BACKUP_KEEP_DAYS"].endswith(":-7}"), "sauvegardes locales : 7 jours (disque 40 Go)")


def nginx_checks() -> None:
    base, prod = NGINX_BASE.read_text(encoding="utf-8"), NGINX_PROD.read_text(encoding="utf-8")
    body = prod.split("\n", 1)[1]
    body = body[body.index("server {"):]
    restored = (body.replace("    " + HSTS + "\n", "").replace("  " + HSTS + "\n", "")
                .replace("$edusync_forwarded_proto;\n    proxy_hide_header Strict-Transport-Security;", "$scheme;")
                .replace("(notifications|platform/inbox|live)", "(notifications|platform/inbox)"))
    check(restored == base, "nginx de production = nginx certifié + 3 écarts permis (HSTS, schéma, flux live)")
    check(prod.count(HSTS) == 1 + sum(1 for b in prod.split("location ")[1:] if "add_header" in b.split("}")[0]),
          "HSTS sur chaque bloc qui déclare ses propres en-têtes")
    check("map $http_x_forwarded_proto $edusync_forwarded_proto" in prod, "schéma HTTPS de Traefik relayé à l'API")


def render() -> None:
    _, doc = load()
    for svc in doc["services"].values():
        for key in COOLIFY_ONLY_KEYS:
            svc.pop(key, None)
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "docker-compose.coolify.yml"
        f.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
        shutil.copytree(ROOT / "deploy/coolify", Path(tmp) / "deploy/coolify")
        base_env = {k: v for k, v in os.environ.items() if not k.startswith(("EDUSYNC_", "SERVICE_"))}
        miss = subprocess.run(["docker", "compose", "-f", str(f), "config", "-q"], capture_output=True, text=True, env=base_env)
        check(miss.returncode != 0 and "EDUSYNC_RELEASE_SHA" in miss.stderr, "rendu refusé sans SHA validé")
        env = {**base_env, "EDUSYNC_RELEASE_SHA": "0" * 40, "SERVICE_PASSWORD_64_SETUPTOKEN": "x" * 64}
        out = subprocess.run(["docker", "compose", "-f", str(f), "config"], capture_output=True, text=True, env=env)
        check(out.returncode == 0, "docker compose config : rendu valide" + (f" — {out.stderr.strip()[:300]}" if out.returncode else ""))
        if out.returncode == 0:
            rendered = yaml.safe_load(out.stdout)
            check(all("ports" not in s for s in rendered["services"].values()), "rendu : aucun port publié")
            check(rendered["services"]["backend"]["environment"]["EDUSYNC_CORS_ORIGINS"] == "https://app.myeducsync.com",
                  "rendu : CORS = https://app.myeducsync.com")
            check(rendered["services"]["frontend"]["image"].endswith(":" + "0" * 40), "rendu : images au SHA demandé")


def shell() -> None:
    sh = shutil.which("sh")
    if not sh:
        check(False, "sh introuvable pour exécuter les scripts")
        return
    _, doc = load()
    services = doc["services"]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_p = Path(tmp)
        (tmp_p / "owner").mkdir(); (tmp_p / "app").mkdir(); (tmp_p / "bin").mkdir()
        for stub in ("chown", "exec_stub"):
            (tmp_p / "bin" / stub).write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            os.chmod(tmp_p / "bin" / stub, 0o755)
        posix = lambda p: subprocess.run([sh, "-c", "cd \"$1\" && pwd", "_", str(p)], capture_output=True, text=True).stdout.strip()
        ptmp = posix(tmp_p)

        def script(name: str) -> str:
            body = services[name]["command"][0].replace("$$", "$").replace("/run/edusync", ptmp)
            return body

        env = {**os.environ, "PATH": f"{ptmp}/bin:" + os.environ.get("PATH", "")}
        init = subprocess.run([sh, "-c", script("secrets-init")], capture_output=True, text=True, env=env)
        check(init.returncode == 0, "secrets-init s'exécute" + (f" — {init.stderr.strip()[:200]}" if init.returncode else ""))
        files = sorted(p.name for p in (tmp_p / "app").iterdir())
        check(files == ["document_link_secret", "jwt_secret", "mfa_key", "platform_password", "s3_access_key", "s3_secret_key",
                        "tenant_password", "worker_password"] and (tmp_p / "owner/owner_password").exists(), "secrets générés : 9 fichiers")
        sizes = {p.name: len(p.read_text().strip()) for p in (tmp_p / "app").iterdir()}
        check(sizes.get("jwt_secret") == 64 and sizes.get("s3_access_key") == 20 and sizes.get("tenant_password") == 40,
              "longueurs attendues (JWT 64, mots de passe 40, clé S3 20)")
        import base64
        check(len(base64.b64decode((tmp_p / "app/mfa_key").read_text().strip())) == 32, "clé MFA : 32 octets en base64")
        before = {p.name: p.read_text() for p in (tmp_p / "app").iterdir()}
        again = subprocess.run([sh, "-c", script("secrets-init")], capture_output=True, text=True, env=env)
        check(again.returncode == 0 and before == {p.name: p.read_text() for p in (tmp_p / "app").iterdir()},
              "secrets-init ne remplace jamais un secret existant")
        check(init.stdout.strip() == "secrets EduSync : présents", "secrets-init n'affiche aucun secret")
        owner = (tmp_p / "owner/owner_password").read_text()
        for name, needed, forbidden in (
            ("backend", ["EDUSYNC_TENANT_DATABASE_URL", "EDUSYNC_PLATFORM_DATABASE_URL", "EDUSYNC_JWT_SECRET",
                         "EDUSYNC_MFA_ENCRYPTION_KEY", "EDUSYNC_DOCUMENT_LINK_SECRET", "EDUSYNC_OBJECT_STORAGE_ACCESS_KEY",
                         "EDUSYNC_OBJECT_STORAGE_SECRET_KEY"], ["EDUSYNC_OWNER_DATABASE_URL", "EDUSYNC_WORKER_DATABASE_URL"]),
            ("outbox-worker", ["EDUSYNC_WORKER_DATABASE_URL", "EDUSYNC_JWT_SECRET"], ["EDUSYNC_OWNER_DATABASE_URL", "EDUSYNC_TENANT_DATABASE_URL"]),
            ("communications-worker", ["EDUSYNC_WORKER_DATABASE_URL", "EDUSYNC_JWT_SECRET", "EDUSYNC_MFA_ENCRYPTION_KEY"], ["EDUSYNC_OWNER_DATABASE_URL"]),
            ("migrator", ["EDUSYNC_OWNER_DATABASE_URL", "EDUSYNC_TENANT_DATABASE_URL", "EDUSYNC_PLATFORM_DATABASE_URL",
                          "EDUSYNC_WORKER_DATABASE_URL", "EDUSYNC_JWT_SECRET", "EDUSYNC_MFA_ENCRYPTION_KEY"], []),
            ("backup", ["PGPASSWORD", "RCLONE_CONFIG_SRC_ACCESS_KEY_ID", "RCLONE_CONFIG_SRC_SECRET_ACCESS_KEY"], []),
        ):
            body = script(name)
            lines = body.splitlines()
            last = [i for i, l in enumerate(lines) if l.startswith(("exec ", "python "))][-1]
            probe = "\n".join(lines[:last] + ['env | cut -d= -f1'])
            clean = {k: v for k, v in env.items() if not k.startswith(("EDUSYNC_", "PG", "RCLONE_"))}
            run = subprocess.run([sh, "-c", probe], capture_output=True, text=True, env=clean)
            names = set(run.stdout.split())
            check(run.returncode == 0 and set(needed) <= names and not (set(forbidden) & names),
                  f"{name} : exporte {len(needed)} secret(s) nécessaires, aucun interdit")
            if name == "backend":
                url = subprocess.run([sh, "-c", "\n".join(lines[:last] + ['printf %s "$EDUSYNC_TENANT_DATABASE_URL"'])],
                                     capture_output=True, text=True, env=clean).stdout
                check(url.startswith("postgresql+psycopg://edusync_tenant:") and url.endswith("@postgres:5432/edusync")
                      and owner not in url, "URL tenant bien formée (rôle edusync_tenant)")
        os.chmod(tmp_p / "app/jwt_secret", 0o644)
        (tmp_p / "app/jwt_secret").unlink()
        broken = subprocess.run([sh, "-c", script("backend").rsplit("exec ", 1)[0] + "echo atteint"], capture_output=True,
                                text=True, env=env)
        check(broken.returncode != 0 and "atteint" not in broken.stdout and "jwt_secret" in broken.stderr,
              "secret manquant : le service s'arrête au lieu de démarrer sans")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--shell", action="store_true")
    a = ap.parse_args()
    static_checks(); nginx_checks()
    if a.render: render()
    if a.shell: shell()
    print(f"\n{'COOLIFY_COMPOSE_CHECK=PASS' if not failures else f'COOLIFY_COMPOSE_CHECK=FAIL ({len(failures)})'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
