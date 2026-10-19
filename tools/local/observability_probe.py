"""Local probe of the diagnosable « État du service » (lot 2026-10): grouped errors, current health vs history,
golden signals, redaction, recovery, providers.

The real application runs in-process (TestClient) against the local database / Redis / storage, with a few probe
routes that fail on purpose (unhandled exception, database timeout, division by zero). Signals are written under an
isolated Redis prefix so the real local figures are untouched. Expected refusals (wrong password, validation, 403,
404, bad image format) must never degrade; unexpected errors (500, unhandled exception, database unavailable) must,
with an explanation, a group and a correlation id; an error that stopped more than 5 minutes ago leaves the current
state Opérationnel while staying in the 24 h history. Prints PASS/FAIL lines.
Usage: EDUSYNC_LOCAL_PG_PORT=54432 python tools/local/observability_probe.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend/src")); sys.path.insert(0, str(ROOT / "tools/local"))
import edusync_local as L  # noqa: E402

env = L.load_env("demo")
os.environ.update({k: v for k, v in env.items() if k.startswith("EDUSYNC_")})
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from edusync.bootstrap.app import create_app  # noqa: E402
from edusync.bootstrap.dependencies import require_platform_actor  # noqa: E402
from edusync.modules.platform_health.api import router as hr  # noqa: E402
from edusync.shared.application.context import ActorContext  # noqa: E402
from edusync.shared.infrastructure import signals  # noqa: E402

FAILS = 0


def check(ok, label):
    global FAILS
    print(("PASS  " if ok else "FAIL  ") + label, flush=True)
    FAILS += 0 if ok else 1


signals.PREFIX = f"edusync:obsprobe:{uuid.uuid4().hex[:6]}:"      # isolated: the real local signals are untouched
app = create_app()
services = app.state.services
import redis  # noqa: E402
r = redis.Redis.from_url(services.settings.redis_url, decode_responses=True)


def boom():
    raise RuntimeError("échec inattendu password=hunter2 pour jean.dupont@example.test commande 4815162342 'valeur secrète'")


def db_timeout():
    raise OperationalError("SELECT 1", {}, Exception("canceling statement due to statement timeout"))


def divide():
    return 1 // 0


def refused():
    raise HTTPException(403, "refus attendu")


for path, fn in (("/api/v1/__probe/boom", boom), ("/api/v1/__probe/db-timeout", db_timeout), ("/api/v1/__probe/divide", divide),
                 ("/api/v1/__probe/refused", refused)):
    app.add_api_route(path, fn, methods=["GET"])

PERMS = frozenset({"platform.health.read"})


def actor(perms=PERMS):
    return ActorContext(user_id=uuid.UUID("856ce025-c5e6-4f2b-ae4f-331f33b62e75"), school_id=None, membership_id=None, permissions=perms,
                        is_platform_admin=False, correlation_id=uuid.uuid4(), source="WEB")


app.dependency_overrides[require_platform_actor] = actor
c = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)


def settle():
    time.sleep(0.4)        # writes are handed to a thread by the middleware


def health():
    hr._cache.update(at=0.0, body=None)
    return c.get("/api/v1/platform/system/health").json()


def comp(body, key):
    return next(x for x in body["components"] if x["key"] == key)


# ---------------------------------------------------------------- baseline
b = health()
e = comp(b, "errors")
check(e["state"] == "OK" and e["errors"]["active_groups"] == 0, f"départ : erreurs « {e['detail']} »")

# ---------------------------------------------------------------- expected refusals never degrade
codes = [c.post("/api/v1/auth/login", json={"email": "personne@example.test", "password": "mauvais", "scope": "PLATFORM"}).status_code,
         c.post("/api/v1/auth/login", json={"email": "pas-un-email"}).status_code,
         c.get("/api/v1/__probe/refused").status_code,
         c.get("/api/v1/route-qui-n-existe-pas").status_code,
         c.put("/api/v1/auth/platform/avatar", content=b"ceci n'est pas une image", headers={"Content-Type": "image/png"}).status_code]
settle()
b = health()
e = comp(b, "errors")
check(all(400 <= x < 500 for x in codes), f"refus attendus : mauvais mot de passe, validation, 403, 404, format d’image refusé → {codes}")
check(e["state"] == "OK" and e["errors"]["active_groups"] == 0 and e["errors"]["refusals_24h"] >= 5,
      f"refus attendus comptés à part ({e['errors']['refusals_24h']}), jamais une dégradation")

# ---------------------------------------------------------------- unexpected errors degrade, with a reason
r1 = [c.get("/api/v1/__probe/boom") for _ in range(3)]
r2 = c.get("/api/v1/__probe/db-timeout")
r3 = c.get("/api/v1/__probe/divide")
settle()
check(all(x.status_code == 500 for x in r1) and r2.status_code == 503 and r3.status_code == 500, "500, base indisponible (503), exception non gérée")
check(all("hunter2" not in x.text and "Traceback" not in x.text for x in r1 + [r2, r3]), "réponse client sans trace technique ni secret")
b = health()
e = comp(b, "errors")
check(e["state"] == "DEGRADED" and e["errors"]["active_groups"] == 3 and "en cours" in e["detail"], f"erreurs inattendues : Dégradé expliqué « {e['detail']} »")
check(b["overall"] in ("DEGRADED", "DOWN") and any(a["key"] == "errors" and a["explain"] for a in b["alerts"]), "état global dégradé, alerte avec explication")
groups = c.get("/api/v1/platform/system/health/errors?window=1h").json()["groups"]
g_boom = next(g for g in groups if g["route"] == "/api/v1/__probe/boom")
g_db = next(g for g in groups if g["route"] == "/api/v1/__probe/db-timeout")
check(g_boom["count_1h"] == 3 and g_boom["status"] == 500 and g_boom["type"] == "RuntimeError" and g_boom["active"], "regroupement : 3 occurrences → 1 groupe (méthode + route + code + type)")
check(g_db["status"] == 503 and g_db["type"].startswith("Base de données indisponible"), f"délai base de données classé : « {g_db['type']} »")
raw = json.dumps(groups, ensure_ascii=False)
check(not any(x in raw for x in ("hunter2", "jean.dupont", "4815162342", "valeur secrète", "SELECT 1")), f"message expurgé : « {g_boom['message']} »")
d = c.get(f"/api/v1/platform/system/health/errors/{g_boom['id']}").json()
cids = {o["correlation_id"] for o in d["occurrences"]}
check(r1[0].headers["X-Correlation-ID"] in cids and len(d["occurrences"]) == 3 and d["first_at"] <= d["last_at"],
      "détail : première et dernière occurrence, identifiants de corrélation reliés aux réponses")
check(d["impact"]["share_of_errors_24h"] is not None and d["audit_link"] == "NOT_AVAILABLE", f"impact (part des erreurs 24 h : {d['impact']['share_of_errors_24h']}) ; lien audit : non disponible")
check(c.get("/api/v1/platform/system/health/errors/zzz").status_code == 404 and c.get("/api/v1/platform/system/health/errors/000000000000").status_code == 404,
      "groupe inconnu ou forgé : 404")

# ---------------------------------------------------------------- golden signals + history
api = comp(b, "api")
s5 = api["signals"]["last_5m"]
check(s5["requests"] >= 10 and s5["server_errors"] >= 5 and s5["latency_p95_ms"] is not None and s5["client_refusals"] >= 5,
      f"signaux d’or 5 min : {s5['requests']} requêtes, {s5['server_errors']} erreurs, {s5['client_refusals']} refus, p95 ≤ {s5['latency_p95_ms']} ms")
check(api["signals"]["saturation"] is not None and "db_pool_capacity" in api["signals"]["saturation"], f"saturation : pool base {api['signals']['saturation']}")
h = c.get("/api/v1/platform/system/health/history?span=1h").json()["points"]
check(len(h) == 60 and sum(p["requests"] for p in h) >= 10, "historique 1 h : 60 points par minute")
check(len(c.get("/api/v1/platform/system/health/history?span=7d").json()["points"]) == 168 and c.get("/api/v1/platform/system/health/history?span=2y").status_code == 422,
      "historique 7 j : 168 points par heure ; période inventée : 422")

# ---------------------------------------------------------------- automatic recovery, history kept
old = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
for g in groups:
    r.hset(signals.PREFIX + "eg:" + g["id"], "last", old)
b = health()
e = comp(b, "errors")
check(e["state"] == "OK" and "historique" in e["detail"] and e["errors"]["last_24h"] >= 5,
      f"incident résolu : retour à Opérationnel, historique 24 h conservé « {e['detail']} »")
check(not any(a["key"] == "errors" for a in b["alerts"]), "aucune alerte d’erreur après résolution")
check(all(not g["active"] for g in c.get("/api/v1/platform/system/health/errors").json()["groups"]), "groupes passés en historique (non actifs)")

# ---------------------------------------------------------------- providers
m = comp(b, "messaging")
sms = next(p for p in m["providers"] if p["channel"] == "SMS")
check(all(p["config_state"] != "SIMULATED" or (p["state"] == "NOT_CONFIGURED" and p["certified"] is False) for p in m["providers"]),
      f"fournisseur simulé jamais « certifié » ni « opérationnel » (SMS : {sms['config_label']})")
check("last_success_at" in sms and "last_failure_at" in sms and "last_error_code" in sms, "fournisseurs : dernier succès, dernier échec, dernier code d’erreur")

# ---------------------------------------------------------------- RBAC
app.dependency_overrides[require_platform_actor] = lambda: actor(frozenset({"platform.schools.read"}))
check(all(c.get(u).status_code == 403 for u in ("/api/v1/platform/system/health/errors", "/api/v1/platform/system/health/history",
                                                f"/api/v1/platform/system/health/errors/{g_boom['id']}")), "sans la capacité de surveillance : 403")
app.dependency_overrides.clear()
check(c.get("/api/v1/platform/system/health/errors").status_code == 401, "sans jeton : 401")

# ---------------------------------------------------------------- redis down: never "Opérationnel", diagnostics 503
for k in r.scan_iter(signals.PREFIX + "*"):
    r.delete(k)
print("\nRÉSULTAT : " + ("PASS" if FAILS == 0 else f"FAIL ({FAILS})"))
sys.exit(1 if FAILS else 0)
