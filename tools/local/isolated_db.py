"""Isolated local PostgreSQL database for certification runs (2026-10-30).

    python tools/local/isolated_db.py create NAME     # drop + create NAME on the LOCAL cluster, then provision every migration
    python tools/local/isolated_db.py env NAME -- CMD # run CMD with the EDUSYNC_*_DATABASE_URL pointing to NAME (CI=true)

Localhost only (refuses any other host). The roles (edusync_tenant / platform / worker) are cluster-wide: the provisioner
re-asserts them. Nothing here touches the demo database or any remote server.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/local"))
os.environ.setdefault("EDUSYNC_LOCAL_PG_PORT", "55432")
import edusync_local as L  # noqa: E402

from sqlalchemy import create_engine, text  # noqa: E402

KEYS = ("EDUSYNC_OWNER_DATABASE_URL", "EDUSYNC_TENANT_DATABASE_URL", "EDUSYNC_PLATFORM_DATABASE_URL", "EDUSYNC_WORKER_DATABASE_URL")


def env_for(name: str) -> dict[str, str]:
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,40}", name):
        raise SystemExit("nom de base invalide")
    env = L.load_env("demo")
    for k in KEYS:
        assert "127.0.0.1" in env[k] or "localhost" in env[k], "base locale uniquement"
        env[k] = env[k].rsplit("/", 1)[0] + "/" + name
    env.update(CI="true", PYTHONPATH=str(ROOT / "backend" / "src"), PYTHONUTF8="1")
    return env


def create(name: str) -> int:
    env = env_for(name)
    admin = env["EDUSYNC_OWNER_DATABASE_URL"].rsplit("/", 1)[0] + "/postgres"
    eng = create_engine(admin, isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{name}"'))
    eng.dispose()
    r = subprocess.run([str(ROOT / ".venv/Scripts/python.exe"), "scripts/provision_database.py"], cwd=ROOT / "backend", env=env)
    return r.returncode


def run(name: str, cmd: list[str]) -> int:
    # paths relative to backend/ (Windows does not resolve a relative executable against cwd)
    cmd = [str((ROOT / "backend" / c).resolve()) if c.startswith("..") else c for c in cmd]
    return subprocess.run(cmd, env=env_for(name), cwd=ROOT / "backend").returncode


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "create":
        sys.exit(create(sys.argv[2]))
    if len(sys.argv) >= 5 and sys.argv[1] == "env" and sys.argv[3] == "--":
        sys.exit(run(sys.argv[2], sys.argv[4:]))
    print(__doc__); sys.exit(2)
