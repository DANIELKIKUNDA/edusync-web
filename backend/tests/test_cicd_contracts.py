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
IMAGES = (ROOT / "deploy/staging/privileged/compose.digests.yml").read_text(encoding="utf-8")


def test_ci_runs_tests_typecheck_build_and_security_on_every_push_and_pr():
    assert "pull_request:" in CI and "branches: [main]" in CI and 'tags: ["edusync-*", "v*"]' in CI
    for gate in ("python -m pytest -q", "python -m compileall -q src", "npx tsc --noEmit", "npx vite build", "npm ci",
                 "pip-audit -r backend/requirements.lock", "npm audit --omit=dev", "tools/certification/supply_chain.py",
                 "tools/ci/secret_patterns.py", "pip install -c requirements.lock ."):
        assert gate in CI, gate
    assert 'python-version: "3.13"' in CI and 'node-version: "24"' in CI     # certified runtime versions


def test_images_are_built_only_after_ci_and_tagged_by_commit_sha():
    images = CI.split("  images:", 1)[1]
    assert "needs: [backend, frontend, security]" in images
    assert "linux/amd64,linux/arm64" in images and images.count("${{ github.sha }}") >= 3
    assert ":latest" not in CI
    for name in ("edusync-backend", "edusync-frontend", "edusync-backup"):
        assert name in images and name in CONTROLLER
    assert IMAGES.count("pull_policy: never") == 6           # the controller pulls by digest, compose never pulls


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
    order = [body.index(x) for x in ("docker, \"pull\"", "self.backup(old_env)", "\"up\", \"--detach\", \"--no-build\"", "self.smoke(new_env")]
    assert order == sorted(order)
    assert "SELECT version FROM schema_migrations" in CONTROLLER and "new_migrations" in body       # exact ledger, not a count
    assert "not new_migrations" in body and "return EXIT_ROLLED_BACK" in body                     # automatic rollback
    assert '"stop", *APP_SERVICES' in body and "return EXIT_SAFE_STOP" in body                    # safe stop
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
