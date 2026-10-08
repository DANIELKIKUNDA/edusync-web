"""EduSync local launcher (owner's workstation).

    python tools/local/edusync_local.py start [--profile demo|blank] [--no-browser]
    python tools/local/edusync_local.py stop
    python tools/local/edusync_local.py status
    python tools/local/edusync_local.py logs

Idempotent: a service already answering on its port is reused, never started twice. Secrets and data stay
private under .local/ (never versioned): .local/certification.env, the isolated PostgreSQL cluster
(.local/postgres-certification, port 55432), the Redis config used in WSL, and the S3 store (.local/s3).
Profiles: "demo" = existing demonstration database (edusync_claude_fresh); "blank" = empty installation
(edusync_closure_blank) where the first Manager Système is created from the sign-in page.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / ".local"
RUN = LOCAL / "run"
LOGS = LOCAL / "logs"
ENV_FILE = LOCAL / "certification.env"
PY = ROOT / ".venv" / "Scripts" / "python.exe"
PG_BIN = Path(os.environ.get("EDUSYNC_PG_BIN", r"C:\Program Files\PostgreSQL\16\bin"))
PG_DATA = LOCAL / "postgres-certification"
WSL_DISTRO = os.environ.get("EDUSYNC_WSL_DISTRO", "Ubuntu-22.04")
PROFILES = {"demo": "edusync_claude_fresh", "blank": "edusync_closure_blank"}
PORTS = {"postgres": 55432, "redis": 16379, "s3": 18333, "api": 58100, "app": 5180}
APP_URL = f"http://localhost:{PORTS['app']}/"
DETACHED = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
BREAKAWAY_FROM_JOB = 0x01000000  # CREATE_BREAKAWAY_FROM_JOB
HIDDEN_CONSOLE = 0x00000010 | 0x00000200  # CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP (window hidden via STARTUPINFO)


def say(msg: str) -> None:
    print(f"  {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"\n  ÉCHEC : {msg}\n", flush=True)
    raise SystemExit(1)


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as s:
        s.settimeout(0.6)
        return s.connect_ex((host, port)) == 0


_WSL_IP: str | None = None


def wsl_ip() -> str:
    """Current WSL address (it changes across reboots); cached for the run."""
    global _WSL_IP
    if _WSL_IP is None:
        r = subprocess.run(["wsl.exe", "-d", WSL_DISTRO, "--", "hostname", "-I"], capture_output=True, text=True, timeout=60)
        _WSL_IP = (r.stdout.split() or ["127.0.0.1"])[0]
    return _WSL_IP


def wait(check, seconds: int, what: str) -> None:
    end = time.time() + seconds
    while time.time() < end:
        try:
            if check():
                return
        except Exception:  # noqa: BLE001 — service still starting
            pass
        time.sleep(1)
    fail(f"{what} ne répond pas après {seconds} s. Consultez « Journaux EduSync ».")


def http_ok(url: str) -> bool:
    with urllib.request.urlopen(url, timeout=3) as r:  # noqa: S310 — local loopback URL only
        return r.status == 200


def load_env(profile: str) -> dict[str, str]:
    if not ENV_FILE.exists():
        fail(f"configuration privée absente ({ENV_FILE}).")
    env = dict(os.environ)
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k] = v
    db = PROFILES[profile]
    for k in ("EDUSYNC_OWNER_DATABASE_URL", "EDUSYNC_TENANT_DATABASE_URL", "EDUSYNC_PLATFORM_DATABASE_URL", "EDUSYNC_WORKER_DATABASE_URL"):
        env[k] = env[k].rsplit("/", 1)[0] + "/" + db
    if env.get("EDUSYNC_REDIS_URL"):
        head, _, tail = env["EDUSYNC_REDIS_URL"].rpartition("@")
        env["EDUSYNC_REDIS_URL"] = f"{head}@{wsl_ip()}:{PORTS['redis']}/" + tail.split("/", 1)[1] if "/" in tail else env["EDUSYNC_REDIS_URL"]
    env.update(PYTHONUTF8="1", PYTHONPATH=str(ROOT / "backend" / "src"), EDUSYNC_API_BASE_URL=f"http://127.0.0.1:{PORTS['api']}/api/v1")
    env["EDUSYNC_CORS_ORIGINS"] = f"http://localhost:{PORTS['app']},http://127.0.0.1:{PORTS['app']}"
    return env


def spawn(name: str, args: list[str], env: dict[str, str] | None = None, cwd: Path = ROOT) -> None:
    LOGS.mkdir(parents=True, exist_ok=True); RUN.mkdir(parents=True, exist_ok=True)
    log = open(LOGS / f"{name}.log", "ab")
    log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} start {name}\n".encode())
    # Each service gets its own hidden console. A console-less (DETACHED_PROCESS) service was killed with
    # STATUS_CONTROL_C_EXIT whenever wsl.exe ran afterwards (Redis checks of a later start/status): reproduced
    # 4/4, and 0/4 with a private hidden console. It also leaves the caller's job object when allowed.
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE
    common = dict(cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, startupinfo=si)
    try:
        proc = subprocess.Popen(args, creationflags=HIDDEN_CONSOLE | BREAKAWAY_FROM_JOB, **common)
    except OSError:
        proc = subprocess.Popen(args, creationflags=HIDDEN_CONSOLE, **common)  # the job forbids breakaway
    (RUN / f"{name}.pid").write_text(str(proc.pid))


def check_dependencies() -> None:
    say("Vérification des composants…")
    missing = [str(p) for p in (PY, PG_BIN / "pg_ctl.exe", PG_DATA, LOCAL / "s3" / "bin" / "weed.exe", LOCAL / "s3" / "s3.json") if not Path(p).exists()]
    if not shutil.which("node"):
        missing.append("Node.js (node)")
    if not shutil.which("wsl"):
        missing.append("WSL (Redis)")
    if missing:
        fail("composants manquants : " + ", ".join(missing))
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        say("Préparation de l’interface (première fois, ~1 min)…")
        r = subprocess.run("npm run build", cwd=ROOT / "frontend", shell=True, capture_output=True, text=True)  # noqa: S602,S607 — fixed local command
        if r.returncode != 0:
            fail("construction de l’interface impossible :\n" + r.stdout[-800:] + r.stderr[-800:])


def start(profile: str, open_browser: bool) -> None:
    print("\n  EduSync — démarrage local\n", flush=True)
    check_dependencies()
    env = load_env(profile)
    previous = (RUN / "profile").read_text().strip() if (RUN / "profile").exists() else None
    if previous and previous != profile and port_open(PORTS["api"]):
        say(f"Changement d’environnement ({previous} → {profile}) : arrêt de l’API et des workers en cours.")
        for name in ("api", "outbox-worker", "communications-worker"):
            _kill(name)
        time.sleep(1)

    # 1. PostgreSQL (isolated cluster, never the machine's default service on 5432).
    if port_open(PORTS["postgres"]):
        say("Base de données : déjà démarrée")
    else:
        say("Base de données : démarrage…")
        subprocess.run([str(PG_BIN / "pg_ctl.exe"), "-D", str(PG_DATA), "-l", str(LOCAL / "postgres-certification.log"),
                        "-o", f"-p {PORTS['postgres']} -c listen_addresses=127.0.0.1", "-w", "-t", "180", "start"],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # never capture: postgres inherits the handles and would keep them open forever
        wait(lambda: port_open(PORTS["postgres"]), 240, "La base de données")
        say("Base de données : prête")

    # 2. Redis in WSL (kept alive by a hidden wsl.exe process).
    ip = wsl_ip()
    if port_open(PORTS["redis"], ip):
        say("Messagerie interne (Redis) : déjà démarrée")
    else:
        say("Messagerie interne (Redis) : démarrage…")
        # The WSL address can change after a reboot: the private config is rewritten with the current one
        # (WSL loopback + current WSL address only; password and protected mode unchanged).
        subprocess.run(["wsl.exe", "-d", WSL_DISTRO, "--", "sh", "-c", f"pkill -f 'redis-server.*:{PORTS['redis']}' || true"], capture_output=True)
        RUN.mkdir(parents=True, exist_ok=True)
        lines = [(f"bind 127.0.0.1 {ip}" if l.startswith("bind ") else l) for l in (LOCAL / "redis-certification.conf").read_text(encoding="utf-8").splitlines()]
        (RUN / "redis.conf").write_text("\n".join(lines) + "\n", encoding="utf-8")
        conf = "/mnt/" + str(RUN / "redis.conf")[0].lower() + str(RUN / "redis.conf")[2:].replace("\\", "/")
        spawn("redis", ["wsl.exe", "-d", WSL_DISTRO, "--", "redis-server", conf])
        wait(lambda: port_open(PORTS["redis"], ip), 60, "Redis")
        say("Messagerie interne (Redis) : prête")

    # 3. S3-compatible document storage (SeaweedFS, loopback only).
    if port_open(PORTS["s3"]):
        say("Stockage des documents : déjà démarré")
    else:
        say("Stockage des documents : démarrage…")
        s3dir = LOCAL / "s3"
        spawn("s3", [str(s3dir / "bin" / "weed.exe"), "server", "-ip=127.0.0.1", "-ip.bind=127.0.0.1", "-dir=data",
                     "-master.port=19333", "-master.telemetry=false", "-volume.port=18080", "-volume.max=8", "-filer",
                     "-filer.port=18888", "-s3", f"-s3.port={PORTS['s3']}", "-s3.config=s3.json"], cwd=s3dir)
        # Cold start right after a Windows reboot measured at ~4 min (2026-10-08): allow 6 min.
        wait(lambda: port_open(PORTS["s3"]), 360, "Le stockage des documents")
        say("Stockage des documents : prêt")

    # 4. Database schema up to date for the chosen profile.
    say(f"Environnement : {'démonstration' if profile == 'demo' else 'installation vierge'} ({PROFILES[profile]})")
    _ensure_database(env, profile)

    # 5. API + workers.
    if port_open(PORTS["api"]):
        say("Serveur EduSync : déjà démarré")
    else:
        say("Serveur EduSync : démarrage…")
        spawn("api", [str(PY), "-m", "uvicorn", "edusync.bootstrap.app:create_app", "--factory", "--host", "127.0.0.1", "--port", str(PORTS["api"]), "--no-server-header"], env)
        wait(lambda: http_ok(f"http://127.0.0.1:{PORTS['api']}/health"), 120, "Le serveur EduSync")
        say("Serveur EduSync : prêt")
    for name, module in (("outbox-worker", "edusync.modules.sync.outbox_worker"), ("communications-worker", "edusync.modules.communications.worker")):
        if not _alive(name):
            spawn(name, [str(PY), "-m", module], env)
    say("Tâches de fond (diffusion, SMS) : actives")

    # 6. Web interface (production build, API proxied on the same origin).
    if port_open(PORTS["app"]):
        say("Interface : déjà démarrée")
    else:
        cfg = RUN / "vite.local.config.mjs"
        # Same security headers as the production nginx (frontend/nginx.conf).
        headers = {
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                                       "font-src 'self' data:; connect-src 'self'; worker-src 'self'; manifest-src 'self'; object-src 'none'; "
                                       "base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
            "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()", "Cross-Origin-Opener-Policy": "same-origin",
        }
        cfg.write_text("export default {preview:{host:'127.0.0.1',port:%d,strictPort:true,headers:%s,proxy:{'/api':'http://127.0.0.1:%d','/health':'http://127.0.0.1:%d'}}};\n"
                       % (PORTS["app"], json.dumps(headers), PORTS["api"], PORTS["api"]), encoding="utf-8")
        spawn("app", ["node", str(ROOT / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"), "preview", str(ROOT / "frontend"), "--config", str(cfg)])
        wait(lambda: http_ok(f"http://127.0.0.1:{PORTS['app']}/"), 60, "L’interface")
        say("Interface : prête")
    (RUN / "profile").write_text(profile)
    print(f"\n  EduSync est prêt : {APP_URL}\n", flush=True)
    if open_browser:
        webbrowser.open(APP_URL)


def _ensure_database(env: dict[str, str], profile: str) -> None:
    from_env = dict(env)
    code = ("import os\nfrom sqlalchemy import create_engine,text\n"
            "u=os.environ['EDUSYNC_OWNER_DATABASE_URL'];db=u.rsplit('/',1)[1]\n"
            "e=create_engine(u.rsplit('/',1)[0]+'/postgres',isolation_level='AUTOCOMMIT')\n"
            "with e.connect() as c:\n"
            "  if not c.execute(text('select 1 from pg_database where datname=:d'),{'d':db}).first():c.execute(text('CREATE DATABASE \"'+db+'\"'));print('created')\n")
    r = subprocess.run([str(PY), "-c", code], env=from_env, capture_output=True, text=True)
    if r.returncode != 0:
        fail("base de données inaccessible : " + r.stderr[-400:])
    r = subprocess.run([str(PY), str(ROOT / "backend" / "scripts" / "provision_database.py")], env=from_env, capture_output=True, text=True)
    if r.returncode != 0:
        fail("mise à jour du schéma impossible : " + (r.stdout + r.stderr)[-600:])
    say("Schéma de base : à jour")
    if profile == "blank":
        from_env["EDUSYNC_PLATFORM_ADMIN_PASSWORD"] = " "  # first Manager Système from the sign-in page
    else:
        return
    subprocess.run([str(PY), str(ROOT / "backend" / "scripts" / "bootstrap_platform_admin.py")], env=from_env, capture_output=True, text=True)


def _alive(name: str) -> bool:
    pid_file = RUN / f"{name}.pid"
    if not pid_file.exists():
        return False
    pid = pid_file.read_text().strip()
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
    return pid in r.stdout


def _kill(name: str) -> bool:
    pid_file = RUN / f"{name}.pid"
    if not pid_file.exists():
        return False
    pid = pid_file.read_text().strip()
    subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True)
    pid_file.unlink(missing_ok=True)
    return True


def _kill_port(port: int) -> None:
    r = subprocess.run(["powershell", "-NoProfile", "-Command", f"(Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue).OwningProcess"], capture_output=True, text=True)
    for pid in {x.strip() for x in r.stdout.split() if x.strip().isdigit()}:
        subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True)


def stop() -> None:
    print("\n  EduSync — arrêt\n", flush=True)
    for name, port, label in (("app", PORTS["app"], "Interface"), ("communications-worker", None, "Tâches SMS"), ("outbox-worker", None, "Tâches de diffusion"),
                              ("api", PORTS["api"], "Serveur EduSync"), ("s3", PORTS["s3"], "Stockage des documents")):
        _kill(name)
        if port:
            _kill_port(port)
        say(f"{label} : arrêté")
    subprocess.run(["wsl.exe", "-d", WSL_DISTRO, "--", "sh", "-c", f"pkill -f 'redis-server.*:{PORTS['redis']}' || true"], capture_output=True)
    _kill("redis")
    say("Redis : arrêté")
    subprocess.run([str(PG_BIN / "pg_ctl.exe"), "-D", str(PG_DATA), "-m", "fast", "-w", "stop"], capture_output=True)
    say("Base de données : arrêtée proprement")
    print("\n  EduSync est arrêté. Vos données sont conservées.\n", flush=True)


def reset_blank(confirmed: bool) -> None:
    """Drops and recreates ONLY the blank-installation database (edusync_closure_blank). Never the demo one."""
    db = PROFILES["blank"]
    if not confirmed:
        fail(f"cette commande supprime définitivement la base « {db} ». Relancez avec --yes pour confirmer.")
    if (RUN / "profile").exists() and (RUN / "profile").read_text().strip() == "blank":
        for name in ("api", "outbox-worker", "communications-worker"):
            _kill(name)
        _kill_port(PORTS["api"])
    env = load_env("blank")
    code = "\n".join([
        "import os",
        "from sqlalchemy import create_engine,text",
        "u=os.environ['EDUSYNC_OWNER_DATABASE_URL'];db=u.rsplit('/',1)[1]",
        f"assert db=={db!r}, 'refus: seule la base vierge peut etre reinitialisee'",
        "e=create_engine(u.rsplit('/',1)[0]+'/postgres',isolation_level='AUTOCOMMIT')",
        "with e.connect() as c:",
        "    c.execute(text('DROP DATABASE IF EXISTS \"'+db+'\" WITH (FORCE)'))",
        "    c.execute(text('CREATE DATABASE \"'+db+'\"'))",
    ])
    r = subprocess.run([str(PY), "-c", code], env=env, capture_output=True, text=True)
    if r.returncode != 0:
        fail("réinitialisation impossible : " + r.stderr[-400:])
    say(f"Base « {db} » recréée vide. Lancez « start --profile blank » pour créer le premier Manager Système.")


def status() -> None:
    profile = (RUN / "profile").read_text().strip() if (RUN / "profile").exists() else "—"
    print(json.dumps({**{k: port_open(v, wsl_ip() if k == "redis" else "127.0.0.1") for k, v in PORTS.items()}, "profile": profile, "url": APP_URL}, indent=2, ensure_ascii=False))


def logs() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    os.startfile(str(LOGS))  # noqa: S606 — opens the local logs folder in Explorer


def main() -> None:
    ap = argparse.ArgumentParser(description="Lanceur local EduSync")
    ap.add_argument("command", choices=["start", "stop", "status", "logs", "reset-blank"])
    ap.add_argument("--yes", action="store_true", help="confirme reset-blank")
    ap.add_argument("--profile", choices=sorted(PROFILES), default=None)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    if a.command == "start":
        prof = a.profile or ((RUN / "profile").read_text().strip() if (RUN / "profile").exists() else "demo")
        start(prof if prof in PROFILES else "demo", not a.no_browser)
    elif a.command == "stop":
        stop()
    elif a.command == "reset-blank":
        reset_blank(a.yes)
    elif a.command == "status":
        status()
    else:
        logs()


if __name__ == "__main__":
    main()
