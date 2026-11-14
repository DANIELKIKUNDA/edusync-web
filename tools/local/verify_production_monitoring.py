"""Vérification de la supervision de production, AVANT l'ouverture de la première école (owner, 2026-11-14).

Lecture seule, depuis n'importe quel ordinateur (donc vraiment hors du serveur surveillé) :
  1. l'application répond de l'extérieur : interface, API, API + base de données ;
  2. la version en ligne est celle attendue (--sha, facultatif) ;
  3. le certificat HTTPS est valide encore au moins 14 jours ;
  4. (facultatif) les signaux de vie externes sont reçus : avec HEALTHCHECKS_API_KEY (clé API en LECTURE SEULE de
     Healthchecks.io, jamais écrite dans un fichier), chaque contrôle dont le nom contient « EduSync » doit être « up ».

    python tools/local/verify_production_monitoring.py [--url https://app.myeducsync.com] [--sha <SHA>]

Rien n'est modifié, aucun secret n'est affiché. Code de sortie 1 au moindre échec. Les essais de panne (arrêt volontaire
d'un service, saturation simulée) restent manuels : deploy/coolify/README.md §9.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import sys
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

RESULTS: list[bool] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}{' — ' + detail if detail and not ok else ''}", flush=True)


def get(url: str, headers: dict | None = None) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "edusync-monitoring-check", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:   # noqa: S310 — https only (checked in main)
            return r.status, r.read(200_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001
        return 0, type(e).__name__


def cert_days_left(host: str) -> float:
    ctx = ssl.create_default_context()
    with socket.create_connection((host, 443), timeout=15) as sock, ctx.wrap_socket(sock, server_hostname=host) as tls:
        not_after = tls.getpeercert()["notAfter"]
    end = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    return (end - datetime.now(timezone.utc)).total_seconds() / 86400


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://app.myeducsync.com")
    ap.add_argument("--sha", default="")
    a = ap.parse_args()
    base = a.url.rstrip("/")
    if not base.startswith("https://"):
        print("Adresse https obligatoire"); return 2

    code, body = get(base + "/")
    check("interface joignable de l'extérieur", code == 200 and "<" in body, str(code))
    code, body = get(base + "/health-api")
    check("API joignable", code == 200 and "ok" in body, str(code))
    code, body = get(base + "/api/v1/setup/status")
    check("API + base de données", code == 200, str(code))
    code, body = get(base + "/version.json")
    try:
        build = json.loads(body).get("build", "") if code == 200 else ""
    except ValueError:
        build = ""
    check("version publiée lisible", bool(build), str(code))
    if a.sha:
        check("version en ligne = version attendue", build == a.sha, f"en ligne {build[:12]}, attendue {a.sha[:12]}")
    try:
        days = cert_days_left(urlparse(base).hostname or "")
        check(f"certificat HTTPS valide encore {days:.0f} jours (≥ 14)", days >= 14, f"{days:.1f} jours")
    except Exception as e:  # noqa: BLE001
        check("certificat HTTPS lisible", False, type(e).__name__)

    key = os.environ.get("HEALTHCHECKS_API_KEY", "")
    if key:
        api = os.environ.get("HEALTHCHECKS_API_URL", "https://healthchecks.io/api/v3/checks/")
        code, body = get(api, {"X-Api-Key": key})
        checks = [c for c in (json.loads(body).get("checks", []) if code == 200 else []) if "edusync" in c.get("name", "").lower()]
        check("signaux de vie externes trouvés (contrôles « EduSync »)", len(checks) >= 2, f"{len(checks)} trouvé(s), code {code}")
        for c in checks:
            check(f"signal « {c['name']} » reçu (état {c.get('status')})", c.get("status") == "up", f"dernier signal : {c.get('last_ping') or 'jamais'}")
    else:
        print("INFO  HEALTHCHECKS_API_KEY absente : signaux de vie externes non vérifiés ici (voir README §9)")

    fails = RESULTS.count(False)
    print(f"\n{len(RESULTS) - fails}/{len(RESULTS)} PASS · {fails} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
