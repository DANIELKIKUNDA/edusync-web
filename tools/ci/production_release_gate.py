"""Porte de mise en production Coolify : une version ne part que si elle a réussi CI, déploiement staging et E2E staging.

Mêmes contrôles que .github/workflows/deploy-production.yml (job « gates »), à lancer AVANT de saisir
EDUSYNC_RELEASE_SHA dans Coolify. Ne change rien nulle part (lecture de l'API GitHub avec `gh`).

    python tools/ci/production_release_gate.py <SHA complet de 40 caractères>
Code 0 = version autorisée (affiche la valeur à saisir) ; 1 = refusée, avec la raison.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

REPO = "DANIELKIKUNDA/edusync-web"
WORKFLOWS = ("ci.yml", "deploy-staging.yml", "e2e-staging.yml")


def gh(path: str) -> dict:
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"Refusé : lecture GitHub impossible ({out.stderr.strip()[:200]})")
    return json.loads(out.stdout)


def succeeded(workflow: str, sha: str) -> bool:
    runs = gh(f"repos/{REPO}/actions/workflows/{workflow}/runs?head_sha={sha}&status=success&per_page=1")
    if runs.get("total_count", 0):
        return True
    # deploy-staging / e2e-staging lancés à la main tournent sur la branche par défaut : le SHA est dans leur titre.
    recent = gh(f"repos/{REPO}/actions/workflows/{workflow}/runs?status=success&per_page=50")
    return any(r.get("head_sha") == sha or sha in (r.get("display_title") or "") for r in recent.get("workflow_runs", []))


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not re.fullmatch(r"[0-9a-f]{40}", argv[1]):
        print("Usage : python tools/ci/production_release_gate.py <SHA complet, 40 caractères hexadécimaux>")
        return 1
    sha = argv[1]
    ok = True
    for wf in WORKFLOWS:
        good = succeeded(wf, sha)
        ok = ok and good
        print(f"{'PASS' if good else 'FAIL'}  {wf} réussi pour {sha[:8]}")
    if not ok:
        print("\nRefusé : cette version n'a pas passé toutes les étapes (CI, déploiement staging, E2E staging).")
        return 1
    print(f"\nAutorisé. Dans Coolify : EDUSYNC_RELEASE_SHA={sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
