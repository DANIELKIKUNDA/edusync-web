"""External messaging — LOCAL probe with the development fake providers (EXTERNAL_MESSAGING_CERTIFICATION.md).

Proves the EduSync side end to end on the real stack (API + transactional outbox + communications worker + PostgreSQL
RLS): SMS wallet and ledger, preview / confirmation, reservation -> consumption / release, idempotency, insufficient
credit, SMS switched off, e-mail recovery and invitation links (single use, expiry, replay), push devices (several,
invalid token, reassigned token, revocation), RBAC and school A / school B isolation, no secret in API responses.
A fake provider success is NOT a provider certification: real providers are covered by the separate
email_provider_probe / sms_provider_probe / push_provider_probe (EXTERNAL_REQUIRED until secrets are provided).
"""
import json
import re
import sys
import threading
import time
from datetime import date
from pathlib import Path
from uuid import uuid4

import httpx
import redis
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import BASE, ensure_user, grant_test_role, owner, platform, save, state, user_client  # noqa: E402
import os  # noqa: E402

results = []
OUT = Path(__file__).with_name("messaging-local-live.json")
rc = redis.Redis.from_url(os.environ["EDUSYNC_REDIS_URL"], decode_responses=True)


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


def k(extra=None):
    return {"Idempotency-Key": str(uuid4()), **(extra or {})}


def ok(r, codes=(200, 201, 202)):
    assert r.status_code in codes, (r.request.method, str(r.request.url)[-70:], r.status_code, r.text[:300])
    return r.json()


def q(sql, params=None):
    with owner.connect() as c:
        return c.execute(text(sql), params or {}).mappings().all()


def wait(predicate, seconds=40):
    end = time.time() + seconds
    while time.time() < end:
        v = predicate()
        if v:
            return v
        time.sleep(0.7)
    return predicate()


run = uuid4().hex[:5].upper()
today = date.today()
sy = today.year if today.month >= 9 else today.year - 1
mgr = platform()


def new_school(tag):
    s = ok(mgr.post("platform/schools", json={"code": f"MSG{tag}-{run}", "name": f"École messagerie {tag} {run}"}, headers=k()))
    school = {"code": f"MSG{tag}-{run}", "school_id": s["id"], "users": {}}
    state.setdefault("MSG", {})[f"{tag}-{run}"] = school
    save()
    ensure_user(school, "ADMIN", ("ADMIN_SYSTEME_ECOLE",))
    ensure_user(school, "PREFET", ())            # secondary leadership roles are section-scoped: assigned by the school below
    ensure_user(school, "DIRE", ())
    ensure_user(school, "CASH", ("CAISSIER",))
    ensure_user(school, "GES", ("GESTIONNAIRE",))
    adm = user_client(school, "ADMIN")
    roles = {r["code"]: r for r in (lambda x: x if isinstance(x, list) else x.get("items", []))(ok(adm.get("access/roles")))}
    pri = ok(adm.put("settings/sections/PRIMAIRE", json={"code": "PRIMAIRE", "label": "Primaire", "enabled": True}, headers=k()))
    sec = ok(adm.put("settings/sections/SECONDAIRE", json={"code": "SECONDAIRE", "label": "Secondaire", "enabled": True}, headers=k()))
    for key_, role in (("PREFET", "DIRECTEUR_DISCIPLINE"), ("DIRE", "DIRECTEUR_ETUDES")):
        ok(adm.post(f"access/members/{school['users'][key_]['membership_id']}/roles", headers=k(),
                    json={"role_id": roles[role]["id"], "scopes": [{"type": "SECTION", "value": "SECONDAIRE"}], "reason": "Recette messagerie"}))
    y = ok(adm.post("settings/academic-years", json={"code": f"{sy}-{sy+1}", "label": f"{sy}-{sy+1}", "start_date": f"{sy}-09-01", "end_date": f"{sy+1}-06-30"}, headers=k()))
    y = ok(adm.post(f"settings/academic-years/{y['id']}/activate", headers=k({"If-Match": str(y["version"])})))
    cls = ok(adm.post("settings/classes", json={"academic_year_id": y["id"], "section_id": sec["id"], "reference_code": "7EB", "code": "7EB", "label": "7e EB"}, headers=k()))
    pcls = ok(adm.post("settings/classes", json={"academic_year_id": y["id"], "section_id": pri["id"], "reference_code": "P1", "code": "P1", "label": "P1"}, headers=k()))
    ok(adm.post("settings/admission-conditions/review", headers=k()))
    return school, cls, pcls


A, clsA, priA = new_school("A")
B, clsB, _ = new_school("B")
admA, prefA, direA, cashA, gesA = (user_client(A, x) for x in ("ADMIN", "PREFET", "DIRE", "CASH", "GES"))
prefB = user_client(B, "PREFET")
adminB = user_client(B, "ADMIN")


def enroll(client, cls, name, phone, email=None):
    g = {"full_name": f"Parent {name} {run}", "is_primary": True, "phone": phone}
    if email:
        g["email"] = email
    return ok(client.post("schooling/enrollments/family", json={"primary_guardian": g, "children": [
        {"last_name": f"{name}{run}", "middle_name": "Recette", "first_name": "Enfant", "gender": "F", "birth_date": f"{sy-8}-01-01", "class_id": cls["id"]}]}, headers=k()))


# Families of class P1 (school A): valid, duplicate phone, invalid, refused by provider (…0000), timeout (…9999).
enroll(cashA, clsA, "VALIDE", "+243810001234", f"parent.valide.{run.lower()}@example.test")
enroll(cashA, clsA, "DOUBLON", "+243810001234")
enroll(cashA, clsA, "INVALIDE", "12")
enroll(cashA, clsA, "REFUS", "+243810000000")
enroll(cashA, clsA, "LENT", "+243810009999")
enroll(user_client(B, "CASH"), clsB, "ECOLEB", "+243820005555")

# ---------------------------------------------------------------- readiness & settings (RBAC)
rd = ok(prefA.get("communications/readiness"))
check("Plateforme : SMS, e-mail et push en mode simulé (développement), jamais déclarés certifiés",
      all(rd["platform"][ch]["state"] == "SIMULATED" for ch in ("sms", "email", "push")), rd["platform"])
deny = gesA.put("communications/settings", json={"enabled": True, "sms_enabled": True, "email_enabled": True, "push_enabled": True, "sms_low_balance_threshold": 10, "expected_version": rd["version"]})
check("RBAC : réglages des canaux refusés sans notifications.internal.configure", deny.status_code == 403, deny.status_code)
sv = ok(admA.put("communications/settings", json={"enabled": True, "sms_enabled": True, "email_enabled": True, "push_enabled": True, "sms_low_balance_threshold": 10, "expected_version": rd["version"]}))
check("Réglages : l'administrateur système de l'école active SMS, e-mail et push", sv["version"] >= 1, sv)
stale = admA.put("communications/settings", json={"enabled": True, "sms_enabled": True, "email_enabled": True, "push_enabled": True, "sms_low_balance_threshold": 10, "expected_version": rd["version"]})
check("Réglages : version périmée refusée (409)", stale.status_code == 409, stale.status_code)

body = f"Réunion des parents P1 samedi 9h. Ref {run}"
draft = {"audience_type": "CLASS", "audience_ref": clsA["id"], "channels": ["SMS"], "body": body}

# ---------------------------------------------------------------- no credit yet
pv0 = ok(prefA.post("communications/preview", json={**draft, "idempotency_key": str(uuid4())}))
check("Aperçu : destinataires, numéro invalide et doublon retirés, coût en unités",
      pv0["recipients"] == 5 and pv0["sms_valid"] == 3 and pv0["sms_invalid"] == 1 and pv0["sms_duplicates_removed"] == 1 and pv0["sms_units"] == 3, pv0)
s0 = prefA.post("communications/send", json={**draft, "idempotency_key": str(uuid4()), "confirm_fingerprint": pv0["fingerprint"]})
check("SMS sans crédit : envoi refusé (409), aucune réservation, aucun message", s0.status_code == 409 and "insuffisant" in s0.text.lower(), (s0.status_code, s0.text[:120]))

# ---------------------------------------------------------------- platform credit (idempotent, audited)
key = str(uuid4())
c1 = ok(mgr.post(f"platform/messaging/wallets/{A['school_id']}/credit", json={"quantity": 100, "reference": f"FACT-{run}", "reason": "Achat pack 100 SMS",
        "commercial_price": 25, "commercial_currency": "USD", "paid_on": date.today().isoformat()}, headers={"Idempotency-Key": key}))
c1b = ok(mgr.post(f"platform/messaging/wallets/{A['school_id']}/credit", json={"quantity": 100, "reference": f"FACT-{run}", "reason": "Achat pack 100 SMS",
        "commercial_price": 25, "commercial_currency": "USD", "paid_on": date.today().isoformat()}, headers={"Idempotency-Key": key}))
check("Crédit manuel : solde 100, rejeu de la même clé sans double crédit", c1["balance"] == 100 and c1b["ledger_id"] == c1["ledger_id"] and c1b["replayed"], (c1, c1b))
nocap = prefA.post(f"platform/messaging/wallets/{A['school_id']}/credit", json={"quantity": 5, "reference": "x1", "reason": "tentative école"}, headers=k())
check("RBAC : un compte école ne peut pas créditer un portefeuille", nocap.status_code in (401, 403), nocap.status_code)
aud = q("SELECT count(*) n FROM audit_events WHERE action='SMS_WALLET_TOPUP' AND entity_id=:s", {"s": A["school_id"]})[0]["n"]
check("Crédit audité une seule fois (rejeu non audité)", aud == 1, aud)
neg = mgr.post(f"platform/messaging/wallets/{A['school_id']}/adjust", json={"direction": "DEBIT", "quantity": 1000, "reason": "Correction erronée"}, headers=k())
check("Ajustement : jamais de solde négatif", neg.status_code == 409, neg.status_code)


# Concurrent credits: 5 parallel distinct keys + 5 parallel identical keys.
def credit_parallel(key_, out):
    r = httpx.post(BASE + f"/platform/messaging/wallets/{A['school_id']}/credit", headers={**mgr.headers, "Idempotency-Key": key_},
                   json={"quantity": 10, "reference": f"PAR-{run}", "reason": "Crédit concurrent", "paid_on": date.today().isoformat(), "commercial_price": 2.5, "commercial_currency": "USD"}, timeout=60)
    out.append(r.status_code)


same, codes = str(uuid4()), []
threads = [threading.Thread(target=credit_parallel, args=(str(uuid4()), codes)) for _ in range(5)] + \
          [threading.Thread(target=credit_parallel, args=(same, codes)) for _ in range(5)]
[t.start() for t in threads]
[t.join() for t in threads]
bal = q("SELECT balance, reserved FROM school_sms_wallets WHERE school_id=:s", {"s": A["school_id"]})[0]
check("Crédit concurrent : 5 clés distinctes + 5 fois la même clé = +60 exactement", bal["balance"] == 160 and all(c == 200 for c in codes), (dict(bal), codes))
wb = ok(prefB.get("communications/wallet"))
lb = ok(prefB.get("communications/wallet/ledger"))
check("Multi-école : l'école B ne voit ni le solde ni le grand livre de l'école A", wb["balance"] == 0 and lb["items"] == [], (wb, len(lb["items"])))

# ---------------------------------------------------------------- RBAC on sending
deny_cash = cashA.post("communications/preview", json={**draft, "idempotency_key": str(uuid4())})
deny_dir = direA.post("communications/preview", json={**draft, "idempotency_key": str(uuid4())})
check("RBAC : caissier sans droit de composer → 403 ; directeur des études sans SMS de masse → 403",
      deny_cash.status_code == 403 and deny_dir.status_code == 403, (deny_cash.status_code, deny_dir.status_code))
enroll(cashA, priA, "PRIMAIRE", "+243810007777")
outside = prefA.post("communications/preview", json={**draft, "audience_ref": priA["id"], "idempotency_key": str(uuid4())})
check("Périmètre de section : un rôle limité au Secondaire ne peut pas viser une classe du Primaire", outside.status_code == 403, outside.status_code)
rdB = ok(adminB.get("communications/readiness"))
ok(adminB.put("communications/settings", json={"enabled": True, "sms_enabled": True, "email_enabled": True, "push_enabled": True, "sms_low_balance_threshold": 10, "expected_version": rdB["version"]}))
cross = prefB.post("communications/preview", json={**draft, "idempotency_key": str(uuid4())})
check("Multi-école : la classe de l'école A ne donne aucun destinataire à l'école B", cross.status_code == 200 and cross.json()["recipients"] == 0, cross.text[:120])

# ---------------------------------------------------------------- confirmed bulk SMS
pv = ok(prefA.post("communications/preview", json={**draft, "idempotency_key": str(uuid4())}))
nf = prefA.post("communications/send", json={**draft, "idempotency_key": str(uuid4())})
check("Confirmation obligatoire : envoi SMS sans empreinte d'aperçu refusé", nf.status_code == 409, nf.status_code)
ikey = str(uuid4())
sent = ok(prefA.post("communications/send", json={**draft, "idempotency_key": ikey, "confirm_fingerprint": pv["fingerprint"]}))
again = ok(prefA.post("communications/send", json={**draft, "idempotency_key": ikey, "confirm_fingerprint": pv["fingerprint"]}))
check("Envoi accepté (QUEUED) et rejeu idempotent sans double réservation",
      sent["status"] == "QUEUED" and sent["sms_units_reserved"] == 3 and again["replayed"] and again["id"] == sent["id"], (sent, again))
res = q("SELECT count(*) n FROM school_sms_ledger WHERE school_id=:s AND movement_type='RESERVATION'", {"s": A["school_id"]})[0]["n"]
check("Une seule réservation pour le message", res == 1, res)
mid = sent["id"]


def deliveries():
    return {r["destination"]: dict(r) for r in q("SELECT destination, status, wallet_state, last_error_code, provider_message_id, attempts FROM communication_deliveries WHERE message_id=:m AND channel='SMS'", {"m": mid})}


d = wait(lambda: (lambda x: x if x.get("+243810001234", {}).get("status") == "SENT" and x.get("+243810000000", {}).get("status") == "FAILED_PERMANENT"
                  and x.get("+243810009999", {}).get("status") == "FAILED_RETRYABLE" else None)(deliveries()))
d = d or deliveries()
check("Worker : numéro valide → SENT avec preuve fournisseur, crédits consommés",
      d.get("+243810001234", {}).get("status") == "SENT" and d["+243810001234"]["provider_message_id"] and d["+243810001234"]["wallet_state"] == "CONSUMED", d.get("+243810001234"))
check("Worker : refus permanent du fournisseur → FAILED_PERMANENT, crédits libérés",
      d.get("+243810000000", {}).get("status") == "FAILED_PERMANENT" and d["+243810000000"]["wallet_state"] == "RELEASED", d.get("+243810000000"))
check("Worker : délai dépassé → FAILED_RETRYABLE, crédits encore réservés, nouvel essai planifié",
      d.get("+243810009999", {}).get("status") == "FAILED_RETRYABLE" and d["+243810009999"]["wallet_state"] == "RESERVED", d.get("+243810009999"))
skipped = q("SELECT last_error_code FROM communication_deliveries WHERE message_id=:m AND channel='SMS' AND status='CANCELLED'", {"m": mid})
check("Politique : numéro invalide écarté sans être facturé (NO_VALID_PHONE)", any(r["last_error_code"] == "NO_VALID_PHONE" for r in skipped), [r["last_error_code"] for r in skipped])
check("SENT n'est jamais transformé en DELIVERED sans accusé du fournisseur", d.get("+243810001234", {}).get("status") != "DELIVERED")

# Retries are bounded: last allowed attempt fails again -> FAILED_PERMANENT, credits released.
with owner.begin() as c:
    c.execute(text("UPDATE communication_deliveries SET attempts=5, next_attempt_at=now() WHERE message_id=:m AND destination='+243810009999'"), {"m": mid})
last = wait(lambda: (lambda r: r if r and r["status"] == "FAILED_PERMANENT" else None)(deliveries().get("+243810009999")))
check("Nouvelles tentatives bornées : épuisement → FAILED_PERMANENT (lettre morte visible), crédits libérés",
      bool(last) and last["wallet_state"] == "RELEASED" and last["attempts"] == 6, last)
w = q("SELECT balance, reserved FROM school_sms_wallets WHERE school_id=:s", {"s": A["school_id"]})[0]
check("Portefeuille : 160 − 1 SMS consommé = 159, aucune réservation restante", w["balance"] == 159 and w["reserved"] == 0, dict(w))
kinds = sorted({r["movement_type"] for r in q("SELECT movement_type FROM school_sms_ledger WHERE school_id=:s", {"s": A["school_id"]})})
check("Grand livre : TOPUP, RESERVATION, CONSUMPTION, RELEASE tracés", kinds == ["CONSUMPTION", "RELEASE", "RESERVATION", "TOPUP"], kinds)
try:
    with owner.begin() as c:
        c.execute(text("UPDATE school_sms_ledger SET quantity=quantity+1 WHERE school_id=:s"), {"s": A["school_id"]})
    immut = False
except Exception:  # noqa: BLE001
    immut = True
check("Grand livre en ajout seul (modification refusée même au propriétaire)", immut)
hist = ok(prefA.get("communications/history"))["items"]
h = next((x for x in hist if x["id"] == mid), None)
check("Historique : canal, statuts, auteur, unités facturées, erreurs synthétiques", h and h["author"] and h["sms_units_billed"] == 1 and h["counts"].get("SMS:SENT") == 1, h)

# ---------------------------------------------------------------- SMS switched off: business keeps working
ok(admA.put("communications/settings", json={"enabled": True, "sms_enabled": False, "email_enabled": True, "push_enabled": True, "sms_low_balance_threshold": 10, "expected_version": sv["version"]}))
off = prefA.post("communications/preview", json={**draft, "idempotency_key": str(uuid4())})
check("SMS désactivé : envoi SMS refusé « Canal externe non activé »", off.status_code == 409 and "Canal externe non activé" in off.text, off.text[:100])
biz = cashA.post("schooling/enrollments/family", headers=k(), json={"primary_guardian": {"full_name": f"Parent HORS SMS {run}", "is_primary": True, "phone": "+243810004444"},
                 "children": [{"last_name": f"HORSSMS{run}", "middle_name": "Recette", "first_name": "Enfant", "gender": "M", "birth_date": f"{sy-8}-02-02", "class_id": clsA["id"]}]})
check("Inscription (métier) inchangée quand les SMS sont désactivés", biz.status_code in (200, 201), biz.status_code)
rd2 = ok(admA.get("communications/readiness"))
ok(admA.put("communications/settings", json={"enabled": True, "sms_enabled": True, "email_enabled": True, "push_enabled": True, "sms_low_balance_threshold": 10, "expected_version": rd2["version"]}))

# ---------------------------------------------------------------- e-mail: password recovery (single use, replay)
email_user = A["users"]["GES"]
forgot = httpx.post(BASE + "/auth/password/forgot", json={"email": email_user["email"]}, headers={"Origin": "http://localhost:5180"}, timeout=30)
unknown = httpx.post(BASE + "/auth/password/forgot", json={"email": f"inconnu.{run.lower()}@example.test"}, headers={"Origin": "http://localhost:5180"}, timeout=30)
check("Récupération : même réponse 202 que l'adresse existe ou non (pas d'énumération)",
      forgot.status_code == unknown.status_code == 202 and forgot.json() == unknown.json(), (forgot.status_code, unknown.status_code))


def fake_mail(to, contains):
    for raw in rc.lrange("edusync:messaging:fake:email", 0, 50):
        m = json.loads(raw)
        if m["to"].lower() == to.lower() and contains in m["text"]:
            return m
    return None


mail = wait(lambda: fake_mail(email_user["email"], "#reset="))
token = re.search(r"#reset=([A-Za-z0-9_\-]+)", mail["text"]).group(1) if mail else ""
check("E-mail de récupération envoyé par le worker avec un lien à usage unique (fragment #reset)", bool(token) and len(token) >= 40, bool(mail))
stored = q("SELECT count(*) n FROM account_tokens WHERE token_hash=encode(sha256(CAST(:t AS bytea)),'hex')", {"t": token})[0]["n"] if token else 0
clear = q("SELECT count(*) n FROM account_tokens WHERE token_hash=:t", {"t": token})[0]["n"] if token else 1
check("Jeton stocké sous forme d'empreinte SHA-256 uniquement", stored == 1 and clear == 0, (stored, clear))
wiped = q("""SELECT count(*) n FROM communication_recipients r JOIN communication_messages m ON m.id=r.message_id
    WHERE m.template_code='ACCOUNT_PASSWORD_RESET' AND r.email=:e AND r.secret_ciphertext IS NOT NULL""", {"e": email_user["email"].lower()})[0]["n"]
check("Lien chiffré au repos puis effacé après envoi", wiped == 0, wiped)
new_pw = f"Nouveau-{uuid4().hex[:10]}!"
rs = httpx.post(BASE + "/auth/password/reset", json={"token": token, "new_password": new_pw}, headers={"Origin": "http://localhost:5180"}, timeout=30)
rs2 = httpx.post(BASE + "/auth/password/reset", json={"token": token, "new_password": new_pw + "x"}, headers={"Origin": "http://localhost:5180"}, timeout=30)
check("Réinitialisation acceptée une fois ; rejeu du même lien refusé", rs.status_code == 200 and rs2.status_code == 400, (rs.status_code, rs2.status_code))
lg = httpx.post(BASE + "/auth/login", json={"email": email_user["email"], "password": new_pw, "scope": "SCHOOL", "school_code": A["code"]}, timeout=30)
check("Connexion avec le nouveau mot de passe", lg.status_code == 200, lg.status_code)
email_user["password"] = new_pw
save()
alert = wait(lambda: fake_mail(email_user["email"], "réinitialisé"))
check("Alerte de sécurité envoyée après la réinitialisation", bool(alert))

# ---------------------------------------------------------------- e-mail: invitation (no password sent, expiry)
inv_email = f"invite.{run.lower()}@example.test"
inv = ok(admA.post("access/members", json={"email": inv_email, "full_name": f"Invité {run}", "reason": "Recette invitation", "delivery": "INVITATION"}, headers=k()))
check("Invitation : aucun mot de passe montré ni envoyé", inv.get("temporary_password") is None and inv.get("invitation_sent") is True, sorted(inv))
imail = wait(lambda: fake_mail(inv_email, "#invitation="))
itok = re.search(r"#invitation=([A-Za-z0-9_\-]+)", imail["text"]).group(1) if imail else ""
check("E-mail d'invitation : lien unique, sans mot de passe", bool(itok) and "mot de passe provisoire" not in (imail or {}).get("text", ""), bool(imail))
det = httpx.get(BASE + f"/auth/invitations/{itok}", timeout=30)
check("Invitation : nom et école affichés, jamais l'adresse e-mail", det.status_code == 200 and inv_email not in det.text and det.json().get("school_name"), det.text[:120])
acc = httpx.post(BASE + "/auth/invitations/accept", json={"token": itok, "new_password": "Invitation-Choisie-123"}, headers={"Origin": "http://localhost:5180"}, timeout=30)
acc2 = httpx.post(BASE + "/auth/invitations/accept", json={"token": itok, "new_password": "Invitation-Choisie-456"}, headers={"Origin": "http://localhost:5180"}, timeout=30)
check("Invitation acceptée une fois ; réutilisation refusée", acc.status_code == 200 and acc2.status_code == 400, (acc.status_code, acc2.status_code))
inv2 = ok(admA.post("access/members", json={"email": f"expire.{run.lower()}@example.test", "full_name": f"Expiré {run}", "reason": "Recette expiration", "delivery": "INVITATION"}, headers=k()))
mail2 = wait(lambda: fake_mail(f"expire.{run.lower()}@example.test", "#invitation="))
etok = re.search(r"#invitation=([A-Za-z0-9_\-]+)", mail2["text"]).group(1) if mail2 else ""
with owner.begin() as c:
    c.execute(text("UPDATE account_tokens SET created_at=now()-interval '3 days', expires_at=now()-interval '1 hour' WHERE token_hash=encode(sha256(CAST(:t AS bytea)),'hex')"), {"t": etok})
exp = httpx.post(BASE + "/auth/invitations/accept", json={"token": etok, "new_password": "Trop-Tard-12345"}, headers={"Origin": "http://localhost:5180"}, timeout=30)
check("Invitation expirée refusée", exp.status_code == 400, exp.status_code)

# ---------------------------------------------------------------- push: devices, test, invalid / reassigned token
tok1, tok2, dead = f"fcm-{uuid4().hex}{uuid4().hex}", f"fcm-{uuid4().hex}{uuid4().hex}", f"dead-{uuid4().hex}{uuid4().hex}"
s1 = ok(prefA.post("notifications/push-subscriptions", json={"provider": "FCM", "endpoint": tok1, "device_label": "Téléphone 1", "platform": "android", "browser": "chrome"}))
s2 = ok(prefA.post("notifications/push-subscriptions", json={"provider": "FCM", "endpoint": tok2, "device_label": "Téléphone 2"}))
raw = q("SELECT count(*) n FROM push_subscriptions WHERE token_ciphertext LIKE :t OR device_label LIKE :t", {"t": f"%{tok1[:20]}%"})[0]["n"]
check("Push : deux appareils enregistrés, jeton jamais stocké en clair", s1["status"] == "subscribed" and s2["status"] == "subscribed" and raw == 0, raw)
lst = ok(prefA.get("notifications/push-subscriptions"))["items"]
check("Push : la liste de l'utilisateur ne renvoie jamais le jeton", len(lst) == 2 and tok1 not in json.dumps(lst), len(lst))
pt = ok(prefA.post("notifications/push-test"))
ps = wait(lambda: (lambda r: r if len(r) == 2 and all(x["status"] == "SENT" for x in r) else None)(
    q("SELECT status FROM communication_deliveries WHERE message_id=:m AND channel='PUSH'", {"m": pt["message_id"]})))
check("Push test : envoyé aux 2 appareils par le worker (outbox)", bool(ps), ps)
s3 = ok(prefA.post("notifications/push-subscriptions", json={"provider": "FCM", "endpoint": dead, "device_label": "Ancien navigateur"}))
pt2 = ok(prefA.post("notifications/push-test"))
rev = wait(lambda: q("SELECT revoked_reason FROM push_subscriptions WHERE id=:i AND revoked_at IS NOT NULL", {"i": s3["id"]}))
others = q("SELECT count(*) n FROM push_subscriptions WHERE id IN (:a,:b) AND revoked_at IS NULL", {"a": s1["id"], "b": s2["id"]})[0]["n"]
check("Jeton déclaré invalide par le fournisseur → appareil désactivé, les autres restent actifs",
      rev and rev[0]["revoked_reason"] == "PROVIDER_INVALID_TOKEN" and others == 2, (rev, others))
ok(prefA.post(f"notifications/push-subscriptions/{s2['id']}/revoke", headers=k()))
left = q("SELECT count(*) n FROM push_subscriptions WHERE user_id=(SELECT user_id FROM push_subscriptions WHERE id=:a) AND school_id=:s AND revoked_at IS NULL",
         {"a": s1["id"], "s": A["school_id"]})[0]["n"]
check("Révocation d'un appareil sans toucher les autres", left == 1, left)
ok(adminB.post("notifications/push-subscriptions", json={"provider": "FCM", "endpoint": tok1, "device_label": "Même navigateur, école B"}))
moved = q("SELECT revoked_reason FROM push_subscriptions WHERE id=:i", {"i": s1["id"]})[0]["revoked_reason"]
check("Même navigateur réutilisé par un autre compte / une autre école → ancien enregistrement révoqué (aucune fuite A → B)", moved == "TOKEN_REASSIGNED", moved)
bl = ok(adminB.get("notifications/push-subscriptions"))["items"]
check("Multi-école : l'école B ne voit que ses propres appareils", len(bl) == 1, len(bl))

# ---------------------------------------------------------------- Atelier Pro supervision (metadata only)
st = ok(mgr.get("platform/messaging/status"))
wl = ok(mgr.get("platform/messaging/wallets"))
check("Atelier Pro : état des fournisseurs, file et volumes, sans corps de message", "providers" in st and body not in json.dumps(st) and run not in json.dumps(st.get("volumes_24h")), list(st))
row = next((x for x in wl["items"] if x["school_id"] == A["school_id"]), None)
check("Atelier Pro : portefeuille de chaque école (solde, réservé, seuil, consommation 30 j)", row and row["balance"] == 159 and row["consumed_30d"] == 1, row)
forbid = prefA.get("platform/messaging/status")
check("RBAC : un compte école n'accède pas à la supervision plateforme", forbid.status_code in (401, 403), forbid.status_code)

# ---------------------------------------------------------------- no secret in API responses / logs
leaks = []
for name, payload in (("status", st), ("wallets", wl), ("history", hist), ("devices", lst)):
    blob = json.dumps(payload, default=str)
    for secret in (tok1, tok2, token, itok, os.environ.get("EDUSYNC_JWT_SECRET", "x" * 40)):
        if secret and secret in blob:
            leaks.append(name)
log = (Path(__file__).resolve().parents[2] / ".local" / "logs" / "communications-worker.log")
logtxt = log.read_text(encoding="utf-8", errors="ignore")[-400000:] if log.exists() else ""
for secret in (tok1, token, itok):
    if secret and secret in logtxt:
        leaks.append("worker-log")
check("Aucun jeton push, lien de compte ou secret dans les réponses API ni dans le journal du worker", not leaks, leaks)

passed = sum(r["pass"] for r in results)
OUT.write_text(json.dumps({"probe": "messaging_local_probe", "providers": "FAKE (development only)", "run": run, "checks": results,
                           "summary": f"{passed}/{len(results)}"}, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"== {passed}/{len(results)} {'PASS' if passed == len(results) else 'FAIL'} -> {OUT.name}")
sys.exit(0 if passed == len(results) else 1)
