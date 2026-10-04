"""School access governance, live: each school sets its own policy, guarded automatically."""
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa: E402,F403

A, B = state["A"], state["B"]
for k in ("ACC_GEST", "ACC_M3", "ACC_PROMO", "ACC_TMP"):
    A["users"].pop(k, None)
ensure_user(A, "ACC_GEST", ())
ensure_user(A, "ACC_M3", ())
ensure_user(A, "ACC_TMP", ())
ensure_user(A, "ACC_PROMO", ("PROMOTEUR",))
# ADMIN holds ADMIN_SYSTEME_ECOLE: the school's access manager (standard baseline)
adm = user_client(A, "ADMIN")
badm = user_client(B, "ADMIN")


def member_assignment(client, membership_id, role_label):
    for m in must(client, "GET", "access/members").json()["items"]:
        if m["membership_id"] == membership_id:
            return next((r["assignment_id"] for r in m["roles"] if r["role_label"] == role_label), None)


cat = must(adm, "GET", "access/catalog").json()
codes = {c["code"] for d in cat["domains"] for c in d["capabilities"]}
check("catalog offers school capabilities only (no platform.*)", codes and not any(c.startswith("platform.") for c in codes), f"{cat['total']} capabilities")
roles = {r["code"]: r for r in must(adm, "GET", "access/roles").json()["items"]}
gest = roles["GESTIONNAIRE"]
check("standard roles listed read-only", gest["editable"] is False and "personnel.exit" in gest["capabilities"])

# 1. clone the standard Gestionnaire and remove "record a departure": this school's own policy
r = call(adm, "POST", "access/roles", json={"label": "Gestionnaire sans sortie d'agent", "clone_from_role_id": gest["id"], "description": "Politique propre à l'école A"})
check("clone a standard role into a school role", r.status_code == 201 and "personnel.exit" in r.json()["capabilities"], f"HTTP {r.status_code} {r.text[:120]}")
custom = r.json()
caps = [c for c in custom["capabilities"] if c != "personnel.exit"]
r = call(adm, "PUT", f"access/roles/{custom['id']}", json={"label": custom["label"], "capabilities": caps}, headers={"If-Match": str(custom["version"])})
check("adjust the school role (remove personnel.exit)", r.status_code == 200 and r.json()["removed"] == ["personnel.exit"], f"HTTP {r.status_code} {r.text[:120]}")
r = call(adm, "PUT", f"access/roles/{custom['id']}", json={"label": "x x x", "capabilities": caps}, headers={"If-Match": "1"})
check("stale edit refused (optimistic concurrency)", r.status_code == 409)

# 2. assign it: effective immediately on a live token
g = user_client(A, "ACC_GEST")
check("member without role cannot add an agent", call(g, "POST", "personnel", json={"employee_no": "E-" + uuid4().hex[:6], "last_name": "X", "category": "AUTRE"}).status_code == 403)
r = call(adm, "POST", f"access/members/{A['users']['ACC_GEST']['membership_id']}/roles", json={"role_id": custom["id"], "reason": "Nouveau gestionnaire"})
check("assign the school role", r.status_code == 201, f"HTTP {r.status_code} {r.text[:120]}")
r = call(g, "POST", "personnel", json={"employee_no": "E-" + uuid4().hex[:6], "last_name": "AGENT", "category": "AUTRE"})
check("rights effective immediately (same token, no re-login)", r.status_code == 201, f"HTTP {r.status_code}")
staff = r.json()
r = call(g, "POST", f"personnel/{staff['id']}/exit", json={"reason": "Essai"}, headers={"If-Match": str(staff["version"])})
check("school policy applied: this gestionnaire cannot record a departure", r.status_code == 403, f"HTTP {r.status_code}")

# 3. guardrails
r = call(adm, "POST", f"access/members/{A['users']['ADMIN']['membership_id']}/roles", json={"role_id": roles["PROMOTEUR"]["id"], "reason": "Auto-promotion"})
check("guardrail: nobody grants rights to themselves", r.status_code == 403, f"HTTP {r.status_code}")
r = call(adm, "POST", "access/roles", json={"label": "Rôle piégé", "capabilities": ["platform.schools.create"]})
check("guardrail: no platform capability in a school role", r.status_code == 422, f"HTTP {r.status_code}")
r = call(adm, "PUT", f"access/roles/{gest['id']}", json={"label": "Gestionnaire", "capabilities": []}, headers={"If-Match": "1"})
check("guardrail: standard roles are immutable (clone instead)", r.status_code == 409, f"HTTP {r.status_code}")
r = call(adm, "POST", f"access/members/{A['users']['ACC_GEST']['membership_id']}/roles", json={"role_id": roles["CAISSIER"]["id"], "scopes": [{"type": "SECTION", "value": "INEXISTANTE"}], "reason": "Test"})
check("unknown scope rejected", r.status_code == 422, f"HTTP {r.status_code}")
r = call(adm, "POST", f"access/members/{A['users']['ACC_GEST']['membership_id']}/roles", json={"role_id": roles["CAISSIER"]["id"], "scopes": [{"type": "SECTION", "value": "primaire"}], "reason": "Caisse Primaire seulement"})
check("section-scoped assignment accepted", r.status_code == 201 and r.json()["scopes"] == [{"type": "SECTION", "value": "PRIMAIRE"}], f"HTTP {r.status_code} {r.text[:120]}")

# last access manager can never be removed, even by someone allowed to revoke
assistant = must(adm, "POST", "access/roles", 201, json={"label": "Assistant accès", "capabilities": ["access.permissions.assign", "access.roles.read"]}).json()
must(adm, "POST", f"access/members/{A['users']['ACC_M3']['membership_id']}/roles", 201, json={"role_id": assistant["id"], "reason": "Assistant"})
m3 = user_client(A, "ACC_M3")
admin_assign = member_assignment(m3, A["users"]["ADMIN"]["membership_id"], "Administrateur système école")
r = call(m3, "POST", f"access/assignments/{admin_assign}/revoke", json={"reason": "Tentative de prise de contrôle"})
check("guardrail: the school always keeps at least one access manager", r.status_code == 409, f"HTTP {r.status_code} {r.text[:100]}")

# 4. time-limited right expires by itself
until = (datetime.now(timezone.utc) + timedelta(seconds=6)).isoformat()
must(adm, "POST", f"access/members/{A['users']['ACC_TMP']['membership_id']}/roles", 201, json={"role_id": roles["SECRETARIAT"]["id"], "valid_until": until, "reason": "Remplacement de 6 secondes"})
t = user_client(A, "ACC_TMP")
before = call(t, "POST", "personnel", json={"employee_no": "E-" + uuid4().hex[:6], "last_name": "TMP", "category": "AUTRE"}).status_code
time.sleep(8)
after = call(t, "POST", "personnel", json={"employee_no": "E-" + uuid4().hex[:6], "last_name": "TMP", "category": "AUTRE"}).status_code
check("time-limited right works, then expires automatically", before == 201 and after == 403, f"before={before} after={after}")

# 5. revoke: immediate
aid = member_assignment(adm, A["users"]["ACC_GEST"]["membership_id"], custom["label"])
check("revoke assignment", call(adm, "POST", f"access/assignments/{aid}/revoke", json={"reason": "Fin de mission"}).status_code == 200)
check("revocation effective immediately on live token", call(g, "POST", "personnel", json={"employee_no": "E-" + uuid4().hex[:6], "last_name": "X", "category": "AUTRE"}).status_code == 403)
check("archive unused school role", call(adm, "POST", f"access/roles/{custom['id']}/archive", json={"reason": "Plus utilisé"}).status_code == 200)

# 6. transparency for the Promoteur: read-only journal, nothing to approve
p = user_client(A, "ACC_PROMO")
j = call(p, "GET", "access/journal")
actions = {x["action"] for x in j.json().get("items", [])} if j.status_code == 200 else set()
check("Promoteur sees the rights journal (read-only)", j.status_code == 200 and {"ACCESS_ROLE_CREATED", "ACCESS_ROLE_ASSIGNED", "ACCESS_ROLE_REVOKED"} <= actions, f"HTTP {j.status_code} {sorted(actions)}")
check("Promoteur cannot change rights", call(p, "POST", "access/roles", json={"label": "Essai promoteur", "capabilities": []}).status_code == 403)

# 7. isolation between schools
check("school B never sees school A roles", custom["id"] not in call(badm, "GET", "access/roles").text)
r = call(badm, "POST", f"access/members/{A['users']['ACC_GEST']['membership_id']}/roles", json={"role_id": roles["CAISSIER"]["id"], "reason": "Intrusion"})
check("school B cannot assign roles to A's members", r.status_code == 404, f"HTTP {r.status_code}")
r = call(badm, "POST", f"access/assignments/{admin_assign}/revoke", json={"reason": "Intrusion"})
check("school B cannot revoke A's assignments", r.status_code == 404, f"HTTP {r.status_code}")
dump("access-governance-live.json")
