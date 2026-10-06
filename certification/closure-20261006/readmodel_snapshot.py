"""Snapshot of the 4 heavy finance read models (exact results + timing), to prove an optimisation keeps
numbers identical. Usage: readmodel_snapshot.py before|after   (volume database only)."""
import hashlib
import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path
from uuid import UUID

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude-20260930"))
from common import *  # noqa: E402,F403
from edusync.bootstrap.settings import Settings  # noqa: E402
from edusync.shared.infrastructure.postgres import DatabaseRuntime  # noqa: E402
from edusync.adapters.postgres_finance_recovery import PostgresFinanceRecoveryRepository  # noqa: E402
from edusync.adapters.postgres_fee_tracking import PostgresFeeTrackingRepository  # noqa: E402

assert DB_URL.endswith("/edusync_claude_perf")
tag = sys.argv[1]
A = state["A"]
sid, year = UUID(A["school_id"]), UUID(A["year_id"])
big = sql("SELECT c.id FROM school_classes c JOIN enrollments e ON e.class_id=c.id WHERE c.school_id=:s GROUP BY c.id ORDER BY count(*) DESC LIMIT 1", {"s": A["school_id"]})[0]["id"]
tdb = DatabaseRuntime.from_url(Settings().tenant_database_url, role_kind="tenant")


def norm(x):
    if isinstance(x, dict):
        return {k: norm(v) for k, v in sorted(x.items())}
    if isinstance(x, (list, tuple)):
        return [norm(v) for v in x]
    if isinstance(x, (Decimal, float)):
        return str(Decimal(str(x)).quantize(Decimal("0.01")))
    return str(x) if x is not None and not isinstance(x, (int, str, bool)) else x


out = {}
for label, fn in [
    ("recovery monthly", lambda c: PostgresFinanceRecoveryRepository(c).monthly(sid, year, "CDF", scopes=(("SCHOOL", None),))),
    ("recovery summary school", lambda c: PostgresFinanceRecoveryRepository(c).scope_summary(sid, year, "CDF")),
    ("recovery class register", lambda c: PostgresFinanceRecoveryRepository(c).class_register(sid, year, big, "CDF")),
    ("fee tracking students", lambda c: PostgresFeeTrackingRepository(c).students(sid, year, "CDF")),
]:
    runs = []
    for _ in range(int(os.environ.get("SNAPSHOT_REPEAT", "1"))):
        t0 = time.perf_counter()
        with tdb.tenant_transaction(school_id=sid) as conn:
            res = fn(conn)
        runs.append(round((time.perf_counter() - t0) * 1000))
    ms = sorted(runs)[len(runs) // 2]
    blob = json.dumps(norm(res), sort_keys=True, ensure_ascii=False)
    out[label] = {"ms": ms, "runs_ms": runs, "sha256": hashlib.sha256(blob.encode()).hexdigest(), "size": len(blob)}
    print(f"{tag:6} {label:28} {ms:>8} ms {runs}  sha256={out[label]['sha256'][:16]}  size={len(blob)}")
Path(__file__).with_name(f"readmodel-{tag}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
