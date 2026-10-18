#!/usr/bin/python3 -IS
"""EduSync staging deployment controller — runs as root through ONE sudoers rule (CICD.md §2).

Installed administratively (install_deploy_controller.sh) as /usr/local/libexec/edusync/deploy-controller,
root-owned, mode 0755. It never changes with an application commit: infrastructure (compose files, mounted
configuration, staging.env, state, logs) lives under root-owned paths and is reinstalled only by an administrator.
The shebang flags are ONE argument ("-IS" = isolated mode + no site): Linux passes everything after the interpreter
path as a single argument, so "-I -S" would not work.

Input  : stdin only, at most 4200 bytes, exactly two lines — the full 40-hex commit SHA, then the ephemeral GitHub token of
         the deployment run (read the CI result, pull the images). No argument is accepted.
Checks : SHA syntax; commit of DANIELKIKUNDA/edusync-web; workflow .github/workflows/ci.yml run on a push of main or a
         tag edusync-* concluded success for that exact SHA; application images only from the three allowed GHCR
         repositories, tagged with the SHA, offering linux/arm64 (the VPS) and the host platform, resolved to digests;
         infrastructure images only from the fixed list below (versions and digests fixed in this file).
Preflight (before any change): installed compose = exactly the expected services, images and published ports (public
         HTTPS only by the edge on EDUSYNC_PUBLIC_BIND_ADDRESS, loopback 18080 for the smoke tests, nothing else);
         ports and network not used by anything other than EduSync; pristine host recognised explicitly, otherwise
         PostgreSQL, a valid migration ledger equal to the recorded one, and a verified backup are all mandatory.
Steps  : lock → verify → preflight → pull every image by digest (temporary DOCKER_CONFIG, deleted in every case) →
         verified backup → compose up (project edusync-staging only) → smoke tests → PASS keep | FAIL: ledger exactly
         unchanged and previous version known → rollback to previous digests (+ smoke tests); otherwise safe stop.
Never  : arbitrary compose / project / image / path, docker prune, actions on non-EduSync resources, token in argv or logs.
"""
from __future__ import annotations

import base64
import errno
import ipaddress
import json
import os
import re
import shutil
import socket
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
# Infrastructure images: fixed versions, multi-architecture index digests (linux/arm64 and linux/amd64 verified).
INFRA_IMAGES = {
    "postgres": "docker.io/library/postgres:16.15-alpine3.23@sha256:621a761097839bdb50207afd6b87a72f38e2d718dd46c3d744828d8917c4f1e0",
    "redis": "docker.io/library/redis:7.4.11-alpine3.21@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499",
    "object-storage": "docker.io/chrislusf/seaweedfs:4.48@sha256:4e61d15fd35994cb1e43e1e553dff106794841fd9a99ade2fc8c8bfce4d7872d",
    "tls-proxy": "docker.io/library/caddy:2.10.2-alpine@sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d",
}
INFRA_ENV = {"postgres": "EDUSYNC_POSTGRES_IMAGE", "redis": "EDUSYNC_REDIS_IMAGE", "object-storage": "EDUSYNC_OBJECT_STORAGE_IMAGE",
             "tls-proxy": "EDUSYNC_TLS_PROXY_IMAGE"}
SERVICE_IMAGE = {"migrator": "edusync-backend", "backend": "edusync-backend", "outbox-worker": "edusync-backend",
                 "communications-worker": "edusync-backend", "frontend": "edusync-frontend", "backup": "edusync-backup",
                 "postgres": "postgres", "redis": "redis", "object-storage": "object-storage", "tls-proxy": "tls-proxy"}
REQUIRED_PLATFORM = ("linux", "arm64")                       # the staging VPS
APP_SERVICES = ("backend", "outbox-worker", "communications-worker", "frontend")
ALL_SERVICES = ("postgres", "redis", "object-storage", "backend", "outbox-worker", "communications-worker", "frontend", "backup")
SMOKE_BIND = ("127.0.0.1", 18080)                            # loopback only, never 8000 (Coolify) nor 8080
PUBLIC_PORTS = (80, 443)                                     # only the edge (tls-proxy), only on EDUSYNC_PUBLIC_BIND_ADDRESS
COMPOSE_SUBNET = ipaddress.ip_network("172.30.57.0/24")
FORBIDDEN_PUBLIC_NETS = tuple(ipaddress.ip_network(n) for n in ("0.0.0.0/8", "127.0.0.0/8", "100.64.0.0/10", "169.254.0.0/16", "224.0.0.0/4", "255.255.255.255/32"))
SAFE_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"
SHA_RE = re.compile(r"\A[0-9a-f]{40}\Z")
TOKEN_RE = re.compile(r"\A[A-Za-z0-9._~+/=-]{20,4096}\Z")    # GITHUB_TOKEN: opaque, base64url / JWT characters
DIGEST_RE = re.compile(r"\Asha256:[0-9a-f]{64}\Z")
INFRA_REF_RE = re.compile(r"\Adocker\.io/[a-z0-9]+(?:[._/-][a-z0-9]+)*:[A-Za-z0-9][A-Za-z0-9._-]{0,127}@sha256:[0-9a-f]{64}\Z")
VERSION_RE = re.compile(r"\A[0-9A-Za-z_]{1,128}\Z")
MAX_STDIN = 4200
INDEX_TYPES = ("application/vnd.oci.image.index.v1+json", "application/vnd.docker.distribution.manifest.list.v2+json")

EXIT_OK, EXIT_ROLLED_BACK, EXIT_SAFE_STOP, EXIT_ROLLBACK_FAILED, EXIT_SAFE_STOP_NO_TARGET = 0, 2, 3, 4, 5
EXIT_USAGE, EXIT_REFUSED, EXIT_FAILED, EXIT_BACKUP, EXIT_LEDGER, EXIT_PORT, EXIT_BUSY, EXIT_UNSAFE = 64, 65, 70, 71, 72, 73, 75, 78
VERDICTS = {
    EXIT_OK: "DEPLOY_SUCCESS", EXIT_ROLLED_BACK: "ROLLBACK_SUCCESS", EXIT_SAFE_STOP: "SAFE_STOP_MIGRATION_CHANGED",
    EXIT_ROLLBACK_FAILED: "ROLLBACK_FAILED", EXIT_SAFE_STOP_NO_TARGET: "SAFE_STOP_NO_ROLLBACK_TARGET",
    EXIT_USAGE: "REQUEST_REFUSED", EXIT_REFUSED: "VERIFICATION_REFUSED", EXIT_FAILED: "PRE_CHANGE_FAILED",
    EXIT_BACKUP: "BACKUP_REQUIRED_FAILED", EXIT_LEDGER: "LEDGER_REQUIRED_FAILED", EXIT_PORT: "PORT_CONFLICT",
    EXIT_BUSY: "DEPLOY_IN_PROGRESS", EXIT_UNSAFE: "UNSAFE_INSTALLATION",
}


class Refused(Exception):
    """Request refused before any change."""
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
        return (f"{self.compose_dir}/docker-compose.yml", f"{self.compose_dir}/compose.staging.yml")


# ------------------------------------------------------------------ input and policy helpers
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


def infra_reference(service: str) -> str:
    ref = INFRA_IMAGES.get(service, "")
    if not INFRA_REF_RE.match(ref) or ":latest@" in ref:
        raise Refused(f"image d'infrastructure non autorisée pour {service}", EXIT_UNSAFE)
    return ref


def native_platform(machine: str | None = None) -> tuple[str, str]:
    m = machine or os.uname().machine
    arch = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "amd64", "amd64": "amd64"}.get(m)
    if not arch:
        raise Refused(f"architecture hôte non prise en charge : {m}", EXIT_UNSAFE)
    return ("linux", arch)


def public_bind_address(value: str) -> str:
    """The single owner of public HTTPS binds 80/443 on this exact interface address, never 0.0.0.0 nor Tailscale."""
    try:
        ip = ipaddress.IPv4Address(value)
    except ValueError as exc:
        raise Refused("EDUSYNC_PUBLIC_BIND_ADDRESS doit être l'adresse IPv4 de l'interface publique", EXIT_UNSAFE) from exc
    if any(ip in net for net in FORBIDDEN_PUBLIC_NETS):
        raise Refused(f"EDUSYNC_PUBLIC_BIND_ADDRESS interdite ({ip} : générique, boucle locale, Tailscale ou lien local)", EXIT_UNSAFE)
    return str(ip)


# ------------------------------------------------------------------ default I/O (replaced in tests)
def _http(method: str, url: str, headers: dict[str, str], timeout: int = 30) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — fixed hosts only
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(4 * 1024 * 1024)
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, b""
    except (urllib.error.URLError, OSError):
        return 0, {}, b""


def _run(argv: list[str], env: dict[str, str], stdin: bytes | None = None, timeout: int = 1800) -> tuple[int, str]:
    p = subprocess.run(argv, input=stdin, env=env, capture_output=True, timeout=timeout, check=False)
    return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")


def _probe_port(ip: str, port: int) -> str:
    """'free' | 'busy' | 'unavailable' (address not configured on this host)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((ip, port))
        return "free"
    except OSError as e:
        return "busy" if e.errno == errno.EADDRINUSE else "unavailable"
    finally:
        s.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Controller:
    paths: Paths = field(default_factory=Paths)
    http: object = _http
    run: object = _run
    stat_fn: object = os.stat
    sleep: object = time.sleep
    probe: object = _probe_port
    platform: tuple | None = None
    expected_uid: int = 0
    tls_profile: bool = False
    public_ip: str = "127.0.0.1"
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
        if self.stat_fn(self.paths.env_file).st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise Refused("installation non sûre : staging.env lisible par un autre compte que root", EXIT_UNSAFE)

    def read_env_values(self, read_env=None) -> dict[str, str]:
        text = read_env() if read_env else open(self.paths.env_file, encoding="utf-8").read()
        return dict(line.split("=", 1) for line in text.splitlines() if "=" in line and not line.lstrip().startswith("#"))

    def assert_staging_env(self, values: dict[str, str]) -> str:
        if values.get("EDUSYNC_ENV") != "staging":
            raise Refused("staging.env doit contenir EDUSYNC_ENV=staging (ce contrôleur ne déploie jamais la production)", EXIT_UNSAFE)
        self.tls_profile = values.get("EDUSYNC_DEPLOY_TLS_PROFILE") == "true"
        if self.tls_profile:
            self.public_ip = public_bind_address(values.get("EDUSYNC_PUBLIC_BIND_ADDRESS", ""))
            if not re.fullmatch(r"[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?", values.get("EDUSYNC_DOMAIN", "")):
                raise Refused("EDUSYNC_DOMAIN obligatoire avec le profil TLS", EXIT_UNSAFE)
        host = values.get("EDUSYNC_TRUSTED_HOSTS", "").split(",")[0].strip()
        if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", host):
            raise Refused("EDUSYNC_TRUSTED_HOSTS absent de staging.env", EXIT_UNSAFE)
        return host

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

    # -------------------------------------------------------------- GHCR: digests and platforms
    def resolve_digests(self, sha: str, token: str, plat: tuple[str, str]) -> dict[str, str]:
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
            if plat not in platforms:
                raise Refused(f"image {name} sans {'/'.join(plat)} (plateforme de cet hôte)")
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

    def docker(self, env: dict[str, str], *args: str, stdin: bytes | None = None, timeout: int = 1800) -> tuple[int, str]:
        return self.run([self.paths.docker, *args], env, stdin, timeout)

    def image_env(self, base: dict[str, str], digests: dict[str, str]) -> dict[str, str]:
        env = dict(base)
        for name in ALLOWED_IMAGES:
            env[IMAGE_ENV[name]] = pinned_reference(name, digests[name])
        for service, var in INFRA_ENV.items():
            env[var] = infra_reference(service)
        env["EDUSYNC_PUBLIC_BIND_ADDRESS"] = self.public_ip
        return env

    def expected_services(self) -> set[str]:
        return set(ALL_SERVICES) | {"migrator"} | ({"tls-proxy"} if self.tls_profile else set())

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

    # -------------------------------------------------------------- preflight (read-only)
    def preflight_config(self, env: dict[str, str]) -> list[tuple[str, int]]:
        """The installed compose, resolved with staging.env, must be exactly the expected stack."""
        code, out = self.compose(env, "config", "--format", "json")
        if code != 0:
            raise Refused("configuration compose installée invalide", EXIT_UNSAFE)
        services = json.loads(out).get("services", {})
        if set(services) != self.expected_services():
            raise Refused(f"services compose inattendus : {sorted(set(services) ^ self.expected_services())}", EXIT_UNSAFE)
        bindings = []
        for name, svc in services.items():
            source = SERVICE_IMAGE[name]
            expected = env[IMAGE_ENV[source]] if source in IMAGE_ENV else env[INFRA_ENV[source]]
            if svc.get("image") != expected:
                raise Refused(f"image inattendue pour {name}", EXIT_UNSAFE)
            if svc.get("privileged") or svc.get("network_mode") == "host" or svc.get("pid") == "host":
                raise Refused(f"service {name} : privilèges hôte interdits", EXIT_UNSAFE)
            for vol in svc.get("volumes") or []:
                if vol.get("type") == "bind" and not str(vol.get("source", "")).startswith(self.paths.compose_dir + "/"):
                    raise Refused(f"service {name} : montage hôte hors de {self.paths.compose_dir}", EXIT_UNSAFE)
            ports = [(p.get("host_ip") or "0.0.0.0", int(p.get("published") or 0), int(p.get("target") or 0)) for p in svc.get("ports") or []]
            allowed = {"frontend": [(SMOKE_BIND[0], SMOKE_BIND[1], 80)],
                       "tls-proxy": [(self.public_ip, 80, 80), (self.public_ip, 443, 443)]}.get(name, [])
            if sorted(ports) != sorted(allowed):
                raise Refused(f"ports publiés inattendus pour {name} : {ports}", EXIT_UNSAFE)
            bindings += [(ip, port) for ip, port, _ in ports]
        return bindings

    def preflight_ports(self, env: dict[str, str], bindings: list[tuple[str, int]]) -> None:
        """Refuse if a needed port is held by anything that is not this EduSync project."""
        code, out = self.docker(env, "ps", "--format", '{{.Label "com.docker.compose.project"}}\t{{.Ports}}')
        if code != 0:
            raise Refused("liste des conteneurs illisible", EXIT_FAILED)
        ours, foreign = set(), set()
        for line in out.splitlines():
            project, _, ports = line.partition("\t")
            for ip, port in re.findall(r"(\[?[0-9a-fA-F.:]*\]?):(\d+)->", ports):
                (ours if project == PROJECT else foreign).add((ip.strip("[]"), int(port)))
        for ip, port in bindings:
            if any(p == port and fip in (ip, "0.0.0.0", "::", "") for fip, p in foreign):
                raise Refused(f"port {ip}:{port} déjà publié par un conteneur hors EduSync", EXIT_PORT)
            state = self.probe(ip, port)
            if state == "unavailable":
                raise Refused(f"adresse {ip} absente de cet hôte (EDUSYNC_PUBLIC_BIND_ADDRESS)", EXIT_UNSAFE)
            if state == "busy" and (ip, port) not in ours:
                raise Refused(f"port {ip}:{port} déjà occupé par un service hors EduSync", EXIT_PORT)

    def preflight_network(self, env: dict[str, str]) -> None:
        code, out = self.docker(env, "network", "ls", "--quiet")
        ids = out.split() if code == 0 else None
        if ids is None:
            raise Refused("liste des réseaux Docker illisible", EXIT_FAILED)
        if not ids:
            return
        code, out = self.docker(env, "network", "inspect", *ids)
        if code != 0:
            raise Refused("réseaux Docker illisibles", EXIT_FAILED)
        for net in json.loads(out or "[]"):
            if (net.get("Labels") or {}).get("com.docker.compose.project") == PROJECT:
                continue
            for cfg in ((net.get("IPAM") or {}).get("Config") or []):
                try:
                    if ipaddress.ip_network(cfg.get("Subnet", ""), strict=False).overlaps(COMPOSE_SUBNET):
                        raise Refused(f"le réseau Docker {net.get('Name')} chevauche {COMPOSE_SUBNET}", EXIT_PORT)
                except ValueError:
                    continue

    def is_pristine(self, env: dict[str, str], services: dict[str, dict]) -> bool:
        """First deployment on a really empty host: no EduSync volume, container or recorded state."""
        code, out = self.docker(env, "volume", "ls", "--quiet", "--filter", f"label=com.docker.compose.project={PROJECT}")
        if code != 0:
            raise Refused("liste des volumes Docker illisible", EXIT_FAILED)
        return not out.split() and not services and not any(self.read_state(n) for n in ("current", "ledger", "attempt"))

    # -------------------------------------------------------------- ledger, backup, smoke
    def read_ledger(self, env: dict[str, str]) -> list[str] | None:
        """Exact migration ledger, or None if absent, empty, unreadable or inconsistent."""
        code, out = self.compose(env, "exec", "-T", "postgres", "sh", "-c",
                                 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT version FROM schema_migrations ORDER BY version"')
        if code != 0:
            return None
        versions = [v.strip() for v in out.splitlines() if v.strip()]
        if not versions or not all(VERSION_RE.match(v) for v in versions) or len(set(versions)) != len(versions) or versions != sorted(versions):
            return None
        return versions

    def require_existing_state(self, env: dict[str, str], services: dict[str, dict]) -> list[str]:
        if (services.get("postgres") or {}).get("State") != "running":
            raise Refused("installation EduSync existante mais PostgreSQL indisponible : registre des migrations impossible", EXIT_LEDGER)
        ledger = self.read_ledger(env)
        if ledger is None:
            raise Refused("registre des migrations absent, vide, illisible ou incohérent sur une installation existante", EXIT_LEDGER)
        recorded = self.read_state("ledger")
        if recorded is not None and recorded.get("versions") != ledger:
            raise Refused("registre des migrations différent du dernier registre enregistré par le contrôleur", EXIT_LEDGER)
        if (services.get("backup") or {}).get("State") != "running":
            raise Refused("service de sauvegarde indisponible sur une installation existante", EXIT_BACKUP)
        return ledger

    def backup(self, env: dict[str, str]) -> None:
        code, out = self.compose(env, "exec", "-T", "backup", "sh", "/usr/local/bin/edusync-backup", "once", timeout=3600)
        if code != 0 or "PASS sauvegarde" not in out:
            for line in out.strip().splitlines()[-6:]:              # the backup script never prints a secret
                self.log(f"  sauvegarde : {line[:300]}")
            raise Refused("sauvegarde d'avant mise à jour en échec : déploiement annulé, rien n'a changé", EXIT_BACKUP)
        code, out = self.compose(env, "exec", "-T", "backup", "cat", "/backup-status/last.json")
        try:
            status = json.loads(out) if code == 0 else {}
        except ValueError:
            status = {}
        if not (status.get("ok") is True and status.get("restore_verified") is True):
            raise Refused("sauvegarde non vérifiée (restauration de contrôle absente ou en échec) : déploiement annulé", EXIT_BACKUP)

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
        for svc in ALL_SERVICES + (("tls-proxy",) if self.tls_profile else ()):
            if (services.get(svc) or {}).get("State") != "running":
                return False, f"service {svc} arrêté"
        self.sleep(20)
        services = self.running_services(env)
        for svc in APP_SERVICES:
            if (services.get(svc) or {}).get("State") != "running" or (services.get("backend") or {}).get("Health") != "healthy":
                return False, f"service {svc} en boucle de redémarrage"
        code, _ = self.compose(env, "exec", "-T", "backend", "python", "-c",
                               "from edusync.bootstrap.settings import Settings;s=Settings();s.assert_runtime_safe();assert s.env=='staging'")
        if code != 0:
            return False, "contrôles de sécurité staging"
        for path, needle in (("/", b"<"), ("/health-api", b"ok"), ("/api/v1/setup/status", b"setup_required")):
            code, _, body = self.http("GET", f"http://{SMOKE_BIND[0]}:{SMOKE_BIND[1]}{path}", {"Host": host_header, "User-Agent": "edusync-deploy-controller"})
            if code != 200 or needle not in body:
                return False, f"HTTP {path} : {code}"
        return True, "smoke tests PASS"

    # -------------------------------------------------------------- images
    def pull_all(self, base: dict[str, str], token: str, plat: tuple[str, str], digest_sets: list[dict[str, str]]) -> None:
        code, _ = self.docker(base, "login", REGISTRY, "--username", "edusync-deploy", "--password-stdin", stdin=token.encode())
        if code != 0:
            raise Refused("connexion au registre refusée", EXIT_FAILED)
        try:
            refs = [pinned_reference(n, d[n]) for d in digest_sets for n in ALLOWED_IMAGES]
            for ref in dict.fromkeys(refs):
                if self.docker(base, "pull", "--platform", "/".join(plat), ref)[0] != 0:
                    raise Refused(f"téléchargement de {ref.split('@')[0]} impossible", EXIT_FAILED)
        finally:
            self.docker(base, "logout", REGISTRY)
        for service in INFRA_IMAGES:
            ref = infra_reference(service)
            if self.docker(base, "pull", "--platform", "/".join(plat), ref)[0] != 0:
                raise Refused(f"téléchargement de l'image d'infrastructure {ref.split('@')[0]} impossible", EXIT_FAILED)
            refs.append(ref)
        for ref in dict.fromkeys(refs):
            code, out = self.docker(base, "image", "inspect", "--format", "{{.Os}}/{{.Architecture}}", ref)
            if code != 0 or out.strip() != "/".join(plat):
                raise Refused(f"image {ref.split('@')[0]} absente ou de mauvaise plateforme après téléchargement", EXIT_FAILED)

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

    def finish(self, code: int, sha: str, detail: dict) -> int:
        self.write_state("last_result", {"sha": sha, "exit": code, "verdict": VERDICTS[code], "at": _now(), **detail})
        self.log(f"VERDICT={VERDICTS[code]} (code {code}) pour {sha}")
        return code

    # -------------------------------------------------------------- the deployment
    def deploy(self, sha: str, token: str, read_env=None) -> int:
        self.assert_installation_safe()
        host = self.assert_staging_env(self.read_env_values(read_env))
        plat = self.platform or native_platform()
        ref = self.verify_commit_and_ci(sha, token)
        digests = self.resolve_digests(sha, token, plat)
        self.log(f"Demande {sha} ({ref}) vérifiée : CI réussie, images {'/'.join(plat)} + linux/arm64 "
                 f"{', '.join(f'{k}@{v[:19]}' for k, v in digests.items())}")
        previous = self.read_state("current")
        os.makedirs(self.paths.run_dir, mode=0o700, exist_ok=True)
        docker_config = tempfile.mkdtemp(prefix="docker-", dir=self.paths.run_dir)
        try:
            os.chmod(docker_config, 0o700)
            base = self.clean_env(docker_config)
            new_env = self.image_env(base, digests)
            old_env = self.image_env(base, previous["digests"]) if previous else None
            # ---- preflight, read-only
            bindings = self.preflight_config(new_env)
            self.preflight_ports(base, bindings)
            self.preflight_network(base)
            services = self.running_services(new_env)
            pristine = self.is_pristine(base, services)
            if pristine:
                ledger_before = None
                self.log("Premier déploiement sur hôte vierge reconnu (aucun volume, conteneur ni état EduSync)")
            else:
                ledger_before = self.require_existing_state(old_env or new_env, services)
            # ---- images (application + previous version for the rollback + infrastructure)
            self.pull_all(base, token, plat, [digests] + ([previous["digests"]] if previous else []))
            # ---- verified backup immediately before the change
            if not pristine:
                self.log("Sauvegarde vérifiée avant mise à jour")
                self.backup(old_env or new_env)
            self.write_state("attempt", {"sha": sha, "ref": ref, "digests": digests, "previous": previous,
                                         "ledger_before": ledger_before, "pristine": pristine, "started_at": _now()})
            # ---- change
            code, _ = self.compose(new_env, "up", "--detach", "--no-build", "--pull", "never", "--remove-orphans")
            ok, reason = (code == 0), ("docker compose up en erreur" if code else "")
            if ok:
                ok, reason = self.smoke(new_env, host)
            ledger_after = self.read_ledger(new_env)
            if ok and ledger_after is not None:
                if previous and previous.get("sha") != sha:
                    self.write_state("previous", previous)
                self.write_state("current", {"sha": sha, "ref": ref, "digests": digests, "ledger": ledger_after, "deployed_at": _now()})
                self.write_state("ledger", {"versions": ledger_after, "sha": sha, "at": _now()})
                self.log(f"PASS : {sha} déployé ({reason})")
                return self.finish(EXIT_OK, sha, {})
            reason = reason if not ok else "registre des migrations illisible après déploiement"
            new_migrations = sorted(set(ledger_after or []) - set(ledger_before or []))
            self.log(f"ÉCHEC de {sha} : {reason} ; registre avant={len(ledger_before or [])} après="
                     f"{'illisible' if ledger_after is None else len(ledger_after)} ; nouvelles : {new_migrations or 'aucune'}")
            if ledger_after is not None:
                self.write_state("ledger", {"versions": ledger_after, "sha": sha, "at": _now()})
            if pristine or not previous:
                return self.safe_stop(new_env, sha, EXIT_SAFE_STOP_NO_TARGET, reason, previous, ledger_before, ledger_after)
            if ledger_after is None or ledger_after != ledger_before:
                return self.safe_stop(new_env, sha, EXIT_SAFE_STOP, reason, previous, ledger_before, ledger_after)
            # ---- rollback: ledger exactly identical, previous digests known and present
            self.log(f"Rollback automatique vers {previous['sha']} (digests précédents, registre identique)")
            code, _ = self.compose(old_env, "up", "--detach", "--no-build", "--pull", "never", "--remove-orphans")
            rok, rreason = (code == 0), ("docker compose up du rollback en erreur" if code else "")
            if rok:
                rok, rreason = self.smoke(old_env, host)
            ledger_rb = self.read_ledger(old_env)
            if rok and ledger_rb != ledger_before:
                rok, rreason = False, "registre des migrations modifié pendant le rollback"
            detail = {"reason": reason, "rolled_back_to": previous["sha"], "rollback_ok": rok, "rollback_reason": rreason, "at": _now()}
            self.write_state("failed", {"sha": sha, **detail})
            if rok:
                self.log(f"ROLLBACK PASS : {previous['sha']} de nouveau en service ({rreason})")
                return self.finish(EXIT_ROLLED_BACK, sha, detail)
            self.compose(old_env, "stop", *APP_SERVICES)
            self.log(f"ROLLBACK FAIL : {rreason} ; API, workers et frontend arrêtés ; base, volumes et sauvegarde intacts")
            return self.finish(EXIT_ROLLBACK_FAILED, sha, detail)
        finally:
            shutil.rmtree(docker_config, ignore_errors=True)

    def safe_stop(self, env, sha, code, reason, previous, ledger_before, ledger_after) -> int:
        self.compose(env, "stop", *APP_SERVICES)
        detail = {"reason": reason, "safe_stop": True, "previous": previous, "ledger_before": ledger_before,
                  "ledger_after": ledger_after, "new_migrations": sorted(set(ledger_after or []) - set(ledger_before or [])), "at": _now()}
        self.write_state("failed", {"sha": sha, **detail})
        self.log("Arrêt sûr : API, workers et frontend arrêtés ; base, volumes et sauvegarde intacts ; "
                 "restauration supervisée requise (CICD.md §7)")
        return self.finish(code, sha, detail)


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
        print(f"Refusé : le contrôleur n'accepte aucun argument\nVERDICT={VERDICTS[EXIT_USAGE]}", file=sys.stderr)
        return EXIT_USAGE
    os.environ.clear()
    os.environ.update({"PATH": SAFE_PATH, "LANG": "C.UTF-8"})
    os.umask(0o077)
    ctl = Controller()
    lock = acquire_lock(ctl.paths.lock_file)
    if lock is None:
        print(f"Refusé : un déploiement est déjà en cours\nVERDICT={VERDICTS[EXIT_BUSY]}", file=sys.stderr)
        return EXIT_BUSY
    try:
        sha, token = parse_request(stdin.read(MAX_STDIN + 1))
        return ctl.deploy(sha, token)
    except Refused as exc:
        ctl.log(f"REFUS : {exc}")
        ctl.log(f"VERDICT={VERDICTS[exc.code]} (code {exc.code})")
        return exc.code
    finally:
        os.close(lock)


if __name__ == "__main__":
    sys.exit(main(sys.argv, sys.stdin.buffer))
