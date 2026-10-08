"""Live probe — N1 notifications: targeting (7 kinds), one per recipient, idempotency and concurrency, inbox
isolation (platform vs school, user vs user), read/unread/read-all, expiry, safe links, suspended targets, push
mock (subscribe, title-only payload, revoke, logout-all), permissions, audit, fan-out timing."""
import json
import os
import secrets
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import httpx
import redis
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import BASE, ensure_user, login, owner, platform, state  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


def send(client, target, key=None, **extra):
    body = {"title": extra.pop("title", f"Recette N1 {uuid4().hex[:6]}"), "body": "Message de recette N1", "severity": extra.pop("severity", "INFO"), "target": target, **extra}
    return client.post("platform/notification-campaigns", json=body, headers={"Idempotency-Key": key or str(uuid4())})


def T(type_, **kw):
    return {"type": type_, "school_ids": kw.get("school_ids", []), "role_code": kw.get("role_code"), "user_id": kw.get("user_id")}


def count(cid):
    with owner.connect() as c:
        return c.execute(text("SELECT count(*) FROM notifications WHERE campaign_id=:c"), {"c": cid}).scalar_one()


A, B = state["A"], state["B"]
mgr = platform()
mgr_id = mgr.get("platform/team/me").json()["user"]["id"]
adminA = ensure_user(A, "ADMIN", ("ADMIN_SYSTEME_ECOLE",))
cashA = ensure_user(A, "N1_AUTO_ONE", ("CAISSIER",))
ca = login(adminA["email"], adminA["password"], "SCHOOL", A["code"])
cc = login(cashA["email"], cashA["password"], "SCHOOL", A["code"])

with owner.connect() as c:
    exp_all = c.execute(text("""SELECT count(DISTINCT (m.user_id,m.school_id)) FROM school_memberships m JOIN schools s ON s.id=m.school_id JOIN users u ON u.id=m.user_id
        WHERE m.active AND u.active AND s.status='ACTIVE'""")).scalar_one()
    exp_A = c.execute(text("SELECT count(*) FROM school_memberships m JOIN users u ON u.id=m.user_id WHERE m.school_id=:s AND m.active AND u.active"), {"s": A["school_id"]}).scalar_one()
    exp_cash = c.execute(text("""SELECT count(DISTINCT m.id) FROM school_memberships m JOIN schools s ON s.id=m.school_id JOIN users u ON u.id=m.user_id
        JOIN rbac_assignments a ON a.membership_id=m.id AND a.active JOIN rbac_roles r ON r.id=a.role_id AND r.code='CAISSIER'
        WHERE m.active AND u.active AND s.status='ACTIVE' AND m.school_id=:s"""), {"s": A["school_id"]}).scalar_one()

# ---------- targeting ----------
t0 = time.perf_counter()
r = send(mgr, T("ALL_ACTIVE_SCHOOLS"))
fan = (time.perf_counter() - t0) * 1000
check("Cible : toutes les écoles actives = tous les membres actifs", r.status_code == 201 and r.json()["recipient_count"] == exp_all == count(r.json()["id"]), f"{r.json().get('recipient_count')} attendu {exp_all} ({fan:.0f} ms)")
r = send(mgr, T("SCHOOLS", school_ids=[A["school_id"]]))
check("Cible : école choisie", r.status_code == 201 and r.json()["recipient_count"] == exp_A, f"{r.json().get('recipient_count')}/{exp_A}")
r = send(mgr, T("SCHOOL_ROLE", role_code="CAISSIER", school_ids=[A["school_id"]]))
check("Cible : un rôle école dans une école", r.status_code == 201 and r.json()["recipient_count"] == exp_cash, f"{r.json().get('recipient_count')}/{exp_cash}")
with owner.connect() as c:
    cash_uid = c.execute(text("SELECT id FROM users WHERE lower(email::text)=:e"), {"e": cashA["email"].lower()}).scalar_one()
title_user = f"Pour vous seul {uuid4().hex[:6]}"
r = send(mgr, T("SCHOOL_USER", school_ids=[A["school_id"]], user_id=str(cash_uid)), title=title_user, link_path="/aide/caisse")
check("Cible : un membre précis", r.status_code == 201 and r.json()["recipient_count"] == 1, r.status_code)
r = send(mgr, T("PLATFORM_ALL"))
check("Cible : toute l'équipe plateforme", r.status_code == 201 and r.json()["recipient_count"] >= 1, r.json().get("recipient_count"))
r = send(mgr, T("PLATFORM_ROLE", role_code="MANAGER_SYSTEME"))
check("Cible : un rôle plateforme", r.status_code == 201 and r.json()["recipient_count"] >= 1, r.json().get("recipient_count"))
title_pf = f"Pour le Manager {uuid4().hex[:6]}"
r = send(mgr, T("PLATFORM_USER", user_id=mgr_id), title=title_pf, severity="CRITICAL")
check("Cible : un compte plateforme", r.status_code == 201 and r.json()["recipient_count"] == 1, r.status_code)

# ---------- validation ----------
for bad in ("https://evil.example/x", "//evil.example", "javascript:alert(1)", "/ok\\..\\x"):
    check(f"Lien refusé : {bad[:24]}", send(mgr, T("PLATFORM_ALL"), link_path=bad).status_code == 422)
try:
    with owner.begin() as c:
        c.execute(text("UPDATE notifications SET link_path='https://evil.example' WHERE id=(SELECT id FROM notifications LIMIT 1)"))
    check("Base : lien externe impossible même en SQL direct", False, "accepté")
except Exception as e:  # noqa: BLE001
    check("Base : lien externe impossible même en SQL direct", "link_path" in str(e), type(e).__name__)
check("Rôle inconnu refusé (422)", send(mgr, T("SCHOOL_ROLE", role_code="INEXISTANT")).status_code == 422)
check("Membre hors école refusé (aucun destinataire, 422)", send(mgr, T("SCHOOL_USER", school_ids=[B["school_id"]], user_id=str(cash_uid))).status_code == 422)
check("Expiration dans le passé refusée", send(mgr, T("PLATFORM_ALL"), expires_at="2020-01-01T00:00:00Z").status_code == 422)

# ---------- idempotency & concurrency ----------
key = str(uuid4())
r1 = send(mgr, T("SCHOOLS", school_ids=[A["school_id"]]), key, title="Idempotence N1")
r2 = send(mgr, T("SCHOOLS", school_ids=[A["school_id"]]), key, title="Idempotence N1")
check("Même clé : rejouée, une seule campagne, pas de doublon", r2.status_code == 201 and r2.json()["id"] == r1.json()["id"] and r2.headers.get("Idempotent-Replayed") == "true" and count(r1.json()["id"]) == exp_A)
key2, outs = str(uuid4()), []
def _go():
    with httpx.Client(base_url=BASE + "/", timeout=60, headers=dict(mgr.headers)) as c:
        outs.append(send(c, T("ALL_ACTIVE_SCHOOLS"), key2, title="Concurrence N1"))
ts = [threading.Thread(target=_go) for _ in range(3)]
[t.start() for t in ts]; [t.join() for t in ts]
ids = {o.json().get("id") for o in outs if o.status_code == 201}
with owner.connect() as c:
    n_camp = c.execute(text("SELECT count(*) FROM platform_system_notifications WHERE title='Concurrence N1' AND created_at>now()-interval '2 minutes'")).scalar_one()
check("3 envois simultanés même clé : une seule campagne", n_camp == 1 and len(ids) <= 1, f"{sorted(o.status_code for o in outs)} campagnes={n_camp}")

# ---------- inboxes ----------
ib = cc.get("notifications/inbox").json()
mine = [x for x in ib["items"] if x["title"] == title_user]
check("Boîte école : le membre ciblé reçoit sa notification (avec lien interne)", len(mine) == 1 and mine[0]["link_path"] == "/aide/caisse")
check("Boîte école : un autre membre ne la voit pas", not [x for x in ca.get("notifications/inbox").json()["items"] if x["title"] == title_user])
check("Boîte école : aucune notification plateforme visible", not [x for x in ib["items"] if x["title"] == title_pf])
pf = mgr.get("platform/inbox").json()
mine_pf = [x for x in pf["items"] if x["title"] == title_pf]
check("Boîte plateforme : reçue, gravité conservée", len(mine_pf) == 1 and mine_pf[0]["severity"] == "CRITICAL")
check("Boîte plateforme : aucune notification d'école", not [x for x in pf["items"] if x["title"] == title_user])
nid = mine[0]["id"]
check("BOLA : un autre membre ne peut pas marquer la notification d'autrui", ca.post(f"notifications/{nid}/dismiss", headers={"Idempotency-Key": str(uuid4())}).status_code == 404)
check("BOLA : le Manager ne peut pas marquer une notification d'école via sa boîte", mgr.post(f"platform/inbox/{nid}/read", headers={"Idempotency-Key": str(uuid4())}).status_code == 404)
u_before = cc.get("notifications/inbox").json()["unread"]
cc.post(f"notifications/{nid}/dismiss", headers={"Idempotency-Key": str(uuid4())})
check("Lu / non lu : compteur décrémenté", cc.get("notifications/inbox").json()["unread"] == u_before - 1)
check("Filtre non lues", all(x["read_at"] is None for x in cc.get("notifications/inbox", params={"status": "unread"}).json()["items"]))
check("Filtre gravité", all(x["severity"] == "CRITICAL" for x in mgr.get("platform/inbox", params={"severity": "CRITICAL"}).json()["items"]))
ra = mgr.post("platform/inbox/read-all", headers={"Idempotency-Key": str(uuid4())})
check("Tout marquer comme lu", ra.status_code == 200 and mgr.get("platform/inbox").json()["unread"] == 0, ra.json())
p1 = cc.get("notifications/inbox", params={"limit": 2}).json()
if p1["next_cursor"]:
    p2 = cc.get("notifications/inbox", params={"limit": 2, "cursor_at": p1["next_cursor"]["at"], "cursor_id": p1["next_cursor"]["id"]}).json()
    check("Historique paginé sans recouvrement", not ({x["id"] for x in p1["items"]} & {x["id"] for x in p2["items"]}))
with owner.begin() as c:
    c.execute(text("UPDATE notifications SET expires_at=now()-interval '1 second' WHERE id=:id"), {"id": mine_pf[0]["id"]})
check("Expiration : une notification expirée disparaît de la boîte", not [x for x in mgr.get("platform/inbox").json()["items"] if x["id"] == mine_pf[0]["id"]])

# ---------- suspended targets ----------
sus_code = f"N1N-{uuid4().hex[:5].upper()}"
sid = mgr.post("platform/schools", json={"name": "École suspendue N1", "code": sus_code}, headers={"Idempotency-Key": str(uuid4())}).json()["id"]
mgr.post(f"platform/schools/{sid}/bootstrap-admin", json={"email": f"susp-{uuid4().hex[:6]}@example.test", "full_name": "Admin suspendu", "password": secrets.token_urlsafe(16)}, headers={"Idempotency-Key": str(uuid4())})
mgr.post(f"platform/schools/{sid}/suspend", json={"reason": "Recette N1 notifications"}, headers={"Idempotency-Key": str(uuid4())})
check("École suspendue : refusée comme cible explicite", send(mgr, T("SCHOOLS", school_ids=[sid])).status_code == 422)
r = send(mgr, T("ALL_ACTIVE_SCHOOLS"))
with owner.connect() as c:
    leaked = c.execute(text("SELECT count(*) FROM notifications WHERE campaign_id=:c AND school_id=:s"), {"c": r.json()["id"], "s": sid}).scalar_one()
check("École suspendue : exclue de « toutes les écoles actives »", leaked == 0)

# ---------- push (mock provider) ----------
rc = redis.Redis.from_url(os.environ["EDUSYNC_REDIS_URL"], decode_responses=True)
endpoint = f"https://push.example.test/{uuid4()}"
sub = mgr.post("platform/inbox/push-subscriptions", json={"provider": "MOCK", "endpoint": endpoint, "device_label": "Recette N1"})
check("Push : abonnement d'un appareil (simulateur)", sub.status_code == 201, sub.status_code)
sub2 = mgr.post("platform/inbox/push-subscriptions", json={"provider": "MOCK", "endpoint": endpoint, "device_label": "Recette N1"})
check("Push : réabonnement du même appareil sans doublon", sub2.json().get("status") == "already_subscribed")
with owner.connect() as c:
    stored = c.execute(text("SELECT count(*) FROM push_subscriptions WHERE endpoint_hash=:h"), {"h": __import__("hashlib").sha256(endpoint.encode()).hexdigest()}).scalar_one()
    raw_leak = c.execute(text("SELECT count(*) FROM push_subscriptions WHERE device_label LIKE :e"), {"e": f"%{endpoint}%"}).scalar_one()
check("Push : l'adresse de l'appareil n'est jamais stockée en clair (empreinte seulement)", stored == 1 and raw_leak == 0)
before = rc.llen("edusync:push:mock")
secret_body = f"Corps confidentiel {uuid4().hex}"
r = mgr.post("platform/notification-campaigns", json={"title": "Push N1", "body": secret_body, "severity": "WARNING", "target": T("PLATFORM_USER", user_id=mgr_id)}, headers={"Idempotency-Key": str(uuid4())})
pushed = [json.loads(x) for x in rc.lrange("edusync:push:mock", 0, 5)]
check("Push : envoyé à l'appareil abonné (fournisseur simulé)", r.json().get("push", {}).get("accepted", 0) >= 1 and rc.llen("edusync:push:mock") > before, r.json().get("push"))
check("Push : la charge ne contient ni le corps ni de donnée personnelle", all(secret_body not in json.dumps(p) and "body" not in p for p in pushed))
mgr.post(f"platform/inbox/push-subscriptions/{sub.json()['id']}/revoke", headers={"Idempotency-Key": str(uuid4())})
r = mgr.post("platform/notification-campaigns", json={"title": "Push N1 après désabonnement", "body": "x" * 5, "target": T("PLATFORM_USER", user_id=mgr_id)}, headers={"Idempotency-Key": str(uuid4())})
check("Push : appareil désabonné -> plus aucun envoi", "push" not in r.json() or r.json()["push"]["devices"] == 0, r.json().get("push"))
# Multi-device + logout-all revokes every subscription of the account (school member).
for i in range(2):
    cc.post("notifications/push-subscriptions", json={"provider": "MOCK", "endpoint": f"https://push.example.test/{uuid4()}", "device_label": f"Appareil {i}"})
with owner.connect() as c:
    n_before = c.execute(text("SELECT count(*) FROM push_subscriptions WHERE user_id=:u AND revoked_at IS NULL"), {"u": str(cash_uid)}).scalar_one()
httpx.post(BASE + "/auth/logout-all", cookies={"edusync_session": cc.cookies.get("edusync_session")}, timeout=30)
with owner.connect() as c:
    n_after = c.execute(text("SELECT count(*) FROM push_subscriptions WHERE user_id=:u AND revoked_at IS NULL"), {"u": str(cash_uid)}).scalar_one()
check("Push multi-appareils : déconnexion globale -> tous les abonnements révoqués", n_before >= 2 and n_after == 0, f"{n_before} -> {n_after}")

# ---------- permissions & audit ----------
u2 = state.get("N1_TEAM", {}).get("u2")
if u2:
    lr = httpx.post(BASE + "/auth/login", json={"email": u2["email"], "password": u2["password"]}, timeout=30)
    if lr.status_code == 200:
        c2 = httpx.Client(base_url=BASE + "/", headers={"Authorization": "Bearer " + lr.json()["access_token"]}, timeout=30)
        check("Sans platform.notifications.system.send : envoi refusé", send(c2, T("PLATFORM_ALL")).status_code == 403)
        check("Compte plateforme : sa propre boîte reste accessible", c2.get("platform/inbox").status_code == 200)
check("Compte école : API de campagne refusée", send(ca, T("PLATFORM_ALL")).status_code == 403)
with owner.connect() as c:
    n = c.execute(text("SELECT count(*) FROM audit_events WHERE action='PLATFORM_NOTIFICATION_CAMPAIGN_SENT' AND occurred_at>now()-interval '10 minutes'")).scalar_one()
check("Chaque campagne auditée", n >= 8, n)
check("Liste des campagnes avec taux de lecture", "read_count" in mgr.get("platform/notification-campaigns").json()["items"][0])

out = Path(__file__).with_name("notifications-live.json")
out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(f"== {sum(r['pass'] for r in results)}/{len(results)} PASS -> {out.name}")
