"""EXPLAIN (ANALYZE, BUFFERS) of the real read-model queries, executed by the shipped repository code
under the tenant role with RLS (volume database only). Captures, per statement, total time and the
most expensive plan nodes, so indexes/rewrites are driven by measurement, never guessed."""
import json
import os
import re
import sys
import time
from pathlib import Path
from uuid import UUID

import psycopg

sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa: E402,F403
from edusync.bootstrap.settings import Settings  # noqa: E402
from edusync.shared.infrastructure.postgres import DatabaseRuntime  # noqa: E402
from edusync.adapters.postgres_finance_recovery import PostgresFinanceRecoveryRepository  # noqa: E402
from edusync.adapters.postgres_fee_tracking import PostgresFeeTrackingRepository  # noqa: E402

assert DB_URL.endswith("/edusync_claude_perf")
A = state["A"]
sid, year = UUID(A["school_id"]), UUID(A["year_id"])
big = sql("""SELECT c.id FROM school_classes c JOIN enrollments e ON e.class_id=c.id WHERE c.school_id=:s
             GROUP BY c.id ORDER BY count(*) DESC LIMIT 1""", {"s": A["school_id"]})[0]["id"]
captured = []
_orig = psycopg.Cursor.execute


def explaining_execute(self, query, params=None, **kw):
    q = query if isinstance(query, str) else str(query)
    if "finance_charge" in q and not q.lstrip().upper().startswith("EXPLAIN"):
        t0 = time.perf_counter()
        _orig(self, "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " + q, params, **kw)
        plan = [r[0] if isinstance(r, tuple) else list(r.values())[0] for r in self.fetchall()]
        nodes = []
        for line in plan:
            m = re.search(r"\(actual time=[\d.]+\.\.([\d.]+) rows=(\d+) loops=(\d+)\)", line)
            if m:
                nodes.append((float(m.group(1)) * int(m.group(3)), line.strip()[:170]))
        nodes.sort(reverse=True)
        captured.append({"label": CURRENT, "wall_ms": round((time.perf_counter() - t0) * 1000),
                         "execution": next((l for l in plan if "Execution Time" in l), ""),
                         "top_nodes": [f"{round(t)} ms · {n}" for t, n in nodes[:6]], "plan": plan})
    return _orig(self, query, params, **kw)


psycopg.Cursor.execute = explaining_execute
tdb = DatabaseRuntime.from_url(Settings().tenant_database_url, role_kind="tenant")
CURRENT = ""
scopes = (("SCHOOL", None),)
for label, fn in [
    ("recovery monthly", lambda c: PostgresFinanceRecoveryRepository(c).monthly(sid, year, "CDF", scopes=scopes)),
    ("recovery summary school", lambda c: PostgresFinanceRecoveryRepository(c).scope_summary(sid, year, "CDF")),
    ("recovery class register", lambda c: PostgresFinanceRecoveryRepository(c).class_register(sid, year, big, "CDF")),
    ("fee tracking students", lambda c: PostgresFeeTrackingRepository(c).students(sid, year, "CDF")),
]:
    CURRENT = label
    try:
        with tdb.tenant_transaction(school_id=sid) as conn:
            fn(conn)
    except Exception as e:  # noqa: BLE001
        captured.append({"label": label, "error": f"{type(e).__name__}: {str(e)[:200]}"})
psycopg.Cursor.execute = _orig
for c in captured:
    print(f"\n### {c['label']}  {c.get('execution', c.get('error'))}")
    for n in c.get("top_nodes", []):
        print("   ", n)
Path(__file__).with_name(f"explain-hotspots-{sys.argv[1] if len(sys.argv) > 1 else 'before'}.json").write_text(json.dumps(captured, indent=2, ensure_ascii=False), encoding="utf-8")
