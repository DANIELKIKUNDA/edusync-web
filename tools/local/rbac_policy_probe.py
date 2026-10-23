"""Local certification of the school RBAC policy layer (owner decisions 2026-10-23, migration 0085).

Real API, real database, fixture school A. Proves: /access/me projection per role (pure administrator: no finance,
no student search, no recovery widget), standard role + school GRANT / REVOKE applied by the engine and enforced by the
backend (403 after a REVOKE), protected base refused by the database, separation of duties (SELF_ELEVATION blocked,
GOVERNANCE_GRANT approved by a second manager only, PAIR warning needing an acknowledgement), several roles on one
member, SECTION scope projected, assisted conversion preview. Everything changed is withdrawn at the end.
Usage: EDUSYNC_LOCAL_PG_PORT=54432 python tools/local/rbac_policy_probe.py
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/local"))
import edusync_local as L  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

env = L.load_env("demo")
API = "http://127.0.0.1:58100/api/v1"
FX = json.loads((ROOT / ".local/claude-fixtures-edusync_claude_fresh.json").read_text(encoding="utf-8"))
A = FX["A"]
owner = create_engine(env["EDUSYNC_OWNER_DATABASE_URL"])
FAILS = 0


def check(ok, label):
    global FAILS
    print(("PASS  " if ok else "FAIL  ") + label, flush=True)
    FAILS += 0 if ok else 1


def call(method, path, token=None, body=None, key=True):
    h = {"Content-Type": "application/json", "Origin": "http://localhost:5180"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    if key and method != "GET":
        h["Idempotency-Key"] = str(uuid.uuid4())
    if path.startswith("/access/roles/") and method == "PUT" and "/policy" not in path:
        h["If-Match"] = "1"
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw[:200].decode(errors="replace")}


def login(user):
    code, body = call("POST", "/auth/login", body={"email": user["email"], "password": user["password"], "scope": "SCHOOL", "school_code": A["code"]}, key=False)
    assert code == 200 and body.get("access_token"), (code, body)
    return body["access_token"]


def sql(q, **p):
    with owner.begin() as c:
        res = c.execute(text(q), p)
        return res.mappings().all() if res.returns_rows else res.rowcount


def role_id(code):
    return str(sql("SELECT id FROM rbac_roles WHERE code=:c AND kind='SCHOOL_STANDARD'", c=code)[0]["id"])


U = A["users"]
admin_multi = login(U["ADMIN"])                     # ADMIN + GESTIONNAIRE + SECRETARIAT + RESPONSABLE_FINANCE
created_assignments: list[str] = []

# a pure school administrator for the probe (ACC_TMP, no role today)
code, out = call("POST", f"/access/members/{U['ACC_TMP']['membership_id']}/roles", admin_multi,
                 {"role_id": role_id("ADMIN_SYSTEME_ECOLE"), "scopes": [{"type": "SCHOOL"}], "reason": "Recette RBAC 0085 : administrateur pur"})
check(code in (200, 201) and out.get("assignment_id"), f"administrateur pur attribué ({code})")
created_assignments.append(out.get("assignment_id"))
admin = login(U["ACC_TMP"])

# ---------------------------------------------------------------- /access/me projection
code, me = call("GET", "/access/me", admin)
nav = {n["key"] for n in me.get("navigation", [])}
widgets = {w["id"] for w in me.get("widgets", [])}
actions = {a["id"] for a in me.get("actions", [])}
check(code == 200 and "access" in nav and "settings" in nav, "administrateur : Accès et Paramètres dans la navigation")
check("finance" not in nav and "students" not in nav, f"administrateur : ni Centre financier ni Élèves ({sorted(nav)})")
check("finance.recovery" not in widgets and "access.members" in widgets and "settings.readiness" in widgets, "administrateur : pas de recouvrement, widgets d’administration présents")
check("students.search" not in actions and "members.create" in actions, "administrateur : pas de « Rechercher un élève », « Ajouter un utilisateur » présent")
check(not any(p.startswith("finance.checkout") for p in me.get("permissions", [])), "administrateur : aucune capacité d’encaissement")
code, dash = call("GET", "/access/dashboard", admin)
check(code == 200 and "access.members" in dash and "settings.structure" in dash, "tableau de bord administrateur alimenté")

code, me_multi = call("GET", "/access/me", admin_multi)
check({"finance", "students", "access"} <= {n["key"] for n in me_multi["navigation"]} and len(me_multi["roles"]) >= 4,
      "plusieurs rôles sur un membre : navigation = union des capacités")
intendant = login(U["INTENDANT"])
code, me_int = call("GET", "/access/me", intendant)
check("stewardship" in {n["key"] for n in me_int["navigation"]} and "students.search" not in {a["id"] for a in me_int["actions"]},
      "intendant : Intendance, pas de recherche élève")

# ---------------------------------------------------------------- standard role + school REVOKE / GRANT
INT = role_id("INTENDANT")
code, pol = call("GET", f"/access/roles/{INT}/policy", admin)
base = set(pol.get("effective", []))
check(code == 200 and pol["adjustable"] and "inventory.stock.adjust" in base, "politique du rôle standard Intendant lisible")
desired = sorted((base - {"inventory.stock.adjust"}) | {"finance.cash.read"})
code, res = call("PUT", f"/access/roles/{INT}/policy", admin, {"capabilities": desired, "reason": "Recette 0085 : retrait + ajout"})
check(code == 200 and res.get("status") == "APPLIED" and res["removed"] == ["inventory.stock.adjust"] and res["added"] == ["finance.cash.read"],
      f"REVOKE + GRANT appliqués sans copier le rôle ({code} {res.get('status')})")
intendant = login(U["INTENDANT"])
code, me_int = call("GET", "/access/me", intendant)
check("inventory.stock.adjust" not in me_int["permissions"] and "finance.cash.read" in me_int["permissions"], "moteur : permissions effectives de l’intendant recalculées")
check("finance" in {n["key"] for n in me_int["navigation"]}, "navigation : Centre financier ouvert par la capacité ajoutée")
code, _ = call("POST", "/stewardship/stock/movements", intendant, {"item_id": str(uuid.uuid4()), "movement_type": "ADJUSTMENT",
                                                                   "adjustment_direction": "INCREASE", "quantity": 1, "reason": "Recette RBAC"})
check(code == 403, f"backend : capacité retirée → 403 ({code})")
roles_list = call("GET", "/access/roles", admin)[1]["items"]
check(any(r["id"] == INT and r["adjustments"] == 2 and r["kind"] == "SCHOOL_STANDARD" for r in roles_list), "le rôle garde son identité standard (2 ajustements)")

# ---------------------------------------------------------------- separation of duties
SEC = role_id("SECRETARIAT")
code, res = call("PUT", f"/access/roles/{SEC}/policy", admin_multi, {"capabilities": call("GET", f"/access/roles/{SEC}/policy", admin_multi)[1]["effective"][:-1],
                                                                     "reason": "Recette : rôle détenu"})
check(code == 409 and (res.get("detail") or {}).get("code") == "SOD_BLOCKED", "SELF_ELEVATION : modifier un rôle que l’on détient → BLOCK")
desired_gov = sorted(set(desired) | {"access.users.read"})
code, res = call("PUT", f"/access/roles/{INT}/policy", admin, {"capabilities": desired_gov, "reason": "Recette : droit de gouvernance"})
check(code in (200, 201) and res.get("status") == "PENDING_APPROVAL", f"GOVERNANCE_GRANT → demande d’approbation ({code} {res.get('status')})")
req = res.get("request_id")
code, res2 = call("POST", f"/access/requests/{req}/approve", admin, {"reason": "auto"})
check(code == 409 and (res2.get("detail") or {}).get("code") == "SOD_BLOCKED", "auto-approbation refusée")
try:
    with owner.begin() as c:
        c.execute(text("UPDATE rbac_change_requests SET status='APPROVED', decided_by_user_id=requested_by_user_id, decided_at=now() WHERE id=:id"), {"id": req})
    check(False, "base : auto-approbation acceptée")
except Exception:
    check(True, "base : auto-approbation impossible même en SQL direct (CHECK)")
code, res3 = call("POST", f"/access/requests/{req}/approve", admin_multi, {"reason": "Second gestionnaire"})
check(code == 200 and res3.get("status") == "APPROVED" and res3["result"].get("status") == "APPLIED", f"approbation par un second gestionnaire ({code})")
code, _ = call("GET", "/access/requests?status=ALL", admin)
check(code == 200, "historique des demandes lisible")

try:
    with owner.begin() as c:
        c.execute(text("""INSERT INTO rbac_school_role_policies(school_id,role_id,capability_code,effect,reason)
            VALUES(:s,:r,'access.roles.manage','REVOKE','Recette socle protégé')"""), {"s": A["school_id"], "r": role_id("ADMIN_SYSTEME_ECOLE")})
    check(False, "socle protégé : retrait accepté")
except Exception:
    check(True, "socle protégé de l’Administrateur : retrait refusé par la base")
try:
    with owner.begin() as c:
        c.execute(text("""INSERT INTO rbac_school_role_policies(school_id,role_id,capability_code,effect,reason)
            VALUES(:s,:r,'settings.backups.restore','GRANT','Recette capacité prévue')"""), {"s": A["school_id"], "r": INT})
    check(False, "capacité PLANNED attribuable")
except Exception:
    check(True, "capacité PLANNED : jamais attribuable par une école")

# PAIR warning on an assignment: CAISSIER1 + GESTIONNAIRE (encaisser / annuler en autorité supérieure)
body = {"role_id": role_id("GESTIONNAIRE"), "scopes": [{"type": "SCHOOL"}], "reason": "Recette séparation des tâches"}
code, res = call("POST", f"/access/members/{U['CAISSIER1']['membership_id']}/roles", admin, body)
check(code == 409 and (res.get("detail") or {}).get("code") == "SOD_WARNING", f"cumul sensible → avertissement à confirmer ({code})")
code, res = call("POST", f"/access/members/{U['CAISSIER1']['membership_id']}/roles", admin, {**body, "acknowledge_warnings": True})
check(code in (200, 201) and "FIN_COLLECT_VS_SUPERVISOR_REVERSE" in res.get("acknowledged_rules", []), "avertissement confirmé, tracé dans l’attribution")
created_assignments.append(res.get("assignment_id"))

# SECTION scope projected in /access/me
code, res = call("POST", f"/access/members/{U['SECR']['membership_id']}/roles", admin,
                 {"role_id": role_id("PREFET_ETUDES"), "scopes": [{"type": "SECTION", "value": "PRIMAIRE"}], "reason": "Recette portée interdite"})
check(code == 422, f"Préfet hors Secondaire : refus explicite, plus d’erreur serveur ({code})")
sec_code = "PRIMAIRE"   # school A only has the primary section: Directeur de section
code, res = call("POST", f"/access/members/{U['SECR']['membership_id']}/roles", admin,
                 {"role_id": role_id("DIRECTION_SECTION"), "scopes": [{"type": "SECTION", "value": sec_code}], "reason": "Recette portée section"})
check(code in (200, 201), f"Directeur de section limité à une section ({code})")
created_assignments.append(res.get("assignment_id"))
code, me_sec = call("GET", "/access/me", login(U["SECR"]))
check(any(s["type"] == "SECTION" and s["value"] == sec_code for s in me_sec.get("scoped", [])), "portée SECTION projetée dans /access/me")

# assisted conversion preview of a school-owned clone (never automatic)
custom = sql("SELECT id FROM rbac_roles WHERE kind='SCHOOL_CUSTOM' AND school_id=:s AND status='ACTIVE' ORDER BY created_at LIMIT 1", s=A["school_id"])
if custom:
    code, prev = call("GET", f"/access/roles/{custom[0]['id']}/conversion-preview", admin)
    check(code == 200 and "convertible" in prev and prev["candidates"], f"aperçu de conversion assistée ({code}, convertible={prev.get('convertible')})")

# ---------------------------------------------------------------- cleanup: back to the platform baseline
code, res = call("PUT", f"/access/roles/{INT}/policy", admin, {"capabilities": sorted(base), "reason": "Recette 0085 : retour au standard"})
check(code == 200 and res.get("status") == "APPLIED", "retour exact au rôle standard (politiques retirées, historique conservé)")
for aid in filter(None, created_assignments[1:]):
    call("POST", f"/access/assignments/{aid}/revoke", admin_multi, {"reason": "Fin de recette RBAC"})
call("POST", f"/access/assignments/{created_assignments[0]}/revoke", admin_multi, {"reason": "Fin de recette RBAC"})
left = sql("SELECT count(*) n FROM rbac_school_role_policies WHERE school_id=:s AND active", s=A["school_id"])[0]["n"]
check(left == 0, "aucune politique active laissée par la recette")
print(f"\n{'OK' if FAILS == 0 else 'ÉCHECS'} — {FAILS} échec(s)")
sys.exit(1 if FAILS else 0)
