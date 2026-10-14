"""Live probe — N2: a school administrates itself (users, roles, configuration) and twin schools never leak.

Runs against the isolated local instance (real API + PostgreSQL + Redis). Two fresh twin schools are created through
the public platform API, with deliberately similar classes, fees and users. Generated credentials stay in the private
fixtures file under .local/ and are never printed.
"""
import json
import os
import secrets
import sys
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import BASE, owner, platform, save, settle_first_password, state  # noqa: E402

results = []
COOKIE = "edusync_session"


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


def key():
    return {"Idempotency-Key": str(uuid4())}


def raw_login(email, password, **extra):
    return httpx.post(BASE + "/auth/login", json={"email": email, "password": password, **extra}, timeout=30)


def school_client(email, password, code):
    r = raw_login(email, password, scope="SCHOOL", school_code=code)
    assert r.status_code == 200 and "access_token" in r.json(), (r.status_code, r.text[:200])
    return httpx.Client(base_url=BASE + "/", headers={"Authorization": "Bearer " + r.json()["access_token"]}, timeout=60), r


run = uuid4().hex[:6].upper()
fx = state.setdefault("N2", {})
mgr = platform()

# ---------- twin schools ----------
twins = {}
for t in ("A", "B"):
    code = f"N2{t}-{run}"
    s = mgr.post("platform/schools", json={"code": code, "name": f"École jumelle {t} — N2 {run}"}, headers=key())
    assert s.status_code == 201, s.text[:200]
    email, pw = f"n2-admin-{t.lower()}-{run.lower()}@example.test", secrets.token_urlsafe(18)
    b = mgr.post(f"platform/schools/{s.json()['id']}/bootstrap-admin", json={"email": email, "full_name": f"Admin jumelle {t}", "password": pw}, headers=key())
    assert b.status_code in (200, 201), b.text[:200]
    twins[t] = {"code": code, "school_id": s.json()["id"], "admin": {"email": email, "password": pw, "membership_id": b.json()["membership_id"]}}
fx[run] = twins
save()
for t in ("A", "B"):
    assert settle_first_password(twins[t]["admin"]), "un administrateur créé par la plateforme doit d'abord choisir son mot de passe"
save()
A, B = twins["A"], twins["B"]
ca, _ = school_client(A["admin"]["email"], A["admin"]["password"], A["code"])
cb, _ = school_client(B["admin"]["email"], B["admin"]["password"], B["code"])
check("Écoles jumelles créées par la plateforme, administrateurs connectés", True, f"{A['code']} / {B['code']}")
roles_a = {r["code"]: r for r in ca.get("access/roles").json()["items"]}
cashier_role = roles_a.get("CAISSIER")
check("Rôles standard visibles par l'administrateur (dont Caissier)", cashier_role is not None, sorted(roles_a)[:8])

# ---------- 1. create a member: temporary password, once ----------
k = key()
body = {"email": f"n2-caissier-{run.lower()}@example.test", "full_name": "Caissier Jumelle A", "role_id": cashier_role["id"], "reason": "Arrivée N2"}
c1 = ca.post("access/members", json=body, headers=k)
d1 = c1.json()
tmp = d1.get("temporary_password") or ""
check("Création d'un membre par l'école : compte créé, rôle attribué, mot de passe provisoire affiché", c1.status_code == 201 and d1.get("created") is True and d1.get("role_label") and len(tmp) >= 12, c1.status_code)
c1b = ca.post("access/members", json=body, headers=k)
check("Double clic / réponse perdue : même membre, et le mot de passe n'est jamais rejoué", c1b.status_code in (200, 201) and c1b.json().get("membership_id") == d1.get("membership_id") and not c1b.json().get("temporary_password"))
with owner.connect() as c:
    leak_idem = c.execute(text("SELECT count(*) FROM idempotency_registry WHERE response_json::text LIKE :p"), {"p": f"%{tmp}%"}).scalar_one() if tmp else 1
    leak_audit = c.execute(text("SELECT count(*) FROM audit_events WHERE coalesce(new_json::text,'') LIKE :p OR coalesce(reason,'') LIKE :p"), {"p": f"%{tmp}%"}).scalar_one() if tmp else 1
    flag = c.execute(text("SELECT must_change_password, password_set_by FROM users WHERE lower(email::text)=:e"), {"e": body["email"]}).first()
check("Mot de passe provisoire absent du registre d'idempotence et de l'audit", leak_idem == 0 and leak_audit == 0, (leak_idem, leak_audit))
check("Compte marqué « mot de passe à remplacer » (défini par l'école)", flag and flag[0] is True and flag[1] == "SCHOOL", flag)
dup = ca.post("access/members", json={**body, "role_id": None}, headers=key())
check("Même personne ajoutée deux fois → 409 explicite", dup.status_code == 409, dup.status_code)
cashier_mid = d1["membership_id"]

# ---------- 2. first sign-in: the temporary password must be replaced ----------
r = raw_login(body["email"], tmp)
d = r.json()
check("Première connexion : aucune session avant d'avoir choisi son mot de passe", r.status_code == 200 and d.get("password_change_required") is True and "access_token" not in d and not r.cookies.get(COOKIE), list(d))
same = httpx.post(BASE + "/auth/password/first-change", json={"change_token": d["change_token"], "new_password": tmp}, timeout=30)
check("Nouveau mot de passe identique au provisoire → refusé (422)", same.status_code == 422, same.status_code)
own = secrets.token_urlsafe(16)
ch = httpx.post(BASE + "/auth/password/first-change", json={"change_token": d["change_token"], "new_password": own}, timeout=30)
check("Mot de passe personnel enregistré (sans ouvrir de session)", ch.status_code == 200 and ch.json() == {"changed": True} and not ch.cookies.get(COOKIE), ch.status_code)
check("Étape consommée : réutilisation refusée", httpx.post(BASE + "/auth/password/first-change", json={"change_token": d["change_token"], "new_password": secrets.token_urlsafe(16)}, timeout=30).status_code == 401)
check("Ancien mot de passe provisoire refusé", raw_login(body["email"], tmp).status_code == 401)
cc, lr = school_client(body["email"], own, A["code"])
check("Connexion avec son mot de passe → espace école ouvert avec ses droits de caissier", lr.json().get("scope") == "SCHOOL" and any(p.startswith("finance.") for p in lr.json().get("permissions", [])))
fx[run]["cashier"] = {"email": body["email"], "password": own, "membership_id": cashier_mid}
save()

# ---------- 3. existing account (twin school B): attached, password untouched ----------
att = ca.post("access/members", json={"email": B["admin"]["email"], "full_name": "Ignoré", "reason": "Intervenant partagé"}, headers=key())
ad = att.json()
check("Adresse déjà utilisée dans l'école B → compte rattaché, aucun mot de passe affiché", att.status_code == 201 and ad.get("attached_existing_account") is True and not ad.get("temporary_password"), att.text[:160])
check("Le nom du compte existant n'est pas modifié par l'école A", ad.get("full_name") == "Admin jumelle B")
br = raw_login(B["admin"]["email"], B["admin"]["password"])
check("Le titulaire garde son mot de passe et voit maintenant ses deux écoles", br.status_code == 200 and br.json().get("choice_required") is True and len(br.json().get("contexts", [])) == 2)
shared_mid = ad["membership_id"]
check("Compte partagé : réinitialisation du mot de passe par l'école A refusée (409)", ca.post(f"access/members/{shared_mid}/credentials-reset", json={"reason": "tentative"}, headers=key()).status_code == 409)
check("Compte partagé : changement de nom par l'école A refusé (409)", ca.patch(f"access/members/{shared_mid}", json={"full_name": "Usurpé", "reason": "tentative"}, headers=key()).status_code == 409)
items = {m["membership_id"]: m for m in ca.get("access/members").json()["items"]}
check("Liste des membres : compte partagé signalé, mot de passe provisoire signalé",
      items.get(shared_mid, {}).get("shared_account") is True and items.get(cashier_mid, {}).get("must_change_password") is False)

# ---------- 4. reset, rename, deactivate / reactivate ----------
rn = ca.patch(f"access/members/{cashier_mid}", json={"full_name": "Caissière Jumelle A", "reason": "Correction du nom"}, headers=key())
check("Modification du nom d'un membre propre à l'école", rn.status_code == 200 and rn.json()["full_name"] == "Caissière Jumelle A", rn.status_code)
rs = ca.post(f"access/members/{cashier_mid}/credentials-reset", json={"reason": "Mot de passe oublié"}, headers=key())
new_tmp = rs.json().get("temporary_password") or ""
check("Réinitialisation : nouveau provisoire, sessions coupées", rs.status_code == 200 and len(new_tmp) >= 12 and rs.json().get("sessions_revoked", 0) >= 1, rs.status_code)
check("Après réinitialisation : ancien jeton coupé immédiatement", cc.get("auth/me").status_code == 401)
check("Après réinitialisation : ancien mot de passe refusé, provisoire → changement exigé",
      raw_login(body["email"], own).status_code == 401 and raw_login(body["email"], new_tmp).json().get("password_change_required") is True)
d = raw_login(body["email"], new_tmp).json()
own2 = secrets.token_urlsafe(16)
httpx.post(BASE + "/auth/password/first-change", json={"change_token": d["change_token"], "new_password": own2}, timeout=30)
fx[run]["cashier"]["password"] = own2
save()
cc, _ = school_client(body["email"], own2, A["code"])
de = ca.post(f"access/members/{cashier_mid}/deactivate", json={"reason": "Départ"}, headers=key())
check("Désactivation : accès à l'école coupé", de.status_code == 200 and de.json()["active"] is False, de.status_code)
check("Désactivation : jeton en cours refusé immédiatement", cc.get("auth/me").status_code in (401, 403))
check("Désactivation : plus aucun espace à la connexion (403)", raw_login(body["email"], own2).status_code == 403)
check("Réinitialisation d'un membre désactivé → refusée (409)", ca.post(f"access/members/{cashier_mid}/credentials-reset", json={"reason": "x" * 5}, headers=key()).status_code == 409)
re_ = ca.post(f"access/members/{cashier_mid}/activate", json={"reason": "Retour"}, headers=key())
check("Réactivation : accès rétabli avec ses rôles", re_.status_code == 200 and raw_login(body["email"], own2, scope="SCHOOL", school_code=A["code"]).status_code == 200)
check("Personne n'agit sur son propre compte (désactivation de soi → 403)", ca.post(f"access/members/{A['admin']['membership_id']}/deactivate", json={"reason": "moi"}, headers=key()).status_code == 403)

# ---------- 5. anti-escalation ----------
caps_delegate = ["access.roles.read", "access.permissions.assign", "access.users.create", "access.users.read"]
cr = ca.post("access/roles", json={"label": f"Délégué accès {run}", "capabilities": caps_delegate}, headers=key())
check("Rôle propre à l'école créé (délégation limitée)", cr.status_code == 201, cr.status_code)
dmail, dpw = f"n2-delegue-{run.lower()}@example.test", None
dm = ca.post("access/members", json={"email": dmail, "full_name": "Délégué A", "role_id": cr.json()["id"], "reason": "Délégation"}, headers=key()).json()
dt = raw_login(dmail, dm["temporary_password"]).json()
dpw = secrets.token_urlsafe(16)
httpx.post(BASE + "/auth/password/first-change", json={"change_token": dt["change_token"], "new_password": dpw}, timeout=30)
cd, _ = school_client(dmail, dpw, A["code"])
admin_role = roles_a["ADMIN_SYSTEME_ECOLE"]
esc1 = cd.post(f"access/members/{cashier_mid}/roles", json={"role_id": admin_role["id"], "reason": "escalade"}, headers=key())
check("Anti-escalade : un délégué ne donne pas le rôle d'administrateur qu'il n'a pas (403)", esc1.status_code == 403, esc1.text[:120])
esc2 = cd.post("access/members", json={"email": f"n2-complice-{run.lower()}@example.test", "full_name": "Complice", "role_id": admin_role["id"], "reason": "escalade"}, headers=key())
check("Anti-escalade : création d'un complice administrateur refusée (403)", esc2.status_code == 403, esc2.status_code)
with owner.connect() as c:
    accomplice = c.execute(text("SELECT count(*) FROM users WHERE lower(email::text)=:e"), {"e": f"n2-complice-{run.lower()}@example.test"}).scalar_one()
check("Anti-escalade : aucun compte complice créé (transaction annulée)", accomplice == 0, accomplice)
ok_assign = cd.post(f"access/members/{shared_mid}/roles", json={"role_id": cr.json()["id"], "reason": "délégation identique"}, headers=key())
check("Le délégué peut transmettre un rôle qu'il détient entièrement", ok_assign.status_code == 201, ok_assign.status_code)
check("Le délégué ne peut pas réinitialiser un mot de passe (droit absent → 403)", cd.post(f"access/members/{cashier_mid}/credentials-reset", json={"reason": "x" * 5}, headers=key()).status_code == 403)
with owner.connect() as c:
    actions = set(c.execute(text("SELECT action FROM audit_events WHERE school_id=:s AND action LIKE 'ACCESS_MEMBER_%'"), {"s": A["school_id"]}).scalars())
check("Journal : création, rattachement, modification, réinitialisation, désactivation, réactivation audités",
      {"ACCESS_MEMBER_CREATED", "ACCESS_MEMBER_ATTACHED", "ACCESS_MEMBER_UPDATED", "ACCESS_MEMBER_CREDENTIALS_RESET", "ACCESS_MEMBER_DEACTIVATED", "ACCESS_MEMBER_ACTIVATED"} <= actions, sorted(actions))

# ---------- 6. twin schools: same names, zero leak ----------
for cl in (ca, cb):
    y = cl.post("settings/academic-years", json={"code": "2026-2027", "label": "2026-2027", "start_date": "2026-09-01", "end_date": "2027-06-30"}, headers=key()).json()
    cl.post(f"settings/academic-years/{y['id']}/activate", headers={**key(), "If-Match": str(y["version"])})
    cl.put("settings/sections/PRIMAIRE", json={"code": "PRIMAIRE", "label": "Primaire", "enabled": True}, headers=key())
twin_ids = {}
for t, cl in (("A", ca), ("B", cb)):
    year = next(y for y in cl.get("settings/academic-years").json() if y["status"] == "ACTIVE")
    section = next(s for s in cl.get("settings/sections").json() if s["code"].upper() == "PRIMAIRE")
    cls = cl.post("settings/classes", json={"academic_year_id": year["id"], "section_id": section["id"], "reference_code": "1A", "code": "1A", "label": "1re année A"}, headers=key())
    fee = cl.post("settings/fee-types", json={"code": "MINERVAL", "label": "Minerval", "periodicity": "MONTHLY", "default_currency": "CDF"}, headers=key())
    tar = cl.post("settings/tariffs", json={"academic_year_id": year["id"], "fee_type_id": fee.json()["id"], "currency": "CDF", "amount": "25000.00",
                                            "class_id": cls.json()["id"], "billing_months": []}, headers=key())
    twin_ids[t] = {"class": cls.json(), "fee": fee.json(), "tariff": tar.json(), "year": year}
check("Configuration jumelle : même classe « 1A », même frais « MINERVAL », même tarif dans A et B",
      all(twin_ids[t]["class"].get("id") and twin_ids[t]["tariff"].get("id") for t in "AB"))
a_classes = ca.get("settings/classes").json()
check("École A : ne voit que ses classes", twin_ids["B"]["class"]["id"] not in {c["id"] for c in a_classes} and twin_ids["A"]["class"]["id"] in {c["id"] for c in a_classes})
check("École A : ne voit que ses tarifs", twin_ids["B"]["tariff"]["id"] not in {t["id"] for t in ca.get("settings/tariffs").json()})
check("École A : ne voit que ses types de frais", twin_ids["B"]["fee"]["id"] not in {f["id"] for f in ca.get("settings/fee-types").json()})
bc = twin_ids["B"]["class"]
upd = ca.put(f"settings/classes/{bc['id']}", json={**{k2: bc[k2] for k2 in ("academic_year_id", "section_id", "code", "label")}, "label": "Piratée", "enabled": False},
             headers={**key(), "If-Match": str(bc.get("version", 1))})
check("UUID deviné : modifier la classe de B depuis A → refusé (404/409/422)", upd.status_code in (403, 404, 409, 422), upd.status_code)
b_members = {m["membership_id"] for m in cb.get("access/members").json()["items"]}
a_members = {m["membership_id"] for m in ca.get("access/members").json()["items"]}
check("Membres : A ne liste aucun membre de B (hors compte rattaché à A)", not (a_members & b_members))
for label, call in (("désactiver", lambda: ca.post(f"access/members/{B['admin']['membership_id']}/deactivate", json={"reason": "x" * 5}, headers=key())),
                    ("réinitialiser", lambda: ca.post(f"access/members/{B['admin']['membership_id']}/credentials-reset", json={"reason": "x" * 5}, headers=key())),
                    ("renommer", lambda: ca.patch(f"access/members/{B['admin']['membership_id']}", json={"full_name": "Piraté", "reason": "x" * 5}, headers=key())),
                    ("attribuer un rôle", lambda: ca.post(f"access/members/{B['admin']['membership_id']}/roles", json={"role_id": cashier_role["id"], "reason": "x" * 5}, headers=key()))):
    rr = call()
    check(f"UUID deviné : {label} un membre de l'école B depuis A → 404", rr.status_code == 404, rr.status_code)
b_role = cb.post("access/roles", json={"label": f"Rôle B {run}", "capabilities": ["access.roles.read"]}, headers=key()).json()
check("UUID deviné : attribuer dans A un rôle propre à B → 404",
      ca.post(f"access/members/{cashier_mid}/roles", json={"role_id": b_role["id"], "reason": "x" * 5}, headers=key()).status_code == 404)
b_jour = cb.get("access/journal").json()["items"]
check("Journal des droits de B : aucune action de l'école A", not any("Caissière Jumelle A" in json.dumps(i) or "Délégué A" in json.dumps(i) for i in b_jour))
ov = ca.get("settings/overview").json()
check("Vue d'ensemble de A : identité de A uniquement", ov["school"]["code"].upper() == A["code"].upper())
with owner.connect() as c:
    cross = c.execute(text("""SELECT count(*) FROM rbac_assignments a JOIN school_memberships m ON m.id=a.membership_id
        WHERE a.school_id IS NOT NULL AND a.school_id<>m.school_id"""), {}).scalar_one()
check("Base : aucune attribution de rôle à cheval sur deux écoles", cross == 0, cross)

out = Path(__file__).with_name("n2-live.json")
out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(f"== {sum(r['pass'] for r in results)}/{len(results)} PASS -> {out.name}")
