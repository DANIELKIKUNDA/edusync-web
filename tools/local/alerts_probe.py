"""Local probe of the platform alerts (lot 2026-10).

Against the real local database: a component « Hors service » opens an incident; nothing is sent before 5 minutes;
after 5 minutes ONE e-mail per recipient (Managers Système + extra addresses) is queued through the transactional
outbox; repeated evaluations never send twice; the recovery closes the incident and sends ONE resolution e-mail; a
short outage (< 5 min) closes silently; two concurrent evaluators never double-send (advisory lock); RBAC of the
recipient routes; the communications worker really delivers the alert (simulated e-mail provider locally).
Everything created is removed at the end. Usage: EDUSYNC_LOCAL_PG_PORT=54432 python tools/local/alerts_probe.py
"""
from __future__ import annotations

import os
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend/src")); sys.path.insert(0, str(ROOT / "tools/local"))
import edusync_local as L  # noqa: E402

env = L.load_env("demo")
os.environ.update({k: v for k, v in env.items() if k.startswith("EDUSYNC_")})
from sqlalchemy import create_engine, text  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from edusync.bootstrap.app import create_app  # noqa: E402
from edusync.bootstrap.dependencies import require_platform_actor  # noqa: E402
from edusync.modules.platform_health.application import alerts  # noqa: E402
from edusync.shared.application.context import ActorContext  # noqa: E402

owner = create_engine(env["EDUSYNC_OWNER_DATABASE_URL"])
FAILS = 0
TAG = f"probe-{uuid.uuid4().hex[:6]}"


def check(ok, label):
    global FAILS
    print(("PASS  " if ok else "FAIL  ") + label, flush=True)
    FAILS += 0 if ok else 1


def sql(q, **p):
    with owner.begin() as c:
        res = c.execute(text(q), p)
        return res.mappings().all() if res.returns_rows else res.rowcount


app = create_app()
services = app.state.services
T0 = datetime.now(timezone.utc)
KEY = f"probe_{uuid.uuid4().hex[:6]}"


def body(state):
    return {"components": [{"key": KEY, "label": "Composant de sonde", "state": state, "detail": "Injoignable (sonde)"}]}


def messages():
    return sql("""SELECT m.id, m.subject, m.recipient_count FROM communication_messages m
        WHERE m.template_code='PLATFORM_ALERT' AND m.idempotency_key LIKE 'platform-incident:%' AND m.created_at >= :t ORDER BY m.created_at""", t=T0)


managers = sql("""SELECT count(DISTINCT u.id) n FROM users u JOIN rbac_assignments a ON a.user_id=u.id AND a.school_id IS NULL AND a.active
    JOIN rbac_roles r ON r.id=a.role_id AND r.code='MANAGER_SYSTEME' AND r.status='ACTIVE' WHERE u.active AND u.email IS NOT NULL""")[0]["n"]
extra = f"astreinte-{TAG}@example.test"
sql("INSERT INTO platform_alert_recipients(email, label) VALUES (:e, 'Sonde')", e=extra)
try:
    # ------------------------------------------------------------ outage: open, wait, notify once
    r1 = alerts.evaluate(services, body=body("DOWN"), now=T0)
    check(r1["opened"] == [KEY] and not r1["notified"] and not messages(), "panne détectée : incident ouvert, aucun e-mail avant 5 minutes")
    r2 = alerts.evaluate(services, body=body("DOWN"), now=T0 + timedelta(minutes=3))
    check(not r2["notified"] and not messages(), "toujours en panne à 3 min : pas d’e-mail")
    r3 = alerts.evaluate(services, body=body("DOWN"), now=T0 + timedelta(minutes=5, seconds=5))
    m = messages()
    check(r3["notified"] == [KEY] and len(m) == 1 and m[0]["recipient_count"] == managers + 1,
          f"panne > 5 min : un e-mail à {m[0]['recipient_count'] if m else 0} destinataire(s) ({managers} Manager(s) + l’adresse d’astreinte)")
    check(m and "hors service" in m[0]["subject"], f"objet clair : « {m[0]['subject'] if m else ''} »")
    alerts.evaluate(services, body=body("DOWN"), now=T0 + timedelta(minutes=8))
    alerts.evaluate(services, body=body("DOWN"), now=T0 + timedelta(minutes=12))
    check(len(messages()) == 1, "évaluations suivantes : jamais de deuxième e-mail pour le même incident")
    # ------------------------------------------------------------ recovery
    r4 = alerts.evaluate(services, body=body("OK"), now=T0 + timedelta(minutes=15))
    m = messages()
    inc = sql("SELECT * FROM platform_incidents WHERE component_key=:k", k=KEY)
    check(r4["resolved"] == [KEY] and len(m) == 2 and "Résolu" in m[1]["subject"], "retour à la normale : incident résolu, un e-mail de résolution")
    check(len(inc) == 1 and inc[0]["resolved_at"] and inc[0]["notified_at"] and inc[0]["resolution_notified_at"], "historique : ouverture, notification, résolution enregistrées")
    # ------------------------------------------------------------ short outage: silent
    alerts.evaluate(services, body=body("DOWN"), now=T0 + timedelta(minutes=20))
    alerts.evaluate(services, body=body("OK"), now=T0 + timedelta(minutes=22))
    check(len(messages()) == 2 and len(sql("SELECT 1 FROM platform_incidents WHERE component_key=:k", k=KEY)) == 2, "panne courte (< 5 min) : tracée, aucun e-mail")
    # ------------------------------------------------------------ concurrency: advisory lock
    alerts.evaluate(services, body=body("DOWN"), now=T0 + timedelta(minutes=30))
    outs = []
    ts = [threading.Thread(target=lambda: outs.append(alerts.evaluate(services, body=body("DOWN"), now=T0 + timedelta(minutes=36)))) for _ in range(6)]
    [t.start() for t in ts]; [t.join() for t in ts]
    check(sum(len(o["notified"]) for o in outs) == 1 and len(messages()) == 3, f"6 évaluateurs simultanés : un seul envoi ({sum(o['skipped'] for o in outs)} écartés par le verrou)")
    alerts.evaluate(services, body=body("OK"), now=T0 + timedelta(minutes=40))

    # ------------------------------------------------------------ delivery by the worker (simulated provider locally)
    deadline = time.time() + 40
    st = []
    while time.time() < deadline:
        st = sql("""SELECT d.status FROM communication_deliveries d JOIN communication_messages m ON m.id=d.message_id
            WHERE m.id=:m""", m=messages()[0]["id"])
        if st and all(x["status"] in ("SENT", "DELIVERED", "FAILED_PERMANENT", "CANCELLED") for x in st):
            break
        time.sleep(2)
    check(st and any(x["status"] in ("SENT", "DELIVERED") for x in st), f"le worker remet l’alerte : {sorted({x['status'] for x in st})}")

    # ------------------------------------------------------------ routes + RBAC
    def actor(perms):
        return ActorContext(user_id=uuid.UUID("856ce025-c5e6-4f2b-ae4f-331f33b62e75"), school_id=None, membership_id=None, permissions=frozenset(perms),
                            is_platform_admin=False, correlation_id=uuid.uuid4(), source="WEB")
    c = TestClient(app, base_url="http://localhost")
    app.dependency_overrides[require_platform_actor] = lambda: actor({"platform.health.read"})
    j = c.get("/api/v1/platform/system/health/incidents").json()
    check(any(i["component_key"] == KEY and i["resolved_at"] for i in j["incidents"]) and j["recipients"]["managers"] == managers,
          "historique des incidents et destinataires visibles en lecture")
    check(all("…@" in x["email"] for x in j["recipients"]["extra"]) and not j["recipients"]["can_manage"], "lecture seule : adresses masquées")
    check(c.post("/api/v1/platform/system/health/alert-recipients", json={"email": "x@example.test"}).status_code == 403 and
          c.post("/api/v1/platform/system/health/alerts/test").status_code == 403, "ajout d’adresse et test réservés aux Managers : 403")
    app.dependency_overrides.clear()
    check(c.get("/api/v1/platform/system/health/incidents").status_code == 401, "sans jeton : 401")

    # ------------------------------------------------------------ real HTTP: Manager adds an address (step-up), sends a test
    import json, urllib.request, urllib.error
    from edusync.shared.infrastructure.mfa import current_step, totp_code
    API = "http://127.0.0.1:58100/api/v1"
    FX = json.loads((ROOT / ".local/claude-fixtures-edusync_claude_fresh.json").read_text(encoding="utf-8"))
    ENV = {l.split("=", 1)[0]: l.rstrip("\n").split("=", 1)[1] for l in (ROOT / ".local/certification.env").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#")}

    def call(method, path, token=None, body=None):
        h = {"Content-Type": "application/json", "Origin": "http://localhost:5180", **({"Authorization": f"Bearer {token}"} if token else {})}
        req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode(); return resp.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, raw

    def code_now():
        while time.time() % 30 > 25:
            time.sleep(0.5)
        return totp_code(FX["MFA_TOTP"]["certification@example.test"]["secret"], current_step())

    _, step = call("POST", "/auth/login", body={"email": "certification@example.test", "password": ENV["EDUSYNC_PLATFORM_ADMIN_PASSWORD"], "scope": "PLATFORM"})
    tok = None
    for _ in range(3):
        st_, sess = call("POST", "/auth/mfa/verify", body={"mfa_token": step["mfa_token"], "code": code_now()})
        if st_ == 200:
            tok = sess["access_token"]; break
        time.sleep(31)
    addr = f"astreinte2-{TAG}@example.test"
    # the sign-in code counts as a fresh confirmation for a few minutes: age it to prove the code is asked again
    sql("""UPDATE user_device_sessions SET mfa_stepup_at=now()-interval '2 hours' WHERE user_id=(SELECT id FROM users WHERE email='certification@example.test')
        AND created_at >= :t""", t=T0)
    st1, b1 = call("POST", "/platform/system/health/alert-recipients", tok, {"email": addr, "label": "Astreinte"})
    check(st1 == 403 and isinstance(b1.get("detail"), dict) and b1["detail"].get("code") == "MFA_STEP_UP_REQUIRED", "ajout d’une adresse : confirmation par code exigée")
    time.sleep(31)                                    # a TOTP step is single-use: wait for the next one
    st2, _ = call("POST", "/auth/platform/mfa/step-up", tok, {"code": code_now()})
    st3, b3 = call("POST", "/platform/system/health/alert-recipients", tok, {"email": addr, "label": "Astreinte"})
    st4, _ = call("POST", "/platform/system/health/alert-recipients", tok, {"email": addr.upper()})
    check(st2 in (200, 204) and st3 == 201 and st4 == 409, f"[{st2},{st3},{st4}] après confirmation : adresse ajoutée ; doublon refusé (409)")
    st5, b5 = call("POST", "/platform/system/health/alerts/test", tok)
    check(st5 == 200 and b5["recipients"] >= 2, f"e-mail de test envoyé à {b5.get('recipients') if isinstance(b5, dict) else '?'} destinataire(s)")
    deadline = time.time() + 40
    sent = []
    while time.time() < deadline:
        sent = sql("""SELECT d.status, d.destination FROM communication_deliveries d JOIN communication_messages m ON m.id=d.message_id
            WHERE m.idempotency_key LIKE 'platform-alert-test:%' AND m.created_at >= :t""", t=T0)
        if sent and all(x["status"] != "QUEUED" for x in sent):
            break
        time.sleep(2)
    check(any(x["destination"] == addr and x["status"] == "SENT" for x in sent), "l’adresse d’astreinte reçoit le test (remis par le worker)")
    _, j = call("GET", "/platform/system/health/incidents", tok)
    rid = next(x["id"] for x in j["recipients"]["extra"] if x["email"] == addr)
    st6, _ = call("POST", f"/platform/system/health/alert-recipients/{rid}/remove", tok)
    check(st6 == 200 and len(sql("SELECT 1 FROM audit_events WHERE action IN ('PLATFORM_ALERT_RECIPIENT_ADDED','PLATFORM_ALERT_RECIPIENT_REMOVED','PLATFORM_ALERT_TEST_SENT') AND occurred_at >= :t", t=T0)) >= 3,
          "retrait de l’adresse ; ajout, test et retrait journalisés")
finally:
    sql("DELETE FROM platform_alert_recipients WHERE email LIKE :e", e=f"%{TAG}%")
    sql("DELETE FROM platform_incidents WHERE component_key=:k", k=KEY)
    sql("DELETE FROM platform_alert_recipients WHERE email=:e", e=extra)

print("\nRÉSULTAT : " + ("PASS" if FAILS == 0 else f"FAIL ({FAILS})"))
sys.exit(1 if FAILS else 0)
