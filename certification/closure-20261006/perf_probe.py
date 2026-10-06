"""Performance measurement on the volume database (real HTTP + real PostgreSQL, RLS active).

Load generator: Python threads + httpx (k6 is not installed in this environment).
Reports p50/p95/p99 per endpoint under 10 concurrent clients, multi-cashier collect throughput with
ledger integrity check, pg_stat_statements top statements, and EXPLAIN (ANALYZE, BUFFERS) run with the
tenant role and the same RLS context the API sets.
"""
import json
import os
import statistics
import sys
import threading
import time
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude-20260930"))
from common import *  # noqa: E402,F403
from edusync.bootstrap.settings import Settings  # noqa: E402
from edusync.shared.infrastructure.postgres import DatabaseRuntime  # noqa: E402

assert DB_URL.endswith("/edusync_claude_perf")
A = state["A"]
caps = [r["code"] for r in sql("SELECT code FROM capability_catalog WHERE code NOT LIKE 'platform.%'")]
grant_test_role(A, "ADMIN", "CL_PERF_ALL", tuple(caps))
big_class = sql("""SELECT c.id, count(*) n FROM school_classes c JOIN enrollments e ON e.class_id=c.id
                   WHERE c.school_id=:s GROUP BY c.id ORDER BY n DESC LIMIT 1""", {"s": A["school_id"]})[0]
eid = sql("SELECT e.id FROM enrollments e JOIN students s ON s.id=e.student_id WHERE e.school_id=:s AND s.matricule LIKE 'PA-%' LIMIT 1", {"s": A["school_id"]})[0]["id"]
report = {"environment": {"postgres": sql("SHOW server_version")[0]["server_version"], "shared_buffers": sql("SHOW shared_buffers")[0]["shared_buffers"],
                          "load_generator": "python threads + httpx (k6 not installed)", "concurrency": 8},
          "volume": {t: sql(f"SELECT count(*) n FROM {t}")[0]["n"] for t in ("students", "enrollments", "finance_charges", "finance_payments")},
          "class_size": big_class["n"], "endpoints": {}, "collect": {}, "top_statements": [], "explain": {}}
STATS = True
try:
    sql("SELECT pg_stat_statements_reset()")
except Exception:  # extension not preloaded on this instance: timings still measured client-side
    STATS = False

ENDPOINTS = [
    ("auth/me (auth + session + RBAC reload)", "ADMIN", "auth/me", {}),
    ("checkout search", "CAISSIER1", "finance/checkout/search", {"q": "NOM12"}),
    ("checkout balance", "CAISSIER1", f"finance/checkout/balance/{eid}", {}),
    ("cash current", "CAISSIER1", "finance/cash/current", {}),
    ("students list (search)", "ADMIN", "schooling/students", {"q": "POST7", "limit": 50}),
    ("fee tracking students", "ADMIN", "finance/fees/students", {"limit": 50}),
    ("recovery monthly", "ADMIN", "finance/recovery/monthly", {"currency": "CDF"}),
    ("recovery summary school", "ADMIN", "finance/recovery/summary/school", {"currency": "CDF"}),
    ("recovery class register (largest class)", "ADMIN", "finance/recovery/class-register", {"class_id": str(big_class["id"]), "currency": "CDF"}),
]


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


for name, user, path, params in ENDPOINTS:
    clients = [user_client(A, user) for _ in range(8)]
    for c in clients[:2]:
        call(c, "GET", path, params=params)  # warm-up
    lat, codes, lock = [], [], threading.Lock()

    def worker(c):
        for _ in range(10):
            t0 = time.perf_counter()
            r = call(c, "GET", path, params=params)
            dt = (time.perf_counter() - t0) * 1000
            with lock:
                lat.append(dt)
                codes.append(r.status_code)

    t0 = time.perf_counter()
    ts = [threading.Thread(target=worker, args=(c,)) for c in clients]
    [t.start() for t in ts]
    [t.join() for t in ts]
    wall = time.perf_counter() - t0
    report["endpoints"][name] = {"requests": len(lat), "ok": codes.count(200), "p50_ms": round(pct(lat, 50)), "p95_ms": round(pct(lat, 95)),
                                 "p99_ms": round(pct(lat, 99)), "max_ms": round(max(lat)), "rps": round(len(lat) / wall, 1)}
    print(name, report["endpoints"][name], flush=True)
    check(f"perf {name}: all 200", codes.count(200) == len(codes), str(set(codes)))

# multi-cashier collect throughput on distinct pupils (DECEMBRE is the next due month for paid pupils)
for k in ("CAISSIER3", "CAISSIER4"):
    ensure_user(A, k, ("CAISSIER",))
cashiers = ["CAISSIER1", "CAISSIER2", "CAISSIER3", "CAISSIER4"]
targets = sql("""SELECT fc.enrollment_id, fc.id FROM finance_charges fc JOIN enrollments e ON e.id=fc.enrollment_id JOIN students s ON s.id=e.student_id
                 WHERE fc.school_id=:s AND s.matricule LIKE 'PA-%' AND fc.period_order=4 AND fc.paid_amount=0
                 AND EXISTS(SELECT 1 FROM finance_charges p WHERE p.enrollment_id=fc.enrollment_id AND p.period_order=3 AND p.paid_amount=p.net_amount)
                 ORDER BY fc.id LIMIT 100""", {"s": A["school_id"]})
lat, codes, lock = [], [], threading.Lock()


def cashier(name, rows):
    c = user_client(A, name)
    cur = call(c, "GET", "finance/cash/current").json()["session"]
    if not cur:
        call(c, "POST", "finance/cash/open", json={"opening_cdf": 0, "opening_usd": 0})
    for row in rows:
        t0 = time.perf_counter()
        r = call(c, "POST", "finance/checkout/collect", json={"enrollment_id": str(row["enrollment_id"]), "charge_ids": [str(row["id"])], "amount": "50000", "currency": "CDF"})
        with lock:
            lat.append((time.perf_counter() - t0) * 1000)
            codes.append(r.status_code)


t0 = time.perf_counter()
ts = [threading.Thread(target=cashier, args=(n, targets[i::len(cashiers)])) for i, n in enumerate(cashiers)]
[t.start() for t in ts]
[t.join() for t in ts]
wall = time.perf_counter() - t0
report["collect"] = {"cashiers": len(cashiers), "payments": len(lat), "ok": codes.count(200), "p50_ms": round(pct(lat, 50)), "p95_ms": round(pct(lat, 95)),
                     "p99_ms": round(pct(lat, 99)), "payments_per_second": round(len(lat) / wall, 1)}
print("collect", report["collect"], flush=True)
bad = sql("""SELECT count(*) n FROM finance_charges fc WHERE fc.school_id=:s AND fc.paid_amount <>
             coalesce((SELECT sum(a.amount) FROM finance_payment_allocations a WHERE a.charge_id=fc.id),0)""", {"s": A["school_id"]})[0]["n"]
check("4 concurrent cashiers: all payments accepted, ledger consistent", codes.count(200) == len(codes) and bad == 0, f"ok={codes.count(200)}/{len(codes)} ledger mismatches={bad}")

report["top_statements"] = [] if not STATS else [dict(r) for r in sql("""SELECT left(regexp_replace(query,'\\s+',' ','g'),160) query, calls, round(mean_exec_time::numeric,2) mean_ms,
     round(max_exec_time::numeric,2) max_ms, round(total_exec_time::numeric,1) total_ms, shared_blks_hit, shared_blks_read
     FROM pg_stat_statements WHERE dbid=(SELECT oid FROM pg_database WHERE datname=current_database()) ORDER BY total_exec_time DESC LIMIT 12""")]

# EXPLAIN under the tenant role with the API's RLS context
tdb = DatabaseRuntime.from_url(Settings().tenant_database_url, role_kind="tenant")
EXPLAINS = {
    "checkout search (ILIKE on name/matricule/family)": ("""SELECT s.id FROM students s JOIN families f ON f.id=s.family_id
        WHERE s.school_id=:sid AND (s.matricule ILIKE :q OR concat_ws(' ',s.last_name,s.middle_name,s.first_name) ILIKE :q OR f.display_name ILIKE :q OR coalesce(f.phone,'') ILIKE :q) LIMIT 12""",
                                                          {"sid": A["school_id"], "q": "%NOM12%"}),
    "balance charges of one enrollment": ("SELECT id FROM finance_charges WHERE school_id=:sid AND enrollment_id=:e AND status='ACTIVE'", {"sid": A["school_id"], "e": str(eid)}),
    "recovery school summary aggregate": ("""SELECT sc.id, sum(fc.effective_net_amount), sum(fc.paid_amount) FROM school_classes sc JOIN enrollments e ON e.class_id=sc.id AND e.school_id=sc.school_id
        JOIN finance_charge_effective fc ON fc.enrollment_id=e.id AND fc.school_id=e.school_id WHERE sc.school_id=:sid AND e.academic_year_id=:y AND fc.currency='CDF' AND fc.status='ACTIVE' GROUP BY sc.id""",
                                          {"sid": A["school_id"], "y": A["year_id"]}),
}
for name, (q, p) in EXPLAINS.items():
    with tdb.tenant_transaction(school_id=UUID(A["school_id"])) as c:
        plan = [r[0] for r in c.execute(text("EXPLAIN (ANALYZE, BUFFERS) " + q), p)]
    report["explain"][name] = plan
    exec_ms = next((l for l in plan if "Execution Time" in l), "")
    print(name, "->", exec_ms, "|", next((l.strip() for l in plan if "Scan" in l), ""), flush=True)

Path(__file__).with_name("performance-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
Path(__file__).with_name("perf-checks.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"); print(f"== {sum(r['pass'] for r in results)}/{len(results)} PASS")
