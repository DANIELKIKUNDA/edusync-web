"""Local probe of the « Équipe plateforme » module (lot 2026-10) against the running local API (recette data).

Real HTTP with real sign-in + TOTP (local recette fixtures), plus an in-process part that calls the governance functions
concurrently (real database, real transactions) to prove the last-Manager guarantee under concurrency.
Prints PASS/FAIL lines; never prints a secret (temporary passwords, tokens, TOTP secrets stay in memory).
Usage: EDUSYNC_LOCAL_PG_PORT=54432 python tools/local/team_probe.py
"""
from __future__ import annotations

import json
import os
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

API = "http://127.0.0.1:58100/api/v1"
FX = json.loads((ROOT / ".local/claude-fixtures-edusync_claude_fresh.json").read_text(encoding="utf-8"))
ENV = {l.split("=", 1)[0]: l.rstrip("\n").split("=", 1)[1] for l in (ROOT / ".local/certification.env").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#")}
FAILS = 0


def check(ok, label):
    global FAILS
    print(("PASS  " if ok else "FAIL  ") + label, flush=True)
    FAILS += 0 if ok else 1


def call(method, path, token=None, body=None, key=None):
    h = {"Content-Type": "application/json", "Origin": "http://localhost:5180", **({"Authorization": f"Bearer {token}"} if token else {})}
    if method != "GET":
        h["Idempotency-Key"] = key or str(uuid.uuid4())
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}


def wait_window():
    while time.time() % 30 > 25:
        time.sleep(0.5)


def login(email, password):
    code, step = call("POST", "/auth/login", body={"email": email, "password": password, "scope": "PLATFORM"})
    secret = FX["MFA_TOTP"][email]["secret"]
    for _ in range(3):
        wait_window()
        code, sess = call("POST", "/auth/mfa/verify", body={"mfa_token": step["mfa_token"], "code": totp_code(secret, current_step())})
        if code == 200:
            return sess["access_token"], secret
        time.sleep(31)
    raise SystemExit(f"connexion impossible pour {email}")


def step_up(token, secret):
    time.sleep(31)
    wait_window()
    return call("POST", "/auth/platform/mfa/step-up", token, {"code": totp_code(secret, current_step())})[0] == 200


env = L.load_env("demo")
from sqlalchemy import create_engine, text  # noqa: E402
owner = create_engine(env["EDUSYNC_OWNER_DATABASE_URL"])


def sql(q, **p):
    with owner.begin() as c:
        r = c.execute(text(q), p)
        return r.all() if r.returns_rows else r.rowcount


manager, msecret = login("certification@example.test", ENV["EDUSYNC_PLATFORM_ADMIN_PASSWORD"])
support, _ = login(FX["N1_TEAM"]["u2"]["email"], FX["N1_TEAM"]["u2"]["password"])
me = call("GET", "/platform/team/me", manager)[1]
manager_id = me["user"]["id"]
tag = uuid.uuid4().hex[:6].lower()

# ---------------------------------------------------------------- RBAC / direct API
VALID = {"/platform/team/users": {"email": "x@example.test", "full_name": "Essai interdit", "role_codes": ["MANAGER_SYSTEME"], "reason": "Tentative directe", "delivery": "TEMPORARY"},
         "capabilities": {"capability_code": "platform.schools.create", "reason": "Tentative directe"},
         "platform-access": {"role_codes": ["MANAGER_SYSTEME"], "reason": "Tentative directe"}, "revoke": {"reason": "Tentative directe"}}
for method, path in (("GET", "/platform/team/users"), ("GET", "/platform/team/candidates?q=ad"), ("POST", "/platform/team/users"), ("POST", f"/platform/team/users/{manager_id}/capabilities"),
                     ("POST", f"/platform/team/users/{manager_id}/platform-access"), ("POST", f"/platform/team/users/{manager_id}/platform-access/revoke")):
    body = VALID.get(path) or VALID.get(path.rsplit("/", 1)[1]) if method == "POST" else None
    code, _ = call(method, path, support, body=body)
    check(code == 403, f"rôle restreint refusé (API directe) : {method} {path.split('?')[0].replace(manager_id, '{id}')} → {code}")
check(call("GET", "/platform/team/users")[0] == 401, "sans jeton : 401")

# ---------------------------------------------------------------- list / search / pagination
code, page = call("GET", "/platform/team/users?limit=5", manager)
check(code == 200 and page["total"] >= 1 and len(page["items"]) <= 5 and "email_invitations_available" in page, f"comptes : {page.get('total')} membres, page de 5, curseur")
seen, cursor, pages = [], None, 0
while True:
    code, r = call("GET", "/platform/team/users?limit=20" + (f"&cursor={cursor}" if cursor else ""), manager)
    pages += 1; seen += [x["id"] for x in r["items"]]; cursor = r["next_cursor"]
    if not cursor:
        break
check(len(seen) == r["total"] == len(set(seen)), f"pagination par curseur : {pages} pages, {len(seen)} membres, ni doublon ni trou")
code, s1 = call("GET", "/platform/team/users?q=CERTIFICATION", manager)
check(code == 200 and any(x["id"] == manager_id for x in s1["items"]), "recherche serveur (casse ignorée)")
check(call("GET", "/platform/team/users?status=X", manager)[0] == 422 and call("GET", "/platform/team/users?cursor=Zm9v", manager)[0] == 422, "filtre / curseur forgés refusés (422)")
email_ok = page["email_invitations_available"]

# ---------------------------------------------------------------- new identity (temporary password, server-generated)
check(step_up(manager, msecret), "step-up MFA du Manager")
email_new = f"collab-{tag}@example.test"
key = str(uuid.uuid4())
code, created = call("POST", "/platform/team/users", manager, {"email": email_new, "full_name": f"Collaborateur {tag}", "role_codes": ["COLLABORATEUR_PLATEFORME"],
                                                       "reason": "Recette équipe plateforme", "delivery": "TEMPORARY"}, key=key)
check(code == 201 and isinstance(created.get("temporary_password"), str) and len(created["temporary_password"]) >= 12,
      "nouvelle identité : mot de passe provisoire généré par le serveur, renvoyé une fois")
code, again = call("POST", "/platform/team/users", manager, {"email": email_new, "full_name": f"Collaborateur {tag}", "role_codes": ["COLLABORATEUR_PLATEFORME"],
                                                     "reason": "Recette équipe plateforme", "delivery": "TEMPORARY"}, key=key)
check(code in (200, 201) and again.get("temporary_password") is None and again.get("id") == created.get("id"), "rejeu (même clé) : même compte, mot de passe jamais renvoyé")
code, dup = call("POST", "/platform/team/users", manager, {"email": email_new.upper(), "full_name": "Doublon", "role_codes": ["COLLABORATEUR_PLATEFORME"],
                                                   "reason": "Recette doublon", "delivery": "TEMPORARY"})
check(code == 409 and "Utilisateur existant" in dup.get("detail", ""), "doublon d’e-mail (casse différente) refusé (409) avec orientation « Utilisateur existant »")
audit = sql("SELECT new_json::text FROM audit_events WHERE action='PLATFORM_USER_CREATED' AND entity_id=:u", u=created["id"])
check(len(audit) == 1 and created["temporary_password"] not in audit[0][0], "audit unique, sans le mot de passe provisoire")
check(sql("SELECT must_change_password FROM users WHERE id=:u", u=created["id"])[0][0] is True, "mot de passe provisoire à remplacer à la première connexion")

# race: two simultaneous creations of the same new address → exactly one account
race_email = f"race-{tag}@example.test"
results = []
def create_race():
    results.append(call("POST", "/platform/team/users", manager, {"email": race_email, "full_name": "Course", "role_codes": ["COLLABORATEUR_PLATEFORME"],
                                                         "reason": "Recette concurrence", "delivery": "TEMPORARY"})[0])
ts = [threading.Thread(target=create_race) for _ in range(2)]
[t.start() for t in ts]; [t.join() for t in ts]
check(sorted(results) == [201, 409] and sql("SELECT count(*) FROM users WHERE lower(email::text)=:e", e=race_email)[0][0] == 1,
      f"création simultanée de la même adresse : une seule identité ({sorted(results)})")

# ---------------------------------------------------------------- invitation flow
if email_ok:
    email_inv = f"invite-{tag}@example.test"
    code, inv = call("POST", "/platform/team/users", manager, {"email": email_inv, "full_name": f"Invité {tag}", "role_codes": ["COLLABORATEUR_PLATEFORME"],
                                                       "reason": "Recette invitation", "delivery": "INVITATION"})
    d = call("GET", f"/platform/team/users/{inv.get('id')}", manager)[1]
    check(code == 201 and inv.get("temporary_password") is None and d.get("invitation_state") == "PENDING", "invitation : aucun mot de passe transmis, invitation en attente")
    code, rs = call("POST", f"/platform/team/users/{inv['id']}/invitation/resend", manager, {"reason": "Recette renvoi"})
    open_links = sql("SELECT count(*) FROM account_tokens WHERE user_id=:u AND purpose='INVITATION' AND used_at IS NULL AND revoked_at IS NULL", u=inv["id"])[0][0]
    check(code == 200 and open_links == 1, "renvoi d’invitation : un seul lien valide (l’ancien est révoqué)")
    sql("UPDATE account_tokens SET created_at=now()-interval '3 days', expires_at=now()-interval '1 minute' WHERE user_id=:u AND purpose='INVITATION' AND used_at IS NULL AND revoked_at IS NULL", u=inv["id"])
    check(call("GET", f"/platform/team/users/{inv['id']}", manager)[1].get("invitation_state") == "EXPIRED", "invitation expirée détectée")
    check(call("POST", f"/platform/team/users/{inv['id']}/invitation/resend", manager, {"reason": "Recette renvoi expirée"})[0] == 200, "renvoi après expiration")
    sql("UPDATE account_tokens SET used_at=now() WHERE user_id=:u AND purpose='INVITATION' AND used_at IS NULL AND revoked_at IS NULL", u=inv["id"])
    check(call("POST", f"/platform/team/users/{inv['id']}/invitation/resend", manager, {"reason": "Recette renvoi acceptée"})[0] == 409, "invitation acceptée : renvoi refusé (409)")
    sql("UPDATE users SET must_change_password=false WHERE id=:u", u=inv["id"])
else:
    print("INFO  e-mail non configuré localement : invitation remplacée par le mot de passe provisoire (contrôlé ci-dessus)")

# ---------------------------------------------------------------- existing identity (school account) → same user_id
adm = FX["A"]["users"]["GEST"] if "GEST" in FX["A"]["users"] else FX["A"]["users"]["ADMIN"]
uid = adm["user_id"]
school_roles_before = sql("SELECT count(*) FROM rbac_assignments WHERE user_id=:u AND school_id IS NOT NULL AND active", u=uid)[0][0]
memberships_before = sql("SELECT count(*) FROM school_memberships WHERE user_id=:u AND active", u=uid)[0][0]
users_before = sql("SELECT count(*) FROM users")[0][0]
code, cand = call("GET", "/platform/team/candidates?q=" + urllib.parse.quote(adm["email"].split("@")[0]), manager)
check(code == 200 and any(x["id"] == uid for x in cand["items"]), "« Utilisateur existant » : compte école trouvé parmi les candidats")
key = str(uuid.uuid4())
code, added = call("POST", f"/platform/team/users/{uid}/platform-access", manager, {"role_codes": ["COLLABORATEUR_PLATEFORME"], "reason": "Recette promotion"}, key=key)
check(code == 201 and added.get("id") == uid and added.get("school_memberships_kept") == memberships_before,
      f"accès plateforme donné au compte existant : même user_id, {memberships_before} rattachement(s) école conservé(s)")
check(sql("SELECT count(*) FROM users")[0][0] == users_before, "aucune identité créée (pas de doublon)")
code, rep = call("POST", f"/platform/team/users/{uid}/platform-access", manager, {"role_codes": ["COLLABORATEUR_PLATEFORME"], "reason": "Recette promotion"}, key=key)
check(rep == added and len(sql("SELECT 1 FROM audit_events WHERE action='PLATFORM_MEMBER_ADDED' AND entity_id=:u AND idempotency_key=:k", u=uid, k=key)) == 1,
      "double clic (même clé) : même résultat, un seul événement d’audit")
check(call("POST", f"/platform/team/users/{uid}/platform-access", manager, {"role_codes": ["COLLABORATEUR_PLATEFORME"], "reason": "Recette promotion bis"})[0] == 409,
      "déjà membre : nouvelle promotion refusée (409)")
code, cand2 = call("GET", "/platform/team/candidates?q=" + urllib.parse.quote(adm["email"].split("@")[0]), manager)
check(not any(x["id"] == uid for x in cand2["items"]), "un membre n’apparaît plus parmi les candidats")

# ---------------------------------------------------------------- individual capabilities
def detail(u):
    return call("GET", f"/platform/team/users/{u}", manager)[1]

d0 = detail(uid)
check(d0["inherited_count"] == 3 and d0["supplementary_count"] == 0 and d0["effective_count"] == 3, "rôle seul : 3 capacités héritées, 0 supplémentaire, total 3")
key = str(uuid.uuid4())
code, g = call("POST", f"/platform/team/users/{uid}/capabilities", manager, {"capability_code": "platform.schools.create", "reason": "Recette mission ouverture"}, key=key)
d1 = detail(uid)
check(code == 201 and g["effective_before"] == 3 and g["effective_after"] == 4 and g["added"] == ["platform.schools.create"], "capacité supplémentaire : 3 → 4 (+ platform.schools.create)")
origin = next(x for x in d1["capabilities"] if x["code"] == "platform.schools.create")["origins"]
check(d1["supplementary_count"] == 1 and origin[0]["kind"] == "GRANT" and origin[0]["granted_by"], "origine visible : attribution individuelle, par qui")
check(call("POST", f"/platform/team/users/{uid}/capabilities", manager, {"capability_code": "platform.schools.create", "reason": "Recette mission ouverture"}, key=key)[1] == g,
      "rejeu de l’attribution : même résultat")
check(call("POST", f"/platform/team/users/{uid}/capabilities", manager, {"capability_code": "platform.schools.create", "reason": "Recette doublon"})[0] == 409, "attribution déjà détenue refusée (409)")
check(call("POST", f"/platform/team/users/{uid}/capabilities", manager, {"capability_code": "platform.schools.read", "reason": "Recette héritée"})[0] == 409, "capacité déjà héritée du rôle refusée (409)")
code, r = call("POST", f"/platform/team/users/{uid}/capabilities", manager, {"capability_code": "platform.collaborators.manage", "reason": "Recette escalade"})
check(code == 403, "capacité réservée (non délégable) refusée (403)")
check(call("POST", f"/platform/team/users/{manager_id}/capabilities", manager, {"capability_code": "platform.health.read", "reason": "Recette auto-élévation"})[0] == 403,
      "auto-attribution sur son propre compte refusée (403)")
check(call("POST", f"/platform/team/users/{uid}/capabilities", manager, {"capability_code": "platform.inexistante", "reason": "Recette inconnue"})[0] == 422, "capacité inconnue refusée (422)")
code, g2 = call("POST", f"/platform/team/users/{uid}/capabilities", manager, {"capability_code": "platform.audit.export", "reason": "Recette plusieurs"})
check(code == 201 and detail(uid)["effective_count"] == 5, "rôle + plusieurs attributions : total 5")
exp0 = sql("SELECT count(*) FROM audit_events WHERE action='PLATFORM_CAPABILITY_GRANT_EXPIRED' AND entity_id=:u", u=uid)[0][0]
until = (datetime.now(timezone.utc) + timedelta(seconds=4)).isoformat()
code, g3 = call("POST", f"/platform/team/users/{uid}/capabilities", manager, {"capability_code": "platform.messaging.read", "reason": "Recette temporaire", "valid_until": until})
check(code == 201 and g3["valid_until"] and detail(uid)["effective_count"] == 6, "attribution temporaire : effective tant que l’échéance n’est pas atteinte (6)")
time.sleep(5)
d2 = detail(uid)
exp = sql("SELECT count(*) FROM audit_events WHERE action='PLATFORM_CAPABILITY_GRANT_EXPIRED' AND entity_id=:u", u=uid)[0][0]
detail(uid)
exp2 = sql("SELECT count(*) FROM audit_events WHERE action='PLATFORM_CAPABILITY_GRANT_EXPIRED' AND entity_id=:u", u=uid)[0][0]
check(d2["effective_count"] == 5 and exp - exp0 == 1 and exp2 - exp0 == 1, "échéance : capacité retirée sans intervention, événement d’expiration audité une seule fois")
check(call("POST", f"/platform/team/users/{uid}/capabilities", manager, {"capability_code": "platform.health.read", "reason": "Recette passé",
                                                                "valid_until": "2020-01-01T00:00:00Z"})[0] == 422, "échéance dans le passé refusée (422)")
code, rv = call("POST", f"/platform/team/users/{uid}/capabilities/platform.audit.export/revoke", manager, {"reason": "Recette retrait"})
check(code == 200 and rv["effective_after"] == 4 and rv["removed"] == ["platform.audit.export"], "retrait d’une attribution : 5 → 4 (− platform.audit.export), rôle inchangé")
std = sql("SELECT count(*) FROM rbac_role_capabilities rc JOIN rbac_roles r ON r.id=rc.role_id WHERE r.code='COLLABORATEUR_PLATEFORME'")[0][0]
check(std == 3, "rôle standard Collaborateur intact (3 capacités)")

# DB guard (last line): a reserved capability can never be granted, even by a direct SQL insert
try:
    sql("INSERT INTO platform_capability_grants(user_id,capability_code,granted_by_user_id,reason) VALUES(:u,'platform.collaborators.manage',:by,'Contournement direct')",
        u=uid, by=manager_id)
    check(False, "base : capacité réservée insérée directement")
except Exception:
    check(True, "base de données : capacité réservée impossible à attribuer, même par insertion directe")

# ---------------------------------------------------------------- multi-roles union
code, role = call("POST", "/platform/team/roles", manager, {"code": f"SUPPORT_{tag.upper()}", "label": f"Support {tag}", "description": "Recette union",
                                                   "capabilities": ["platform.schools.read", "platform.messaging.read"]})
call("POST", f"/platform/team/roles/{role['id']}/activate", manager, {"reason": "Recette activation"})
call("POST", f"/platform/team/users/{uid}/roles", manager, {"role_code": f"SUPPORT_{tag.upper()}", "reason": "Recette multi-rôles"})
d3 = detail(uid)
read_origins = next(x for x in d3["capabilities"] if x["code"] == "platform.schools.read")["origins"]
check(d3["effective_count"] == 5 and len(read_origins) == 2, "multi-rôles : union sans doublon (schools.read listée une fois, deux origines)")
order_a = set(d3["effective_permissions"])
call("POST", f"/platform/team/users/{uid}/roles/COLLABORATEUR_PLATEFORME/revoke", manager, {"reason": "Recette ordre"})
call("POST", f"/platform/team/users/{uid}/roles", manager, {"role_code": "COLLABORATEUR_PLATEFORME", "reason": "Recette ordre"})
check(set(detail(uid)["effective_permissions"]) == order_a, "ordre d’attribution des rôles sans effet sur le résultat")

# custom role edit: reason required once active, audit with diff and members affected
code, cur = call("GET", "/platform/team/roles", manager)
r0 = next(x for x in cur["items"] if x["id"] == role["id"])
check(call("PUT", f"/platform/team/roles/{role['id']}", manager, {"label": r0["label"], "description": "", "capabilities": ["platform.schools.read"], "version": r0["version"]})[0] == 422,
      "modification d’un rôle actif sans motif refusée")
code, upd = call("PUT", f"/platform/team/roles/{role['id']}", manager, {"label": r0["label"], "description": "", "capabilities": ["platform.schools.read"],
                                                              "version": r0["version"], "reason": "Recette retrait messagerie"})
row = sql("SELECT old_json::text, new_json::text, reason FROM audit_events WHERE action='PLATFORM_ROLE_UPDATED' AND entity_id=:r ORDER BY occurred_at DESC LIMIT 1", r=role["id"])[0]
check(code == 200 and '"removed": ["platform.messaging.read"]' in row[1] and '"members_affected": 1' in row[1] and row[2], "rôle personnalisé modifié : diff, membres concernés et motif audités")
std_role = next(x for x in cur["items"] if x["code"] == "COLLABORATEUR_PLATEFORME")
check(call("PUT", f"/platform/team/roles/{std_role['id']}", manager, {"label": "Collaborateur modifié", "description": "", "capabilities": ["platform.schools.read"], "version": std_role["version"], "reason": "Tentative directe"})[0] == 403,
      "rôle standard non modifiable (403)")
code, cl = call("POST", f"/platform/team/roles/{std_role['id']}/clone", manager, {"code": f"COLLAB_CLONE_{tag.upper()}", "label": f"Collaborateur (copie {tag})"})
check(code == 201 and cl["status"] == "DRAFT" and sorted(cl["capabilities"]) == sorted(std_role["capabilities"]), "clone d’un rôle standard : rôle personnalisé indépendant, en brouillon")

# ---------------------------------------------------------------- platform access removal keeps the school account intact
check(step_up(manager, msecret), "step-up MFA (retrait d’accès)")
key = str(uuid.uuid4())
code, rm = call("POST", f"/platform/team/users/{uid}/platform-access/revoke", manager, {"reason": "Recette retrait accès"}, key=key)
check(code == 200 and rm["school_memberships_kept"] == memberships_before and "platform.schools.create" in rm["capabilities_ended"], "retrait de l’accès plateforme : rôles et attributions terminés")
check(sql("SELECT count(*) FROM school_memberships WHERE user_id=:u AND active", u=uid)[0][0] == memberships_before
      and sql("SELECT count(*) FROM rbac_assignments WHERE user_id=:u AND school_id IS NOT NULL AND active", u=uid)[0][0] == school_roles_before
      and sql("SELECT active FROM users WHERE id=:u", u=uid)[0][0] is True, "compte école intact : identité, rattachements et rôles locaux conservés")
check(call("POST", f"/platform/team/users/{uid}/platform-access/revoke", manager, {"reason": "Recette retrait accès"}, key=key)[1] == rm, "rejeu du retrait : même résultat")
ident = call("GET", f"/platform/identities/{uid}", manager)[1]
check(ident.get("scope") == "SCHOOL" and not ident.get("platform_roles"), "« Utilisateurs & accès » reflète le retrait (portée École, aucun rôle plateforme)")
check(sql("SELECT count(*) FROM platform_capability_grants WHERE user_id=:u AND active", u=uid)[0][0] == 0, "aucune attribution individuelle ne survit au retrait")
call("POST", f"/platform/team/users/{uid}/platform-access", manager, {"role_codes": ["COLLABORATEUR_PLATEFORME"], "reason": "Recette retour"})
check(detail(uid)["effective_count"] == 3, "nouvel accès ultérieur : aucune ancienne capacité ne revient silencieusement")
call("POST", f"/platform/team/users/{uid}/platform-access/revoke", manager, {"reason": "Recette nettoyage"})

# ---------------------------------------------------------------- managers: second Manager banner, last Manager, concurrency
check(call("GET", "/platform/team/me", manager)[1]["active_managers"] == 1, "un seul Manager actif : le bandeau d’avertissement s’affiche (compteur = 1)")
email_m2 = f"manager-{tag}@example.test"
code, m2 = call("POST", "/platform/team/users", manager, {"email": email_m2, "full_name": f"Manager {tag}", "role_codes": ["MANAGER_SYSTEME"],
                                                  "reason": "Recette second Manager", "delivery": "TEMPORARY"})
check(code == 201 and call("GET", "/platform/team/me", manager)[1]["active_managers"] == 2, "deuxième Manager actif : le bandeau disparaît (compteur = 2)")

os.environ.update({k: v for k, v in env.items() if k.startswith("EDUSYNC_")})
from edusync.bootstrap.services import AppServices  # noqa: E402
from edusync.bootstrap.settings import Settings  # noqa: E402
from edusync.modules.platform_team.api import router as team  # noqa: E402
from edusync.shared.application.context import ActorContext  # noqa: E402
from fastapi import HTTPException  # noqa: E402
services = AppServices.build(Settings())
team.require_recent_mfa = lambda *a, **k: None   # in-process only: the step-up is proven over HTTP above
perms = frozenset(me["permissions"])


def actor(user_id):
    return ActorContext(user_id=uuid.UUID(user_id), school_id=None, membership_id=None, permissions=perms, is_platform_admin=False,
                        correlation_id=uuid.uuid4(), source="WEB", session_id=uuid.uuid4())


def attempt(fn, out):
    try:
        fn(); out.append("ok")
    except HTTPException as e:
        out.append(e.status_code)


reason = team.ReasonInput(reason="Recette concurrence Managers")
for label, make in (("suspensions croisées", lambda a, t: (lambda: team._set_status(uuid.UUID(t), "SUSPENDED", reason, str(uuid.uuid4()), actor(a), services))),
                    ("retraits d’accès croisés", lambda a, t: (lambda: team.team_remove_access(uuid.UUID(t), reason, str(uuid.uuid4()), actor(a), services))),
                    ("rétrogradations croisées", lambda a, t: (lambda: team.team_revoke_role(uuid.UUID(t), "MANAGER_SYSTEME", reason, str(uuid.uuid4()), actor(a), services)))):
    out: list = []
    barrier = threading.Barrier(2)
    def run(a, t):
        barrier.wait(); attempt(make(a, t), out)
    ts = [threading.Thread(target=run, args=(manager_id, m2["id"])), threading.Thread(target=run, args=(m2["id"], manager_id))]
    [t.start() for t in ts]; [t.join() for t in ts]
    with services.platform_db.platform_transaction() as c:
        n = team._active_managers(c)
    check(sorted(map(str, out)) == ["409", "ok"] and n == 1, f"concurrence ({label}) : une requête aboutit, l’autre est refusée, il reste {n} Manager actif")
    # restore the second Manager for the next scenario
    with services.platform_db.platform_transaction() as c:
        for uid_m in (manager_id, m2["id"]):
            c.execute(text("UPDATE platform_account_status SET status='ACTIVE' WHERE user_id=:u"), {"u": uid_m})
            c.execute(text("""UPDATE rbac_assignments a SET active=true FROM rbac_roles r WHERE r.id=a.role_id AND r.code='MANAGER_SYSTEME'
                AND a.user_id=:u AND a.school_id IS NULL"""), {"u": uid_m})
            c.execute(text("UPDATE users SET is_platform_admin=true WHERE id=:u"), {"u": uid_m})
    # a suspension or an access removal closes the platform sessions of the target: sign in again
    manager, msecret = login("certification@example.test", ENV["EDUSYNC_PLATFORM_ADMIN_PASSWORD"])

check(step_up(manager, msecret), "step-up MFA après reconnexion")
# sequential: with a single active Manager, an actor holding the team capability (synthetic, not a Manager) is refused
call("POST", f"/platform/team/users/{m2['id']}/platform-access/revoke", manager, {"reason": "Recette retour à un Manager"})
check(call("GET", "/platform/team/me", manager)[1]["active_managers"] == 1, "suppression du second Manager : il en reste 1, protection réactivée")
outsider = FX["N1_TEAM"]["u2"]["id"]
for label, fn in (("suspension", lambda: team._set_status(uuid.UUID(manager_id), "SUSPENDED", reason, str(uuid.uuid4()), actor(outsider), services)),
                  ("rétrogradation", lambda: team.team_revoke_role(uuid.UUID(manager_id), "MANAGER_SYSTEME", reason, str(uuid.uuid4()), actor(outsider), services)),
                  ("retrait d’accès", lambda: team.team_remove_access(uuid.UUID(manager_id), reason, str(uuid.uuid4()), actor(outsider), services))):
    out = []
    attempt(fn, out)
    check(out == [409], f"1 Manager actif → {label} refusée (409)")
with services.platform_db.platform_transaction() as c:
    check(team._active_managers(c) == 1, "toujours 1 Manager Système actif")

# ---------------------------------------------------------------- audit trail
actions = {r[0] for r in sql("""SELECT DISTINCT action FROM audit_events WHERE occurred_at > now() - interval '30 minutes' AND action LIKE 'PLATFORM_%'""")}
need = {"PLATFORM_USER_CREATED", "PLATFORM_MEMBER_ADDED", "PLATFORM_ACCESS_REVOKED", "PLATFORM_ROLE_ASSIGNED", "PLATFORM_ROLE_REVOKED",
        "PLATFORM_CAPABILITY_GRANTED", "PLATFORM_CAPABILITY_REVOKED", "PLATFORM_CAPABILITY_GRANT_EXPIRED", "PLATFORM_ROLE_CREATED",
        "PLATFORM_ROLE_CLONED", "PLATFORM_ROLE_UPDATED", "PLATFORM_ROLE_ACTIVATED"} | ({"PLATFORM_INVITATION_RESENT"} if email_ok else set())
check(need <= actions, "journal d’audit : " + (", ".join(sorted(need - actions)) or "toutes les actions de gouvernance tracées"))
leak = sql("""SELECT count(*) FROM audit_events WHERE occurred_at > now() - interval '30 minutes'
              AND (new_json::text ILIKE '%temporary_password%' OR new_json::text ILIKE '%token%' OR new_json::text ILIKE '%secret%')""")[0][0]
check(leak == 0, "aucun secret (mot de passe provisoire, jeton, secret) dans l’audit")

print("\nRÉSULTAT : " + ("PASS" if FAILS == 0 else f"FAIL ({FAILS})"))
sys.exit(1 if FAILS else 0)
