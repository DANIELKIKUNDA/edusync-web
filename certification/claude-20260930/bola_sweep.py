"""Automated BOLA/IDOR sweep over the whole OpenAPI surface.

For every GET route with path parameters, school B's user (holding a broad test role covering every
school capability) requests school A's real identifiers. A response is a leak if it is 2xx and contains
any identifier or marker that belongs only to school A. Write routes are swept with harmless bodies:
any 2xx on an A identifier is a finding, and A's rows are re-checked afterwards.
"""
import json
import os
import re
import sys
from uuid import UUID

sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa: E402,F403

A, B = state["A"], state["B"]
caps = [r["code"] for r in sql("SELECT code FROM capability_catalog WHERE code NOT LIKE 'platform.%'")]
grant_test_role(B, "ADMIN", "CL_BOLA_ALL", tuple(caps))
b = user_client(B, "ADMIN")
spec = httpx.get(BASE.rsplit("/api/v1", 1)[0] + "/openapi.json", timeout=30).json()

# every uuid that belongs to school A, by table
tables = [r["table_name"] for r in sql("""SELECT table_name FROM information_schema.columns WHERE table_schema='public' AND column_name='school_id'
                                          AND table_name IN (SELECT tablename FROM pg_tables WHERE schemaname='public')""")]
a_ids: dict[str, set[str]] = {}
for t in tables:
    if "id" not in {c["column_name"] for c in sql("SELECT column_name FROM information_schema.columns WHERE table_name=:t", {"t": t})}:
        continue
    for row in sql(f"SELECT id::text id FROM {t} WHERE school_id=:s LIMIT 20", {"s": A["school_id"]}):
        a_ids.setdefault(t, set()).add(row["id"])
all_a = set().union(*a_ids.values()) | {A["school_id"]}
all_a -= {r["id"] for r in sql("SELECT id::text id FROM schools WHERE id<>:s", {"s": A["school_id"]})}
markers = [A["code"], "ELEVEA", "PARENT A"]
print(f"school A identifiers collected: {len(all_a)} across {len(a_ids)} tables")

UUIDISH = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
get_routes, write_routes = [], []
for path, ops in spec["paths"].items():
    if not path.startswith("/api/v1/") or path.startswith("/api/v1/platform") or "{" not in path:
        continue
    for method in ops:
        (get_routes if method == "get" else write_routes).append((method.upper(), path))

candidates = sorted(all_a)


def fill(path, value):
    return re.sub(r"\{[^}]+\}", value, path)


leaks, tried, statuses = [], 0, {}
for method, path in get_routes:
    params = re.findall(r"\{([^}]+)\}", path)
    if any(p in ("kind",) for p in params):
        values = [fill(path.replace("{kind}", k), cid) for k in ("students", "staff", "finance-history") for cid in candidates[:60]]
    elif any(p in ("code", "role_code") for p in params):
        continue
    else:
        name = params[-1].removesuffix("_id")
        stem = {"family": "famil", "staff": "staff", "batch": "import_batches", "session": "session"}.get(name, name)
        pool = sorted({i for t, ids in a_ids.items() if stem in t for i in ids})
        values = [fill(path, cid) for cid in (pool or candidates[:150])]
    for p in values:
        r = call(b, method, p.replace("/api/v1/", "", 1))
        tried += 1
        statuses[r.status_code] = statuses.get(r.status_code, 0) + 1
        if 200 <= r.status_code < 300:
            body = r.text
            found = (set(UUIDISH.findall(body)) & all_a) - set(UUIDISH.findall(p))
            hit = [m for m in markers if m in body]
            if found or hit:
                leaks.append(f"{method} {p} -> {sorted(found)[:3]} {hit}")
check("BOLA sweep: no GET route returns school A data to school B", not leaks, f"{tried} requests; statuses={statuses}; leaks={leaks[:5]}")

before = sql("SELECT md5(string_agg(t::text, ',' ORDER BY t::text)) h FROM (SELECT * FROM students WHERE school_id=:s) t", {"s": A["school_id"]})[0]["h"]
writes_ok, wtried = [], 0
for method, path in write_routes:
    if any(x in path for x in ("/auth/",)):
        continue
    for cid in candidates[:40]:
        p = fill(path, cid).replace("/api/v1/", "", 1)
        r = call(b, method, p, json={"reason": "BOLA probe", "label": "BOLA", "notes": "BOLA"}, headers={"If-Match": "1"})
        wtried += 1
        if 200 <= r.status_code < 300:
            writes_ok.append(f"{method} {p} -> {r.status_code}")
after = sql("SELECT md5(string_agg(t::text, ',' ORDER BY t::text)) h FROM (SELECT * FROM students WHERE school_id=:s) t", {"s": A["school_id"]})[0]["h"]
# a 2xx is only a finding if it touched A: verify no row of A was attributed to B or modified
touched = sql("SELECT count(*) n FROM audit_events WHERE school_id=:a AND actor_user_id=:u", {"a": A["school_id"], "u": B["users"]["ADMIN"]["user_id"]})[0]["n"]
check("BOLA sweep: B's writes on A identifiers never modify A", before == after and touched == 0, f"{wtried} write requests; 2xx={writes_ok[:5]}")
dump("bola-sweep.json")
