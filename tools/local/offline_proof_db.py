"""Offline proof (2026-10-31) — READ ONLY look at the local demo database after a mobile offline session.

Usage: python tools/local/offline_proof_db.py <pupil_last_name> <idempotency_key,...>
Prints JSON: how many pupils carry that last name, and for each Idempotency-Key how many payments exist.
A correct synchronisation gives exactly 1 everywhere (never 0, never 2). Local database only.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/local"))
os.environ.setdefault("EDUSYNC_LOCAL_PG_PORT", "55432")
import edusync_local as L  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

URL = L.load_env("demo")["EDUSYNC_OWNER_DATABASE_URL"]
assert "127.0.0.1" in URL or "localhost" in URL, "base locale uniquement"


def main(pupil: str, keys: list[str]) -> None:
    with create_engine(URL).connect() as c:
        out = {"pupils": c.execute(text("SELECT count(*) FROM students WHERE last_name=:n"), {"n": pupil}).scalar_one(),
               "enrollments": c.execute(text("SELECT count(*) FROM enrollments e JOIN students s ON s.id=e.student_id WHERE s.last_name=:n AND e.status<>'CANCELLED'"), {"n": pupil}).scalar_one(),
               "keys": {}}
        for k in keys:
            out["keys"][k] = {"payments": c.execute(text("SELECT count(*) FROM finance_payments WHERE idempotency_key=:k"), {"k": k}).scalar_one()}
    print(json.dumps(out))


if __name__ == "__main__":
    main(sys.argv[1], [k for k in (sys.argv[2] if len(sys.argv) > 2 else "").split(",") if k])
