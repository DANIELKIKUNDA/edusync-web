"""Select a main-branch build with complete, SHA-bound staging evidence."""
from __future__ import annotations

import argparse
import json
import re
import subprocess

REPO = "DANIELKIKUNDA/edusync-web"
SHA = re.compile(r"[0-9a-f]{40}")
EVIDENCE = (
    ("ci.yml", {"push"}, "Images Docker (amd64 + arm64) → GHCR", ()),
    ("deploy-staging.yml", {"workflow_run"}, "Staging — deploy <SHA> (commande forcée)",
     ("deploy <SHA>", "Vérification externe (HTTPS public)")),
    ("e2e-staging.yml", {"workflow_run", "workflow_dispatch"}, "Certification authentifiée plateforme et école",
     ("Parcours plateforme authentifié du SHA staging", "Parcours école authentifié du SHA staging dans Chromium")),
)


def gh(path: str):
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError("Lecture de l’API GitHub impossible.")
    return json.loads(out.stdout)


def runs(workflow: str, query: str) -> list[dict]:
    url = f"repos/{REPO}/actions/workflows/{workflow}/runs?branch=main&per_page=50&{query}"
    return gh(url)["workflow_runs"]


def has_evidence(sha: str) -> bool:
    for workflow, events, job_name, required_steps in EVIDENCE:
        eligible = [
            run for run in runs(workflow, f"head_sha={sha}")
            if run["event"] in events and run["head_sha"] == sha
            and run.get("head_repository", {}).get("full_name", "").lower() == REPO.lower()
        ]
        if not eligible or eligible[0]["conclusion"] != "success":
            return False
        run = eligible[0]
        jobs = gh(f"repos/{REPO}/actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs?per_page=100")["jobs"]
        if not any(job["name"] == job_name and job["conclusion"] == "success"
                   and set(required_steps) <= {s["name"] for s in job["steps"] if s["conclusion"] == "success"}
                   for job in jobs):
            return False
    return True


def select(requested: str | None) -> str:
    if requested and not SHA.fullmatch(requested):
        raise RuntimeError("SHA attendu : 40 caractères hexadécimaux minuscules.")
    if requested:
        candidates = [requested]
    else:
        candidates = dict.fromkeys(run["head_sha"] for run in runs("ci.yml", "event=push&status=success"))
    for sha in candidates:
        if SHA.fullmatch(sha) and has_evidence(sha):
            return sha
    raise RuntimeError("Aucun SHA avec CI, déploiement réel et deux parcours authentifiés réussis.")


def require_owner_approval(run_id: str, attempt: str) -> None:
    if not run_id.isdecimal() or attempt != "1":
        raise RuntimeError("Lancer une nouvelle exécution pour obtenir une approbation.")
    approvals = gh(f"repos/{REPO}/actions/runs/{run_id}/approvals")
    if not any(review["state"] == "approved"
               and review["user"]["login"].lower() == REPO.split("/")[0].lower()
               and any(env["name"] == "production" for env in review["environments"])
               for review in approvals):
        raise RuntimeError("Approbation explicite du propriétaire pour l’environnement production absente.")


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("sha", nargs="?")
    cli.add_argument("--approval", nargs=2, metavar=("RUN_ID", "ATTEMPT"))
    args = cli.parse_args()
    try:
        if args.approval:
            require_owner_approval(*args.approval)
        else:
            print(select(args.sha))
    except (RuntimeError, KeyError, ValueError) as exc:
        cli.exit(1, f"Refusé : {exc}\n")
