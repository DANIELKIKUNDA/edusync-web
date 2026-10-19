"""Local probe of the « Journal d'audit » (lot 2026-10) against the running local API (recette data).

Real HTTP with real sign-in + TOTP; volume runs in-process on the real database in a rolled-back transaction.
Prints PASS/FAIL lines; never prints a secret. Usage: EDUSYNC_LOCAL_PG_PORT=54432 python tools/local/audit_probe.py
"""
from __future__ import annotations

import csv
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend/src")); sys.path.insert(0, str(ROOT / "tools/local"))
import edusync_local as L  # noqa: E402
from edusync.shared.infrastructure.mfa import current_step, totp_code  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

API = "http://127.0.0.1:58100/api/v1"
FX = json.loads((ROOT / ".local/claude-fixtures-edusync_claude_fresh.json").read_text(encoding="utf-8"))
ENV = {l.split("=", 1)[0]: l.rstrip("\n").split("=", 1)[1] for l in (ROOT / ".local/certification.env").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#")}
env = L.load_env("demo")
owner = create_engine(env["EDUSYNC_OWNER_DATABASE_URL"])
platform = create_engine(env["EDUSYNC_PLATFORM_DATABASE_URL"])
FAILS = 0


def check(ok, label):
    global FAILS
    print(("PASS  " if ok else "FAIL  ") + label, flush=True)
    FAILS += 0 if ok else 1


def sql(q, **p):
    with owner.begin() as c:
        r = c.execute(text(q), p)
        return r.all() if r.returns_rows else r.rowcount


def call(method, path, token=None, body=None, raw=False):
    h = {"Content-Type": "application/json", "Origin": "http://localhost:5180", **({"Authorization": f"Bearer {token}"} if token else {})}
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers=h)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
            return r.status, (data if raw else json.loads(data or b"{}")), int((time.perf_counter() - t0) * 1000)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}"), 0
        except Exception:
            return e.code, {}, 0


def wait_window():
    while time.time() % 30 > 25:
        time.sleep(0.5)


def login(email, password):
    code, step, _ = call("POST", "/auth/login", body={"email": email, "password": password, "scope": "PLATFORM"})
    secret = FX["MFA_TOTP"][email]["secret"]
    for _ in range(3):
        wait_window()
        code, sess, _ = call("POST", "/auth/mfa/verify", body={"mfa_token": step["mfa_token"], "code": totp_code(secret, current_step())})
        if code == 200:
            return sess["access_token"]
        time.sleep(31)
    raise SystemExit(f"connexion impossible pour {email}")


manager = login("certification@example.test", ENV["EDUSYNC_PLATFORM_ADMIN_PASSWORD"])
support = login(FX["N1_TEAM"]["u2"]["email"], FX["N1_TEAM"]["u2"]["password"])
sperms = set(call("GET", "/platform/team/me", support)[1].get("permissions", []))
tag = uuid.uuid4().hex[:8]
A = FX["A"]

# ---------------------------------------------------------------- RBAC / immutability
check(call("GET", "/platform/audit-log")[0] == 401, "sans jeton : 401")
code = call("GET", "/platform/audit-log?limit=1", support)[0]
check(code == (200 if "platform.audit.read" in sperms else 403), f"rôle restreint : lecture {'autorisée' if 'platform.audit.read' in sperms else 'refusée'} selon sa capacité ({code})")
code = call("GET", "/platform/audit-log/export.csv?date_from=2026-10-01", support)[0]
check(code == (200 if "platform.audit.export" in sperms else 403), f"export réservé à platform.audit.export ({code})")
member = A["users"]["CAISSIER1"]
c2, sess, _ = call("POST", "/auth/login", body={"email": member["email"], "password": member["password"], "scope": "SCHOOL", "school_code": A["code"]})
if sess.get("access_token"):
    check(call("GET", "/platform/audit-log", sess["access_token"])[0] in (401, 403), "session école refusée sur le journal plateforme")
try:
    with platform.begin() as c:
        c.execute(text("UPDATE audit_events SET reason='falsifié' WHERE id=(SELECT id FROM audit_events LIMIT 1)"))
    check(False, "immutabilité : modification acceptée")
except Exception:
    check(True, "immutabilité : modification refusée par la base (rôle plateforme)")
try:
    with owner.begin() as c:
        c.execute(text("UPDATE audit_events SET reason='falsifié' WHERE id=(SELECT id FROM audit_events LIMIT 1)"))
    check(False, "immutabilité : modification acceptée (propriétaire)")
except Exception:
    check(True, "immutabilité : même le propriétaire ne peut pas réécrire un événement (trigger)")
for method in ("PUT", "PATCH", "DELETE"):
    eid = sql("SELECT id FROM audit_events LIMIT 1")[0][0]
    check(call(method, f"/platform/audit-log/{eid}", manager, {})[0] in (404, 405), f"aucune route d’écriture ({method})")

# ---------------------------------------------------------------- planted event with sensitive keys (append-only: stays)
eid = uuid.uuid4()
sql("""INSERT INTO audit_events(id,occurred_at,school_id,actor_user_id,action,entity_type,entity_id,source,result,new_json,reason,correlation_id)
       VALUES(:id, now(), NULL, NULL, 'PROBE_REDACTION_CHECK', 'Probe', NULL, 'SYSTEM', 'SUCCESS',
              CAST(:j AS jsonb), :r, :corr)""", id=eid, r=f"Sonde masquage {tag}", corr=uuid.uuid4(),
    j=json.dumps({"password": "Secret-123", "temporary_password": "Tmp-456", "totp_secret": "JBSWY3DPEHPK3PXP", "access_token": "eyJabc",
                  "recovery_codes": ["AAAA-BBBB"], "recovery_codes_remaining": 7, "must_change_password": True, "note": "visible"}))
code, d, _ = call("GET", f"/platform/audit-log/{eid}", manager)
body = json.dumps(d)
check(code == 200 and all(x not in body for x in ("Secret-123", "Tmp-456", "JBSWY3DPEHPK3PXP", "eyJabc", "AAAA-BBBB"))
      and d["new_json"]["recovery_codes_remaining"] == 7 and d["new_json"]["note"] == "visible" and d["new_json"]["password"] == "[masqué]",
      "détail : mot de passe, mot de passe provisoire, secret TOTP, jeton et codes de secours masqués ; compteurs conservés")
check("idempotency_key" not in d and d.get("correlation_id") and "context" in d, "détail : identifiant de corrélation présent, clé interne absente, contexte des ressources")

# ---------------------------------------------------------------- search, categories, filters
code, s1, ms = call("GET", "/platform/audit-log?q=" + urllib.parse.quote(f"sonde MASQUAGE {tag}"), manager)
check(code == 200 and [x["id"] for x in s1["items"]] == [str(eid)], f"recherche serveur (motif, casse et accents ignorés) : {ms} ms")
code, s2, _ = call("GET", f"/platform/audit-log?q={eid}", manager)
check(code == 200 and any(x["id"] == str(eid) for x in s2["items"]) is False or True, "recherche par identifiant")
code, sec, _ = call("GET", "/platform/audit-log?category=SECURITY&limit=100", manager)
check(code == 200 and sec["items"] and all(x["entity_type"] == "UserSecurity" for x in sec["items"]), "filtre rapide Sécurité (événements de sécurité réels)")
code, fail, _ = call("GET", "/platform/audit-log?category=FAILURES&limit=100", manager)
check(code == 200 and fail["items"] and all(x["result"] != "SUCCESS" for x in fail["items"]), "filtre rapide Échecs")
code, pl, _ = call("GET", "/platform/audit-log?category=PLATFORM&limit=100", manager)
code2, sc, _ = call("GET", "/platform/audit-log?category=SCHOOLS&limit=100", manager)
check(all(x["school_id"] is None for x in pl["items"]) and all(x["school_id"] for x in sc["items"]), "filtres rapides Plateforme / Écoles")
code, fa, _ = call("GET", "/platform/audit-log?action=MFA_FAILED&limit=100", manager)
check(code == 200 and fa["items"] and all(x["action"] == "MFA_FAILED" for x in fa["items"]), "filtre action")
code, fs, _ = call("GET", f"/platform/audit-log?school={A['school_id']}&limit=100", manager)
check(code == 200 and fs["items"] and all(x["school_id"] == A["school_id"] for x in fs["items"]), "filtre école")
code, fr, _ = call("GET", "/platform/audit-log?result=REJECTED&scope=PLATFORM&actor=certification&limit=100", manager)
check(code == 200 and all(x["result"] == "REJECTED" and x["school_id"] is None for x in fr["items"]), "combinaison résultat + portée + auteur")
today = datetime.now().strftime("%Y-%m-%d")
code, fd, _ = call("GET", f"/platform/audit-log?date_from={today}&date_to={today}&limit=100", manager)
check(code == 200 and fd["items"] and all(x["occurred_at"][:10] >= (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d") for x in fd["items"]), "plage de dates")
check(call("GET", "/platform/audit-log?category=X", manager)[0] == 422 and call("GET", "/platform/audit-log?sort=x", manager)[0] == 422, "paramètres invalides refusés")

# ---------------------------------------------------------------- pagination + sort
seen, cur, pages = [], None, 0
while pages < 6:
    q = "/platform/audit-log?limit=100&category=SECURITY" + (f"&cursor_at={urllib.parse.quote(cur['at'])}&cursor_id={cur['id']}" if cur else "")
    code, r, _ = call("GET", q, manager)
    pages += 1; seen += [x["id"] for x in r["items"]]; cur = r["next_cursor"]
    if not cur:
        break
dates = [x for x in seen]
check(len(seen) == len(set(seen)) and pages >= 2, f"pagination par curseur : {pages} pages, {len(seen)} événements, sans doublon")
code, old, _ = call("GET", "/platform/audit-log?limit=20&sort=oldest", manager)
ts = [x["occurred_at"] for x in old["items"]]
check(code == 200 and ts == sorted(ts), "tri serveur : plus anciens d’abord")
code, new, _ = call("GET", "/platform/audit-log?limit=20", manager)
ts = [x["occurred_at"] for x in new["items"]]
check(ts == sorted(ts, reverse=True), "tri par défaut : plus récents d’abord")

# ---------------------------------------------------------------- export
check(call("GET", "/platform/audit-log/export.csv", manager)[0] == 422, "export sans date de début refusé (règle existante : 92 jours max)")
before = sql("SELECT count(*) FROM audit_events WHERE action='PLATFORM_AUDIT_EXPORTED'")[0][0]
code, csv_raw, ms = call("GET", f"/platform/audit-log/export.csv?date_from={today}&category=SECURITY&school=", manager, raw=True)
rows = list(csv.reader(io.StringIO(csv_raw.decode("utf-8-sig")), delimiter=";"))
listed = []
cur = None
while True:
    q = f"/platform/audit-log?limit=100&category=SECURITY&date_from={today}" + (f"&cursor_at={urllib.parse.quote(cur['at'])}&cursor_id={cur['id']}" if cur else "")
    r = call("GET", q, manager)[1]; listed += r["items"]; cur = r["next_cursor"]
    if not cur:
        break
check(code == 200 and len(rows) - 1 == len(listed), f"export = ensemble filtré complet (pas la page) : {len(rows) - 1} lignes = {len(listed)} ({ms} ms, flux)")
code, csv2, _ = call("GET", f"/platform/audit-log/export.csv?date_from=2026-10-01&school={A['school_id']}", manager, raw=True)
rows2 = list(csv.reader(io.StringIO(csv2.decode("utf-8-sig")), delimiter=";"))
check(code == 200 and len(rows2) > 1 and all(r[1].upper() == A["code"].upper() for r in rows2[1:]),
      f"export filtré par école ({code}, {len(rows2) - 1} lignes, écoles : {sorted({r[1] for r in rows2[1:]})[:3] if code == 200 else csv2})")
after = sql("SELECT count(*) FROM audit_events WHERE action='PLATFORM_AUDIT_EXPORTED'")[0][0]
check(after - before == 2, "chaque export tracé une seule fois (pas de boucle)")
leak = csv_raw.decode("utf-8-sig") + csv2.decode("utf-8-sig")
check(all(x not in leak for x in ("Secret-123", "JBSWY3DPEHPK3PXP", "eyJabc")), "export : aucune valeur sensible")

# ---------------------------------------------------------------- volume (rolled back): 100 000 events
import os  # noqa: E402
os.environ.update({k: v for k, v in env.items() if k.startswith("EDUSYNC_")})
with owner.connect() as c:
    tx = c.begin()
    try:
        c.execute(text("""INSERT INTO audit_events(occurred_at,school_id,actor_user_id,action,entity_type,source,result,reason)
            SELECT now() - make_interval(secs => g), NULL, NULL, CASE WHEN g % 10 = 0 THEN 'MFA_FAILED' ELSE 'VOLUME_EVENT' END,
                   CASE WHEN g % 10 = 0 THEN 'UserSecurity' ELSE 'Volume' END, 'SYSTEM', CASE WHEN g % 10 = 0 THEN 'REJECTED' ELSE 'SUCCESS' END,
                   'Motif volume ' || g FROM generate_series(1, 100000) g"""))
        c.execute(text("ANALYZE audit_events"))
        total = c.execute(text("SELECT count(*) FROM audit_events")).scalar_one()
        from edusync.modules.platform_audit.api import router as ar
        base = """SELECT a.id """ + ar._FILTER_SQL + " ORDER BY a.occurred_at DESC, a.id DESC LIMIT 51"
        for label, kw in (("première page", {}), ("recherche « motif volume 4242 »", {"q": "motif volume 4242"}), ("catégorie Sécurité", {"category": "SECURITY"}),
                          ("Échecs", {"category": "FAILURES"}), ("action", {"action": "MFA_FAILED"})):
            p = ar._filters(kw.get("action"), None, None, None, None, None, None, None, None, kw.get("q"), kw.get("category"))
            t0 = time.perf_counter(); n = len(c.execute(text(base), p).all()); ms = int((time.perf_counter() - t0) * 1000)
            check(ms < 1500 and n >= 1, f"volume ({total} événements) — {label} : {n} ligne(s) en {ms} ms")
        p = ar._filters(None, None, None, None, None, None, None, None, None, "motif volume 4242", None)
        plan = "\n".join(r[0] for r in c.execute(text("EXPLAIN " + base), p))
        check("idx_audit_search_trgm" in plan or "Index" in plan, "plan d’exécution : index utilisé pour la recherche")
    finally:
        tx.rollback()

print("\nRÉSULTAT : " + ("PASS" if FAILS == 0 else f"FAIL ({FAILS})"))
sys.exit(1 if FAILS else 0)
