"""Contrôle de la configuration de PRODUCTION Coolify (docker-compose.coolify.yml + frontend/nginx.production.conf).

Vérifie, sans rien déployer :
  - lisible tel quel par Coolify 4.4.x : ni ancre YAML, ni champ « x- », ni « $ » dans les commandes, ni fichier monté
    depuis le dépôt (aucune dépendance à « Preserve repository »), une seule variable obligatoire (EDUSYNC_RELEASE_SHA) ;
  - images certifiées seulement (aucun build sur le VPS) : applicatives = ghcr.io/danielkikunda/edusync-* au SHA validé,
    infrastructure = les mêmes empreintes que le contrôleur du staging ;
  - aucun env_file, aucun port publié, pas de Caddy ; journaux bornés ;
  - aucun secret généré dans les variables Coolify (injectées dans tous les conteneurs, coollabsio/coolify#7655) ;
    le mot de passe propriétaire PostgreSQL n'est monté que là où il sert ;
  - HTTPS : CORS, hôtes, adresse publique ; nginx de production = nginx certifié + 3 écarts permis, copié dans l'image ;
  - --render : `docker compose config` (clés propres à Coolify retirées), comme Coolify le lit.

    python tools/ci/coolify_compose_check.py [--render]
Code de sortie 1 au premier écart.
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.coolify.yml"
NGINX_PROD = ROOT / "frontend/nginx.production.conf"
NGINX_BASE = ROOT / "frontend/nginx.conf"
DOCKERFILE = ROOT / "frontend/Dockerfile"
CONTROLLER = ROOT / "deploy/staging/privileged/deploy_controller.py"
APP_IMAGE = re.compile(r"^ghcr\.io/danielkikunda/edusync-(backend|frontend|backup):\$\{EDUSYNC_RELEASE_SHA:\?[^}]+\}$")
HSTS = 'add_header Strict-Transport-Security "max-age=31536000" always;'
# Générés par secrets-init : ne doivent JAMAIS figurer dans une variable Coolify (seul leur chemin *_FILE le peut).
GENERATED = re.compile(r"(JWT_SECRET|MFA_ENCRYPTION_KEY|DOCUMENT_LINK_SECRET|DATABASE_URL|POSTGRES_PASSWORD|PGPASSWORD|"
                       r"OBJECT_STORAGE_(ACCESS|SECRET)_KEY|SRC_(ACCESS_KEY_ID|SECRET_ACCESS_KEY))")
OWNER_MOUNTS = {"secrets-init", "postgres", "migrator", "backup"}
COOLIFY_ONLY_KEYS = ("exclude_from_hc",)
ROLE_OF = {"migrator": "migrate", "backend": "api", "outbox-worker": "outbox", "communications-worker": "communications"}

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
    code = "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("#"))
    services = doc["services"]
    infra = controller_infra_images()
    certified = {infra["postgres"], infra["redis"], infra["object-storage"]}

    required = sorted(set(re.findall(r"\$\{([A-Z0-9_]+):?\?", code)))
    check(required == ["EDUSYNC_RELEASE_SHA"], f"une seule variable obligatoire (EDUSYNC_RELEASE_SHA) — trouvé {required}")
    check(not re.search(r"(^|\s)[&*][A-Za-z_-]+|<<:", code), "aucune ancre ni fusion YAML (lecteur Coolify)")
    check(set(doc) == {"services", "volumes"}, f"seulement services et volumes au premier niveau — trouvé {sorted(doc)}")
    check("env_file" not in code, "aucun env_file")
    check("tls-proxy" not in services and "caddy" not in code.lower(), "pas de Caddy : Traefik (Coolify) termine le HTTPS")
    for name, svc in services.items():
        check("build" not in svc, f"{name} : aucune compilation sur le VPS")
        image = svc.get("image", "")
        check(bool(APP_IMAGE.match(image)) or image in certified, f"{name} : image certifiée ({image.split('@')[0]})")
        check("ports" not in svc, f"{name} : aucun port publié (Traefik seul entre)")
        log = svc.get("logging", {})
        check(log.get("driver") == "json-file" and log.get("options", {}).get("max-size") == "10m", f"{name} : journaux bornés")
        env = svc.get("environment", {}) or {}
        leaked = [k for k in env if GENERATED.search(k) and not k.endswith("_FILE")]
        check(not leaked, f"{name} : aucun secret généré dans les variables Coolify {leaked or ''}".rstrip())
        for field in ("command", "entrypoint"):
            value = svc.get(field) or []
            text = " ".join(value) if isinstance(value, list) else str(value)
            check("$" not in text, f"{name} : {field} sans « $ » (rien à interpréter pour Coolify)")
        vols = [str(v) for v in svc.get("volumes", [])]
        check(all(not v.startswith((".", "/")) for v in vols), f"{name} : volumes nommés seulement (aucun fichier du dépôt)")
        if any(v.startswith("secrets_owner:") for v in vols):
            check(name in OWNER_MOUNTS, f"{name} : autorisé à voir le mot de passe propriétaire")
        for v in vols:
            if v.startswith("secrets_") and name != "secrets-init":
                check(v.endswith(":ro"), f"{name} : secrets montés en lecture seule ({v})")
    for name, role in ROLE_OF.items():
        check(services[name]["command"] == ["python", "scripts/coolify_run.py", role], f"{name} : démarré par coolify_run.py {role}")
    check(services["secrets-init"]["command"] == ["python", "scripts/coolify_secrets.py"], "secrets-init : scripts/coolify_secrets.py")
    check(not any(str(v).startswith("secrets_owner:") for v in services["backend"]["volumes"]),
          "l'API ne voit jamais le mot de passe propriétaire")
    for name in ("secrets-init", "migrator"):
        check(services[name].get("restart") == "no" and services[name].get("exclude_from_hc") is True,
              f"{name} : tâche ponctuelle exclue du contrôle de santé Coolify")
    check(services["backend"]["depends_on"]["migrator"]["condition"] == "service_completed_successfully", "l'API attend les migrations")
    check(services["postgres"]["environment"].get("POSTGRES_PASSWORD_FILE") == "/run/edusync/owner/owner_password",
          "PostgreSQL lit son mot de passe dans un fichier")
    check(services["migrator"]["environment"].get("EDUSYNC_PLATFORM_ADMIN_PASSWORD") == "",
          "aucun compte plateforme par script (valeur de démonstration jamais utilisée)")
    env = services["backend"]["environment"]
    check(env["EDUSYNC_ENV"] == "production", "EDUSYNC_ENV=production (contrôles de sûreté actifs)")
    check(env["EDUSYNC_CORS_ORIGINS"].startswith("https://") and "," not in env["EDUSYNC_CORS_ORIGINS"], "CORS : une origine HTTPS")
    check(env["EDUSYNC_PUBLIC_APP_URL"].startswith("https://"), "adresse publique HTTPS (liens des e-mails)")
    check("*" not in env["EDUSYNC_TRUSTED_HOSTS"] and "localhost" in env["EDUSYNC_TRUSTED_HOSTS"],
          "hôtes de confiance explicites (+ localhost pour le contrôle de santé)")
    check(env["FORWARDED_ALLOW_IPS"] == "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16", "X-Forwarded-For cru seulement des réseaux Docker privés")
    check("app.myeducsync.com" in code, "domaine app.myeducsync.com")
    check("/etc/nginx/edusync/production.conf" in " ".join(services["frontend"]["command"]), "nginx de production activé sur le frontend")
    check(services["backup"]["environment"]["BACKUP_KEEP_DAYS"].endswith(":-7}"), "sauvegardes locales : 7 jours (disque 40 Go)")
    # Supervision (README §9) : signaux de vie externes, facultatifs mais prévus, hors du serveur surveillé.
    check(env.get("EDUSYNC_HEARTBEAT_URL") == "${EDUSYNC_HEARTBEAT_URL:-}", "signal de vie externe de l'API prévu (vide par défaut)")
    check(services["backup"]["environment"].get("BACKUP_HEARTBEAT_URL") == "${EDUSYNC_BACKUP_HEARTBEAT_URL:-}",
          "signal de vie externe de la sauvegarde prévu (vide par défaut)")
    check(all(services[n].get("logging", {}).get("options", {}).get("max-file") == "3" for n in services),
          "journaux limités partout : 3 fichiers de 10 Mo par service")


def nginx_checks() -> None:
    base, prod = NGINX_BASE.read_text(encoding="utf-8"), NGINX_PROD.read_text(encoding="utf-8")
    body = prod[prod.index("server {"):]
    restored = (body.replace("    " + HSTS + "\n", "").replace("  " + HSTS + "\n", "")
                .replace("$edusync_forwarded_proto;\n    proxy_hide_header Strict-Transport-Security;", "$scheme;")
                .replace("(notifications|platform/inbox|live)", "(notifications|platform/inbox)"))
    check(restored == base, "nginx de production = nginx certifié + 3 écarts permis (HSTS, schéma, flux live)")
    blocks = [b.split("}")[0] for b in body.split("location ")[1:]]
    check(body.count(HSTS) == 1 + sum(1 for b in blocks if "add_header" in b), "HSTS sur chaque bloc qui déclare ses en-têtes")
    check("map $http_x_forwarded_proto $edusync_forwarded_proto" in prod, "schéma HTTPS de Traefik relayé à l'API")
    check("COPY nginx.production.conf /etc/nginx/edusync/production.conf" in DOCKERFILE.read_text(encoding="utf-8"),
          "configuration de production incluse dans l'image frontend certifiée")


def render() -> None:
    _, doc = load()
    for svc in doc["services"].values():
        for key in COOLIFY_ONLY_KEYS:
            svc.pop(key, None)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        f = Path(tmp) / "docker-compose.coolify.yml"
        f.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", action="store_true")
    a = ap.parse_args()
    static_checks(); nginx_checks()
    if a.render: render()
    print(f"\n{'COOLIFY_COMPOSE_CHECK=PASS' if not failures else f'COOLIFY_COMPOSE_CHECK=FAIL ({len(failures)})'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
