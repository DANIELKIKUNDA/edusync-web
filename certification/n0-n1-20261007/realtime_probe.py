"""Live probe — real-time notifications (SSE over Redis Pub/Sub): latency through the web app proxy, no content
in the signal, per-account isolation, authentication required."""
import json
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import ensure_user, login, platform, state  # noqa: E402

APP = "http://localhost:5180/api/v1"
results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


def listen(path, token, events, stop, ready):
    try:
        with httpx.stream("GET", APP + path, headers={"Authorization": "Bearer " + token, "Accept": "text/event-stream"}, timeout=httpx.Timeout(10, read=None)) as r:
            events.append(("status", r.status_code, time.perf_counter()))
            buf = ""
            for chunk in r.iter_text():
                buf += chunk
                while "\n\n" in buf:
                    evt, buf = buf.split("\n\n", 1)
                    events.append(("event", evt, time.perf_counter()))
                    if "event: ready" in evt:
                        ready.set()
                if stop.is_set():
                    return
    except Exception as e:  # noqa: BLE001
        events.append(("error", repr(e), time.perf_counter()))
        ready.set()


mgr = platform()
me = mgr.get("platform/team/me").json()["user"]["id"]
A = state["A"]
cash = ensure_user(A, "N1_AUTO_ONE", ("CAISSIER",))
cc = login(cash["email"], cash["password"], "SCHOOL", A["code"])

pf_events, sc_events, stop = [], [], threading.Event()
r1, r2 = threading.Event(), threading.Event()
t1 = threading.Thread(target=listen, args=("/platform/inbox/stream", mgr.headers["Authorization"].split()[1], pf_events, stop, r1), daemon=True)
t2 = threading.Thread(target=listen, args=("/notifications/stream", cc.headers["Authorization"].split()[1], sc_events, stop, r2), daemon=True)
t1.start(); t2.start()
check("Flux plateforme ouvert (via le proxy de l'interface)", r1.wait(20) and pf_events[0][1] == 200, pf_events[:1])
check("Flux école ouvert", r2.wait(20) and sc_events[0][1] == 200, sc_events[:1])

secret = f"Contenu confidentiel {uuid4().hex}"
t0 = time.perf_counter()
mgr.post("platform/notification-campaigns", json={"title": "Temps réel N1", "body": secret, "target": {"type": "PLATFORM_USER", "school_ids": [], "role_code": None, "user_id": me}},
         headers={"Idempotency-Key": str(uuid4())})
deadline = time.time() + 10
while time.time() < deadline and not any(k == "event" and "event: inbox" in v for k, v, _ in pf_events):
    time.sleep(0.05)
hit = next(((v, ts) for k, v, ts in pf_events if k == "event" and "event: inbox" in v), None)
check("Notification plateforme reçue en temps réel (< 2 s)", hit is not None and hit[1] - t0 < 2, f"{(hit[1] - t0) * 1000:.0f} ms" if hit else "rien reçu")
check("Le signal ne transporte aucun contenu", hit is not None and secret not in hit[0] and "Temps réel" not in hit[0], hit[0] if hit else "")
time.sleep(1)
check("Isolation : le flux du membre d'école n'a rien reçu", not any(k == "event" and "event: inbox" in v for k, v, _ in sc_events))

from common import owner  # noqa: E402
from sqlalchemy import text  # noqa: E402
with owner.connect() as c:
    uid = c.execute(text("SELECT id FROM users WHERE lower(email::text)=:e"), {"e": cash["email"].lower()}).scalar_one()
t0 = time.perf_counter()
mgr.post("platform/notification-campaigns", json={"title": "Temps réel école", "body": "x" * 5, "target": {"type": "SCHOOL_USER", "school_ids": [A["school_id"]], "role_code": None, "user_id": str(uid)}},
         headers={"Idempotency-Key": str(uuid4())})
deadline = time.time() + 10
while time.time() < deadline and not any(k == "event" and "event: inbox" in v for k, v, _ in sc_events):
    time.sleep(0.05)
hit2 = next((ts for k, v, ts in sc_events if k == "event" and "event: inbox" in v), None)
check("Notification école reçue en temps réel (< 2 s)", hit2 is not None and hit2 - t0 < 2, f"{(hit2 - t0) * 1000:.0f} ms" if hit2 else "rien reçu")
stop.set()

no_auth = httpx.get(APP + "/platform/inbox/stream", timeout=10)
check("Flux sans authentification refusé", no_auth.status_code in (401, 403), no_auth.status_code)
cross = httpx.get(APP + "/platform/inbox/stream", headers={"Authorization": cc.headers["Authorization"]}, timeout=10)
check("Jeton d'école refusé sur le flux plateforme", cross.status_code == 403, cross.status_code)

out = Path(__file__).with_name("realtime-live.json")
out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(f"== {sum(r['pass'] for r in results)}/{len(results)} PASS -> {out.name}")
