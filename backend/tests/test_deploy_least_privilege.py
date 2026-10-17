"""Least-privilege staging deployment (CICD.md §2): forced command, root controller, installer — security tests.

The forced command is executed for real by bash with a fake sudo; the controller runs with injected I/O (GitHub API,
GHCR, docker) so every refusal and every positive path is exercised without touching a server."""
import importlib.util
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
PRIV = ROOT / "deploy/staging/privileged"
GATE = (PRIV / "deploy-gate.sh").read_text(encoding="utf-8")
INSTALLER = (PRIV / "install_deploy_controller.sh").read_text(encoding="utf-8")
CD = (ROOT / ".github/workflows/deploy-staging.yml").read_text(encoding="utf-8")
SHA = "2ad66ef309cf16a614d96ca20307254d2fc5a8b1"
PREV = "aed2305802c3959cc5c4434bc77d1ec89bf5909f"
TOKEN = "ghs_" + "A" * 36

spec = importlib.util.spec_from_file_location("deploy_controller", PRIV / "deploy_controller.py")
dc = importlib.util.module_from_spec(spec)
sys.modules["deploy_controller"] = dc
spec.loader.exec_module(dc)

BASH = shutil.which("bash")


# =============================================================== forced command (deploy-gate), real bash
def run_gate(tmp_path, command, stdin=TOKEN + "\n", extra_env=None):
    gate = GATE.replace("readonly SUDO=/usr/bin/sudo", "readonly SUDO=./fake_sudo")
    (tmp_path / "gate.sh").write_text(gate, encoding="utf-8", newline="\n")
    (tmp_path / "fake_sudo").write_text('#!/bin/bash\nprintf "%s\\n" "$@" > sudo_args.txt\ncat > sudo_stdin.txt\n', encoding="utf-8", newline="\n")
    (tmp_path / "fake_sudo").chmod(0o755)
    env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
    if command is not None:
        env["SSH_ORIGINAL_COMMAND"] = command
    env.update(extra_env or {})
    r = subprocess.run([BASH, "gate.sh"], cwd=tmp_path, input=stdin.encode(), capture_output=True, env=env, timeout=120)   # bytes: no CRLF
    r.stderr = r.stderr.decode("utf-8", "replace")
    args = (tmp_path / "sudo_args.txt").read_bytes().decode() if (tmp_path / "sudo_args.txt").exists() else None
    fed = (tmp_path / "sudo_stdin.txt").read_bytes().decode() if (tmp_path / "sudo_stdin.txt").exists() else None
    return r, args, fed


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_gate_accepts_exactly_deploy_full_sha_and_calls_only_the_controller(tmp_path):
    r, args, fed = run_gate(tmp_path, f"deploy {SHA}")
    assert r.returncode == 0, (r.returncode, r.stderr, args, fed)
    assert args.split() == ["-n", "/usr/local/libexec/edusync/deploy-controller"]      # no argument to the controller
    assert fed == f"{SHA}\n{TOKEN}\n"                                                  # data only through stdin


@pytest.mark.skipif(BASH is None, reason="bash absent")
@pytest.mark.parametrize("command", [
    None, "", "deploy", f"deploy {SHA[:7]}", f"deploy {SHA[:39]}", f"deploy {SHA}0", f"deploy {SHA.upper()}",
    f"deploy  {SHA}", f" deploy {SHA}", f"deploy {SHA} ", f"deploy {SHA} --project other", f"deploy {SHA} extra",
    f"deploy {SHA};id", f"deploy {SHA} && id", f"deploy {SHA} | sh", f"deploy $(id)", f"deploy `id`", f"deploy {SHA}\nid",
    f"deploy {SHA}\n", "bash", "sh -c id", "scp -t /tmp", "internal-sftp", f"rollback {SHA}", f"deploy ../../{SHA[:30]}",
    "deploy /etc/edusync-deploy/staging.env", f"DEPLOY {SHA}", f"deploy\t{SHA}",
])
def test_gate_refuses_everything_else(tmp_path, command):
    r, args, _ = run_gate(tmp_path, command)
    assert r.returncode == 64 and args is None, (command, r.returncode)


@pytest.mark.skipif(BASH is None, reason="bash absent")
@pytest.mark.parametrize("stdin", ["", "court\n", "tok en avec espaces " + "A" * 30 + "\n", "$(id)" + "A" * 30 + "\n", "A" * 400 + "\n"])
def test_gate_refuses_missing_or_malformed_token(tmp_path, stdin):
    r, args, _ = run_gate(tmp_path, f"deploy {SHA}", stdin=stdin)
    assert r.returncode == 64 and args is None


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_gate_ignores_hijacked_environment(tmp_path):
    evil = tmp_path / "evil"
    evil.mkdir()
    (evil / "sudo").write_text("#!/bin/bash\ntouch PWNED\n", encoding="utf-8", newline="\n")
    (evil / "sudo").chmod(0o755)
    r, args, _ = run_gate(tmp_path, f"deploy {SHA}", extra_env={"PATH": str(evil), "SUDO": str(evil / "sudo"), "CONTROLLER": "/bin/sh"})
    assert not (tmp_path / "PWNED").exists() and r.returncode == 0 and args is not None


def test_gate_never_executes_the_original_command():
    code = "\n".join(l for l in GATE.splitlines() if not l.lstrip().startswith("#"))
    assert "eval" not in code and 'exec "$request"' not in code and "$SSH_ORIGINAL_COMMAND" not in code.replace('"${SSH_ORIGINAL_COMMAND-}"', "")
    assert 'readonly SUDO=/usr/bin/sudo' in GATE and 'readonly CONTROLLER=/usr/local/libexec/edusync/deploy-controller' in GATE
    assert 'exec "$SUDO" -n "$CONTROLLER" <' in GATE


# =============================================================== controller: request parsing and policy
@pytest.mark.parametrize("raw", [b"", SHA.encode(), f"{SHA}\n".encode(), f"{SHA[:7]}\n{TOKEN}\n".encode(), f"{SHA}\n{TOKEN}\nextra\n".encode(),
                                 f"{SHA};id\n{TOKEN}\n".encode(), f"{SHA}\nbad token\n".encode(), b"x" * 2000, "é\n".encode()])
def test_controller_refuses_malformed_requests(raw):
    with pytest.raises(dc.Refused) as e:
        dc.parse_request(raw)
    assert e.value.code == dc.EXIT_USAGE


def test_controller_policy_is_fixed_in_code():
    assert dc.PROJECT == "edusync-staging" and dc.REPOSITORY == "DANIELKIKUNDA/edusync-web"
    assert dc.ALLOWED_IMAGES == ("edusync-backend", "edusync-frontend", "edusync-backup") and dc.IMAGE_NAMESPACE == "danielkikunda"
    for bad in ("edusync-backend:latest", "atelierpro-api", "../edusync-backend", "edusync-backend@sha256:x"):
        with pytest.raises(dc.Refused):
            dc.image_repository(bad)
    with pytest.raises(dc.Refused):
        dc.pinned_reference("edusync-backend", "latest")
    src = (PRIV / "deploy_controller.py").read_text(encoding="utf-8")
    assert "os.environ.get" not in src and "prune" not in src.split('"""', 2)[2]      # no env-driven policy, no prune
    assert "--password-stdin" in src and "shell=True" not in src
    assert dc.main(["deploy-controller", "extra"], io.BytesIO(b"")) == dc.EXIT_USAGE


# =============================================================== controller: simulated server
class FakeServer:
    """GitHub API + GHCR + docker compose of the project edusync-staging, all simulated."""
    def __init__(self, *, ci_ok=True, ci_ref="main", ci_path=".github/workflows/ci.yml", commit_ok=True, arm64=True, foreign_project=False,
                 running=True, smoke_ok=True, rollback_smoke_ok=True, new_migration=False, backup_ok=True, compose_up_ok=True):
        self.__dict__.update(locals())
        self.calls = []
        self.deployed = None
        self.ledger = ["0001_foundation", "0076_external_messaging"]

    def http(self, method, url, headers, timeout=30):
        assert "ghs_" not in url                                  # never a token in a URL
        if url.startswith("https://api.github.com/repos/DANIELKIKUNDA/edusync-web/commits/"):
            return (200, {}, json.dumps({"sha": SHA}).encode()) if self.commit_ok else (404, {}, b"")
        if "/actions/runs?head_sha=" in url:
            runs = [{"path": self.ci_path, "head_sha": SHA, "conclusion": "success" if self.ci_ok else "failure", "event": "push",
                     "head_branch": self.ci_ref, "head_repository": {"full_name": "DANIELKIKUNDA/edusync-web"}}]
            return 200, {}, json.dumps({"workflow_runs": runs}).encode()
        if url.startswith("https://ghcr.io/token?scope=repository:danielkikunda/"):
            return 200, {}, json.dumps({"token": "registry-bearer"}).encode()
        m = re.match(r"https://ghcr.io/v2/danielkikunda/(edusync-[a-z]+)/manifests/([0-9a-f]{40})$", url)
        if m:
            plats = [{"platform": {"os": "linux", "architecture": "amd64"}}] + ([{"platform": {"os": "linux", "architecture": "arm64"}}] if self.arm64 else [])
            digest = "sha256:" + (m.group(1).encode().hex() * 8)[:64]
            return 200, {"content-type": "application/vnd.oci.image.index.v1+json", "docker-content-digest": digest}, json.dumps({"manifests": plats}).encode()
        if url.startswith("http://127.0.0.1:8080"):
            ok = self.smoke_ok if self.deployed == "new" else self.rollback_smoke_ok
            body = {"/": b"<html>", "/health-api": b'{"status":"ok"}', "/api/v1/setup/status": b'{"setup_required":false}'}[url[21:]]
            return (200, {}, body) if ok else (502, {}, b"")
        raise AssertionError(f"URL inattendue {url}")

    def run(self, argv, env, stdin=None, timeout=1800):
        self.calls.append((list(argv), dict(env), stdin))
        assert argv[0] == "/usr/bin/docker" and "prune" not in argv
        assert env["PATH"] == dc.SAFE_PATH and "DOCKER_CONFIG" in env and set(env) <= {"PATH", "LANG", "HOME", "EDUSYNC_ENV_FILE", "COMPOSE_PROJECT_NAME",
                                                                                         "DOCKER_CONFIG", *dc.IMAGE_ENV.values()}
        if stdin is not None:
            assert TOKEN not in " ".join(argv)                   # the token only ever goes through stdin
        if argv[1] in ("login", "logout", "pull"):
            if argv[1] == "pull":
                assert re.fullmatch(r"ghcr.io/danielkikunda/edusync-(backend|frontend|backup)@sha256:[0-9a-f]{64}", argv[-1])
            return 0, ""
        assert argv[1] == "compose" and argv[2:6] == ["--project-name", "edusync-staging", "--project-directory", "/etc/edusync-deploy/compose"]
        assert "-f" in argv and argv[argv.index("-f") + 1].startswith("/etc/edusync-deploy/compose/")
        for name, var in dc.IMAGE_ENV.items():
            assert re.fullmatch(rf"ghcr.io/danielkikunda/{name}@sha256:[0-9a-f]{{64}}", env[var])
        sub = argv[argv.index("compose.digests.yml") + 1:] if "compose.digests.yml" in argv else argv[argv.index("/etc/edusync-deploy/compose/compose.digests.yml") + 1:]
        if sub[:1] == ["ps"]:
            if not self.running and self.deployed is None:
                return 0, ""
            healthy = (self.deployed == "new" and self.smoke_ok) or (self.deployed == "old" and self.rollback_smoke_ok) or self.deployed is None
            rows = [{"Service": s, "State": "running", "Project": "edusync-staging", "Health": "healthy" if healthy else "unhealthy"} for s in dc.ALL_SERVICES]
            rows.append({"Service": "migrator", "State": "exited", "ExitCode": 0, "Project": "edusync-staging"})
            if self.foreign_project:
                rows.append({"Service": "backend", "State": "exited", "Project": "atelierpro"})
            return 0, "\n".join(json.dumps(r) for r in rows)
        if sub[:3] == ["exec", "-T", "postgres"]:
            return 0, "\n".join(self.ledger)
        if sub[:3] == ["exec", "-T", "backup"]:
            if "once" in sub:
                return (0, "PASS sauvegarde 20261017T") if self.backup_ok else (1, "FAIL")
            return 0, json.dumps({"ok": True, "restore_verified": True})
        if sub[:3] == ["exec", "-T", "backend"]:
            return (0, "") if (self.smoke_ok if self.deployed == "new" else self.rollback_smoke_ok) else (1, "")
        if sub[:1] == ["up"]:
            new = env["EDUSYNC_BACKEND_IMAGE"].endswith(("sha256:" + ("edusync-backend".encode().hex() * 8)[:64]))
            self.deployed = "new" if (new and not getattr(self, "_rolled", False) and self.deployed != "new") else "old"
            if self.deployed == "new" and self.new_migration:
                self.ledger = self.ledger + ["0077_new_feature"]
            if self.deployed == "new" and not self.compose_up_ok:
                return 1, "error"
            return 0, ""
        if sub[:1] == ["stop"]:
            assert sub[1:] == list(dc.APP_SERVICES)
            return 0, ""
        raise AssertionError(f"commande docker inattendue {sub}")


def make_controller(tmp_path, server, *, previous=True, unsafe=None):
    for d in ("state", "log", "run"):
        (tmp_path / d).mkdir(exist_ok=True)
    paths = dc.Paths(state_dir=str(tmp_path / "state"), log_dir=str(tmp_path / "log"), run_dir=str(tmp_path / "run"))

    def fake_stat(p):
        if unsafe == p:
            return SimpleNamespace(st_uid=1001, st_mode=stat.S_IFREG | 0o755)
        if unsafe == "writable:" + p:
            return SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o775)
        return SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | (0o600 if p.endswith("staging.env") else 0o755))

    ctl = dc.Controller(paths=paths, http=server.http, run=server.run, stat_fn=fake_stat, sleep=lambda s: None)
    if previous:
        old = {n: "sha256:" + ("1" * 64) for n in dc.ALLOWED_IMAGES}
        ctl.write_state("current", {"sha": PREV, "digests": old, "ledger": list(server.ledger)})
    return ctl


ENV_TEXT = "EDUSYNC_ENV=staging\nEDUSYNC_TRUSTED_HOSTS=staging.edusync.test,localhost\n"


def deploy(tmp_path, server, **kw):
    ctl = make_controller(tmp_path, server, **kw)
    code = ctl.deploy(SHA, TOKEN, read_env=lambda: ENV_TEXT)
    state = {n: ctl.read_state(n) for n in ("current", "previous", "failed", "attempt")}
    return code, ctl, state


def test_positive_deploy_pins_digests_records_ledger_and_previous(tmp_path):
    s = FakeServer()
    code, ctl, st = deploy(tmp_path, s)
    assert code == dc.EXIT_OK and st["current"]["sha"] == SHA and st["previous"]["sha"] == PREV
    assert all(v.startswith("sha256:") for v in st["current"]["digests"].values()) and st["current"]["ledger"] == s.ledger
    order = [c[0][1] if c[0][1] != "compose" else c[0][c[0].index("/etc/edusync-deploy/compose/compose.digests.yml") + 1] for c in s.calls]
    assert order.index("login") < order.index("pull") < order.index("logout") < order.index("up")
    assert any("once" in c[0] for c in s.calls)                 # verified backup before the change
    assert not os.listdir(tmp_path / "run")                       # temporary DOCKER_CONFIG removed
    assert not any(TOKEN in line for line in ctl.log_lines)


@pytest.mark.parametrize("kw,expected", [
    ({"ci_ok": False}, "aucune CI réussie"), ({"ci_ref": "feature/x"}, "aucune CI réussie"), ({"ci_path": ".github/workflows/other.yml"}, "aucune CI réussie"),
    ({"commit_ok": False}, "n'appartient pas"), ({"arm64": False}, "sans linux/arm64"),
])
def test_verification_refusals_change_nothing(tmp_path, kw, expected):
    s = FakeServer(**kw)
    with pytest.raises(dc.Refused) as e:
        deploy(tmp_path, s)
    assert expected in str(e.value) and e.value.code == dc.EXIT_REFUSED
    assert not any(c[0][1] == "compose" for c in s.calls)           # no docker action at all


def test_backup_failure_aborts_before_any_change(tmp_path):
    s = FakeServer(backup_ok=False)
    with pytest.raises(dc.Refused) as e:
        deploy(tmp_path, s)
    assert e.value.code == dc.EXIT_FAILED and s.deployed is None
    assert not os.listdir(tmp_path / "run")


def test_failed_smoke_without_new_migration_rolls_back_to_previous_digests(tmp_path):
    s = FakeServer(smoke_ok=False)
    code, ctl, st = deploy(tmp_path, s)
    assert code == dc.EXIT_ROLLED_BACK and st["failed"]["rolled_back_to"] == PREV and st["failed"]["rollback_ok"]
    last_up = [c for c in s.calls if "up" in c[0]][-1]
    assert last_up[1]["EDUSYNC_BACKEND_IMAGE"].endswith("sha256:" + "1" * 64)     # previous digest, not a rebuild
    assert st["current"]["sha"] == PREV                                              # previous version stays current


def test_failed_smoke_after_new_migration_stops_safely_without_downgrade(tmp_path):
    s = FakeServer(smoke_ok=False, new_migration=True)
    code, ctl, st = deploy(tmp_path, s)
    assert code == dc.EXIT_SAFE_STOP and st["failed"]["safe_stop"] and st["failed"]["new_migrations"] == ["0077_new_feature"]
    assert len([c for c in s.calls if "up" in c[0]]) == 1                           # no rollback attempted
    assert any("stop" in c[0] for c in s.calls) and st["current"]["sha"] == PREV     # state and backup preserved


def test_first_deployment_failure_is_a_safe_stop(tmp_path):
    s = FakeServer(running=False, smoke_ok=False)
    code, _, st = deploy(tmp_path, s, previous=False)
    assert code == dc.EXIT_SAFE_STOP and st["current"] is None


def test_other_projects_are_ignored(tmp_path):
    s = FakeServer(foreign_project=True)
    code, ctl, _ = deploy(tmp_path, s)
    assert code == dc.EXIT_OK
    services = ctl.running_services(ctl.image_env(ctl.clean_env("x"), {n: "sha256:" + "2" * 64 for n in dc.ALLOWED_IMAGES}))
    assert services["backend"]["Project"] == "edusync-staging"


@pytest.mark.parametrize("target", ["/usr/local/libexec/edusync/deploy-controller", "/usr/local/libexec/edusync/deploy-gate",
                                    "/etc/edusync-deploy/compose/docker-compose.yml", "/etc/edusync-deploy/staging.env",
                                    "writable:/etc/edusync-deploy/compose/compose.digests.yml", "writable:/usr/local/libexec/edusync/deploy-controller"])
def test_controller_refuses_an_installation_modifiable_by_deploy(tmp_path, target):
    s = FakeServer()
    with pytest.raises(dc.Refused) as e:
        deploy(tmp_path, s, unsafe=target)
    assert e.value.code == dc.EXIT_UNSAFE and not s.calls


def test_controller_refuses_a_production_environment(tmp_path):
    ctl = make_controller(tmp_path, FakeServer())
    with pytest.raises(dc.Refused):
        ctl.deploy(SHA, TOKEN, read_env=lambda: "EDUSYNC_ENV=production\nEDUSYNC_TRUSTED_HOSTS=x.test\n")


@pytest.mark.skipif(not hasattr(os, "fork") or sys.platform == "win32", reason="flock Linux")
def test_two_deployments_never_run_concurrently(tmp_path):
    lock = str(tmp_path / "deploy.lock")
    first = dc.acquire_lock(lock)
    assert first is not None and dc.acquire_lock(lock) is None
    os.close(first)
    again = dc.acquire_lock(lock)
    assert again is not None
    os.close(again)


# =============================================================== installer and workflow
def test_installer_grants_one_sudo_rule_and_no_docker_group():
    assert 'deploy ALL=(root) NOPASSWD: $LIBEXEC/deploy-controller ""' in INSTALLER.replace("$DEPLOY_USER", "deploy")
    assert "visudo -cf" in INSTALLER and "env_reset, !setenv" in INSTALLER
    for forbidden in ("usermod -aG docker", "gpasswd -a", "NOPASSWD: ALL", "sshd_config", "systemctl restart ssh", "docker run", "docker exec", "chown deploy", "chmod 777"):
        assert forbidden not in INSTALLER.replace("gpasswd -d", ""), forbidden
    assert 'restrict,command=\\"$LIBEXEC/deploy-gate\\"' in INSTALLER and 'install -o root -g root -m 0644 "$TMP_AUTH" "$AUTH"' in INSTALLER
    assert 'install -o root -g root -m 0755 "$SRC/deploy/staging/privileged/deploy_controller.py" "$LIBEXEC/deploy-controller"' in INSTALLER
    assert 'install -d -o root -g root -m 0700 "$ETC"' in INSTALLER and 'install -d -o root -g root -m 0700 "$STATE"' in INSTALLER


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_privileged_scripts_are_valid_bash():
    for script in ("deploy/staging/privileged/deploy-gate.sh", "deploy/staging/privileged/install_deploy_controller.sh"):
        r = subprocess.run([BASH, "-n", script], capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 0, (script, r.stderr)


def test_workflow_only_sends_deploy_sha_with_strict_host_checking():
    assert '"deploy $SHA"' in CD and "StrictHostKeyChecking=yes" in CD and "BatchMode=yes" in CD
    for gone in ("scp ", "remote_deploy.sh", "/tmp/", "sftp", "docker compose", "actions/checkout"):
        assert gone not in CD, gone
    assert set(re.findall(r"secrets\.([A-Z0-9_]+)", CD)) == {"STAGING_SSH_HOST", "STAGING_SSH_USER", "STAGING_SSH_KEY", "STAGING_SSH_KNOWN_HOSTS", "GITHUB_TOKEN"}
    assert "environment: staging" in CD and "production" not in CD.split("jobs:", 1)[1]
