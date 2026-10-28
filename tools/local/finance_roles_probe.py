"""Certification probe — Responsable chargé des finances and Promoteur on the LOCAL stack (2026-10-28).

Signs in through the real API with the accounts created by frontend/browser-tests/local_role_prepare.mjs
(.local/<folder>/.account.json, never printed). Both roles read, follow, print and export: every READ below must answer,
every WRITE must be refused (403) and leave nothing in the database (local PostgreSQL, read only). Owner decision
2026-10-28: they may ANALYSE the financial history import, never EXECUTE it. Exits 1 on any FAIL.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/local"))
os.environ.setdefault("EDUSYNC_LOCAL_PG_PORT", "55432")
import edusync_local as L  # noqa: E402

API = "http://localhost:5180/api/v1"
FX = json.loads((ROOT / ".local/claude-fixtures-edusync_claude_fresh.json").read_text(encoding="utf-8"))
SCHOOL_CODE, SCHOOL_ID = FX["C"]["code"], FX["C"]["school_id"]
DB_URL = L.load_env("demo")["EDUSYNC_OWNER_DATABASE_URL"]
assert "127.0.0.1" in DB_URL or "localhost" in DB_URL, "base locale uniquement"
ENGINE = create_engine(DB_URL)
ROLES = [("responsable_finance", "Responsable financier"), ("promoteur", "Promoteur")]
Z = "00000000-0000-0000-0000-000000000000"
RESULTS: list[tuple[str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(("PASS" if ok else "FAIL", name))
    print(f"{'PASS' if ok else 'FAIL':5} {name}{' — ' + detail if detail and not ok else ''}")


def q(sql: str, **params):
    with ENGINE.connect() as c:
        return c.execute(text(sql), params).all()


def login(folder: str) -> httpx.Client:
    acc = json.loads((ROOT / f".local/{folder}/.account.json").read_text(encoding="utf-8"))
    r = httpx.post(f"{API}/auth/login", json={"email": acc["email"], "password": acc["password"], "scope": "SCHOOL", "school_code": SCHOOL_CODE}, timeout=30)
    r.raise_for_status()
    return httpx.Client(base_url=API, headers={"Authorization": f"Bearer {r.json()['access_token']}"}, timeout=90)


def mut(extra: dict | None = None) -> dict:
    return {"Idempotency-Key": f"probe-{uuid.uuid4().hex}", **(extra or {})}


def counts() -> dict:
    return {t: q(f"SELECT count(*) FROM {t} WHERE school_id=:s", s=SCHOOL_ID)[0][0]
            for t in ("finance_payments", "finance_cash_sessions", "enrollments", "staff_members", "school_memberships")}


def main() -> int:
    pupil = q("""SELECT s.id::text FROM students s JOIN enrollments e ON e.student_id=s.id WHERE s.school_id=:s AND e.status='VALIDATED' LIMIT 1""", s=SCHOOL_ID)[0][0]
    foreign = q("SELECT id::text FROM students WHERE school_id<>:s LIMIT 1", s=SCHOOL_ID)[0][0]
    period = {"profile_code": "CONSOLIDE", "period_type": "MENSUEL", "start": "2026-10-01", "end": "2026-10-31"}
    for folder, label in ROLES:
        c = login(folder)
        me = c.get("/access/me").json()
        caps = set(me.get("permissions", []))
        print(f"\n== {label} ({me.get('role_label')}) — {len(caps)} droits")
        check(f"{label} · aucun droit d'exécuter la reprise financière (décision 28/10)", "migration.finance_history.execute" not in caps)
        # --- reads -------------------------------------------------------------------------------------------
        reads = [("profils de rapports", "/finance/reports/profiles", {}), ("rapport périodique", "/finance/reports/periodic", period),
                 ("élèves", "/schooling/students", {"limit": 5}), ("sélecteur des années", "/settings/academic-years/selector", {}),
                 ("sélecteur des classes", "/settings/classes/selector", {}), ("sélecteur des options (nouveau)", "/settings/options/selector", {}),
                 ("relevé d'un élève", f"/finance/reports/students/{pupil}/account", {})]
        for name, path, params in reads:
            code = c.get(path, params=params).status_code
            check(f"{label} · lecture : {name}", code == 200, f"HTTP {code}")
        pdf = c.get(f"/finance/reports/students/{pupil}/account.pdf")
        check(f"{label} · « Relevé PDF » d'un élève (était en erreur 500)", pdf.status_code == 200 and pdf.content[:4] == b"%PDF",
              f"HTTP {pdf.status_code} {pdf.text[:100] if pdf.status_code != 200 else ''}")
        code = c.get(f"/schooling/students/{foreign}").status_code
        check(f"{label} · élève d'une autre école introuvable", code in (403, 404), f"HTTP {code}")
        # --- writes: refused, nothing written ------------------------------------------------------------------
        before = counts()
        forbid = [("ouvrir une caisse", "POST", "/finance/cash/open", {"opening_cdf": "0", "opening_usd": "0"}),
                  ("encaisser", "POST", "/finance/checkout/collect", {"enrollment_id": Z, "charge_ids": [Z], "amount": "1", "currency": "CDF"}),
                  ("inscrire", "POST", "/schooling/enrollments/family", {"children": [{"last_name": "TEST", "middle_name": "TEST", "first_name": "Test", "class_id": Z, "gender": "M"}]}),
                  ("modifier l'identité de l'école", "PATCH", "/settings/identity", {"name": "Nom modifié"}),
                  ("créer un agent", "POST", "/personnel", {"employee_no": f"PR{uuid.uuid4().hex[:6]}", "last_name": "TEST", "category": "AUTRE"}),
                  ("exécuter une reprise financière", "POST", f"/import/finance-history/batches/{Z}/execute", {"accept_warnings": False, "confirm_outside_cash": False}),
                  ("ajouter un membre", "POST", "/access/members", {"email": f"x{uuid.uuid4().hex[:6]}@example.test", "full_name": "Sonde", "reason": "Recette"})]
        for name, method, path, body in forbid:
            r = c.request(method, path, json=body, headers=mut({"If-Match": "1"}))
            check(f"{label} · refusé : {name}", r.status_code == 403, f"HTTP {r.status_code} {r.text[:120]}")
        check(f"{label} · aucune écriture en base après ces refus", counts() == before, f"{before} → {counts()}")
        c.close()
    fails = [r for r in RESULTS if r[0] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
