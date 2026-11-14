"""Essai réel de la pile de PRODUCTION Coolify (docker-compose.coolify.yml) sur un Docker local, sans aucune donnée réelle.

Démarre la pile comme Coolify le ferait (clés propres à Coolify retirées, même fichier sinon), avec les images de
EDUSYNC_RELEASE_SHA déjà présentes localement (CI ou `docker build`), puis vérifie :
  secrets générés et stables, migrations et rôles à moindre privilège, API et nginx en bonne santé, mot de passe
  propriétaire invisible de l'API, HSTS unique, schéma HTTPS relayé, vraie adresse du client derrière deux proxys,
  sauvegarde avec restauration vérifiée, second déploiement idempotent, mémoire consommée.
Un faux « Traefik » est simulé par des requêtes internes portant les en-têtes X-Forwarded-*. Rien n'est affiché des
secrets. La pile et ses volumes (données de test) sont supprimés à la fin, sauf avec --garder.

    python tools/local/coolify_stack_e2e.py <SHA des images locales> [--garder]
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "edusync-coolify-e2e"
CLIENT_IP = "203.0.113.7"          # adresse documentaire (RFC 5737) : le « vrai client » derrière Traefik
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{' — ' + detail if detail and not ok else ''}", flush=True)


def run(args: list[str], env: dict, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, env=env, timeout=timeout, encoding="utf-8", errors="replace")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__); return 2
    sha, garder = sys.argv[1], "--garder" in sys.argv
    doc = yaml.safe_load((ROOT / "docker-compose.coolify.yml").read_text(encoding="utf-8"))
    for svc in doc["services"].values():
        svc.pop("exclude_from_hc", None)
    tmp = Path(tempfile.mkdtemp(prefix="edusync-coolify-"))
    compose = tmp / "docker-compose.yml"
    compose.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    env = {**{k: v for k, v in os.environ.items() if not k.startswith(("EDUSYNC_", "SERVICE_"))},
           "EDUSYNC_RELEASE_SHA": sha, "SERVICE_PASSWORD_64_SETUPTOKEN": secrets.token_urlsafe(48)}
    dc = ["docker", "compose", "-p", PROJECT, "-f", str(compose)]

    def ex(service: str, *cmd: str) -> subprocess.CompletedProcess:
        return run(dc + ["exec", "-T", service, *cmd], env, timeout=120)

    def http(path: str, extra: str = "") -> dict:
        code = ("import json,urllib.request\n"
                f"r=urllib.request.Request('http://frontend{path}',headers={{'Host':'app.myeducsync.com','X-Forwarded-Proto':'https',"
                f"'X-Forwarded-For':'{CLIENT_IP}'{extra}}})\n"
                "try:\n o=urllib.request.urlopen(r,timeout=10);s=o.status;h=o.headers\n"
                "except urllib.error.HTTPError as e:\n s=e.code;h=e.headers\n"
                "print(json.dumps({'status':s,'hsts':h.get_all('Strict-Transport-Security') or [],'csp':bool(h.get('Content-Security-Policy'))}))")
        out = ex("backend", "python", "-c", code)
        return json.loads(out.stdout.strip().splitlines()[-1]) if out.returncode == 0 else {"status": None, "err": out.stderr[-300:]}

    try:
        run(dc + ["down", "-v"], env)
        t0 = time.time()
        up = run(dc + ["up", "-d", "--wait", "--wait-timeout", "420"], env, timeout=600)
        check("pile démarrée, services sains (docker compose up --wait)", up.returncode == 0, up.stderr[-600:])
        check(f"démarrage complet en {time.time() - t0:.0f} s", True)
        ps = {json.loads(l)["Service"]: json.loads(l) for l in run(dc + ["ps", "-a", "--format", "json"], env).stdout.splitlines() if l.strip()}
        for one_shot in ("secrets-init", "migrator"):
            st = ps.get(one_shot, {})
            check(f"{one_shot} terminé avec succès", st.get("State") == "exited" and st.get("ExitCode") == 0, str(st.get("Status")))
        for svc in ("postgres", "redis", "backend", "frontend"):
            check(f"{svc} en bonne santé", ps.get(svc, {}).get("Health") == "healthy", str(ps.get(svc, {}).get("Status")))
        for svc in ("object-storage", "outbox-worker", "communications-worker", "backup"):
            check(f"{svc} en marche", ps.get(svc, {}).get("State") == "running", str(ps.get(svc, {}).get("Status")))

        sql = lambda q: ex("postgres", "psql", "-U", "edusync_owner", "-d", "edusync", "-tAc", q).stdout.strip()
        check("migrations appliquées (≥ 100)", int(sql("SELECT count(*) FROM schema_migrations") or 0) >= 100)
        roles = sql("SELECT string_agg(rolname||':'||rolsuper||rolbypassrls,',' ORDER BY rolname) FROM pg_roles WHERE rolname LIKE 'edusync_%'")
        check("rôles tenant/platform/worker sans superutilisateur ni contournement du RLS",
              roles == "edusync_owner:truetrue,edusync_platform:falsefalse,edusync_tenant:falsefalse,edusync_worker:falsefalse"
              or all(r in roles for r in ("edusync_platform:falsefalse", "edusync_tenant:falsefalse", "edusync_worker:falsefalse")), roles)

        owner = ex("postgres", "cat", "/run/edusync/owner/owner_password").stdout.strip()
        api_env = ex("backend", "sh", "-c", "cat /proc/1/environ | tr '\\0' '\\n'").stdout
        check("l'API n'a pas le mot de passe propriétaire (ni volume, ni variable)",
              bool(owner) and owner not in api_env and ex("backend", "test", "-e", "/run/edusync/owner").returncode != 0)
        check("l'API a reçu ses secrets depuis les fichiers", "EDUSYNC_TENANT_DATABASE_URL=postgresql+psycopg://edusync_tenant:" in api_env
              and "EDUSYNC_OWNER_DATABASE_URL" not in api_env)
        # Le migrateur est arrêté : les droits se lisent depuis la sauvegarde, qui monte les deux volumes.
        perms = ex("backup", "sh", "-c", "stat -c '%a %u' /run/edusync/owner/owner_password /run/edusync/app/jwt_secret").stdout.split()
        check("droits : propriétaire 400 (uid 70), autres secrets 444", perms == ["400", "70", "444", "0"], " ".join(perms))

        page = http("/")
        check("page d'accueil servie (HTTPS simulé)", page.get("status") == 200 and page.get("csp"), str(page))
        check("HSTS présent une seule fois sur la page", page.get("hsts") == ["max-age=31536000"], str(page.get("hsts")))
        health = http("/health-api")
        check("API joignable à travers nginx", health.get("status") == 200, str(health))
        api = http("/api/v1/auth/login", ",'Content-Type':'application/json'")
        check("réponse de l'API : HSTS unique (celui de l'API masqué)", len(api.get("hsts", [])) == 1, str(api))
        logs = run(dc + ["logs", "--no-color", "backend"], env).stdout
        check("vraie adresse du client vue par l'API derrière Traefik + nginx", CLIENT_IP in logs)

        # Supervision (README §9): host resources measured from the API container, curl present for the backup heartbeat.
        host = ex("backend", "python", "-c", "from edusync.bootstrap.settings import Settings;"
                  "from edusync.modules.platform_health.application.host import host_component as h;c=h(Settings());print(c['state'],c['detail'])")
        check("ressources du serveur mesurées depuis l'API (mémoire, disque, charge)",
              host.returncode == 0 and host.stdout.split()[:1] in (["OK"], ["DEGRADED"], ["DOWN"]), host.stdout.strip() or host.stderr[-300:])
        check("image de sauvegarde : curl présent pour le signal de vie externe", ex("backup", "curl", "--version").returncode == 0)

        status = None
        for _ in range(40):
            out = ex("backend", "cat", "/backup-status/last.json")
            if out.returncode == 0 and out.stdout.strip():
                status = json.loads(out.stdout); break
            time.sleep(5)
        check("sauvegarde faite et restauration vérifiée", bool(status) and status.get("ok") is True and status.get("restore_verified") is True,
              json.dumps(status) if status else "aucun état")

        before = ex("backup", "sh", "-c", "cat /run/edusync/owner/owner_password /run/edusync/app/* | sha256sum").stdout
        again = run(dc + ["up", "-d", "--wait", "--wait-timeout", "300"], env, timeout=420)
        after = ex("backup", "sh", "-c", "cat /run/edusync/owner/owner_password /run/edusync/app/* | sha256sum").stdout
        check("second déploiement : réussi, secrets inchangés, migrateur rejoué sans erreur",
              again.returncode == 0 and before == after and bool(before.strip()), again.stderr[-300:])

        stats = run(["docker", "stats", "--no-stream", "--format", "{{.Name}}|{{.MemUsage}}"], env).stdout
        total = 0.0
        for line in stats.splitlines():
            if PROJECT in line:
                used = line.split("|")[1].split("/")[0].strip()
                num = float(used[:-3]); unit = used[-3:]
                total += num / 1024 if unit == "KiB" else num if unit == "MiB" else num * 1024
        check(f"mémoire de la pile au repos : {total:.0f} Mio (VPS 4 Go)", total < 2048, stats)
    finally:
        if not garder:
            run(dc + ["down", "-v"], env)
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} PASS · {len(failed)} FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
