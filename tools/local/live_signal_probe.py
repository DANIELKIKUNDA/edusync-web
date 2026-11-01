"""Live changes — raw signal probe (2026-11-01), LOCAL stack. A member WITHOUT any finance right (Secrétariat) listens to
/api/v1/live/stream while the Caissier records a cash expense: the signal must arrive within seconds and carry ONLY the
domain name (no amount, name or identifier). Accounts from .local (never printed). Exits 1 on failure."""
from __future__ import annotations

import json
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
API = "http://localhost:5180/api/v1"
FX = json.loads((ROOT / ".local/claude-fixtures-edusync_claude_fresh.json").read_text(encoding="utf-8"))
CODE = FX["C"]["code"]


def token(folder: str) -> str:
    acc = json.loads((ROOT / f".local/{folder}/.account.json").read_text(encoding="utf-8"))
    r = httpx.post(f"{API}/auth/login", json={"email": acc["email"], "password": acc["password"], "scope": "SCHOOL", "school_code": CODE}, timeout=30)
    r.raise_for_status(); return r.json()["access_token"]


def main() -> int:
    sec, cash = token("secretariat"), token("caissier")
    perms = httpx.get(f"{API}/access/me", headers={"Authorization": f"Bearer {sec}"}).json().get("permissions", [])
    events: list[str] = []; ready = threading.Event()
    def listen():
        with httpx.stream("GET", f"{API}/live/stream", headers={"Authorization": f"Bearer {sec}", "Accept": "text/event-stream"}, timeout=40) as r:
            buf = ""
            for chunk in r.iter_text():
                buf += chunk
                while "\n\n" in buf:
                    evt, buf = buf.split("\n\n", 1)
                    if "event: ready" in evt: ready.set()
                    elif "event: change" in evt: events.append(evt); return
    t = threading.Thread(target=listen, daemon=True); t.start(); ready.wait(15)
    h = {"Authorization": f"Bearer {cash}"}
    httpx.post(f"{API}/finance/cash/open", json={"opening_cdf": "0", "opening_usd": "0"}, headers={**h, "Idempotency-Key": uuid.uuid4().hex}, timeout=30)
    t0 = time.time(); reason = f"Sonde temps réel {uuid.uuid4().hex[:6]}"
    r = httpx.post(f"{API}/finance/cash/expenses", json={"category": "Fournitures", "amount": "500", "currency": "CDF", "reason": reason}, headers={**h, "Idempotency-Key": uuid.uuid4().hex}, timeout=30)
    t.join(12); delay = time.time() - t0
    ok = True
    def check(name, cond, detail=""):
        nonlocal ok; ok = ok and cond; print(f"{'PASS' if cond else 'FAIL':5} {name}{' — ' + detail if detail and not cond else ''}")
    check("la Secrétaire n'a aucun droit financier", not any(p.startswith("finance.") for p in perms))
    check("dépense du caissier enregistrée", r.status_code == 201, f"HTTP {r.status_code}")
    check(f"signal reçu par la Secrétaire en {delay:.1f} s (< 5 s)", bool(events) and delay < 5, f"{len(events)} signal(s)")
    data = events[0].split("data: ", 1)[1] if events else "{}"
    payload = json.loads(data)
    check("le signal ne contient que le domaine (aucun montant, nom ni identifiant)", payload == {"domains": ["finance"]} and "500" not in data and reason not in data, data)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
