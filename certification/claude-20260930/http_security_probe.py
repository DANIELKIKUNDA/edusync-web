"""Live HTTP security probe: headers, CORS, Host, body/query limits (incl. chunked), SQL injection,
stored XSS handling, Excel formula injection in exports, mass assignment, error leakage."""
import io
import os
import sys
import time
from uuid import uuid4

import httpx
from openpyxl import load_workbook

sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa: E402,F403

A, B = state["A"], state["B"]
c1 = user_client(A, "CAISSIER1")
adm = user_client(A, "ADMIN")
anon = httpx.Client(base_url=BASE + "/", timeout=30)

# --- security headers ----------------------------------------------------------------------------
r = call(c1, "GET", "auth/me")
h = {k.lower(): v for k, v in r.headers.items()}
check("X-Content-Type-Options: nosniff", h.get("x-content-type-options") == "nosniff", str(h.get("x-content-type-options")))
check("clickjacking protection (X-Frame-Options or CSP frame-ancestors)", "x-frame-options" in h or "frame-ancestors" in h.get("content-security-policy", ""))
check("Referrer-Policy set", "referrer-policy" in h)
check("API responses not cacheable (no-store)", "no-store" in h.get("cache-control", ""))
check("no server version disclosure (Server header)", "server" not in h, h.get("server", ""))

# --- CORS / Host -----------------------------------------------------------------------------------
r = anon.options("auth/login", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
check("CORS: foreign origin not allowed", "access-control-allow-origin" not in {k.lower() for k in r.headers}, f"HTTP {r.status_code} {r.headers.get('access-control-allow-origin')}")
r = anon.options("auth/login", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
check("CORS: configured origin echoed exactly, never *", r.headers.get("access-control-allow-origin") == "http://localhost:5173")
r = anon.get("/health".lstrip("/"), headers={"Host": "evil.example"})
check("TrustedHost: unknown Host rejected", r.status_code == 400, f"HTTP {r.status_code}")

# --- size limits -------------------------------------------------------------------------------------
r = call(c1, "POST", "finance/checkout/collect", content=b"{" + b" " * (2 * 1024 * 1024 + 10) + b"}", headers={"Content-Type": "application/json"})
check("body > 2 MiB rejected (413)", r.status_code == 413, f"HTTP {r.status_code}")


def gen():
    for _ in range(40):
        yield b" " * 65536


r = c1.post("finance/checkout/collect", content=gen(), headers={"Content-Type": "application/json", "Idempotency-Key": str(uuid4())})
check("chunked body without Content-Length > 2 MiB rejected (413)", r.status_code == 413, f"HTTP {r.status_code}")
r = call(c1, "GET", "finance/checkout/search", params={"q": "x" * 9000})
check("query string > 8 KiB rejected (414)", r.status_code == 414, f"HTTP {r.status_code}")
import socket
from urllib.parse import urlparse
u = urlparse(BASE)
with socket.create_connection((u.hostname, u.port), timeout=10) as so:
    so.sendall(b"POST /api/v1/finance/checkout/collect HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: abc\r\nConnection: close\r\n\r\n{}")
    status_line = so.recv(200).split(b"\r\n", 1)[0].decode(errors="replace")
check("invalid Content-Length rejected (400, raw socket)", " 400 " in status_line, status_line)

# --- SQL injection -------------------------------------------------------------------------------------
payloads = ["' OR '1'='1", "%' OR 1=1 --", "'; DROP TABLE students; --", "' UNION SELECT id,email,password_hash FROM users --",
            "\\' OR 1=1 --", "'||(SELECT pg_sleep(3))||'", "1); SELECT pg_sleep(3); --"]
for path in ["finance/checkout/search", "schooling/students", "schooling/families", "personnel"]:
    worst, codes = 0.0, set()
    for p in payloads:
        t0 = time.perf_counter()
        r = call(c1 if path.startswith("finance") else adm, "GET", path, params={"q": p})
        worst = max(worst, time.perf_counter() - t0)
        codes.add(r.status_code)
        if r.status_code == 200 and "password_hash" in r.text:
            codes.add("LEAK")
    check(f"SQLi on {path}: no 500, no leak, no time-based injection", 500 not in codes and "LEAK" not in codes and worst < 2.5, f"codes={sorted(map(str, codes))} worst={worst:.2f}s")
n = sql("SELECT count(*) n FROM students")[0]["n"]
check("students table intact after injection attempts", n > 0)

# --- stored XSS: data stays data -------------------------------------------------------------------
xss = '<img src=x onerror=alert(1)>'
cc = user_client(A, "CAISSIER1")
body = {"household_confidence": "NONE", "primary_guardian": {"full_name": xss, "role": "PERE", "phone": "+243810000099", "is_primary": True},
        "children": [{"last_name": "XSS", "middle_name": "TEST", "first_name": xss[:40], "class_id": A["class_id"], "gender": "M"}]}
r = call(cc, "POST", "schooling/enrollments/family", json=body)
check("hostile markup accepted only as inert data (JSON API)", r.status_code in (201, 409, 422), f"HTTP {r.status_code}")
r = call(adm, "GET", "schooling/families", params={"q": "XSS"})
check("API serves application/json (never text/html) for user data", r.headers.get("content-type", "").startswith("application/json"))
src = ROOT / "frontend" / "src"
danger = [p.name for p in src.rglob("*.ts*") if "dangerouslySetInnerHTML" in p.read_text(encoding="utf-8") or "innerHTML" in p.read_text(encoding="utf-8")]
check("frontend never injects raw HTML (no dangerouslySetInnerHTML/innerHTML)", not danger, str(danger))

# --- Excel formula injection (CWE-1236) -------------------------------------------------------------
formula = '=HYPERLINK("http://evil.example/pay","Payer ici")'
body = {"household_confidence": "NONE", "primary_guardian": {"full_name": formula, "role": "PERE", "phone": "+243810000098", "is_primary": True},
        "children": [{"last_name": "=1+2", "middle_name": "FORMULE", "first_name": "Test", "class_id": A["class_id"], "gender": "F"}]}
r = call(cc, "POST", "schooling/enrollments/family", json=body)
check("student with formula-like name stored", r.status_code == 201, f"HTTP {r.status_code} {r.text[:120]}")
grant_test_role(A, "ADMIN", "CL_EXPORTS", ("students.directory.export_xlsx", "families.directory.export_xlsx", "students.read", "families.read"))
adm = user_client(A, "ADMIN")
for path in ["schooling/exports/students.xlsx", "schooling/exports/families.xlsx"]:
    r = call(adm, "GET", path)
    if r.status_code != 200:
        check(f"export {path} available", False, f"HTTP {r.status_code} {r.text[:120]}")
        continue
    wb = load_workbook(io.BytesIO(r.content))
    formulas = [c.coordinate for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.data_type == "f"]
    check(f"{path}: user data never exported as a live formula", not formulas, f"formula cells={formulas[:5]}")

# --- mass assignment ----------------------------------------------------------------------------------
sid = sql("SELECT id,version FROM students WHERE school_id=:s ORDER BY created_at LIMIT 1", {"s": A["school_id"]})[0]
r = call(adm, "PATCH", f"schooling/students/{sid['id']}", json={"notes": "maj", "school_id": B["school_id"], "status": "LEFT", "matricule": "HACK"}, headers={"If-Match": str(sid["version"])})
row = sql("SELECT school_id,status,matricule FROM students WHERE id=:i", {"i": sid["id"]})[0]
check("mass assignment: school_id/status/matricule not writable via PATCH", str(row["school_id"]) == A["school_id"] and row["status"] != "LEFT" and row["matricule"] != "HACK", f"HTTP {r.status_code}")

# --- error leakage --------------------------------------------------------------------------------------
r = c1.post("finance/checkout/collect", content=b"{not json", headers={"Content-Type": "application/json", "Idempotency-Key": str(uuid4())})
check("malformed JSON -> 422 without stack trace", r.status_code == 422 and "Traceback" not in r.text and "site-packages" not in r.text)
r = call(c1, "GET", "finance/checkout/balance/not-a-uuid")
check("malformed id -> 422, no SQL error text", r.status_code == 422 and "psycopg" not in r.text and "SELECT" not in r.text)
dump("http-security-live.json")
