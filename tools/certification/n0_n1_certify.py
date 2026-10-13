"""EduSync N0/N1 certification runner (hardening L, 2026-10).

    python tools/certification/n0_n1_certify.py [--skip-resilience] [--skip-build]

Runs every automated check against the local isolated stack (it must be started: tools/local/edusync_local.py
start --profile demo) and writes CERTIFICATION_EVIDENCE_MANIFEST.md: commit SHA, environment and versions,
each command with its result and duration, and SHA-256 checksums of every evidence file. It never prints
secrets (they stay in .local/certification.env). A failing step is reported as FAIL: no global PASS is stated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVID = ROOT / "certification" / "n0-n1-20261007"
PY = ROOT / ".venv" / "Scripts" / "python.exe"
RUN = [str(PY), str(ROOT / ".local" / "closure" / "run.py")]
NPX = "npx.cmd" if os.name == "nt" else "npx"
NPM = "npm.cmd" if os.name == "nt" else "npm"
PROBES = ("prereq_probe.py", "team_probe.py", "school_lifecycle_probe.py", "health_probe.py", "audit_probe.py",
          "notifications_probe.py", "realtime_probe.py", "hardening_http_probe.py", "mfa_probe.py")


def run(cmd: list[str], cwd: Path = ROOT, env: dict | None = None, timeout: int = 1800) -> tuple[int, str, float]:
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return p.returncode, (p.stdout + p.stderr), time.time() - t0
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT", time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-resilience", action="store_true", help="do not stop PostgreSQL/Redis/S3/worker")
    ap.add_argument("--skip-build", action="store_true")
    a = ap.parse_args()
    probe_env = {"EDUSYNC_DB": "edusync_claude_fresh", "EDUSYNC_API_PORT": "58100", "PYTHONUTF8": "1"}
    steps: list[dict] = []
    # The tree is inspected BEFORE any step: the probes write their evidence files during the run, so a check made
    # afterwards would always see a modified tree and prove nothing about the code that was actually tested.
    start_sha = run(["git", "rev-parse", "HEAD"])[1].strip()
    start_dirty = sorted(line[3:] for line in run(["git", "status", "--porcelain"])[1].splitlines() if line.strip())
    steps.append({"step": "Arbre Git propre au démarrage", "command": "git status --porcelain", "result": "FAIL" if start_dirty else "PASS",
                  "summary": f"{len(start_dirty)} fichier(s) non commité(s)" if start_dirty else f"propre sur {start_sha[:12]}", "duration_s": 0})

    def step(name: str, cmd: list[str], ok_rule, cwd: Path = ROOT, env: dict | None = None, timeout: int = 1800, shown: str | None = None):
        code, out, dur = run(cmd, cwd, env, timeout)
        ok, summary = ok_rule(code, out)
        steps.append({"step": name, "command": shown or " ".join(Path(c).name if i == 0 else c for i, c in enumerate(cmd)), "result": "PASS" if ok else "FAIL",
                      "summary": summary, "duration_s": round(dur, 1)})
        print(f"{'PASS' if ok else 'FAIL'} {name} — {summary} ({dur:.0f} s)", flush=True)

    def tail_match(pattern: str):
        def rule(code, out):
            m = re.findall(pattern, out)
            last = m[-1] if m else (out.strip().splitlines()[-1][:160] if out.strip() else f"code {code}")
            score = re.search(r"(\d+)/(\d+) PASS", last)
            # Strict: a probe passes only when every one of its checks passed, whatever its exit code.
            return code == 0 and (score is None or score.group(1) == score.group(2)), last
        return rule

    step("Tests backend (pytest)", [str(PY), "-m", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp=../.local/pytest-tmp"],
         tail_match(r"\d+ passed[^\n]*"), cwd=ROOT / "backend", env={"PYTHONPATH": "src", "PYTHONUTF8": "1"})
    step("Compilation Python (compileall)", [str(PY), "-m", "compileall", "-q", "src"], lambda c, o: (c == 0, "OK" if c == 0 else o[-160:]), cwd=ROOT / "backend")
    step("Typecheck frontend (tsc)", [NPX, "tsc", "--noEmit", "-p", "tsconfig.json"], lambda c, o: (c == 0, "0 erreur" if c == 0 else o[-160:]), cwd=ROOT / "frontend")
    if not a.skip_build:
        step("Build frontend (vite)", [NPM, "run", "build"], lambda c, o: (c == 0 and "built in" in o, (re.findall(r"built in [^\n]+", o) or ["échec"])[-1]), cwd=ROOT / "frontend")
    step("Migrations sur base vierge (provisionnement)", RUN + ["backend/scripts/provision_database.py"],
         lambda c, o: (c == 0 and "PASS" in o, o.strip().splitlines()[-1][:120] if o.strip() else f"code {c}"), env={"EDUSYNC_DB": "edusync_closure_blank"})
    for probe in PROBES + (() if a.skip_resilience else ("resilience_probe.py",)):
        step(f"Sonde en conditions réelles : {probe}", RUN + [f"certification/n0-n1-20261007/{probe}"], tail_match(r"== \d+/\d+ PASS"), env=probe_env, timeout=2400)
    step("Sauvegarde + restauration vérifiée", [str(PY), "tools/local/backup_restore.py", "--db", "edusync_claude_fresh"], tail_match(r"== \d+/\d+ PASS[^\n]*"))
    step("Chaîne d'approvisionnement (licences, SBOM)", [str(PY), "tools/certification/supply_chain.py"], lambda c, o: (c == 0, o.strip().splitlines()[0] if o.strip() else "?"))
    step("Vulnérabilités npm (npm audit)", [NPM, "audit", "--omit=dev"], lambda c, o: (c == 0, (re.findall(r"found \d+ vulnerabilit\w+", o) or [o.strip()[-120:]])[-1]), cwd=ROOT / "frontend")
    step("Scan de secrets", [str(PY), ".local/closure/secret_scan.py"], lambda c, o: (c == 0 and " 0 leak" in o, o.strip().splitlines()[-1] if o.strip() else "?"))

    sha = start_sha
    if run(["git", "rev-parse", "HEAD"])[1].strip() != sha:
        steps.append({"step": "Commit inchangé pendant l'exécution", "command": "git rev-parse HEAD", "result": "FAIL", "summary": "HEAD a changé pendant la certification", "duration_s": 0})
    versions = {"OS": f"{platform.system()} {platform.release()} ({platform.version()})", "Python": platform.python_version(),
                "Node": run(["node", "--version"])[1].strip(), "PostgreSQL": run([r"C:\Program Files\PostgreSQL\16\bin\postgres.exe", "--version"])[1].strip(),
                "Redis (WSL)": run(["wsl.exe", "-d", "Ubuntu-22.04", "--", "redis-server", "--version"], timeout=90)[1].strip()[:60]}
    evid = sorted(p for p in EVID.iterdir() if p.is_file() and p.suffix in (".json", ".py", ".mjs"))
    passed = sum(s["result"] == "PASS" for s in steps)
    lines = ["# Manifeste de preuves — certification N0 / N1", "",
             f"Généré le {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} par `tools/certification/n0_n1_certify.py`.", "",
             f"* Commit : `{sha}`" + (" (arbre propre au démarrage : le code testé est exactement ce commit)" if not start_dirty
                                      else f" (ATTENTION : {len(start_dirty)} fichier(s) modifié(s) au démarrage : " + ", ".join(f"`{x}`" for x in start_dirty[:20]) + ")"),
             "* Environnement : instance locale isolée (PostgreSQL 16 RLS FORCE, Redis WSL, SeaweedFS S3, API FastAPI, interface Vite preview)",
             *[f"* {k} : {v}" for k, v in versions.items()], "",
             f"## Résultats : {passed}/{len(steps)} étapes PASS", "",
             "Aucune certification globale n'est prononcée par ce script : il consigne les résultats et les limites.", "",
             "| Étape | Commande | Résultat | Détail | Durée |", "|---|---|---|---|---|",
             *[f"| {s['step']} | `{s['command'][:90]}` | **{s['result']}** | {s['summary'].replace('|', '/')} | {s['duration_s']} s |" for s in steps], "",
             "## Fichiers de preuve (SHA-256)", "", "| Fichier | SHA-256 |", "|---|---|",
             *[f"| `{p.relative_to(ROOT).as_posix()}` | `{hashlib.sha256(p.read_bytes()).hexdigest()}` |" for p in evid], "",
             "Les secrets, sauvegardes et bases restent dans `.local/` (non versionné) et ne figurent dans aucun fichier de preuve.", ""]
    (ROOT / "CERTIFICATION_EVIDENCE_MANIFEST.md").write_text("\n".join(lines), encoding="utf-8")
    (EVID / "certify-run.json").write_text(json.dumps({"sha": sha, "clean_tree_at_start": not start_dirty, "modified_at_start": start_dirty,
                                                       "steps": steps, "versions": versions}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"== {passed}/{len(steps)} étapes PASS -> CERTIFICATION_EVIDENCE_MANIFEST.md")
    return 0 if passed == len(steps) else 1


if __name__ == "__main__":
    sys.exit(main())
