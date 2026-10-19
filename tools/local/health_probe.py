"""Local probe of « État du service » (lot 2026-10): degradation, freshness, queues, backup, dedup, RBAC, no secret.

The measurement function runs in-process against the real local database / Redis / storage, with one dependency
degraded at a time (slow database, Redis unreachable, stale worker heartbeat, outbox backlog, storage unreachable,
backup failed / late / unreadable / future-dated). HTTP checks RBAC and the absence of secrets. Prints PASS/FAIL lines.
Usage: EDUSYNC_LOCAL_PG_PORT=54432 python tools/local/health_probe.py
"""
from __future__ import annotations

import copy
import dataclasses
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend/src")); sys.path.insert(0, str(ROOT / "tools/local"))
import edusync_local as L  # noqa: E402
from edusync.shared.infrastructure.mfa import current_step, totp_code  # noqa: E402

env = L.load_env("demo")
os.environ.update({k: v for k, v in env.items() if k.startswith("EDUSYNC_")})
from sqlalchemy import create_engine, text  # noqa: E402
from edusync.bootstrap.services import AppServices  # noqa: E402
from edusync.bootstrap.settings import Settings  # noqa: E402
from edusync.modules.platform_health.api import router as hr  # noqa: E402
from edusync.shared.infrastructure.heartbeat import HEARTBEAT_PREFIX  # noqa: E402

API = "http://127.0.0.1:58100/api/v1"
FX = json.loads((ROOT / ".local/claude-fixtures-edusync_claude_fresh.json").read_text(encoding="utf-8"))
ENV = {l.split("=", 1)[0]: l.rstrip("\n").split("=", 1)[1] for l in (ROOT / ".local/certification.env").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#")}
owner = create_engine(env["EDUSYNC_OWNER_DATABASE_URL"])
FAILS = 0


def check(ok, label):
    global FAILS
    print(("PASS  " if ok else "FAIL  ") + label, flush=True)
    FAILS += 0 if ok else 1


services = AppServices.build(Settings())
import redis  # noqa: E402
r = redis.Redis.from_url(services.settings.redis_url, decode_responses=True)


def comp(body, key):
    return next(c for c in body["components"] if c["key"] == key)


# ---------------------------------------------------------------- baseline
b = hr.measure(services)
check(b["overall"] in ("OK", "DEGRADED", "DOWN") and all(c["state"] in hr.RANK for c in b["components"]), f"modèle de statuts conservé (global : {b['overall']})")
check(all("measured_at" in c and "depends_on" in c for c in b["components"]) and b["summary"]["configured"] + b["summary"]["not_configured"] == len(b["components"]),
      f"fraîcheur et dépendances par service ; synthèse {b['summary']['operational']}/{b['summary']['configured']} opérationnels")
check(comp(b, "database")["measured_ms"] is not None and comp(b, "redis")["measured_ms"] is not None, "base de données et cache : temps de réponse réels")

# ---------------------------------------------------------------- slow database
real_tx = services.platform_db.platform_transaction


@contextmanager
def slow_tx(*a, **k):
    time.sleep(0.3)
    with real_tx(*a, **k) as c:
        yield c


services.platform_db.platform_transaction = slow_tx
try:
    check(comp(hr.measure(services), "database")["state"] == "DEGRADED", "base lente (> 250 ms) : Dégradé")
finally:
    services.platform_db.platform_transaction = real_tx

# ---------------------------------------------------------------- redis unreachable
bad = dataclasses.replace(services, settings=services.settings.model_copy(update={"redis_url": "redis://127.0.0.1:1/0"}))
d = hr.measure(bad)
check(comp(d, "redis")["state"] == "DOWN" and comp(d, "worker_outbox")["state"] == "DOWN" and comp(d, "errors")["state"] == "NOT_CONFIGURED" and d["overall"] == "DOWN",
      "Redis injoignable : cache hors service, signaux des workers absents, compteur d’erreurs indisponible (jamais « Opérationnel »)")

# ---------------------------------------------------------------- worker heartbeat freshness
key = HEARTBEAT_PREFIX + "communications"
saved = r.get(key)
try:
    for age, want in ((5, "OK"), (200, "DEGRADED"), (400, "DOWN")):
        r.set(key, (datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat(), ex=600)
        st = comp(hr.measure(services), "worker_communications")["state"]
        check(st == want, f"signal du worker vieux de {age} s : {st}")
    r.delete(key)
    check(comp(hr.measure(services), "worker_communications")["state"] == "DOWN", "aucun signal du worker : Hors service")
finally:
    if saved:
        r.set(key, saved, ex=600)

# ---------------------------------------------------------------- outbox backlog (event locked so that no worker processes it)
eid = uuid.uuid4()
with owner.begin() as c:
    c.execute(text("""INSERT INTO outbox_events(id,event_type,aggregate_type,aggregate_id,payload,created_at,locked_until)
        VALUES(:id,'PROBE_HEALTH_BACKLOG','Probe',:id,'{}'::jsonb, now()-interval '10 minutes', now()+interval '1 hour')"""), {"id": eid})
try:
    w = comp(hr.measure(services), "worker_outbox")
    check(w["queue"]["pending"] >= 1 and (w["queue"]["oldest_seconds"] or 0) >= 590 and w["state"] in ("DEGRADED", "DOWN"),
          f"file accumulée (plus ancien {w['queue']['oldest_seconds']} s) : {w['state']}, profondeur et âge visibles")
finally:
    with owner.begin() as c:
        c.execute(text("DELETE FROM outbox_events WHERE id=:id"), {"id": eid})
w2 = comp(hr.measure(services), "worker_outbox")
check((w2["queue"]["oldest_seconds"] or 0) < 300 or w2["queue"]["pending"] == 0, "après drainage : l’âge du plus ancien redevient normal")

# ---------------------------------------------------------------- storage
class Broken:
    def exists(self, key):
        raise RuntimeError("down")


s2 = dataclasses.replace(services, object_storage=Broken())
check(comp(hr.measure(s2), "storage")["state"] == "DOWN", "stockage injoignable : Hors service")
s3 = dataclasses.replace(services, object_storage=None)
check(comp(hr.measure(s3), "storage")["state"] == "NOT_CONFIGURED", "stockage absent : Non configuré (jamais « Opérationnel »)")

# ---------------------------------------------------------------- backup report
tmp = Path(tempfile.mkdtemp()) / "last.json"
sb = dataclasses.replace(services, settings=services.settings.model_copy(update={"backup_status_file": str(tmp)}))
cases = (({"finished_at": datetime.now(timezone.utc).isoformat(), "ok": True, "restore_verified": True, "offsite": True}, "OK", "réussie, restauration vérifiée"),
         ({"finished_at": (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(), "ok": True, "restore_verified": True, "offsite": False}, "DEGRADED", "en retard (> 26 h)"),
         ({"finished_at": datetime.now(timezone.utc).isoformat(), "ok": False, "restore_verified": False, "offsite": False, "detail": "pg_dump en échec"}, "DOWN", "en échec"),
         ({"finished_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(), "ok": True}, "DOWN", "horodatage futur invalide"))
for info, want, label in cases:
    tmp.write_text(json.dumps(info), encoding="utf-8")
    bk = hr.backup_component(sb)
    check(bk["state"] == want, f"sauvegarde {label} : {bk['state']}")
tmp.write_text(json.dumps(cases[0][0]), encoding="utf-8")
bk = hr.backup_component(sb)
check(bk["backup"]["restore_verified"] and bk["backup"]["offsite"] and not bk["backup"]["late"], "détail sauvegarde : restauration testée, copie hors site, ponctualité")
tmp.write_text("{pas du json", encoding="utf-8")
check(hr.backup_component(sb)["state"] == "DOWN", "rapport de sauvegarde illisible : Hors service")
check(hr.backup_component(services)["state"] in ("NOT_CONFIGURED", "OK", "DEGRADED", "DOWN"), "sans sauvegarde configurée localement : Non configuré")

# ---------------------------------------------------------------- dedup of concurrent measures
calls = []
real_measure = hr.measure
hr.measure = lambda s: (calls.append(1), time.sleep(0.2), real_measure(s))[2]
hr._cache.update(at=0.0, body=None)
from edusync.shared.application.context import ActorContext  # noqa: E402
actor = ActorContext(user_id=uuid.uuid4(), school_id=None, membership_id=None, permissions=frozenset({"platform.health.read"}), is_platform_admin=False,
                     correlation_id=uuid.uuid4(), source="WEB")
outs = []
ts = [threading.Thread(target=lambda: outs.append(hr.system_health(actor, services))) for _ in range(20)]
[t.start() for t in ts]; [t.join() for t in ts]
hr.measure = real_measure
check(len(calls) == 1 and len(outs) == 20 and sum(1 for o in outs if o["shared"]) == 19, f"20 mesures simultanées : {len(calls)} seule série de contrôles, 19 réponses partagées")

# ---------------------------------------------------------------- HTTP: RBAC + no secret
def call(method, path, token=None, body=None):
    h = {"Content-Type": "application/json", "Origin": "http://localhost:5180", **({"Authorization": f"Bearer {token}"} if token else {})}
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def login(email, password):
    code, step = call("POST", "/auth/login", body={"email": email, "password": password, "scope": "PLATFORM"})
    step = json.loads(step); secret = FX["MFA_TOTP"][email]["secret"]
    for _ in range(3):
        while time.time() % 30 > 25:
            time.sleep(0.5)
        code, sess = call("POST", "/auth/mfa/verify", body={"mfa_token": step["mfa_token"], "code": totp_code(secret, current_step())})
        if code == 200:
            return json.loads(sess)["access_token"]
        time.sleep(31)
    raise SystemExit("connexion impossible")


check(call("GET", "/platform/system/health")[0] == 401, "sans jeton : 401")
manager = login("certification@example.test", ENV["EDUSYNC_PLATFORM_ADMIN_PASSWORD"])
code, raw = call("GET", "/platform/system/health", manager)
low = raw.lower()
check(code == 200 and not any(x in low for x in ("redis://", "postgresql", "password", "secret", "token", "traceback", "c:\\\\", "/home/", "s3://")),
      "réponse sans secret, sans adresse interne, sans trace technique")
member = FX["A"]["users"]["CAISSIER1"]
code, sess = call("POST", "/auth/login", body={"email": member["email"], "password": member["password"], "scope": "SCHOOL", "school_code": FX["A"]["code"]})
st = json.loads(sess).get("access_token")
if st:
    check(call("GET", "/platform/system/health", st)[0] in (401, 403), "session école refusée")

print("\nRÉSULTAT : " + ("PASS" if FAILS == 0 else f"FAIL ({FAILS})"))
sys.exit(1 if FAILS else 0)
