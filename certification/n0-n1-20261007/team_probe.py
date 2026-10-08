"""Live probe — N1 platform team governance: PLATFORM_CUSTOM roles, anti-escalation, accounts, suspension, concurrency.

Runs against the isolated local instance (real API + PostgreSQL). Generated accounts are test accounts; their
credentials are kept in the private fixtures file under .local/ and never printed.
"""
import json
import os
import secrets
import sys
import threading
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import BASE, owner, platform, save, state  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


def post(client, path, body, key=None):
    return client.post(path, json=body, headers={"Idempotency-Key": key or str(uuid4())})


def login_auto(email, password):
    return httpx.post(BASE + "/auth/login", json={"email": email, "password": password}, timeout=30)


def client_for(email, password):
    r = login_auto(email, password)
    c = httpx.Client(base_url=BASE + "/", timeout=60)
    if r.status_code == 200 and "access_token" in r.json():
        c.headers["Authorization"] = "Bearer " + r.json()["access_token"]
    return c, r


def audit_count(action, entity_id=None):
    with owner.connect() as c:
        return c.execute(text("SELECT count(*) FROM audit_events WHERE action=:a AND (CAST(:e AS uuid) IS NULL OR entity_id=:e)"),
                         {"a": action, "e": entity_id}).scalar_one()


run = uuid4().hex[:6].upper()
fx = state.setdefault("N1_TEAM", {})
mgr = platform()

# ---------- me / menu ----------
me = mgr.get("platform/team/me").json()
keys = [m["key"] for m in me["menu"]]
check("Manager : menu calculé par le serveur, 7 entrées dont Équipe", len(keys) == 7 and "team" in keys, keys)
check("Manager : rôle MANAGER_SYSTEME actif", any(r["code"] == "MANAGER_SYSTEME" for r in me["roles"]))

caps = mgr.get("platform/team/capabilities").json()["items"]
reserved = [c["code"] for c in caps if c["reserved"]]
check("Catalogue plateforme : uniquement des capacités platform.*", caps and all(c["code"].startswith("platform.") for c in caps), len(caps))
check("Capacité de gouvernance d'équipe marquée réservée", reserved == ["platform.collaborators.manage"], reserved)

# ---------- custom roles ----------
support_code, audit_code = f"SUPPORT_{run}", f"AUDITEUR_{run}"
key = str(uuid4())
r1 = post(mgr, "platform/team/roles", {"code": support_code, "label": "Support niveau 1", "capabilities": ["platform.schools.read", "platform.health.read"]}, key)
r1b = post(mgr, "platform/team/roles", {"code": support_code, "label": "Support niveau 1", "capabilities": ["platform.schools.read", "platform.health.read"]}, key)
check("Création PLATFORM_CUSTOM en brouillon", r1.status_code == 201 and r1.json()["status"] == "DRAFT", r1.status_code)
check("Double clic / réponse perdue : même clé -> même rôle, pas de doublon", r1b.status_code in (200, 201) and r1b.json().get("id") == r1.json().get("id"), r1b.status_code)
support_id = r1.json()["id"]
dup = post(mgr, "platform/team/roles", {"code": support_code, "label": "Autre", "capabilities": []})
check("Code de rôle unique (nouvelle clé) -> 409", dup.status_code == 409, dup.status_code)
check("Rôle avec capacité réservée refusé", post(mgr, "platform/team/roles", {"code": f"X1_{run}", "label": "Escalade", "capabilities": ["platform.collaborators.manage"]}).status_code == 403)
check("Rôle plateforme avec capacité ÉCOLE refusé (aucune capacité SCHOOL implicite)", post(mgr, "platform/team/roles", {"code": f"X2_{run}", "label": "Mélange", "capabilities": ["students.read"]}).status_code == 422)
check("Code de rôle invalide refusé", post(mgr, "platform/team/roles", {"code": "x y", "label": "Invalide", "capabilities": []}).status_code == 422)
try:
    with owner.begin() as c:
        c.execute(text("INSERT INTO rbac_role_capabilities(role_id,capability_code) VALUES(:r,'students.read')"), {"r": support_id})
    check("Base : capacité école dans un rôle plateforme bloquée par déclencheur", False, "insérée")
except Exception as e:  # noqa: BLE001
    check("Base : capacité école dans un rôle plateforme bloquée par déclencheur", "plateforme" in str(e), type(e).__name__)
try:
    with owner.begin() as c:
        c.execute(text("INSERT INTO rbac_role_capabilities(role_id,capability_code) VALUES(:r,'platform.collaborators.manage')"), {"r": support_id})
    check("Base : capacité réservée dans un rôle personnalisé bloquée", False, "insérée")
except Exception as e:  # noqa: BLE001
    check("Base : capacité réservée dans un rôle personnalisé bloquée", "réservée" in str(e), type(e).__name__)

std = next(r for r in mgr.get("platform/team/roles").json()["items"] if r["code"] == "MANAGER_SYSTEME")
check("Rôle standard non modifiable par l'API", mgr.put(f"platform/team/roles/{std['id']}", json={"label": "Hack", "capabilities": [], "version": std["version"]}, headers={"Idempotency-Key": str(uuid4())}).status_code == 403)

# Accounts cannot receive a DRAFT role.
fx["u2"] = ({"email": f"support-{run.lower()}@example.test", "password": secrets.token_urlsafe(18)})
fx["m2"] = ({"email": f"manager2-{run.lower()}@example.test", "password": secrets.token_urlsafe(18)})
save()
u2 = fx["u2"]
bad = post(mgr, "platform/team/users", {"email": u2["email"], "full_name": "Agent Support", "password": u2["password"], "role_codes": [support_code], "reason": "Recette N1 : support"})
check("Rôle en brouillon non attribuable", bad.status_code == 422, bad.status_code)
act = post(mgr, f"platform/team/roles/{support_id}/activate", {"reason": "Recette N1 : activation"})
check("Activation du rôle (audit)", act.status_code == 200 and act.json()["status"] == "ACTIVE" and audit_count("PLATFORM_ROLE_ACTIVATED", support_id) == 1, act.status_code)

# ---------- create platform user (concurrent double submission) ----------
ukey = str(uuid4())
outs = []
def _create():
    with httpx.Client(base_url=BASE + "/", timeout=60, headers=dict(mgr.headers)) as c:
        outs.append(post(c, "platform/team/users", {"email": u2["email"], "full_name": "Agent Support", "password": u2["password"], "role_codes": [support_code], "reason": "Recette N1 : support"}, ukey))
ts = [threading.Thread(target=_create) for _ in range(2)]
[t.start() for t in ts]; [t.join() for t in ts]
codes = sorted(o.status_code for o in outs)
with owner.connect() as c:
    n_users = c.execute(text("SELECT count(*) FROM users WHERE lower(email::text)=:e"), {"e": u2["email"]}).scalar_one()
check("Création concurrente du même compte : un seul compte", n_users == 1, f"{codes} users={n_users}")
u2_id = next((o.json()["id"] for o in outs if o.status_code in (200, 201) and "id" in o.json()), None)
if u2_id is None:
    u2_id = next(x["id"] for x in mgr.get("platform/team/users", params={"q": u2["email"]}).json()["items"])
fx["u2"]["id"] = u2_id
save()
check("Création de compte auditée", audit_count("PLATFORM_USER_CREATED", u2_id) == 1)

# ---------- custom-role user: menu differs, no escalation ----------
c2, lr = client_for(u2["email"], u2["password"])
check("Compte PLATFORM_CUSTOM : connexion AUTO vers Atelier Pro", lr.status_code == 200 and lr.json().get("scope") == "PLATFORM", lr.status_code)
me2 = c2.get("platform/team/me").json()
keys2 = sorted(m["key"] for m in me2["menu"])
check("Menu différent : uniquement ce que le rôle ouvre", keys2 == ["access", "dashboard", "diagnostics", "schools"], keys2)
check("Lecture des écoles autorisée", c2.get("platform/schools").status_code == 200)
check("Création d'école refusée (403)", post(c2, "platform/schools", {"name": "École pirate", "code": f"PIR{run}"}).status_code == 403)
check("Audit refusé (403)", c2.get("platform/audit").status_code == 403)
check("Gestion d'équipe refusée (403)", c2.get("platform/team/users").status_code == 403 and post(c2, "platform/team/roles", {"code": f"SELF_{run}", "label": "Auto", "capabilities": ["platform.schools.read"]}).status_code == 403)
check("Auto-promotion impossible (attribution de rôle à soi)", post(c2, f"platform/team/users/{u2_id}/roles", {"role_code": "MANAGER_SYSTEME", "reason": "Auto promotion"}).status_code == 403)
check("Aucune capacité ÉCOLE implicite : API école refusée", c2.get("auth/me").status_code == 403 and c2.get("settings/overview").status_code in (401, 403))

# ---------- cumulative roles and archive ----------
r2 = post(mgr, "platform/team/roles", {"code": audit_code, "label": "Auditeur", "capabilities": ["platform.audit.read"]})
audit_id = r2.json()["id"]
post(mgr, f"platform/team/roles/{audit_id}/activate", {"reason": "Recette N1 : activation"})
asg = post(mgr, f"platform/team/users/{u2_id}/roles", {"role_code": audit_code, "reason": "Recette N1 : cumul"})
check("Cumul de rôles : attribution d'un 2e rôle", asg.status_code == 200, asg.status_code)
perms2 = set(c2.get("platform/team/me").json()["permissions"])
check("Permissions effectives = union des rôles", perms2 == {"platform.schools.read", "platform.health.read", "platform.audit.read"}, sorted(perms2))
check("Cumul : audit devient accessible immédiatement", c2.get("platform/audit").status_code == 200)
detail = mgr.get(f"platform/team/users/{u2_id}").json()
check("Fiche compte : rôles, permissions effectives, sessions, audit", len(detail["roles"]) == 2 and len(detail["effective_permissions"]) == 3 and detail["sessions"] and detail["audit"], [r["code"] for r in detail["roles"]])
arc = post(mgr, f"platform/team/roles/{audit_id}/archive", {"reason": "Recette N1 : archivage"})
check("Archivage : nombre de comptes concernés annoncé", arc.status_code == 200 and arc.json()["users_losing_role"] == 1, arc.json())
check("Rôle archivé : capacité retirée immédiatement", c2.get("platform/audit").status_code == 403)
check("Rôle archivé non modifiable", mgr.put(f"platform/team/roles/{audit_id}", json={"label": "Auditeur modifié", "capabilities": [], "version": 3}, headers={"Idempotency-Key": str(uuid4())}).status_code == 409)
cl = post(mgr, f"platform/team/roles/{audit_id}/clone", {"code": f"AUDITEUR2_{run}", "label": "Auditeur v2"})
check("Clonage d'un rôle archivé en nouveau brouillon", cl.status_code == 201 and cl.json()["status"] == "DRAFT" and cl.json()["capabilities"] == ["platform.audit.read"], cl.status_code)
clm = post(mgr, f"platform/team/roles/{std['id']}/clone", {"code": f"MGRCOPY_{run}", "label": "Copie manager"})
check("Clonage du rôle Manager : la capacité réservée ne suit pas", clm.status_code == 201 and "platform.collaborators.manage" not in clm.json()["capabilities"], clm.json().get("capabilities"))

# ---------- self-protection and anti-escalation on targets ----------
mid = me["user"]["id"]
check("Manager : suspension de soi-même refusée", post(mgr, f"platform/team/users/{mid}/suspend", {"reason": "Auto suspension"}).status_code == 403)
check("Manager : retrait de son propre rôle refusé", post(mgr, f"platform/team/users/{mid}/roles/MANAGER_SYSTEME/revoke", {"reason": "Auto retrait"}).status_code == 403)
check("Manager : réinitialisation de son propre mot de passe par cette voie refusée", post(mgr, f"platform/team/users/{mid}/password-reset", {"new_password": secrets.token_urlsafe(16), "reason": "Auto reset"}).status_code == 403)

# ---------- suspension / reactivation effects ----------
sp = post(mgr, f"platform/team/users/{u2_id}/suspend", {"reason": "Recette N1 : suspension"})
check("Suspension : sessions révoquées", sp.status_code == 200 and sp.json()["sessions_revoked"] >= 1, sp.json())
check("Suspension : jeton en cours coupé immédiatement", c2.get("platform/schools").status_code in (401, 403))
check("Suspension : nouvelle connexion refusée", login_auto(u2["email"], u2["password"]).status_code == 403)
rv = post(mgr, f"platform/team/users/{u2_id}/reactivate", {"reason": "Recette N1 : réactivation"})
c2, lr = client_for(u2["email"], u2["password"])
check("Réactivation : connexion de nouveau possible, rôles conservés", rv.status_code == 200 and lr.status_code == 200 and c2.get("platform/schools").status_code == 200, lr.status_code)

# ---------- password reset ----------
newp = secrets.token_urlsafe(18)
pr = post(mgr, f"platform/team/users/{u2_id}/password-reset", {"new_password": newp, "reason": "Recette N1 : mot de passe oublié"})
check("Réinitialisation : sessions coupées", pr.status_code == 200 and c2.get("platform/schools").status_code == 401, pr.status_code)
check("Réinitialisation : ancien mot de passe refusé, nouveau accepté", login_auto(u2["email"], u2["password"]).status_code == 401 and login_auto(u2["email"], newp).status_code == 200)
fx["u2"]["password"] = newp
save()
with owner.connect() as c:
    leaked = c.execute(text("SELECT count(*) FROM audit_events WHERE new_json::text LIKE :p OR old_json::text LIKE :p"), {"p": f"%{newp}%"}).scalar_one()
check("Mot de passe jamais écrit dans l'audit", leaked == 0)

# ---------- second Manager and concurrent mutual suspension ----------
m2 = fx["m2"]
cm = post(mgr, "platform/team/users", {"email": m2["email"], "full_name": "Manager Deux", "password": m2["password"], "role_codes": ["MANAGER_SYSTEME"], "reason": "Recette N1 : second manager"})
check("Second Manager créé par le Manager", cm.status_code in (201, 409), cm.status_code)
cm2, _ = client_for(m2["email"], m2["password"])
m2_id = cm2.get("platform/team/me").json()["user"]["id"]
outs = []
def _suspend(client, target):
    with httpx.Client(base_url=BASE + "/", timeout=60, headers=dict(client.headers)) as c:
        outs.append(post(c, f"platform/team/users/{target}/suspend", {"reason": "Recette N1 : course"}))
ts = [threading.Thread(target=_suspend, args=(mgr, m2_id)), threading.Thread(target=_suspend, args=(cm2, mid))]
[t.start() for t in ts]; [t.join() for t in ts]
with owner.connect() as c:
    active_mgrs = c.execute(text("""SELECT count(DISTINCT a.user_id) FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id
        LEFT JOIN platform_account_status ps ON ps.user_id=a.user_id WHERE r.code='MANAGER_SYSTEME' AND a.active AND a.school_id IS NULL
        AND coalesce(ps.status,'ACTIVE')='ACTIVE'"""), {}).scalar_one()
check("Suspension croisée simultanée : il reste toujours au moins un Manager actif", active_mgrs >= 1, f"{sorted(o.status_code for o in outs)} actifs={active_mgrs}")
# Restore: whoever is still active reactivates the other, then the main manager retires the second one.
alive = mgr if mgr.get("platform/team/me").status_code == 200 else None
if alive is None:
    alive, _ = client_for(m2["email"], m2["password"])
    post(alive, f"platform/team/users/{mid}/reactivate", {"reason": "Recette N1 : restauration"})
    mgr = platform()
post(mgr, f"platform/team/users/{m2_id}/reactivate", {"reason": "Recette N1 : restauration"})
rr = post(mgr, f"platform/team/users/{m2_id}/roles/MANAGER_SYSTEME/revoke", {"reason": "Recette N1 : retrait second manager"})
check("Retrait du rôle Manager d'un autre Manager (il en reste un)", rr.status_code == 200, rr.status_code)
check("Compte sans rôle : connexion AUTO refusée (aucun espace)", login_auto(m2["email"], m2["password"]).status_code == 403)

# ---------- tenant isolation of platform roles ----------
tenant = create_engine(os.environ["EDUSYNC_TENANT_DATABASE_URL"], pool_size=1)
with tenant.begin() as c:
    c.execute(text("SELECT set_config('app.current_school_id', :s, true)"), {"s": state["A"]["school_id"]})
    seen = c.execute(text("SELECT count(*) FROM rbac_roles WHERE level='PLATFORM'")).scalar_one()
check("RLS : le rôle tenant ne voit aucun rôle plateforme", seen == 0, seen)
with tenant.connect() as c:
    try:
        c.execute(text("SELECT count(*) FROM platform_account_status")).scalar_one()
        check("RLS : statut des comptes plateforme invisible au tenant", False, "lisible")
    except Exception as e:  # noqa: BLE001
        check("RLS : statut des comptes plateforme invisible au tenant", True, type(e).__name__)

for action in ("PLATFORM_ROLE_CREATED", "PLATFORM_ROLE_ARCHIVED", "PLATFORM_ROLE_CLONED", "PLATFORM_ROLE_ASSIGNED", "PLATFORM_ROLE_REVOKED",
               "PLATFORM_USER_SUSPENDED", "PLATFORM_USER_REACTIVATED", "PLATFORM_USER_PASSWORD_RESET"):
    check(f"Audit présent : {action}", audit_count(action) >= 1)

out = Path(__file__).with_name("team-live.json")
out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(f"== {sum(r['pass'] for r in results)}/{len(results)} PASS -> {out.name}")
