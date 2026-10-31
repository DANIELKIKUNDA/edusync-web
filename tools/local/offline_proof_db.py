"""Offline proof (2026-10-31) — READ ONLY look at the local demo database after a mobile offline session.

Usage: python tools/local/offline_proof_db.py <pupil_last_name> <idempotency_key,...> [staff_employee_no] [stock_movement_reason]
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


def main(pupil: str, keys: list[str], staff: str = "", reason: str = "") -> None:
    with create_engine(URL).connect() as c:
        out = {"pupils": c.execute(text("SELECT count(*) FROM students WHERE last_name=:n"), {"n": pupil}).scalar_one(),
               "enrollments": c.execute(text("SELECT count(*) FROM enrollments e JOIN students s ON s.id=e.student_id WHERE s.last_name=:n AND e.status<>'CANCELLED'"), {"n": pupil}).scalar_one(),
               "keys": {}}
        for k in keys:
            out["keys"][k] = {"payments": c.execute(text("SELECT count(*) FROM finance_payments WHERE idempotency_key=:k"), {"k": k}).scalar_one()}
        if staff:
            out["staff"] = c.execute(text("SELECT count(*) FROM staff_members WHERE employee_no=:e"), {"e": staff}).scalar_one()
        if reason:
            out["stock_movements"] = c.execute(text("SELECT count(*) FROM inventory_item_movements WHERE reason=:r"), {"r": reason}).scalar_one()
    print(json.dumps(out))


def seed_item(code: str) -> None:
    """Test fixture (local demo school C only): one consumable, as if the Intendant had recorded it the day before."""
    fx = json.loads((ROOT / ".local/claude-fixtures-edusync_claude_fresh.json").read_text(encoding="utf-8"))
    with create_engine(URL).begin() as c:
        c.execute(text("INSERT INTO inventory_items(school_id,code,label,item_kind,unit,low_threshold) VALUES(:s,:c,:l,'CONSUMABLE','boîte',2) ON CONFLICT DO NOTHING"),
                  {"s": fx["C"]["school_id"], "c": code, "l": f"Craie {code}"})
    print(json.dumps({"seeded": code}))


if __name__ == "__main__":
    if sys.argv[1] == "--seed-item":
        seed_item(sys.argv[2]); sys.exit(0)
    main(sys.argv[1], [k for k in (sys.argv[2] if len(sys.argv) > 2 else "").split(",") if k],
         sys.argv[3] if len(sys.argv) > 3 else "", sys.argv[4] if len(sys.argv) > 4 else "")
