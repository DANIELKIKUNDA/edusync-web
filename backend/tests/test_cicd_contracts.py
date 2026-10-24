"""CI/CD contracts (CICD.md): CI gates, images by commit SHA, staging-only deployment, migrations, smoke tests,
rollback / safe stop, secrets referenced by name only."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CI = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
CD = (ROOT / ".github/workflows/deploy-staging.yml").read_text(encoding="utf-8")
CONTROLLER = (ROOT / "deploy/staging/privileged/deploy_controller.py").read_text(encoding="utf-8")
IMAGES = (ROOT / "deploy/staging/privileged/compose.staging.yml").read_text(encoding="utf-8")


def test_ci_runs_tests_typecheck_build_and_security_on_every_push_and_pr():
    assert "pull_request:" in CI and "branches: [main]" in CI and 'tags: ["edusync-*", "v*"]' in CI
    for gate in ("python -m pytest -q", "python -m compileall -q src", "npx tsc --noEmit", "npx vite build", "npm ci",
                 "pip-audit -r backend/requirements.lock", "npm audit --omit=dev", "tools/certification/supply_chain.py",
                 "tools/ci/secret_patterns.py", "pip install -c requirements.lock ."):
        assert gate in CI, gate
    assert 'python-version: "3.13"' in CI and 'node-version: "24"' in CI     # certified runtime versions


def test_images_are_built_only_after_ci_and_tagged_by_commit_sha():
    images = CI.split("  images:", 1)[1]
    assert "needs: [backend, rbac-contract, frontend, security]" in images  # + RBAC contract (2026-10-23)
    assert "linux/amd64,linux/arm64" in images and images.count("${{ github.sha }}") >= 3
    assert ":latest" not in CI
    for name in ("edusync-backend", "edusync-frontend", "edusync-backup"):
        assert name in images and name in CONTROLLER
    assert IMAGES.count("pull_policy: never") == 10           # the controller pulls by digest, compose never pulls


def test_deployment_is_staging_only_after_successful_ci():
    assert "environment: staging" in CD and "production" not in CD.split("jobs:", 1)[1].lower().replace("jamais de production", "")
    assert "workflows: [CI]" in CD and "github.event.workflow_run.conclusion == 'success'" in CD
    assert "cancel-in-progress: false" in CD                           # two deployments never overlap
    assert "EDUSYNC_ENV=staging (ce contrôleur ne déploie jamais la production)" in CONTROLLER   # the controller refuses production
    assert "Staging non configuré" in CD                               # no secret yet: clean stop, CI stays green


def test_secrets_are_referenced_by_name_and_never_echoed():
    referenced = set(re.findall(r"secrets\.([A-Z0-9_]+)", CD + CI))
    assert referenced == {"STAGING_SSH_HOST", "STAGING_SSH_USER", "STAGING_SSH_KEY", "STAGING_SSH_KNOWN_HOSTS", "GITHUB_TOKEN"}
    assert "StrictHostKeyChecking=yes" in CD and "rm -f ~/.ssh/staging_key" in CD
    assert "--password-stdin" in CONTROLLER and "shutil.rmtree(docker_config" in CONTROLLER   # registry token never in argv / kept on disk


def test_deploy_takes_backup_runs_migrations_smoke_tests_and_rolls_back_or_stops_safely():
    body = CONTROLLER.split("def deploy(self", 1)[1]
    order = [body.index(x) for x in ("self.preflight_config(", "self.pull_all(", "self.backup(old_env or new_env)", "\"up\", \"--detach\", \"--no-build\"", "self.smoke(new_env")]
    assert order == sorted(order)
    assert "SELECT version FROM schema_migrations" in CONTROLLER and "new_migrations" in body       # exact ledger, not a count
    assert "ledger_after != ledger_before" in body and "self.finish(EXIT_ROLLED_BACK" in body     # rollback only on an identical ledger
    assert '"stop", *APP_SERVICES' in body and "EXIT_SAFE_STOP," in body and "self.finish(EXIT_ROLLBACK_FAILED" in body
    for check in ("healthy", "migrateur en erreur", "assert_runtime_safe", "/health-api", "/api/v1/setup/status", "boucle de redémarrage"):
        assert check in CONTROLLER, check


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash absent")
def test_deploy_scripts_are_valid_bash():
    for script in ("deploy/staging/privileged/deploy-gate.sh", "deploy/staging/privileged/install_deploy_controller.sh", "deploy/backup/backup.sh"):
        r = subprocess.run(["bash", "-n", script], capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 0, (script, r.stderr)


def test_ci_secret_scanner_is_clean():
    import sys
    r = subprocess.run([sys.executable, str(ROOT / "tools/ci/secret_patterns.py")], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout[-500:]


def test_ci_never_installs_a_python_package_outside_the_lock():
    """Security audit 2026-10-24: the backend job re-installed pypdf==6.19.0 (11 CVE) over the locked 6.21.2 — the audits
    read the lock, not what the CI installs. Every package installed for the application or its tests is constrained
    by backend/requirements.lock; only the audit tool itself (pip-audit, pinned) is installed on its own."""
    import re
    lock = dict(line.strip().split("==", 1) for line in (ROOT / "backend" / "requirements.lock").read_text(encoding="utf-8").splitlines()
                if "==" in line and not line.lstrip().startswith("#"))
    lock = {k.lower(): v.split(";")[0].strip() for k, v in lock.items()}
    workflows = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / ".github" / "workflows").glob("*.yml"))
    for line in re.findall(r"^\s*pip install [^\n]+$", workflows, re.M):
        if "pip-audit==" in line or "--upgrade pip" in line:
            continue
        assert "-c requirements.lock" in line or "-c backend/requirements.lock" in line, line.strip()
        for name, version in re.findall(r"([A-Za-z0-9_.-]+)==([0-9][^\s]*)", line):
            assert lock.get(name.lower()) == version, f"{name}=={version} differs from the lock ({lock.get(name.lower())})"
