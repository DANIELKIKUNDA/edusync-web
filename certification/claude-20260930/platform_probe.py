"""Atelier Pro (platform) live probe: read surface, Codex open defects, collaborator least privilege."""
import os
import sys
from uuid import uuid4

sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa: E402,F403

A, B = state["A"], state["B"]
mgr = platform()

# --- read surface: no 500 anywhere ---------------------------------------------------------------
for path in ["platform/schools", "platform/audit-count", "platform/dashboard", "platform/schools-page", "platform/access",
             "platform/audit", "platform/diagnostics", "platform/system-notifications", f"platform/schools/{A['school_id']}/detail",
             "platform/rbac/roles"]:
    r = call(mgr, "GET", path)
    check(f"manager GET {path.split('/', 1)[1]}", r.status_code == 200, f"HTTP {r.status_code} {r.text[:160] if r.status_code != 200 else ''}")

# --- Codex open defect: a user holding several roles must appear once in the access list -------
r = call(mgr, "GET", "platform/access", params={"q": A["users"]["ADMIN"]["email"]})
if r.status_code == 200:
    body = r.json()
    items = body.get("items", body if isinstance(body, list) else [])
    mine = [x for x in items if str(x.get("id")) == A["users"]["ADMIN"]["user_id"]]
    check("multi-role user listed once with one school membership", len(mine) == 1 and mine[0]["school_memberships"] == 1,
          f"rows={len(mine)} memberships={mine[0]['school_memberships'] if mine else '-'} (user holds {len(A['users']['ADMIN'].get('roles', []))} roles)")

# --- system notification send/read ----------------------------------------------------------------
r = call(mgr, "POST", "platform/system-notifications", json={"title": "Recette", "body": "Notification système de recette", "severity": "INFO", "target_scope": "ALL_ACTIVE_SCHOOLS"})
check("manager can send a system notification", r.status_code in (200, 201), f"HTTP {r.status_code} {r.text[:200]}")
r = call(user_client(A, "ADMIN"), "GET", "notifications")
check("school A user can read notifications after system broadcast", r.status_code == 200, f"HTTP {r.status_code}")

# --- collaborator: limited, revocable -------------------------------------------------------------
B["users"].pop("COLLAB", None)
col = ensure_user(B, "COLLAB", ())
r = call(mgr, "POST", f"platform/collaborators/{col['user_id']}/grant", json={"reason": "Recette collaborateur limité"})
check("manager grants collaborator", r.status_code == 200, r.text[:120])
cc = login(col["email"], col["password"], "PLATFORM")
for path in ["platform/schools", "platform/audit", "platform/diagnostics"]:
    check(f"collaborator can read {path}", call(cc, "GET", path).status_code == 200)
forbidden = [
    ("POST", "platform/schools", {"code": "X-" + uuid4().hex[:6], "name": "Interdit"}),
    ("POST", f"platform/schools/{A['school_id']}/suspend", {"reason": "Tentative collaborateur"}),
    ("POST", f"platform/schools/{A['school_id']}/bootstrap-admin", {"email": f"x{uuid4().hex[:6]}@example.test", "full_name": "Intrus", "password": "Intrus-123456"}),
    ("POST", f"platform/memberships/{A['users']['ADMIN']['membership_id']}/roles", {"role_code": "PROMOTEUR", "reason": "Escalade tentée"}),
    ("POST", f"platform/memberships/{A['users']['ADMIN']['membership_id']}/deactivate", {"reason": "Tentative collaborateur"}),
    ("POST", f"platform/collaborators/{A['users']['ADMIN']['user_id']}/grant", {"reason": "Escalade tentée"}),
    ("POST", "platform/system-notifications", {"title": "Tentative", "body": "Tentative collaborateur", "severity": "INFO", "target_scope": "ALL_ACTIVE_SCHOOLS"}),
]
for method, path, body in forbidden:
    r = call(cc, method, path, json=body)
    check(f"collaborator forbidden: {method} {path.split('/', 2)[1]}…", r.status_code == 403, f"HTTP {r.status_code}")
check("collaborator token refused on school API", call(cc, "GET", "auth/me").status_code == 403)
status = sql("SELECT status FROM schools WHERE id=:s", {"s": A["school_id"]})[0]["status"]
check("school A still ACTIVE after collaborator attempts", status == "ACTIVE", status)
r = call(mgr, "POST", f"platform/collaborators/{col['user_id']}/revoke", json={"reason": "Fin de collaboration recette"})
check("manager revokes collaborator", r.status_code == 200)
check("revoked collaborator token rejected", call(cc, "GET", "platform/schools").status_code in (401, 403))
check("school user cannot use platform API", call(user_client(A, "ADMIN"), "GET", "platform/schools").status_code == 403)
dump("platform-live.json")
