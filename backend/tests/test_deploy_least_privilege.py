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
@pytest.mark.parametrize("token", [TOKEN, "ghs_" + "Ab9-_." * 60, "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJyZXBvIn0.c2lnbmF0dXJl-_x"])
def test_gate_accepts_long_github_token_formats(tmp_path, token):
    r, args, fed = run_gate(tmp_path, f"deploy {SHA}", stdin=token + "\n")
    assert r.returncode == 0 and fed == f"{SHA}\n{token}\n", r.stderr
    assert dc.parse_request(fed.encode()) == (SHA, token)


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
@pytest.mark.parametrize("stdin", ["", "court\n", "tok en avec espaces " + "A" * 30 + "\n", "$(id)" + "A" * 30 + "\n", "A" * 5000 + "\n",
                                   "jeton;id" + "A" * 30 + "\n", "jeton`id`" + "A" * 30 + "\n", "jeton|sh" + "A" * 30 + "\n"])
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
                                 f"{SHA};id\n{TOKEN}\n".encode(), f"{SHA}\nbad token\n".encode(), b"x" * 5000, "é\n".encode()])
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


# =============================================================== controller: simulated Docker host + GitHub + GHCR
BASE_LEDGER = ["0001_foundation", "0076_external_messaging"]
OLD = {n: "sha256:" + "1" * 64 for n in dc.ALLOWED_IMAGES}
PLAT = ("linux", "arm64")


def new_digest(name):
    return "sha256:" + (name.encode().hex() * 8)[:64]


NEW = {n: new_digest(n) for n in dc.ALLOWED_IMAGES}


class FakeHost:
    """A Docker host (project edusync-staging + foreign containers), the GitHub API and GHCR, all simulated with state."""

    def __init__(self, *, existing=True, ci_ok=True, ci_ref="main", ci_path=".github/workflows/ci.yml", commit_ok=True, arm64=True,
                 host_arch=True, broken=(), backup="ok", ledger="ok", postgres_up=True, on_new_up=None, pull_fail=(),
                 foreign_ports=(), busy=(), unavailable=(), networks=(), config_patch=None):
        self.__dict__.update({k: v for k, v in locals().items() if k != "self"})
        self.calls, self.images, self.volumes, self.containers = [], set(), set(), {}
        self.db = None
        self.recorded_ledger = None
        if existing:                                   # a running staging deployed from the OLD digests
            self.images |= {dc.pinned_reference(n, OLD[n]) for n in dc.ALLOWED_IMAGES} | set(dc.INFRA_IMAGES.values())
            self.volumes = {"edusync-staging_postgres_data", "edusync-staging_backups"}
            self.db = list(BASE_LEDGER)
            self._start({**{dc.IMAGE_ENV[n]: dc.pinned_reference(n, OLD[n]) for n in dc.ALLOWED_IMAGES}})
            if not postgres_up:
                self.containers["postgres"]["State"] = "exited"
            if backup == "down":
                self.containers["backup"]["State"] = "exited"

    # ---------------------------------------------------------------- docker model
    def _start(self, env):
        backend = env["EDUSYNC_BACKEND_IMAGE"]
        healthy = backend not in {dc.pinned_reference("edusync-backend", d) for d in self.broken}
        for svc in dc.ALL_SERVICES:
            self.containers[svc] = {"Service": svc, "Project": "edusync-staging", "State": "running", "Image": backend if svc in dc.APP_SERVICES[:3] else svc,
                                    "Health": ("healthy" if healthy else "unhealthy") if svc == "backend" else "",
                                    "Publishers": [{"URL": "127.0.0.1", "PublishedPort": 18080, "TargetPort": 80}] if svc == "frontend" else []}
        self.containers["migrator"] = {"Service": "migrator", "Project": "edusync-staging", "State": "exited", "ExitCode": 0}

    def compose_config(self, env):
        services = {}
        for name, source in dc.SERVICE_IMAGE.items():
            if name == "tls-proxy":
                continue
            image = env[dc.IMAGE_ENV[source]] if source in dc.IMAGE_ENV else env[dc.INFRA_ENV[source]]
            svc = {"image": image, "volumes": [{"type": "volume", "source": "data", "target": "/data"}]}
            if name == "frontend":
                svc["ports"] = [{"mode": "ingress", "host_ip": "127.0.0.1", "target": 80, "published": "18080", "protocol": "tcp"}]
            if name == "object-storage":
                svc["volumes"].append({"type": "bind", "source": "/etc/edusync-deploy/compose/deploy/seaweedfs/entrypoint.sh", "target": "/deploy/entrypoint.sh"})
            services[name] = svc
        if self.config_patch:
            self.config_patch(services)
        return json.dumps({"name": "edusync-staging", "services": services})

    def run(self, argv, env, stdin=None, timeout=1800):
        self.calls.append((list(argv), dict(env), stdin))
        assert argv[0] == "/usr/bin/docker" and "prune" not in argv and "rm" not in argv[1:3]
        assert env["PATH"] == dc.SAFE_PATH and "DOCKER_CONFIG" in env
        assert set(env) <= {"PATH", "LANG", "HOME", "EDUSYNC_ENV_FILE", "COMPOSE_PROJECT_NAME", "DOCKER_CONFIG", "EDUSYNC_PUBLIC_BIND_ADDRESS",
                            *dc.IMAGE_ENV.values(), *dc.INFRA_ENV.values()}
        assert TOKEN not in " ".join(argv)                       # the token only ever goes through stdin
        cmd = argv[1]
        if cmd in ("login", "logout"):
            return 0, ""
        if cmd == "pull":
            assert argv[2:4] == ["--platform", "linux/arm64"]
            ref = argv[4]
            assert re.fullmatch(r"ghcr.io/danielkikunda/edusync-(backend|frontend|backup)@sha256:[0-9a-f]{64}", ref) or ref in dc.INFRA_IMAGES.values()
            if any(p in ref for p in self.pull_fail):
                return 1, "manifest unknown"
            self.images.add(ref)
            return 0, ""
        if cmd == "image":
            return (0, "linux/arm64\n") if argv[-1] in self.images else (1, "No such image")
        if cmd == "ps":                                          # read-only list of every container (port collisions)
            rows = [f"edusync-staging\t127.0.0.1:18080->80/tcp" for c in self.containers.values() if c.get("Publishers") and c["State"] == "running"]
            rows += [f"{proj}\t{ip}:{port}->{port}/tcp" for proj, ip, port in self.foreign_ports]
            return 0, "\n".join(rows)
        if cmd == "network":
            nets = [{"Name": "coolify", "Labels": {}, "IPAM": {"Config": [{"Subnet": "10.0.1.0/24"}]}}, *self.networks]
            return (0, "\n".join(f"id{i}" for i in range(len(nets)))) if argv[2] == "ls" else (0, json.dumps(nets))
        if cmd == "volume":
            assert argv[2:] == ["ls", "--quiet", "--filter", "label=com.docker.compose.project=edusync-staging"]
            return 0, "\n".join(sorted(self.volumes))
        assert cmd == "compose" and argv[2:6] == ["--project-name", "edusync-staging", "--project-directory", "/etc/edusync-deploy/compose"]
        files = [argv[i + 1] for i, a in enumerate(argv) if a == "-f"]
        assert files == ["/etc/edusync-deploy/compose/docker-compose.yml", "/etc/edusync-deploy/compose/compose.staging.yml"]
        for var in (*dc.IMAGE_ENV.values(), *dc.INFRA_ENV.values()):
            assert "@sha256:" in env[var] and ":latest" not in env[var]
        sub = argv[argv.index("/etc/edusync-deploy/compose/compose.staging.yml") + 1:]
        if sub[0] == "config":
            return 0, self.compose_config(env)
        if sub[0] == "ps":
            return 0, "\n".join(json.dumps(c) for c in self.containers.values())
        if sub[:3] == ["exec", "-T", "postgres"]:
            if (self.containers.get("postgres") or {}).get("State") != "running" or self.db is None:
                return 1, "service not running"
            mode = self.ledger
            if mode == "absent":
                return 1, 'ERROR:  relation "schema_migrations" does not exist'
            if mode == "empty":
                return 0, ""
            if mode == "garbage":
                return 0, "\n".join(self.db + ["0077 x;drop"])
            if mode == "duplicate":
                return 0, "\n".join(self.db + self.db[-1:])
            return 0, "\n".join(self.db)
        if sub[:3] == ["exec", "-T", "backup"]:
            if (self.containers.get("backup") or {}).get("State") != "running":
                return 1, "not running"
            if "once" in sub:
                return (0, "PASS sauvegarde 20261018T") if self.backup in ("ok", "unverified") else (1, "FAIL sauvegarde")
            return 0, json.dumps({"ok": True, "restore_verified": self.backup == "ok"})
        if sub[:3] == ["exec", "-T", "backend"]:
            return (0, "") if self.containers["backend"]["Health"] == "healthy" else (1, "")
        if sub[0] == "up":
            assert sub == ["up", "--detach", "--no-build", "--pull", "never", "--remove-orphans"]
            needed = {env[v] for v in (*dc.IMAGE_ENV.values(), *dc.INFRA_ENV.values()) if v != "EDUSYNC_TLS_PROXY_IMAGE"}
            if not needed <= self.images:
                return 1, "pull access denied (--pull never)"
            self.volumes |= {"edusync-staging_postgres_data", "edusync-staging_backups"}
            if self.db is None:
                self.db = list(BASE_LEDGER)
            self._start(env)
            if self.on_new_up and env["EDUSYNC_BACKEND_IMAGE"] == dc.pinned_reference("edusync-backend", NEW["edusync-backend"]):
                self.on_new_up(self)
            return 0, ""
        if sub[0] == "stop":
            assert sub[1:] == list(dc.APP_SERVICES)
            for svc in dc.APP_SERVICES:
                self.containers[svc]["State"] = "exited"
            return 0, ""
        raise AssertionError(f"commande docker inattendue {sub}")

    def probe(self, ip, port):
        if (ip, port) in self.unavailable:
            return "unavailable"
        if (ip, port) in self.busy:
            return "busy"
        ours = any(c.get("Publishers") and c["State"] == "running" for c in self.containers.values())
        return "busy" if ours and (ip, port) == ("127.0.0.1", 18080) else "free"

    # ---------------------------------------------------------------- GitHub + GHCR + smoke
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
            plats = ([{"platform": {"os": "linux", "architecture": "amd64"}}] +
                     ([{"platform": {"os": "linux", "architecture": "arm64"}}] if self.arm64 else []))
            return 200, {"content-type": "application/vnd.oci.image.index.v1+json", "docker-content-digest": new_digest(m.group(1))}, json.dumps({"manifests": plats}).encode()
        if url.startswith("http://127.0.0.1:18080"):
            ok = self.containers["backend"]["Health"] == "healthy" and self.containers["frontend"]["State"] == "running"
            body = {"/": b"<html>", "/health-api": b'{"status":"ok"}', "/api/v1/setup/status": b'{"setup_required":false}'}[url[22:]]
            return (200, {}, body) if ok else (502, {}, b"")
        raise AssertionError(f"URL inattendue {url}")


ENV_TEXT = "EDUSYNC_ENV=staging\nEDUSYNC_TRUSTED_HOSTS=staging.edusync.test,localhost\n"


def make_controller(tmp_path, host, *, previous=True, unsafe=None, plat=PLAT):
    for d in ("state", "log", "run"):
        (tmp_path / d).mkdir(exist_ok=True)
    paths = dc.Paths(state_dir=str(tmp_path / "state"), log_dir=str(tmp_path / "log"), run_dir=str(tmp_path / "run"))

    def fake_stat(p):
        if unsafe == p:
            return SimpleNamespace(st_uid=1001, st_mode=stat.S_IFREG | 0o755)
        if unsafe == "writable:" + p:
            return SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o775)
        return SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | (0o600 if p.endswith("staging.env") else 0o755))

    ctl = dc.Controller(paths=paths, http=host.http, run=host.run, stat_fn=fake_stat, sleep=lambda s: None, probe=host.probe, platform=plat)
    if previous and host.existing:
        ctl.write_state("current", {"sha": PREV, "digests": OLD, "ledger": list(BASE_LEDGER)})
        ctl.write_state("ledger", {"versions": list(BASE_LEDGER), "sha": PREV})
    return ctl


def deploy(tmp_path, host, env_text=ENV_TEXT, **kw):
    ctl = make_controller(tmp_path, host, **kw)
    code = ctl.deploy(SHA, TOKEN, read_env=lambda: env_text)
    state = {n: ctl.read_state(n) for n in ("current", "previous", "failed", "attempt", "ledger", "last_result")}
    return code, ctl, state


def ups(host):
    return [c for c in host.calls if c[0][1] == "compose" and "up" in c[0]]


def refused(tmp_path, host, code, *, env_text=ENV_TEXT, **kw):
    with pytest.raises(dc.Refused) as e:
        deploy(tmp_path, host, env_text=env_text, **kw)
    assert e.value.code == code, (e.value.code, str(e.value))
    assert not ups(host) and not any("stop" in c[0] for c in host.calls)        # nothing changed
    assert not os.listdir(tmp_path / "run")                                     # temporary DOCKER_CONFIG removed
    return str(e.value)


# ---------------------------------------------------------------- positive paths
def test_first_deployment_on_an_empty_docker_host_prepares_every_image_and_starts(tmp_path):
    host = FakeHost(existing=False)
    assert not host.images and not host.volumes                                  # no EduSync, PostgreSQL, Redis, SeaweedFS, edge image
    code, ctl, st = deploy(tmp_path, host)
    assert code == dc.EXIT_OK and st["last_result"]["verdict"] == "DEPLOY_SUCCESS"
    assert set(dc.INFRA_IMAGES.values()) <= host.images                          # infrastructure pulled by digest before up
    assert {dc.pinned_reference(n, NEW[n]) for n in dc.ALLOWED_IMAGES} <= host.images
    order = [c[0][1] if c[0][1] != "compose" else c[0][c[0].index("/etc/edusync-deploy/compose/compose.staging.yml") + 1] for c in host.calls]
    assert order.index("login") < order.index("pull") < order.index("logout") < order.index("image") < order.index("up")
    assert not any("once" in c[0] for c in host.calls)                          # pristine host: nothing to back up
    assert st["current"]["sha"] == SHA and st["ledger"]["versions"] == BASE_LEDGER and st["attempt"]["pristine"] is True
    assert any("hôte vierge reconnu" in line for line in ctl.log_lines)
    assert not os.listdir(tmp_path / "run") and not any(TOKEN in line for line in ctl.log_lines)


def test_redeploy_takes_a_verified_backup_and_keeps_previous_digests(tmp_path):
    host = FakeHost()
    code, _, st = deploy(tmp_path, host)
    assert code == dc.EXIT_OK and st["previous"]["sha"] == PREV and st["current"]["digests"] == NEW
    once = next(i for i, c in enumerate(host.calls) if "once" in c[0])
    assert once < host.calls.index(ups(host)[0])                                # backup before the change
    assert {dc.pinned_reference(n, OLD[n]) for n in dc.ALLOWED_IMAGES} <= host.images   # rollback target present


# ---------------------------------------------------------------- verification refusals
@pytest.mark.parametrize("kw,expected", [
    ({"ci_ok": False}, "aucune CI réussie"), ({"ci_ref": "feature/x"}, "aucune CI réussie"), ({"ci_path": ".github/workflows/other.yml"}, "aucune CI réussie"),
    ({"commit_ok": False}, "n'appartient pas"), ({"arm64": False}, "sans linux/arm64"),
])
def test_verification_refusals_change_nothing(tmp_path, kw, expected):
    host = FakeHost(**kw)
    assert expected in refused(tmp_path, host, dc.EXIT_REFUSED)
    assert not host.calls                                                        # not a single docker command


def test_host_platform_must_be_offered_by_the_images(tmp_path):
    host = FakeHost()
    assert "plateforme de cet hôte" in refused(tmp_path, host, dc.EXIT_REFUSED, plat=("linux", "riscv64"))
    with pytest.raises(dc.Refused):
        dc.native_platform("mips")
    assert dc.native_platform("aarch64") == ("linux", "arm64") and dc.native_platform("x86_64") == ("linux", "amd64")


# ---------------------------------------------------------------- infrastructure images
def test_infrastructure_images_are_allowlisted_pinned_and_cover_the_whole_compose():
    import yaml
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    override = yaml.safe_load((PRIV / "compose.staging.yml").read_text(encoding="utf-8").replace("!reset ", "").replace("!override", ""))
    assert set(compose["services"]) == set(dc.SERVICE_IMAGE) == set(override["services"])
    for name, svc in override["services"].items():
        source = dc.SERVICE_IMAGE[name]
        var = dc.IMAGE_ENV.get(source) or dc.INFRA_ENV[source]
        assert svc["image"] == "${%s:?set by the deploy controller}" % var and svc["pull_policy"] == "never"
    for service, ref in dc.INFRA_IMAGES.items():
        assert dc.infra_reference(service) == ref and ":latest" not in ref and dc.INFRA_REF_RE.match(ref)
        repo, tag = ref.split("@")[0].rsplit(":", 1)
        dev = compose["services"][service]["image"]                              # same image family as the canonical compose
        assert repo.endswith("/" + dev.split(":")[0]) and tag.split(".")[0] == dev.split(":")[1].split(".")[0].split("-")[0]
    with pytest.raises(dc.Refused):
        dc.infra_reference("atelierpro-db")


# ---------------------------------------------------------------- ports and network (VPS: Coolify 127.0.0.1:8000, Tailscale 100.x:443)
def no_ports(services):
    services["backend"]["ports"] = [{"host_ip": "127.0.0.1", "published": "8000", "target": 8000}]


def wildcard_edge(services):
    services["frontend"]["ports"] = [{"host_ip": "", "published": "443", "target": 80}]


def extra_service(services):
    services["atelierpro"] = {"image": "atelierpro:latest"}


def foreign_image(services):
    services["redis"]["image"] = "docker.io/library/redis:latest"


def host_mount(services):
    services["backend"]["volumes"] = [{"type": "bind", "source": "/var/run/docker.sock", "target": "/var/run/docker.sock"}]


def privileged(services):
    services["backup"]["privileged"] = True


@pytest.mark.parametrize("patch", [no_ports, wildcard_edge, extra_service, foreign_image, host_mount, privileged])
def test_unexpected_compose_configuration_is_refused(tmp_path, patch):
    refused(tmp_path, FakeHost(config_patch=patch), dc.EXIT_UNSAFE)


@pytest.mark.parametrize("kw", [
    {"foreign_ports": [("coolify", "127.0.0.1", 18080)]}, {"foreign_ports": [("other", "0.0.0.0", 18080)]},
    {"existing": False, "busy": [("127.0.0.1", 18080)]},
    {"networks": [{"Name": "atelierpro_default", "Labels": {"com.docker.compose.project": "atelierpro"}, "IPAM": {"Config": [{"Subnet": "172.30.0.0/16"}]}}]},
])
def test_ports_or_network_held_by_another_service_refuse_the_deployment(tmp_path, kw):
    refused(tmp_path, FakeHost(**kw), dc.EXIT_PORT)


def test_coolify_on_8000_and_tailscale_on_443_do_not_collide(tmp_path):
    host = FakeHost(foreign_ports=[("coolify", "127.0.0.1", 8000)], busy=[("100.120.8.56", 443), ("127.0.0.1", 8000)])
    code, _, _ = deploy(tmp_path, host)
    assert code == dc.EXIT_OK                                                    # our own 18080 is busy because it is ours


def tls_env(ip="203.0.113.7", domain="staging.myeducsync.com"):
    return ENV_TEXT + f"EDUSYNC_DEPLOY_TLS_PROFILE=true\nEDUSYNC_PUBLIC_BIND_ADDRESS={ip}\nEDUSYNC_DOMAIN={domain}\n"


@pytest.mark.parametrize("ip", ["0.0.0.0", "127.0.0.1", "100.120.8.56", "169.254.1.1", "::", "", "staging.myeducsync.com"])
def test_public_https_is_never_bound_to_a_wildcard_loopback_or_tailscale_address(tmp_path, ip):
    refused(tmp_path, FakeHost(), dc.EXIT_UNSAFE, env_text=tls_env(ip))


def test_edge_binds_80_443_on_the_public_interface_only(tmp_path):
    def with_edge(services):
        services["tls-proxy"] = {"image": dc.INFRA_IMAGES["tls-proxy"], "ports": [
            {"host_ip": "203.0.113.7", "published": "80", "target": 80}, {"host_ip": "203.0.113.7", "published": "443", "target": 443}]}
    host = FakeHost(config_patch=with_edge)
    ctl = make_controller(tmp_path, host)
    ctl.assert_staging_env(ctl.read_env_values(lambda: tls_env()))
    env = ctl.image_env(ctl.clean_env("x"), NEW)
    assert ctl.preflight_config(env) == [("127.0.0.1", 18080), ("203.0.113.7", 80), ("203.0.113.7", 443)] or \
        sorted(ctl.preflight_config(env)) == sorted([("127.0.0.1", 18080), ("203.0.113.7", 80), ("203.0.113.7", 443)])
    assert "--profile" in ctl.compose_argv("up") and env["EDUSYNC_PUBLIC_BIND_ADDRESS"] == "203.0.113.7"
    host.unavailable = [("203.0.113.7", 443)]
    with pytest.raises(dc.Refused) as e:
        ctl.preflight_ports(env, ctl.preflight_config(env))
    assert e.value.code == dc.EXIT_UNSAFE


def test_tls_profile_requires_a_domain(tmp_path):
    refused(tmp_path, FakeHost(), dc.EXIT_UNSAFE, env_text=tls_env(domain=""))


# ---------------------------------------------------------------- backup and ledger: fail closed
@pytest.mark.parametrize("mode,needle", [("down", "sauvegarde indisponible"), ("fail", "sauvegarde d'avant mise à jour en échec"),
                                         ("unverified", "sauvegarde non vérifiée")])
def test_backup_is_mandatory_on_an_existing_installation(tmp_path, mode, needle):
    assert needle in refused(tmp_path, FakeHost(backup=mode), dc.EXIT_BACKUP)


@pytest.mark.parametrize("kw", [{"postgres_up": False}, {"ledger": "absent"}, {"ledger": "empty"}, {"ledger": "garbage"}, {"ledger": "duplicate"}])
def test_ledger_is_mandatory_and_must_be_consistent_on_an_existing_installation(tmp_path, kw):
    refused(tmp_path, FakeHost(**kw), dc.EXIT_LEDGER)


def test_ledger_diverging_from_the_recorded_one_is_refused(tmp_path):
    host = FakeHost()
    host.db = BASE_LEDGER[:1]                                                    # someone removed a migration row
    assert "dernier registre enregistré" in refused(tmp_path, host, dc.EXIT_LEDGER)


def test_recorded_state_without_any_docker_resource_is_not_a_pristine_host(tmp_path):
    host = FakeHost(existing=False)
    ctl = make_controller(tmp_path, host)
    ctl.write_state("current", {"sha": PREV, "digests": OLD, "ledger": BASE_LEDGER})
    with pytest.raises(dc.Refused) as e:
        ctl.deploy(SHA, TOKEN, read_env=lambda: ENV_TEXT)
    assert e.value.code == dc.EXIT_LEDGER and not ups(host)


def test_existing_volumes_without_state_are_not_a_pristine_host(tmp_path):
    host = FakeHost()
    host.ledger = "absent"
    refused(tmp_path, host, dc.EXIT_LEDGER, previous=False)


def test_missing_previous_images_refuse_before_any_change(tmp_path):
    refused(tmp_path, FakeHost(pull_fail=["1111111111"]), dc.EXIT_FAILED)


# ---------------------------------------------------------------- rollback: exact ledger, exact verdict
def test_failed_smoke_with_identical_ledger_rolls_back_to_previous_digests(tmp_path):
    host = FakeHost(broken=[NEW["edusync-backend"]])
    code, _, st = deploy(tmp_path, host)
    assert code == dc.EXIT_ROLLED_BACK and st["last_result"]["verdict"] == "ROLLBACK_SUCCESS"
    assert st["failed"]["rolled_back_to"] == PREV and st["failed"]["rollback_ok"] is True
    assert ups(host)[-1][1]["EDUSYNC_BACKEND_IMAGE"].endswith(OLD["edusync-backend"])  # previous digest, no rebuild
    assert st["current"]["sha"] == PREV and host.containers["backend"]["Health"] == "healthy"


def test_failed_rollback_smoke_is_never_reported_as_a_successful_rollback(tmp_path):
    host = FakeHost(broken=[NEW["edusync-backend"], OLD["edusync-backend"]])
    code, _, st = deploy(tmp_path, host)
    assert code == dc.EXIT_ROLLBACK_FAILED and st["last_result"]["verdict"] == "ROLLBACK_FAILED"
    assert st["failed"]["rollback_ok"] is False and len(ups(host)) == 2
    assert all(host.containers[s]["State"] == "exited" for s in dc.APP_SERVICES)      # stopped safely, data kept


@pytest.mark.parametrize("change", [
    lambda h: h.db.append("0077_new_feature"),                 # new migration
    lambda h: h.db.remove("0001_foundation"),                  # deletion
    lambda h: h.db.__setitem__(1, "0076_external_messaging_v2"),  # modification
    lambda h: setattr(h, "ledger", "absent"),                  # unreadable after the change
])
def test_any_ledger_difference_after_a_failure_stops_safely_without_rollback(tmp_path, change):
    host = FakeHost(broken=[NEW["edusync-backend"]], on_new_up=change)
    code, _, st = deploy(tmp_path, host)
    assert code == dc.EXIT_SAFE_STOP and st["last_result"]["verdict"] == "SAFE_STOP_MIGRATION_CHANGED"
    assert len(ups(host)) == 1 and st["failed"]["safe_stop"] and st["current"]["sha"] == PREV
    assert all(host.containers[s]["State"] == "exited" for s in dc.APP_SERVICES)


def test_first_deployment_failure_is_a_safe_stop(tmp_path):
    host = FakeHost(existing=False, broken=[NEW["edusync-backend"]])
    code, _, st = deploy(tmp_path, host)
    assert code == dc.EXIT_SAFE_STOP_NO_TARGET and st["current"] is None
    assert st["last_result"]["verdict"] == "SAFE_STOP_NO_ROLLBACK_TARGET"


def test_verdicts_are_distinct_and_documented():
    assert len(set(dc.VERDICTS.values())) == len(dc.VERDICTS)
    doc = (ROOT / "CICD.md").read_text(encoding="utf-8")
    for code, name in dc.VERDICTS.items():
        assert f"| {code} | `{name}`" in doc, name


# ---------------------------------------------------------------- installation safety, environment, lock
@pytest.mark.parametrize("target", ["/usr/local/libexec/edusync/deploy-controller", "/usr/local/libexec/edusync/deploy-gate",
                                    "/etc/edusync-deploy/compose/docker-compose.yml", "/etc/edusync-deploy/staging.env",
                                    "writable:/etc/edusync-deploy/compose/compose.staging.yml", "writable:/usr/local/libexec/edusync/deploy-controller"])
def test_controller_refuses_an_installation_modifiable_by_deploy(tmp_path, target):
    host = FakeHost()
    refused(tmp_path, host, dc.EXIT_UNSAFE, unsafe=target)
    assert not host.calls


def test_controller_refuses_a_production_environment(tmp_path):
    refused(tmp_path, FakeHost(), dc.EXIT_UNSAFE, env_text="EDUSYNC_ENV=production\nEDUSYNC_TRUSTED_HOSTS=x.test\n")


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
    for forbidden in ("usermod -aG docker", "gpasswd -a", "NOPASSWD: ALL", "docker run", "docker exec", "chown deploy", "chmod 777", "PermitUserEnvironment yes"):
        assert forbidden not in INSTALLER.replace("gpasswd -d", ""), forbidden
    assert 'install -o root -g root -m 0755 "$SRC/deploy/staging/privileged/deploy_controller.py" "$LIBEXEC/deploy-controller"' in INSTALLER
    assert 'install -d -o root -g root -m 0700 "$ETC"' in INSTALLER and 'install -d -o root -g root -m 0700 "$STATE"' in INSTALLER


def test_installer_moves_the_key_to_a_root_owned_chain_with_a_scoped_sshd_dropin():
    assert re.findall(r"/etc/ssh/sshd_config(?![.]d)", INSTALLER) == []          # the main sshd_config is never touched
    assert "SSH_DROPIN=/etc/ssh/sshd_config.d/edusync-deploy.conf" in INSTALLER and "Match User $DEPLOY_USER" in INSTALLER
    for directive in ("AuthorizedKeysFile $SSH_KEYS", "ForceCommand $LIBEXEC/deploy-gate", "PermitTTY no", "DisableForwarding yes",
                      "PermitUserRC no", "AuthenticationMethods publickey", "PermitOpen none"):
        assert "\t" + directive + "\n" in INSTALLER, directive
    assert 'restrict,command=\\"$LIBEXEC/deploy-gate\\"' in INSTALLER and 'install -o root -g root -m 0644 "$TMP_AUTH" "$SSH_KEYS"' in INSTALLER
    assert 'chown root:root "$HOME_DIR"' in INSTALLER and '"$SSHD" -t' in INSTALLER
    assert 'rollback_dropin "le drop-in modifierait la configuration SSH de $u' in INSTALLER        # other accounts unchanged
    assert "sort -V -C" in INSTALLER and "#!/usr/bin/python3 -IS" in INSTALLER


def test_controller_shebang_is_a_single_linux_argument():
    first = (PRIV / "deploy_controller.py").read_text(encoding="utf-8").splitlines()[0]
    assert first == "#!/usr/bin/python3 -IS"                                    # Linux passes "-IS" as ONE argument
    r = subprocess.run([sys.executable, "-IS", "-c", "import sys; print(sys.flags.isolated, sys.flags.no_site)"], capture_output=True, text=True)
    assert r.stdout.split() == ["1", "1"]


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


def test_real_linux_certification_runs_in_ci_and_after_ci():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    cert = (ROOT / ".github/workflows/cd-certification.yml").read_text(encoding="utf-8")
    assert "bash tools/ci/cd_linux/privileged_checks.sh" in ci and "runs-on: ubuntu-24.04" in ci.split("cd-privileged:", 1)[1]
    assert "workflows: [CI]" in cert and "bash tools/ci/cd_linux/stack_scenarios.sh" in cert and "packages: read" in cert
    assert "git diff --quiet \"$c\" \"$CUR_SHA\" -- backend/migrations" in cert
    checks = (ROOT / "tools/ci/cd_linux/privileged_checks.sh").read_text(encoding="utf-8")
    for probe in ("renommer ~/.ssh", "remplacer ~/.ssh", "remplacer authorized_keys", "lien symbolique", "clé plantée dans ~/.ssh ignorée",
                  "/usr/bin/python3 -IS /usr/local/libexec/edusync/deploy-controller", "mode isolé (-I)", "sans site (-S)",
                  "second déploiement pendant un déploiement", "argument supplémentaire", "scp refusé", "sftp refusé"):
        assert probe in checks, probe
    stack = (ROOT / "tools/ci/cd_linux/stack_scenarios.sh").read_text(encoding="utf-8")
    for scenario in ("Hôte Docker vierge", "refus PORT_CONFLICT", "verdict ROLLBACK_SUCCESS", "refus BACKUP_REQUIRED_FAILED",
                     "registre divergent", "registre illisible", "registre absent", "verdict ROLLBACK_FAILED", "témoin Coolify intact"):
        assert scenario in stack, scenario
