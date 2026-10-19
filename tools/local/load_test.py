"""Local load test of the platform screens (lot 2026-10). NEVER against the shared staging.

Target written before measuring: 1 000 schools, 200 simultaneous users, p95 < 1 s on the heavy platform screens,
0 server error (5xx). The local data (400 schools) is completed with synthetic schools (code LOAD-…) committed for the
duration of the test and deleted at the end. 200 virtual users share signed-in platform sessions and loop over the
heavy screens (dashboard, schools directory + search, users & accesses, audit log, service health, error groups) for
DURATION seconds. Prints per-screen p50 / p95 / p99, throughput and errors; writes .local/load_test_report.json.
Usage: EDUSYNC_LOCAL_PG_PORT=54432 python tools/local/load_test.py [users=200] [seconds=60] [schools=1000] [realiste|stress]
"""
from __future__ import annotations

import asyncio
import json
import random
import statistics
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend/src")); sys.path.insert(0, str(ROOT / "tools/local"))
import edusync_local as L  # noqa: E402
import httpx  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from edusync.shared.infrastructure.mfa import current_step, totp_code  # noqa: E402

USERS = int(sys.argv[1]) if len(sys.argv) > 1 else 200
DURATION = int(sys.argv[2]) if len(sys.argv) > 2 else 60
SCHOOLS = int(sys.argv[3]) if len(sys.argv) > 3 else 1000
MODE = sys.argv[4] if len(sys.argv) > 4 else "realiste"     # realiste: a person reads 3-10 s between screens; stress: 0.2-1 s
THINK = (3.0, 10.0) if MODE == "realiste" else (0.2, 1.0)
API = "http://127.0.0.1:58100/api/v1"
env = L.load_env("demo")
owner = create_engine(env["EDUSYNC_OWNER_DATABASE_URL"])
FX = json.loads((ROOT / ".local/claude-fixtures-edusync_claude_fresh.json").read_text(encoding="utf-8"))
ENV = {l.split("=", 1)[0]: l.rstrip("\n").split("=", 1)[1] for l in (ROOT / ".local/certification.env").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#")}
SCREENS = (("Tableau de bord", "/platform/dashboard"),
           ("Écoles (1re page)", "/platform/schools-page?limit=25"),
           ("Écoles (recherche)", "/platform/schools-page?limit=25&q=sainte"),
           ("Utilisateurs & accès", "/platform/identities?limit=25"),
           ("Journal d’audit", "/platform/audit-log?limit=50"),
           ("État du service", "/platform/system/health"),
           ("Erreurs regroupées", "/platform/system/health/errors?window=24h"))


def post(path, body):
    req = urllib.request.Request(API + path, method="POST", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Origin": "http://localhost:5180"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def login(email, password, secret) -> str:
    step = post("/auth/login", {"email": email, "password": password, "scope": "PLATFORM"})
    for _ in range(3):
        while time.time() % 30 > 25:
            time.sleep(0.5)
        try:
            return post("/auth/mfa/verify", {"mfa_token": step["mfa_token"], "code": totp_code(secret, current_step())})["access_token"]
        except Exception:  # noqa: BLE001 — same step already used: next one
            time.sleep(31)
    raise SystemExit("connexion impossible")


async def user(client: httpx.AsyncClient, token: str, stop: float, results: dict):
    await asyncio.sleep(random.random() * THINK[1])       # ramp-up
    while time.monotonic() < stop:
        label, path = random.choice(SCREENS)
        t0 = time.perf_counter()
        try:
            r = await client.get(API + path, headers={"Authorization": f"Bearer {token}"})
            code = r.status_code
        except Exception:  # noqa: BLE001
            code = 0
        ms = (time.perf_counter() - t0) * 1000
        results.setdefault(label, []).append((ms, code))
        await asyncio.sleep(random.uniform(*THINK))        # think time of a person reading a screen


async def run(tokens: list[str]) -> dict:
    results: dict[str, list] = {}
    limits = httpx.Limits(max_connections=USERS, max_keepalive_connections=USERS)
    async with httpx.AsyncClient(timeout=30, limits=limits) as client:
        stop = time.monotonic() + DURATION
        await asyncio.gather(*(user(client, tokens[i % len(tokens)], stop, results) for i in range(USERS)))
    return results


def pct(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(q * len(values)))] if values else None


def main() -> int:
    add = max(0, SCHOOLS - owner.connect().execute(text("SELECT count(*) FROM schools")).scalar())
    with owner.begin() as c:
        c.execute(text("""INSERT INTO schools(code,name,status,province,city,contact_name)
            SELECT 'LOAD-' || g, 'École de charge ' || g || CASE WHEN g % 9 = 0 THEN ' Sainte-Marie' ELSE '' END,
                   CASE WHEN g % 12 = 0 THEN 'SUSPENDED' ELSE 'ACTIVE' END, 'Kinshasa', 'Kinshasa', 'Promoteur ' || g
              FROM generate_series(1, :n) g"""), {"n": add})
        c.execute(text("ANALYZE schools"))
    try:
        total = owner.connect().execute(text("SELECT count(*) FROM schools")).scalar()
        tokens = [login("certification@example.test", ENV["EDUSYNC_PLATFORM_ADMIN_PASSWORD"], FX["MFA_TOTP"]["certification@example.test"]["secret"])]
        print(f"{total} écoles · {USERS} utilisateurs simultanés · mode {MODE} · {DURATION} s · objectif p95 < 1 000 ms, 0 erreur 5xx", flush=True)
        t0 = time.perf_counter()
        results = asyncio.run(run(tokens))
        elapsed = time.perf_counter() - t0
    finally:
        with owner.begin() as c:
            c.execute(text("DELETE FROM schools WHERE code LIKE 'LOAD-%'"))
    report = {"schools": total, "users": USERS, "seconds": DURATION, "mode": MODE, "screens": {}}
    all_ms, n5, n4, n0, ok_all = [], 0, 0, 0, True
    print(f"{'Écran':<24}{'requêtes':>9}{'p50':>8}{'p95':>8}{'p99':>8}{'5xx':>6}{'autres':>8}")
    for label, _ in SCREENS:
        rows = results.get(label, [])
        ms = [m for m, c in rows if c == 200]
        e5 = sum(1 for _, c in rows if c >= 500); e0 = sum(1 for _, c in rows if c == 0); e4 = sum(1 for _, c in rows if 400 <= c < 500)
        n5 += e5; n0 += e0; n4 += e4; all_ms += ms
        p50, p95, p99 = (int(pct(ms, q)) if ms else None for q in (.5, .95, .99))
        good = p95 is not None and p95 < 1000 and e5 == 0 and e0 == 0
        ok_all &= good
        report["screens"][label] = {"requests": len(rows), "p50_ms": p50, "p95_ms": p95, "p99_ms": p99, "errors_5xx": e5, "errors_network": e0, "client_4xx": e4, "ok": good}
        print(f"{label:<24}{len(rows):>9}{p50 or '—':>8}{p95 or '—':>8}{p99 or '—':>8}{e5:>6}{e0 + e4:>8}  {'OK' if good else 'HORS OBJECTIF'}")
    report.update(requests=sum(len(v) for v in results.values()), throughput_rps=round(sum(len(v) for v in results.values()) / elapsed, 1),
                  p95_ms=int(pct(all_ms, .95)) if all_ms else None, errors_5xx=n5, errors_network=n0, client_4xx=n4, target_met=ok_all)
    print(f"Total : {report['requests']} requêtes, {report['throughput_rps']} req/s, p95 global {report['p95_ms']} ms, 5xx {n5}, réseau {n0}")
    print("OBJECTIF ATTEINT" if ok_all else "OBJECTIF NON ATTEINT (voir les écrans hors objectif)")
    (ROOT / ".local/load_test_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
