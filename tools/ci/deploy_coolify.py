"""Apply one approved SHA and verify the public serving version."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from production_release_gate import SHA

PUBLIC_URL = "https://app.myeducsync.com"
RESOURCE_ID = re.compile(r"[a-zA-Z0-9-]{8,80}")


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(NoRedirects())


def call(base: str, path: str, method: str = "GET", token: str = "", body: dict | None = None):
    headers = {"Accept": "application/json", "Cache-Control": "no-store"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, headers=headers, method=method,
                                     data=json.dumps(body).encode() if body is not None else None)
    with OPENER.open(request, timeout=20) as response:
        return json.load(response)


def verify(sha: str) -> None:
    if call(PUBLIC_URL, "/version.json").get("build") != sha:
        raise RuntimeError("Le SHA public ne correspond pas au SHA approuvé.")
    if call(PUBLIC_URL, "/health-api").get("status") != "ok":
        raise RuntimeError("Le backend public ne confirme pas son état de santé.")


def deploy(sha: str, rollback_from: str) -> None:
    origin = os.environ["COOLIFY_API_ORIGIN"].rstrip("/")
    app = os.environ["COOLIFY_APP_UUID"]
    token = os.environ["COOLIFY_API_TOKEN"]
    url = urllib.parse.urlsplit(origin)
    if (url.scheme != "https" or not url.hostname or url.username or url.path or url.query or url.fragment
            or not RESOURCE_ID.fullmatch(app) or not token):
        raise RuntimeError("Configuration Coolify incomplète ou invalide.")
    previous = call(PUBLIC_URL, "/version.json").get("build", "")
    if not SHA.fullmatch(previous):
        raise RuntimeError("Le SHA actuellement servi est inconnu.")
    print(f"SHA précédemment servi : {previous}", flush=True)
    if rollback_from:
        if previous != rollback_from:
            raise RuntimeError("Le SHA actuellement servi a changé depuis la demande de retour arrière.")
        comparison = subprocess.run(
            ["git", "diff", "--quiet", previous, sha, "--", "backend/migrations", "backend/scripts/coolify_run.py",
             "docker-compose.coolify.yml"], check=False)
        if comparison.returncode != 0:
            raise RuntimeError("Retour arrière refusé : migrations ou configuration Compose différentes ou non vérifiables.")
    if previous == sha:
        verify(sha)
        print("Le SHA approuvé est déjà servi.")
        return
    api = origin + "/api/v1"
    call(api, f"/applications/{app}/envs", "PATCH", token,
         {"key": "EDUSYNC_RELEASE_SHA", "value": sha, "is_preview": False})
    result = call(api, f"/deploy?uuid={app}&force=true", "POST", token)
    deployments = result.get("deployments", [])
    if len(deployments) != 1 or deployments[0].get("resource_uuid") != app:
        raise RuntimeError("Coolify n’a pas confirmé le déploiement de l’application attendue.")
    deployment = deployments[0].get("deployment_uuid", "")
    if not RESOURCE_ID.fullmatch(deployment):
        raise RuntimeError("Identifiant de déploiement Coolify absent.")
    for _ in range(90):
        status = call(api, f"/deployments/{deployment}", token=token).get("status")
        if status == "finished":
            verify(sha)
            print(f"Déploiement vérifié : {sha}")
            return
        if status not in {"queued", "in_progress"}:
            raise RuntimeError("Coolify signale un échec ou un état inattendu. Vérifier le déploiement dans Coolify.")
        time.sleep(10)
    raise RuntimeError("Coolify n’a pas confirmé la fin du déploiement dans le délai prévu.")


if __name__ == "__main__":
    try:
        target, source = sys.argv[1:]
        if not SHA.fullmatch(target) or (source and not SHA.fullmatch(source)):
            raise RuntimeError("SHA de déploiement invalide.")
        deploy(target, source)
    except urllib.error.HTTPError as exc:
        sys.exit(f"Échec HTTP {exc.code}. Vérifier le tableau Coolify avant toute autre action.")
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        sys.exit(str(exc) if isinstance(exc, RuntimeError) else "Échec de configuration ou de communication.")
