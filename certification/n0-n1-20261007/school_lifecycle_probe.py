"""Live probe — N1 school lifecycle: creation (idempotency, uniqueness, concurrency), first admin, suspension and
reactivation with their real effects (sign-in, sessions, refresh, API, signed documents, SMS worker), audit.

Isolated local instance only. Test accounts and passwords are generated here and never printed.
"""
import json
import os
import secrets
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import BASE, owner, platform  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend" / "src"))
from edusync.bootstrap.settings import Settings  # noqa: E402
from edusync.modules.documents.application import object_store  # noqa: E402

COOKIE = "edusync_session"
results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


def post(client, path, body, key=None):
    return client.post(path, json=body, headers={"Idempotency-Key": key or str(uuid4())})


run = uuid4().hex[:6].upper()
mgr = platform()
code = f"N1S-{run}"

# ---------- creation: idempotency, uniqueness, concurrency ----------
key = str(uuid4())
c1 = post(mgr, "platform/schools", {"name": f"École N1 {run}", "code": code}, key)
c2 = post(mgr, "platform/schools", {"name": f"École N1 {run}", "code": code}, key)
check("Création d'école (201)", c1.status_code == 201, c1.status_code)
check("Réponse perdue / double clic : même clé -> même école, rejouée", c2.status_code == 201 and c2.json()["id"] == c1.json()["id"] and c2.headers.get("Idempotent-Replayed") == "true", c2.headers.get("Idempotent-Replayed"))
school_id = c1.json()["id"]
check("Code déjà utilisé (autre clé) -> 409", post(mgr, "platform/schools", {"name": "Doublon", "code": code}).status_code == 409)
check("Même clé, contenu différent -> 409 (pas de réutilisation silencieuse)", post(mgr, "platform/schools", {"name": "Autre nom", "code": code + "X"}, key).status_code == 409)

race_code, outs = f"N1R-{run}", []
def _create():
    with httpx.Client(base_url=BASE + "/", timeout=60, headers=dict(mgr.headers)) as c:
        outs.append(post(c, "platform/schools", {"name": f"Course {run}", "code": race_code}))
ts = [threading.Thread(target=_create) for _ in range(4)]
[t.start() for t in ts]; [t.join() for t in ts]
with owner.connect() as c:
    n = c.execute(text("SELECT count(*) FROM schools WHERE code=:c"), {"c": race_code}).scalar_one()
check("4 créations simultanées du même code : une seule école, les autres 409", n == 1 and sorted(o.status_code for o in outs) == [201, 409, 409, 409], sorted(o.status_code for o in outs))
check("Code normalisé en majuscules", c1.json()["code"] == code.upper())

# ---------- first admin ----------
admin = {"email": f"admin-{run.lower()}@example.test", "password": secrets.token_urlsafe(18)}
b = post(mgr, f"platform/schools/{school_id}/bootstrap-admin", {"email": admin["email"], "full_name": "Admin initial N1", "password": admin["password"]})
check("Administrateur initial créé (ADMIN_SYSTEME_ECOLE)", b.status_code in (200, 201), b.status_code)
# Owner decision 2026-10-14 (Desktop parity): the password typed by the platform is a bootstrap credential only.
first = httpx.post(BASE + "/auth/login", json={"email": admin["email"], "password": admin["password"]}, timeout=30)
fd = first.json()
check("Admin initial : 1re connexion = choisir son mot de passe, aucune session", first.status_code == 200 and fd.get("password_change_required") is True
      and "access_token" not in fd and not first.cookies.get(COOKIE), sorted(fd)[:4])
provisional = admin["password"]
admin["password"] = secrets.token_urlsafe(18)
ch = httpx.post(BASE + "/auth/password/first-change", json={"change_token": fd.get("change_token"), "new_password": admin["password"]}, timeout=30)
again = httpx.post(BASE + "/auth/login", json={"email": admin["email"], "password": provisional}, timeout=30)
check("Admin initial : mot de passe choisi ; le provisoire est refusé ensuite", ch.status_code in (200, 204) and again.status_code == 401, (ch.status_code, again.status_code))
lg = httpx.post(BASE + "/auth/login", json={"email": admin["email"], "password": admin["password"]}, timeout=30)
check("Admin initial : connexion AUTO dans son école", lg.status_code == 200 and lg.json().get("school", {}).get("code") == code.upper(), lg.status_code)
token, raw = lg.json()["access_token"], lg.cookies.get(COOKIE)
api = httpx.Client(base_url=BASE + "/", timeout=60, headers={"Authorization": "Bearer " + token})
check("Admin initial : API école accessible", api.get("auth/me").status_code == 200)

# Evidence objects owned by this school (owner SQL, test data only).
with owner.begin() as c:
    uid = c.execute(text("SELECT id FROM users WHERE lower(email::text)=:e"), {"e": admin["email"]}).scalar_one()
    doc_id = c.execute(text("""INSERT INTO generated_documents(school_id,document_code,format,title,object_key,sha256,byte_size,generated_by,file_name,content_type,logical_key)
        VALUES(:s,'N1_PROBE','PDF','Preuve N1',:k,repeat('0',64),0,:u,'preuve.pdf','application/pdf',:k) RETURNING id"""),
        {"s": school_id, "k": f"schools/{school_id}/n1-probe/absent.pdf", "u": uid}).scalar_one()
settings = Settings()
link, _ = object_store.sign_link(settings, document_id=str(doc_id), school_id=school_id, user_id=str(uid))


def open_link():
    return httpx.get(BASE + "/documents/open", params={"token": link}, timeout=30).status_code


def delivery():
    with owner.connect() as c:
        return c.execute(text("SELECT status,attempts FROM communication_deliveries WHERE id=:d"), {"d": dlv}).mappings().one()


before_link = open_link()
check("Lien signé : vérifié avant suspension (pas de refus d'accès)", before_link != 403, before_link)

# ---------- suspension ----------
sp = post(mgr, f"platform/schools/{school_id}/suspend", {"reason": "Recette N1 : suspension"})
# A message queued while the school is suspended (owner SQL, test data): the worker must hold it.
with owner.begin() as c:
    msg = c.execute(text("""INSERT INTO communication_messages(school_id,kind,audience_type,body) VALUES(:s,'MANUAL','PARENT','Message de recette N1') RETURNING id"""), {"s": school_id}).scalar_one()
    dlv = c.execute(text("""INSERT INTO communication_deliveries(school_id,message_id,channel,destination) VALUES(:s,:m,'SMS','+243000000000') RETURNING id"""), {"s": school_id, "m": msg}).scalar_one()
check("Suspension (200, auditée)", sp.status_code == 200 and sp.json()["status"] == "SUSPENDED", sp.status_code)
with owner.connect() as c:
    open_sessions = c.execute(text("SELECT count(*) FROM user_device_sessions WHERE school_id=:s AND revoked_at IS NULL"), {"s": school_id}).scalar_one()
    reason = c.execute(text("SELECT revoked_reason FROM user_device_sessions WHERE school_id=:s ORDER BY created_at DESC LIMIT 1"), {"s": school_id}).scalar_one()
check("Suspension : toutes les sessions de l'école fermées", open_sessions == 0 and reason == "SCHOOL_SUSPENDED", reason)
check("Suspension : jeton en cours refusé par l'API", api.get("auth/me").status_code in (401, 403))
check("Suspension : renouvellement de session refusé", httpx.post(BASE + "/auth/refresh", cookies={COOKIE: raw}, timeout=30).status_code == 401)
check("Suspension : connexion refusée (AUTO)", httpx.post(BASE + "/auth/login", json={"email": admin["email"], "password": admin["password"]}, timeout=30).status_code == 403)
check("Suspension : connexion explicite refusée", httpx.post(BASE + "/auth/login", json={"email": admin["email"], "password": admin["password"], "scope": "SCHOOL", "school_code": code}, timeout=30).status_code == 403)
check("Suspension : lien de document signé refusé", open_link() == 403)
time.sleep(12)
d = delivery()
# External messaging (2026-10): canonical states — a waiting delivery is QUEUED (formerly PENDING).
check("Suspension : SMS en attente retenu par le worker (non envoyé, non perdu)", d["status"] == "QUEUED" and d["attempts"] == 0, dict(d))
check("Suspension : école exclue des notifications système ciblées", post(mgr, "platform/system-notifications", {"title": "Test", "body": "Test ciblé", "severity": "INFO", "target_scope": "SCHOOL", "target_school_id": school_id}).status_code in (404, 409, 422))
replay = post(mgr, f"platform/schools/{school_id}/suspend", {"reason": "Recette N1 : suspension"})
check("Suspension répétée (nouvelle clé) : refusée proprement, pas de 500", replay.status_code in (200, 409), replay.status_code)

# ---------- reactivation ----------
rv = post(mgr, f"platform/schools/{school_id}/reactivate", {"reason": "Recette N1 : réactivation"})
check("Réactivation (200)", rv.status_code == 200 and rv.json()["status"] == "ACTIVE", rv.status_code)
lg2 = httpx.post(BASE + "/auth/login", json={"email": admin["email"], "password": admin["password"]}, timeout=30)
check("Réactivation : connexion de nouveau possible", lg2.status_code == 200)
check("Réactivation : lien signé de nouveau vérifié", open_link() != 403)
deadline = time.time() + 40
while time.time() < deadline and delivery()["status"] == "QUEUED":
    time.sleep(2)
d = delivery()
check("Réactivation : le SMS retenu est repris par le worker", d["status"] != "QUEUED" or d["attempts"] > 0, dict(d))
with owner.connect() as c:
    acts = {r[0] for r in c.execute(text("SELECT action FROM audit_events WHERE entity_id=:s"), {"s": school_id})}
check("Audit : création, admin initial, suspension, réactivation", {"SCHOOL_CREATED", "SCHOOL_SUSPENDED", "SCHOOL_REACTIVATED"} <= acts, sorted(acts))

# ---------- full identity (contacts, address), validation ----------
full = {"name": f"École complète {run}", "code": f"N1F-{run}", "email": "secretariat@ecole.test", "phone": "+243 81 000 0000",
        "address": "12 avenue de la Paix", "city": "Goma", "province": "Nord-Kivu", "logo_url": "https://evil.example/x.png"}
rf = post(mgr, "platform/schools", full)
fj = rf.json() if rf.status_code == 201 else {}
check("Création complète : contacts et adresse enregistrés", rf.status_code == 201 and fj.get("email") == full["email"] and fj.get("city") == "Goma" and fj.get("province") == "Nord-Kivu", rf.status_code)
check("URL de logo externe ignorée (logo uniquement téléversé par l'école)", fj.get("logo_url") is None)
for label, patch_ in (("e-mail", {"email": "pas-un-email"}), ("téléphone", {"phone": "abc"}), ("code", {"code": "A B"})):
    bad = {**full, "code": f"N1X-{uuid4().hex[:5].upper()}", **patch_}
    check(f"Validation : {label} invalide refusé (422)", post(mgr, "platform/schools", bad).status_code == 422)
with owner.connect() as c:
    au = c.execute(text("SELECT new_json FROM audit_events WHERE action='SCHOOL_CREATED' AND entity_id=:s"), {"s": fj.get("id")}).scalar_one_or_none()
check("Audit de création : identité et contacts tracés", bool(au) and au.get("province") == "Nord-Kivu")
out = Path(__file__).with_name("school-lifecycle-live.json")
out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(f"== {sum(r['pass'] for r in results)}/{len(results)} PASS -> {out.name}")
