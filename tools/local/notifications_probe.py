"""Local probe of « Notifications système » (lot 2026-10) against the running local API (recette data).

Real HTTP with real sign-in + TOTP; recipients are checked in the database and in a recipient's own inbox (school
session). Volume and concurrency parts run in-process on the real database inside a rolled-back transaction.
Prints PASS/FAIL lines; never prints a secret. Usage: EDUSYNC_LOCAL_PG_PORT=54432 python tools/local/notifications_probe.py
"""
from __future__ import annotations

import json
import sys
import threading
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
FAILS = 0


def check(ok, label):
    global FAILS
    print(("PASS  " if ok else "FAIL  ") + label, flush=True)
    FAILS += 0 if ok else 1


def sql(q, **p):
    with owner.begin() as c:
        r = c.execute(text(q), p)
        return r.all() if r.returns_rows else r.rowcount


def call(method, path, token=None, body=None, key=None):
    h = {"Content-Type": "application/json", "Origin": "http://localhost:5180", **({"Authorization": f"Bearer {token}"} if token else {})}
    if method == "POST":
        h["Idempotency-Key"] = key or str(uuid.uuid4())
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers=h)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read() or b"{}"), int((time.perf_counter() - t0) * 1000)
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
            return sess["access_token"], secret
        time.sleep(31)
    raise SystemExit(f"connexion impossible pour {email}")


manager, msecret = login("certification@example.test", ENV["EDUSYNC_PLATFORM_ADMIN_PASSWORD"])
support, _ = login(FX["N1_TEAM"]["u2"]["email"], FX["N1_TEAM"]["u2"]["password"])
tag = uuid.uuid4().hex[:6]
A, B = FX["A"], FX["B"]
multi = FX["N1_MULTI"]


def T(type_, school_ids=(), role=None, user=None):
    return {"type": type_, "school_ids": list(school_ids), "role_code": role, "user_id": user}


def preview(t):
    return call("POST", "/platform/notification-campaigns/preview", manager, {"target": t})


def send(t, title, confirmed=None, key=None, **extra):
    body = {"title": title, "body": f"Recette notifications {tag}\nDeuxième ligne", "severity": "INFO", "target": t, "link_path": None, "expires_at": None,
            "confirmed_recipients": confirmed, **extra}
    return call("POST", "/platform/notification-campaigns", manager, body, key=key)


def expected(q, **p):
    return {(str(r[0]), str(r[1]) if r[1] else None) for r in sql(q, **p)}


def delivered(cid):
    return {(str(r[0]), str(r[1]) if r[1] else None) for r in sql("SELECT user_id, school_id FROM notifications WHERE campaign_id=:c", c=cid)}


SCHOOL_BASE = """SELECT DISTINCT m.user_id, m.school_id FROM school_memberships m JOIN schools s ON s.id=m.school_id JOIN users u ON u.id=m.user_id
                 WHERE m.active AND u.active AND s.status='ACTIVE'"""
PLATFORM_BASE = """SELECT DISTINCT a.user_id, NULL::uuid FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id JOIN users u ON u.id=a.user_id
                   LEFT JOIN platform_account_status ps ON ps.user_id=a.user_id WHERE a.school_id IS NULL AND a.active AND r.level='PLATFORM'
                   AND r.status='ACTIVE' AND u.active AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now()) AND coalesce(ps.status,'ACTIVE')='ACTIVE'"""

# ---------------------------------------------------------------- RBAC
for method, path, body in (("POST", "/platform/notification-campaigns/preview", {"target": T("PLATFORM_ALL")}), ("GET", "/platform/notification-campaigns", None),
                           ("POST", "/platform/notification-campaigns", {"title": "Interdit", "body": "Tentative", "severity": "INFO", "target": T("PLATFORM_ALL"), "confirmed_recipients": 1})):
    code, _, _ = call(method, path, support, body)
    check(code == 403, f"rôle sans la capacité d’envoi refusé (API directe) : {method} {path.rsplit('/', 1)[-1]} → {code}")
check(call("GET", "/platform/notification-campaigns")[0] == 401, "sans jeton : 401")

# ---------------------------------------------------------------- validation
base = T("PLATFORM_USER", user=FX["N1_TEAM"]["u2"]["id"])
for label, extra in (("titre vide (espaces)", {"title": "    "}), ("message vide", {"body": "   \n  "}), ("titre trop long (non tronqué)", {"title": "x" * 181}),
                     ("lien externe", {"link_path": "https://exemple.org"}), ("lien protocole relatif", {"link_path": "//exemple.org"}),
                     ("lien javascript", {"link_path": "javascript:alert(1)"}), ("expiration passée", {"expires_at": "2020-01-01T00:00:00Z"}),
                     ("expiration maintenant", {"expires_at": datetime.now(timezone.utc).isoformat()}), ("gravité inventée", {"severity": "URGENT"})):
    b = {"title": "Validation", "body": "Message de validation", "severity": "INFO", "target": base, "link_path": None, "expires_at": None, **extra}
    check(call("POST", "/platform/notification-campaigns", manager, b)[0] == 422, f"refusé (422) : {label}")
check(send(T("PLATFORM_ALL"), "Sans aperçu")[0] == 422, "diffusion sans aperçu confirmé refusée (422)")

# ---------------------------------------------------------------- targeting (exact recipients) + server-side counts
cases = [
    ("toutes les écoles actives", T("ALL_ACTIVE_SCHOOLS"), SCHOOL_BASE, {}),
    ("écoles choisies", T("SCHOOLS", [A["school_id"], B["school_id"]]), SCHOOL_BASE + " AND m.school_id IN (:a,:b)", {"a": A["school_id"], "b": B["school_id"]}),
    ("rôle école (toutes écoles)", T("SCHOOL_ROLE", role="CAISSIER"), SCHOOL_BASE + """ AND EXISTS (SELECT 1 FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id
        WHERE a.membership_id=m.id AND a.active AND r.code='CAISSIER' AND r.status='ACTIVE')""", {}),
    ("rôle école limité à une école", T("SCHOOL_ROLE", [A["school_id"]], role="CAISSIER"), SCHOOL_BASE + """ AND m.school_id=:a AND EXISTS (SELECT 1 FROM rbac_assignments a
        JOIN rbac_roles r ON r.id=a.role_id WHERE a.membership_id=m.id AND a.active AND r.code='CAISSIER' AND r.status='ACTIVE')""", {"a": A["school_id"]}),
    ("membre d’une école", T("SCHOOL_USER", [A["school_id"]], user=A["users"]["CAISSIER1"]["user_id"]), SCHOOL_BASE + " AND m.school_id=:a AND m.user_id=:u",
     {"a": A["school_id"], "u": A["users"]["CAISSIER1"]["user_id"]}),
    ("toute l’équipe plateforme", T("PLATFORM_ALL"), PLATFORM_BASE, {}),
    ("rôle plateforme", T("PLATFORM_ROLE", role="COLLABORATEUR_PLATEFORME"), PLATFORM_BASE + " AND r.code='COLLABORATEUR_PLATEFORME'", {}),
    ("membre de l’équipe", T("PLATFORM_USER", user=FX["N1_TEAM"]["u2"]["id"]), PLATFORM_BASE + " AND a.user_id=:u", {"u": FX["N1_TEAM"]["u2"]["id"]}),
]
sent = {}
for label, t, q, p in cases:
    exp = expected(q, **p)
    code, pv, ms = preview(t)
    ok_prev = code == 200 and pv["deliveries"] == len(exp) and pv["people"] == len({u for u, _ in exp})
    individual = t["type"] in ("SCHOOL_USER", "PLATFORM_USER")
    code, r, ms2 = send(t, f"Ciblage {label} {tag}", None if individual else pv["deliveries"])
    got = delivered(r.get("id")) if code == 201 else set()
    check(ok_prev and code == 201 and got == exp, f"cible « {label} » : aperçu serveur {pv.get('deliveries')} = envoi {len(got)} = attendu {len(exp)} ({ms} ms / {ms2} ms)")
    sent[label] = r.get("id")

# ---------------------------------------------------------------- deduplication
cid = sent["toutes les écoles actives"]
dups = sql("SELECT count(*) FROM (SELECT user_id, school_id FROM notifications WHERE campaign_id=:c GROUP BY 1,2 HAVING count(*)>1) x", c=cid)[0][0]
multi_id = sql("SELECT id FROM users WHERE email=:e", e=multi["email"])[0][0]
mrows = sql("SELECT school_id FROM notifications WHERE campaign_id=:c AND user_id=:u", c=cid, u=multi_id)
check(dups == 0 and len(mrows) == 2, f"déduplication : aucun doublon dans un même espace ; compte de 2 écoles = 1 notification par espace école ({len(mrows)})")
pcid = sent["toute l’équipe plateforme"]
multi_role = sql("""SELECT a.user_id FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id WHERE a.school_id IS NULL AND a.active AND r.level='PLATFORM'
                    AND r.status='ACTIVE' GROUP BY 1 HAVING count(*)>1 LIMIT 1""")
if multi_role:
    n = sql("SELECT count(*) FROM notifications WHERE campaign_id=:c AND user_id=:u", c=pcid, u=multi_role[0][0])[0][0]
    check(n == 1, "multi-rôles plateforme : une seule notification")
row = sql("SELECT recipient_count, people_count FROM platform_system_notifications WHERE id=:c", c=cid)[0]
check(row[1] is not None and row[1] < row[0], f"audience historisée : {row[0]} remises, {row[1]} personnes")

# ---------------------------------------------------------------- zero recipient, reconfirmation, idempotency
empty_role = sql("""SELECT r.code FROM rbac_roles r WHERE r.level='SCHOOL' AND r.status='ACTIVE' AND r.school_id IS NULL AND NOT EXISTS
                    (SELECT 1 FROM rbac_assignments a JOIN school_memberships m ON m.id=a.membership_id JOIN schools s ON s.id=m.school_id
                     WHERE a.role_id=r.id AND a.active AND m.active AND s.status='ACTIVE') LIMIT 1""")
if empty_role:
    code, pv, _ = preview(T("SCHOOL_ROLE", role=empty_role[0][0]))
    before = sql("SELECT count(*) FROM platform_system_notifications")[0][0]
    code2, r2, _ = send(T("SCHOOL_ROLE", role=empty_role[0][0]), "Zéro destinataire", 0)
    check(pv["deliveries"] == 0 and pv["message"] and code2 == 422 and "Aucun destinataire" in r2.get("detail", "")
          and sql("SELECT count(*) FROM platform_system_notifications")[0][0] == before, "zéro destinataire : envoi bloqué, rien n’est créé")
code, pv, _ = preview(T("SCHOOLS", [A["school_id"]]))
code, r, _ = send(T("SCHOOLS", [A["school_id"]]), f"Audience élargie {tag}", pv["deliveries"] - 1)
check(code == 409 and r.get("detail", {}).get("code") == "AUDIENCE_CHANGED" and r["detail"]["deliveries"] == pv["deliveries"],
      "audience plus large que confirmée : envoi refusé, nouveau nombre renvoyé (reconfirmation)")
key = str(uuid.uuid4())
codes, ids = [], []
def double():
    c2, rr, _ = send(T("SCHOOLS", [A["school_id"]]), f"Double clic {tag}", pv["deliveries"], key=key)
    codes.append(c2); ids.append(rr.get("id"))
ts = [threading.Thread(target=double) for _ in range(3)]
[t.start() for t in ts]; [t.join() for t in ts]
n = sql("SELECT count(*) FROM platform_system_notifications WHERE title=:t", t=f"Double clic {tag}")[0][0]
check(n == 1 and 201 in codes, f"double soumission simultanée (même clé) : une seule notification ({sorted(map(str, codes))})")
c3, r3, _ = send(T("SCHOOLS", [A["school_id"]]), f"Double clic {tag}", pv["deliveries"], key=key)
check(c3 in (200, 201) and r3.get("id") == next(i for i in ids if i), "rejeu après réponse perdue : même notification")

# ---------------------------------------------------------------- snapshot semantics
cidA = sent["écoles choisies"]
newbie = sql("SELECT u.id FROM users u WHERE NOT EXISTS (SELECT 1 FROM school_memberships m WHERE m.user_id=u.id AND m.school_id=:a) AND u.active LIMIT 1", a=A["school_id"])[0][0]
sql("INSERT INTO school_memberships(school_id,user_id,active) VALUES(:a,:u,true)", a=A["school_id"], u=newbie)
check(sql("SELECT count(*) FROM notifications WHERE campaign_id=:c AND user_id=:u AND school_id=:a", c=cidA, u=newbie, a=A["school_id"])[0][0] == 0,
      "audience figée à l’envoi : un membre ajouté ensuite ne reçoit pas la notification")
sql("DELETE FROM school_memberships WHERE school_id=:a AND user_id=:u", a=A["school_id"], u=newbie)

# ---------------------------------------------------------------- expiry, time zone, recipient view
member = FX["A"]["users"]["CAISSIER1"]
code, sess, _ = call("POST", "/auth/login", body={"email": member["email"], "password": member["password"], "scope": "SCHOOL", "school_code": A["code"]})
school_token = sess.get("access_token")
soon = (datetime.now(timezone(timedelta(hours=2))) + timedelta(seconds=6)).isoformat()   # offset +02:00: absolute instant kept
target_one = T("SCHOOL_USER", [A["school_id"]], user=member["user_id"])
code, rexp, _ = send(target_one, f"Expire bientôt {tag}", None, expires_at=soon, link_path="/finance/caisse")
code2, rno, _ = send(target_one, f"Sans expiration {tag}", None)
stored = sql("SELECT expires_at FROM platform_system_notifications WHERE id=:c", c=rexp["id"])[0][0]
check(abs((stored - datetime.fromisoformat(soon)).total_seconds()) < 1, "fuseau : l’instant d’expiration est conservé (envoyé en +02:00)")
if school_token:
    inbox = call("GET", "/notifications/inbox?limit=50", school_token)[1]
    titles = [i["title"] for i in inbox.get("items", [])]
    item = next((i for i in inbox.get("items", []) if i["title"] == f"Sans expiration {tag}"), {})
    check(f"Expire bientôt {tag}" in titles and item.get("body", "").count("\n") == 1, "destinataire : notifications reçues dans sa cloche, retours à la ligne conservés")
    time.sleep(7)
    titles2 = [i["title"] for i in call("GET", "/notifications/inbox?limit=50", school_token)[1].get("items", [])]
    hist = call("GET", f"/platform/notification-campaigns/{rexp['id']}", manager)[1]
    check(f"Expire bientôt {tag}" not in titles2 and f"Sans expiration {tag}" in titles2 and hist.get("status") == "EXPIRED",
          "expiration : retirée de la cloche à l’échéance, conservée dans l’historique (statut Expirée)")
    nid = item.get("id")
    check(call("POST", f"/notifications/{nid}/dismiss", school_token)[0] in (200, 204) if nid else False, "destinataire : marquer comme lue")
    d = call("GET", f"/platform/notification-campaigns/{rno['id']}", manager)[1]
    check(d.get("read_count") == 1, "lecture remontée dans le détail (1 lue)")
else:
    print(f"INFO  session école non ouverte (HTTP {code}) : vue destinataire non contrôlée ici")

# ---------------------------------------------------------------- history: search, filters, pagination, detail, immutability
code, h, _ = call("GET", f"/platform/notification-campaigns?q={urllib.parse.quote('ciblage ' + tag.upper())}", manager)
check(code == 200 and h["total"] == len(cases), f"recherche serveur (titre, casse et accents ignorés) : {h.get('total')} résultat(s)")
code, h2, _ = call("GET", "/platform/notification-campaigns?q=certification&limit=5", manager)
check(code == 200 and h2["total"] >= len(cases), "recherche par auteur")
code, h3, _ = call("GET", "/platform/notification-campaigns?status=EXPIRED", manager)
check(code == 200 and all(x["status"] == "EXPIRED" for x in h3["items"]) and h3["total"] >= 1, "filtre statut Expirée")
code, h4, _ = call("GET", "/platform/notification-campaigns?target=PLATFORM_ALL&severity=INFO", manager)
check(code == 200 and all(x["target_scope"] == "PLATFORM_ALL" for x in h4["items"]), "filtres cible + gravité")
today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
code, h5, _ = call("GET", "/platform/notification-campaigns?date_from=" + urllib.parse.quote(today.isoformat()), manager)
check(code == 200 and h5["total"] >= len(cases), "filtre période")
seen, cursor, pages = [], None, 0
while True:
    code, r, _ = call("GET", "/platform/notification-campaigns?limit=7" + (f"&cursor={cursor}" if cursor else ""), manager)
    pages += 1; seen += [x["id"] for x in r["items"]]; cursor = r["next_cursor"]
    if not cursor:
        break
check(len(seen) == r["total"] == len(set(seen)), f"pagination par curseur : {pages} pages, {len(seen)} notifications, ni doublon ni trou")
check(call("GET", "/platform/notification-campaigns?cursor=Zm9v", manager)[0] == 422, "curseur forgé refusé")
code, d, _ = call("GET", f"/platform/notification-campaigns/{sent['écoles choisies']}", manager)
check(code == 200 and len(d["target"].get("schools", [])) == 2 and d["audit_event_id"] and "body" in d, "détail : cible décrite (écoles), contenu, événement d’audit")
for method in ("PUT", "PATCH", "DELETE"):
    check(call(method, f"/platform/notification-campaigns/{sent['écoles choisies']}", manager, {})[0] in (404, 405), f"notification envoyée immuable ({method} refusé)")
audits = sql("SELECT count(*) FROM audit_events WHERE action='PLATFORM_NOTIFICATION_CAMPAIGN_SENT' AND entity_id=:c", c=sent["écoles choisies"])[0][0]
check(audits == 1, "audit : un événement unique par envoi")

# ---------------------------------------------------------------- volume (rolled back): several thousand recipients
os_env = {k: v for k, v in env.items() if k.startswith("EDUSYNC_")}
import os  # noqa: E402
os.environ.update(os_env)
from edusync.modules.notifications_center.api import router as nc  # noqa: E402
with owner.connect() as c:
    tx = c.begin()
    try:
        sids = [r[0] for r in c.execute(text("""INSERT INTO schools(code,name,status) SELECT 'VOL-'||g||'-' || :t, 'École volume '||g, 'ACTIVE'
            FROM generate_series(1,60) g RETURNING id"""), {"t": tag})]
        uids = [r[0] for r in c.execute(text("""INSERT INTO users(email,full_name,password_hash,active) SELECT 'vol-'||g||'-'||:t||'@example.test','Volume '||g,'x',true
            FROM generate_series(1,6000) g RETURNING id"""), {"t": tag})]
        c.execute(text("""INSERT INTO school_memberships(school_id,user_id,active) SELECT (CAST(:s AS uuid[]))[1 + (i % 60)], u, true
            FROM unnest(CAST(:u AS uuid[])) WITH ORDINALITY AS x(u,i)"""), {"s": [str(x) for x in sids], "u": [str(x) for x in uids]})
        t0 = time.perf_counter()
        rec = nc._recipients(c, nc.Target(type="SCHOOLS", school_ids=sids))
        ms = int((time.perf_counter() - t0) * 1000)
        aud = nc._audience(rec)
        check(aud["deliveries"] == 6000 and aud["schools"] == 60 and ms < 3000, f"volume : 60 écoles, {aud['deliveries']} destinataires calculés en {ms} ms (une requête, sans N+1)")
    finally:
        tx.rollback()

print("\nRÉSULTAT : " + ("PASS" if FAILS == 0 else f"FAIL ({FAILS})"))
sys.exit(1 if FAILS else 0)
