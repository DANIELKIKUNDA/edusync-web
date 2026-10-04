"""Every GET route of the API, called by a school-A user holding every school capability, with valid
query parameters drawn from school A's real data. Goal: zero HTTP 500 across the whole read surface."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa: E402,F403

A = state["A"]
caps = [r["code"] for r in sql("SELECT code FROM capability_catalog WHERE code NOT LIKE 'platform.%'")]
grant_test_role(A, "ADMIN", "CL_SMOKE_ALL", tuple(caps))
a = user_client(A, "ADMIN")
spec = httpx.get(BASE.rsplit("/api/v1", 1)[0] + "/openapi.json", timeout=30).json()


def first(q, p=None):
    rows = sql(q, p or {"s": A["school_id"]})
    return str(list(rows[0].values())[0]) if rows else None


values = {
    "year_id": A["year_id"], "academic_year_id": A["year_id"], "class_id": A["class_id"], "section_id": A["section_id"],
    "currency": "CDF", "q": "ELEVE", "student_id": first("SELECT id FROM students WHERE school_id=:s LIMIT 1"),
    "family_id": A["family"]["family_id"], "enrollment_id": A["family"]["enrollment_ids"][0],
    "staff_id": first("SELECT id FROM staff_members WHERE school_id=:s LIMIT 1"),
    "session_id": first("SELECT id FROM finance_cash_sessions WHERE school_id=:s LIMIT 1"),
    "batch_id": first("SELECT id FROM student_import_batches WHERE school_id=:s LIMIT 1"),
    "kind": "students", "period_order": "1", "limit": "20", "date": "2026-10-01", "day": "2026-10-01",
    "date_from": "2026-09-01", "date_to": "2026-12-31", "start": "2026-09-01", "end": "2026-12-31", "month": "10",
    "status": None, "fmt": "xlsx",
}
results_by_status: dict[int, list[str]] = {}
for path, ops in sorted(spec["paths"].items()):
    if "get" not in ops or not path.startswith("/api/v1/") or path.startswith("/api/v1/platform"):
        continue
    op = ops["get"]
    url, skip = path, False
    for name in re.findall(r"\{([^}]+)\}", path):
        v = values.get(name)
        if v is None:
            skip = True
        url = url.replace("{" + name + "}", str(v))
    if skip:
        continue
    params = {}
    for prm in op.get("parameters", []):
        if prm.get("in") == "query" and values.get(prm["name"]) is not None:
            params[prm["name"]] = values[prm["name"]]
    r = call(a, "GET", url.replace("/api/v1/", "", 1), params=params)
    results_by_status.setdefault(r.status_code, []).append(path)
errors = results_by_status.get(500, [])
total = sum(len(v) for v in results_by_status.values())
check("GET smoke sweep: no route returns HTTP 500", not errors, f"{total} routes; statuses={ {k: len(v) for k, v in sorted(results_by_status.items())} }; 500={errors}")
for code in sorted(results_by_status):
    if code >= 400:
        print(code, results_by_status[code])
dump("get-smoke-sweep.json")
