#!/usr/bin/python3 -I -S
"""EduSync staging deployment controller — runs as root through ONE sudoers rule (CICD.md §2).

Installed administratively (install_deploy_controller.sh) as /usr/local/libexec/edusync/deploy-controller,
root-owned, mode 0755. It never changes with an application commit: infrastructure (compose files, mounted
configuration, staging.env, state, logs) lives under root-owned paths and is reinstalled only by an administrator.

Input  : stdin only, at most 1 KiB, exactly two lines — the full 40-hex commit SHA, then the ephemeral GitHub token of
         the deployment run (read the CI result, pull the images). No argument is accepted.
Checks : SHA syntax; commit of DANIELKIKUNDA/edusync-web; workflow .github/workflows/ci.yml run on a push of main or a
         tag edusync-* concluded success for that exact SHA; images only from the three allowed GHCR repositories,
         tagged with the SHA, offering linux/arm64, resolved to digests.
Steps  : lock → verify → pull by digest (temporary DOCKER_CONFIG, deleted in every case) → verified backup → record
         previous SHA, digests and exact migration ledger → compose up (project edusync-staging only) → smoke tests →
         PASS keep | FAIL: no new migration → automatic rollback to previous digests; new migration → safe stop.
Never  : arbitrary compose / project / image / path, docker prune, actions on non-EduSync resources, token in argv or logs.
Exit   : 0 deployed, 2 refused + rolled back, 3 refused + safe stop, 64 invalid request, 65 verification refused,
         70 failure before any change, 75 another deployment in progress, 78 unsafe installation.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

# ------------------------------------------------------------------ fixed policy (never read from the environment)
REPOSITORY = "DANIELKIKUNDA/edusync-web"
CI_WORKFLOW_PATH = ".github/workflows/ci.yml"
PROJECT = "edusync-staging"
REGISTRY = "ghcr.io"
IMAGE_NAMESPACE = "danielkikunda"
ALLOWED_IMAGES = ("edusync-backend", "edusync-frontend", "edusync-backup")
IMAGE_ENV = {"edusync-backend": "EDUSYNC_BACKEND_IMAGE", "edusync-frontend": "EDUSYNC_FRONTEND_IMAGE", "edusync-backup": "EDUSYNC_BACKUP_IMAGE"}
REQUIRED_PLATFORM = ("linux", "arm64")
APP_SERVICES = ("backend", "outbox-worker", "communications-worker", "frontend")
ALL_SERVICES = ("postgres", "redis", "object-storage", "backend", "outbox-worker", "communications-worker", "frontend", "backup")
SAFE_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"
SHA_RE = re.compile(r"\A[0-9a-f]{40}\Z")
TOKEN_RE = re.compile(r"\A[A-Za-z0-9_]{20,255}\Z")
DIGEST_RE = re.compile(r"\Asha256:[0-9a-f]{64}\Z")
VERSION_RE = re.compile(r"\A[0-9A-Za-z_]{1,128}\Z")
MAX_STDIN = 1024
INDEX_TYPES = ("application/vnd.oci.image.index.v1+json", "application/vnd.docker.distribution.manifest.list.v2+json")

EXIT_OK, EXIT_ROLLED_BACK, EXIT_SAFE_STOP = 0, 2, 3
EXIT_USAGE, EXIT_REFUSED, EXIT_FAILED, EXIT_BUSY, EXIT_UNSAFE = 64, 65, 70, 75, 78


class Refused(Exception):
    """Request refused before any change (exit 64 / 65 / 78)."""
    def __init__(self, message: str, code: int = EXIT_REFUSED):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Paths:
    controller: str = "/usr/local/libexec/edusync/deploy-controller"
    gate: str = "/usr/local/libexec/edusync/deploy-gate"
    etc: str = "/etc/edusync-deploy"
    compose_dir: str = "/etc/edusync-deploy/compose"
    env_file: str = "/etc/edusync-deploy/staging.env"
    state_dir: str = "/var/lib/edusync-deploy"
    log_dir: str = "/var/log/edusync-deploy"
    lock_file: str = "/run/edusync-deploy.lock"
    run_dir: str = "/run/edusync-deploy"
    docker: str = "/usr/bin/docker"

    @property
    def compose_files(self) -> tuple[str, str]:
        return (f"{self.compose_dir}/docker-compose.yml", f"{self.compose_dir}/compose.digests.yml")


# ------------------------------------------------------------------ input
def parse_request(raw: bytes) -> tuple[str, str]:
    if len(raw) > MAX_STDIN:
        raise Refused("requête trop longue", EXIT_USAGE)
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise Refused("requête non ASCII", EXIT_USAGE) from exc
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    if len(lines) != 2:
        raise Refused("la requête doit contenir exactement le SHA puis le jeton", EXIT_USAGE)
    sha, token = lines
    if not SHA_RE.match(sha):
        raise Refused("SHA invalide : 40 caractères hexadécimaux minuscules attendus", EXIT_USAGE)
    if not TOKEN_RE.match(token):
        raise Refused("jeton de registre invalide", EXIT_USAGE)
    return sha, token


def image_repository(name: str) -> str:
    if name not in ALLOWED_IMAGES:
        raise Refused(f"image non autorisée : {name}")
    return f"{IMAGE_NAMESPACE}/{name}"


def pinned_reference(name: str, digest: str) -> str:
    if not DIGEST_RE.match(digest or ""):
        raise Refused(f"digest invalide pour {name}")
    return f"{REGISTRY}/{image_repository(name)}@{digest}"


# ------------------------------------------------------------------ default I/O (replaced in tests)
def _http(method: str, url: str, headers: dict[str, str], timeout: int = 30) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — fixed https hosts only
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(4 * 1024 * 1024)
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, b""


def _run(argv: list[str], env: dict[str, str], stdin: bytes | None = None, timeout: int = 1800) -> tuple[int, str]:
    p = subprocess.run(argv, input=stdin, env=env, capture_output=True, timeout=timeout, check=False)
    return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")


@dataclass
class Controller:
    paths: Paths = field(default_factory=Paths)
    http: object = _http
    run: object = _run
    stat_fn: object = os.stat
    sleep: object = time.sleep
    expected_uid: int = 0
    tls_profile: bool = False
    log_lines: list[str] = field(default_factory=list)

    # -------------------------------------------------------------- environment & installation safety
    def clean_env(self, docker_config: str | None = None) -> dict[str, str]:
        env = {"PATH": SAFE_PATH, "LANG": "C.UTF-8", "HOME": "/nonexistent", "EDUSYNC_ENV_FILE": self.paths.env_file,
               "COMPOSE_PROJECT_NAME": PROJECT}
        if docker_config:
            env["DOCKER_CONFIG"] = docker_config
        return env

    def assert_installation_safe(self) -> None:
        """Everything root executes or reads must be root-owned and not writable by group / others."""
        for path in (self.paths.controller, self.paths.gate, self.paths.etc, self.paths.compose_dir, self.paths.env_file,
                     *self.paths.compose_files, self.paths.state_dir, self.paths.log_dir):
            try:
                st = self.stat_fn(path)
            except FileNotFoundError as exc:
                raise Refused(f"installation incomplète : {path}", EXIT_UNSAFE) from exc
            if st.st_uid != self.expected_uid:
                raise Refused(f"installation non sûre : {path} n'appartient pas à root", EXIT_UNSAFE)
            if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                raise Refused(f"installation non sûre : {path} modifiable par un autre compte que root", EXIT_UNSAFE)
        env_mode = self.stat_fn(self.paths.env_file).st_mode
        if env_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise Refused("installation non sûre : staging.env lisible par un autre compte que root", EXIT_UNSAFE)

    def assert_staging_env(self, read_env=None) -> None:
        text = read_env() if read_env else open(self.paths.env_file, encoding="utf-8").read()
        values = dict(line.split("=", 1) for line in text.splitlines() if "=" in line and not line.lstrip().startswith("#"))
        if values.get("EDUSYNC_ENV") != "staging":
            raise Refused("staging.env doit contenir EDUSYNC_ENV=staging (ce contrôleur ne déploie jamais la production)", EXIT_UNSAFE)
        # Public TLS by the Caddy service of the installed compose only when the administrator asked for it.
        self.tls_profile = values.get("EDUSYNC_DEPLOY_TLS_PROFILE") == "true"

    # -------------------------------------------------------------- GitHub verification
    def verify_commit_and_ci(self, sha: str, token: str) -> str:
        h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
             "User-Agent": "edusync-deploy-controller"}
        code, _, body = self.http("GET", f"https://api.github.com/repos/{REPOSITORY}/commits/{sha}", h)
        if code != 200 or json.loads(body or b"{}").get("sha") != sha:
            raise Refused("ce SHA n'appartient pas au dépôt EduSync attendu")
        code, _, body = self.http("GET", f"https://api.github.com/repos/{REPOSITORY}/actions/runs?head_sha={sha}&event=push&status=success&per_page=50", h)
        if code != 200:
            raise Refused("résultat de la CI illisible")
        for run in json.loads(body or b"{}").get("workflow_runs", []):
            ref = run.get("head_branch") or ""
            if (run.get("path") == CI_WORKFLOW_PATH and run.get("head_sha") == sha and run.get("conclusion") == "success"
                    and run.get("event") == "push" and (run.get("head_repository") or {}).get("full_name") == REPOSITORY
                    and (ref == "main" or ref.startswith("edusync-"))):
                return ref
        raise Refused("aucune CI réussie sur main ou un tag edusync-* pour ce SHA")

    # -------------------------------------------------------------- GHCR: digests and platform
    def resolve_digests(self, sha: str, token: str) -> dict[str, str]:
        basic = base64.b64encode(f"edusync-deploy:{token}".encode()).decode()
        digests = {}
        for name in ALLOWED_IMAGES:
            repo = image_repository(name)
            code, _, body = self.http("GET", f"https://{REGISTRY}/token?scope=repository:{repo}:pull&service={REGISTRY}",
                                      {"Authorization": f"Basic {basic}", "User-Agent": "edusync-deploy-controller"})
            bearer = json.loads(body or b"{}").get("token") if code == 200 else None
            if not bearer:
                raise Refused(f"accès refusé au registre pour {name}")
            code, headers, body = self.http("GET", f"https://{REGISTRY}/v2/{repo}/manifests/{sha}",
                                            {"Authorization": f"Bearer {bearer}", "Accept": ", ".join(INDEX_TYPES),
                                             "User-Agent": "edusync-deploy-controller"})
            if code != 200:
                raise Refused(f"image {name}:{sha} introuvable dans le registre autorisé")
            if headers.get("content-type", "").split(";")[0] not in INDEX_TYPES:
                raise Refused(f"image {name} : index multi-architecture attendu")
            index = json.loads(body or b"{}")
            platforms = {((m.get("platform") or {}).get("os"), (m.get("platform") or {}).get("architecture")) for m in index.get("manifests", [])}
            if REQUIRED_PLATFORM not in platforms:
                raise Refused(f"image {name} sans linux/arm64")
            digest = headers.get("docker-content-digest", "")
            if not DIGEST_RE.match(digest):
                raise Refused(f"digest absent pour {name}")
            digests[name] = digest
        return digests

    # -------------------------------------------------------------- docker (project edusync-staging only)
    def compose_argv(self, *args: str) -> list[str]:
        argv = [self.paths.docker, "compose", "--project-name", PROJECT, "--project-directory", self.paths.compose_dir,
                "--env-file", self.paths.env_file]
        if self.tls_profile:
            argv += ["--profile", "tls"]
        for f in self.paths.compose_files:
            argv += ["-f", f]
        return argv + list(args)

    def compose(self, env: dict[str, str], *args: str, stdin: bytes | None = None, timeout: int = 1800) -> tuple[int, str]:
        return self.run(self.compose_argv(*args), env, stdin, timeout)

    def image_env(self, base: dict[str, str], digests: dict[str, str]) -> dict[str, str]:
        env = dict(base)
        for name in ALLOWED_IMAGES:
            env[IMAGE_ENV[name]] = pinned_reference(name, digests[name])
        return env

    def running_services(self, env: dict[str, str]) -> dict[str, dict]:
        code, out = self.compose(env, "ps", "--all", "--format", "json")
        if code != 0:
            return {}
        rows = []
        for line in out.strip().splitlines():
            line = line.strip()
            if not line.startswith("{") and not line.startswith("["):
                continue
            data = json.loads(line)
            rows.extend(data if isinstance(data, list) else [data])
        return {r.get("Service"): r for r in rows if r.get("Project", PROJECT) == PROJECT}

    def migration_ledger(self, env: dict[str, str]) -> list[str] | None:
        code, out = self.compose(env, "exec", "-T", "postgres", "sh", "-c",
                                 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT version FROM schema_migrations ORDER BY version"')
        if code != 0:
            return None
        versions = [v.strip() for v in out.splitlines() if v.strip()]
        if not all(VERSION_RE.match(v) for v in versions):
            raise Refused("registre des migrations illisible")
        return versions

    def backup(self, env: dict[str, str]) -> None:
        code, out = self.compose(env, "exec", "-T", "backup", "sh", "/usr/local/bin/edusync-backup", "once", timeout=3600)
        if code != 0 or "PASS sauvegarde" not in out:
            raise Refused("sauvegarde d'avant mise à jour en échec : déploiement annulé, rien n'a changé", EXIT_FAILED)
        code, out = self.compose(env, "exec", "-T", "backup", "cat", "/backup-status/last.json")
        status = json.loads(out or "{}") if code == 0 else {}
        if not (status.get("ok") is True and status.get("restore_verified") is True):
            raise Refused("sauvegarde non vérifiée : déploiement annulé, rien n'a changé", EXIT_FAILED)

    def smoke(self, env: dict[str, str], host_header: str) -> tuple[bool, str]:
        for _ in range(60):
            services = self.running_services(env)
            if (services.get("backend") or {}).get("Health") == "healthy":
                break
            self.sleep(5)
        services = self.running_services(env)
        if (services.get("backend") or {}).get("Health") != "healthy":
            return False, "API non saine"
        mig = services.get("migrator") or {}
        if mig.get("ExitCode", 1) != 0:
            return False, "migrateur en erreur"
        for svc in ALL_SERVICES:
            if (services.get(svc) or {}).get("State") != "running":
                return False, f"service {svc} arrêté"
        self.sleep(20)
        services = self.running_services(env)
        for svc in APP_SERVICES:
            if (services.get(svc) or {}).get("State") != "running":
                return False, f"service {svc} en boucle de redémarrage"
        code, _ = self.compose(env, "exec", "-T", "backend", "python", "-c",
                               "from edusync.bootstrap.settings import Settings;s=Settings();s.assert_runtime_safe();assert s.env=='staging'")
        if code != 0:
            return False, "contrôles de sécurité staging"
        for path, needle in (("/", b"<"), ("/health-api", b"ok"), ("/api/v1/setup/status", b"setup_required")):
            code, _, body = self.http("GET", f"http://127.0.0.1:8080{path}", {"Host": host_header, "User-Agent": "edusync-deploy-controller"})
            if code != 200 or needle not in body:
                return False, f"HTTP {path} : {code}"
        return True, "smoke tests PASS"

    # -------------------------------------------------------------- state & log (root-owned)
    def read_state(self, name: str) -> dict | None:
        try:
            with open(os.path.join(self.paths.state_dir, f"{name}.json"), encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None

    def write_state(self, name: str, data: dict) -> None:
        final = os.path.join(self.paths.state_dir, f"{name}.json")
        fd, tmp = tempfile.mkstemp(dir=self.paths.state_dir, prefix=f".{name}.")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        os.replace(tmp, final)

    def log(self, message: str) -> None:
        line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {message}"
        self.log_lines.append(line)
        print(line, flush=True)
        try:
            with open(os.path.join(self.paths.log_dir, "deploy.log"), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def host_header(self, read_env=None) -> str:
        text = read_env() if read_env else open(self.paths.env_file, encoding="utf-8").read()
        for line in text.splitlines():
            if line.startswith("EDUSYNC_TRUSTED_HOSTS="):
                host = line.split("=", 1)[1].split(",")[0].strip()
                if re.fullmatch(r"[A-Za-z0-9.-]{1,253}", host):
                    return host
        raise Refused("EDUSYNC_TRUSTED_HOSTS absent de staging.env", EXIT_UNSAFE)

    # -------------------------------------------------------------- the deployment
    def deploy(self, sha: str, token: str, read_env=None) -> int:
        self.assert_installation_safe()
        self.assert_staging_env(read_env)
        host = self.host_header(read_env)
        ref = self.verify_commit_and_ci(sha, token)
        digests = self.resolve_digests(sha, token)
        self.log(f"Demande {sha} ({ref}) vérifiée : CI réussie, images arm64 {', '.join(f'{k}@{v[:19]}' for k, v in digests.items())}")
        previous = self.read_state("current")
        os.makedirs(self.paths.run_dir, mode=0o700, exist_ok=True)
        docker_config = tempfile.mkdtemp(prefix="docker-", dir=self.paths.run_dir)
        try:
            os.chmod(docker_config, 0o700)
            base = self.clean_env(docker_config)
            code, _ = self.run([self.paths.docker, "login", REGISTRY, "--username", "edusync-deploy", "--password-stdin"], base, token.encode())
            if code != 0:
                raise Refused("connexion au registre refusée", EXIT_FAILED)
            for name in ALLOWED_IMAGES:
                code, _ = self.run([self.paths.docker, "pull", "--platform", "linux/arm64", pinned_reference(name, digests[name])], base)
                if code != 0:
                    raise Refused(f"téléchargement de {name} impossible", EXIT_FAILED)
            self.run([self.paths.docker, "logout", REGISTRY], base)
            new_env = self.image_env(base, digests)
            old_env = self.image_env(base, previous["digests"]) if previous else new_env
            services = self.running_services(old_env)
            ledger_before = None
            if (services.get("postgres") or {}).get("State") == "running":
                ledger_before = self.migration_ledger(old_env)
                if (services.get("backup") or {}).get("State") == "running":
                    self.log("Sauvegarde vérifiée avant mise à jour")
                    self.backup(old_env)
            self.write_state("attempt", {"sha": sha, "ref": ref, "digests": digests, "previous": previous, "ledger_before": ledger_before,
                                         "started_at": datetime.now(timezone.utc).isoformat()})
            code, out = self.compose(new_env, "up", "--detach", "--no-build", "--pull", "never", "--remove-orphans")
            ok, reason = (code == 0), ("docker compose up en erreur" if code else "")
            if ok:
                ok, reason = self.smoke(new_env, host)
            ledger_after = self.migration_ledger(new_env)
            if ok:
                if previous and previous.get("sha") != sha:
                    self.write_state("previous", previous)
                self.write_state("current", {"sha": sha, "ref": ref, "digests": digests, "ledger": ledger_after,
                                             "deployed_at": datetime.now(timezone.utc).isoformat()})
                self.log(f"PASS : {sha} déployé ({reason})")
                return EXIT_OK
            new_migrations = sorted(set(ledger_after or []) - set(ledger_before or []))
            self.log(f"ÉCHEC de {sha} : {reason} ; migrations nouvelles : {new_migrations or 'aucune'}")
            if previous and ledger_before is not None and ledger_after is not None and not new_migrations:
                self.log(f"Rollback automatique vers {previous['sha']} (digests précédents)")
                self.compose(old_env, "up", "--detach", "--no-build", "--pull", "never", "--remove-orphans")
                rok, rreason = self.smoke(old_env, host)
                self.write_state("failed", {"sha": sha, "reason": reason, "rolled_back_to": previous["sha"], "rollback_ok": rok,
                                            "at": datetime.now(timezone.utc).isoformat()})
                self.log(f"ROLLBACK {'PASS' if rok else 'FAIL'} : {rreason}")
                return EXIT_ROLLED_BACK
            self.compose(new_env, "stop", *APP_SERVICES)
            self.write_state("failed", {"sha": sha, "reason": reason, "new_migrations": new_migrations, "safe_stop": True,
                                        "previous": previous, "at": datetime.now(timezone.utc).isoformat()})
            self.log("Arrêt sûr : migration nouvelle ou premier déploiement ; base, volumes et sauvegarde intacts ; "
                     "restauration supervisée requise (CICD.md §6)")
            return EXIT_SAFE_STOP
        finally:
            shutil.rmtree(docker_config, ignore_errors=True)


def acquire_lock(path: str):
    import fcntl
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


def main(argv: list[str], stdin) -> int:
    if len(argv) != 1:
        print("Refusé : le contrôleur n'accepte aucun argument", file=sys.stderr)
        return EXIT_USAGE
    os.environ.clear()
    os.environ.update({"PATH": SAFE_PATH, "LANG": "C.UTF-8"})
    os.umask(0o077)
    ctl = Controller()
    lock = acquire_lock(ctl.paths.lock_file)
    if lock is None:
        print("Refusé : un déploiement est déjà en cours", file=sys.stderr)
        return EXIT_BUSY
    try:
        sha, token = parse_request(stdin.read(MAX_STDIN + 1))
        return ctl.deploy(sha, token)
    except Refused as exc:
        ctl.log(f"REFUS : {exc}")
        return exc.code
    finally:
        os.close(lock)


if __name__ == "__main__":
    sys.exit(main(sys.argv, sys.stdin.buffer))
