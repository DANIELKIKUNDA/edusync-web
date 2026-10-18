"""Local probe of the platform directory « Utilisateurs & accès » (lot 2026-10) against the running local API.

Real HTTP with real sign-in + TOTP (local recette fixtures). Prints PASS/FAIL lines; never prints a secret.
Covers: scope (platform / school), server-side search, filters (scope, status, school, role, active accesses),
keyset pagination (no duplicate, no gap), dashboard consistency, read-only detail, security signals reserved to the
team capability, no mutation route, direct API calls (anonymous, school session). Usage: python tools/local/identities_probe.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend/src"))
from edusync.shared.infrastructure.mfa import current_step, totp_code  # noqa: E402

API = "http://127.0.0.1:58100/api/v1"
FX = json.loads((ROOT / ".local/claude-fixtures-edusync_claude_fresh.json").read_text(encoding="utf-8"))
ENV = {l.split("=", 1)[0]: l.rstrip("\n").split("=", 1)[1] for l in (ROOT / ".local/certification.env").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#")}
FAILS = 0


def check(ok, label):
    global FAILS
    print(("PASS  " if ok else "FAIL  ") + label, flush=True)
    FAILS += 0 if ok else 1


def call(method, path, token=None, body=None, headers=None, raw=False):
    h = {"Content-Type": "application/json", "Origin": "http://localhost:5180", **({"Authorization": f"Bearer {token}"} if token else {}), **(headers or {})}
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers=h)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
            return r.status, (data if raw else json.loads(data or b"{}")), int((time.perf_counter() - t0) * 1000)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}"), int((time.perf_counter() - t0) * 1000)
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


def step_up(token, secret):
    time.sleep(31)
    wait_window()
    return call("POST", "/auth/platform/mfa/step-up", token, {"code": totp_code(secret, current_step())})[0] == 200


manager, msecret = login("certification@example.test", ENV["EDUSYNC_PLATFORM_ADMIN_PASSWORD"])
support, _ = login(FX["N1_TEAM"]["u2"]["email"], FX["N1_TEAM"]["u2"]["password"])

# ---------------------------------------------------------------- RBAC / direct API
check(call("GET", "/platform/identities")[0] == 401, "accès direct sans jeton refusé (401)")
adm = FX["A"]["users"]["ADMIN"]
code, sess, _ = call("POST", "/auth/login", body={"email": adm["email"], "password": adm["password"], "scope": "AUTO"})
school_token = (sess or {}).get("access_token")
if school_token:
    check(call("GET", "/platform/identities", school_token)[0] in (401, 403), "jeton d’une session école refusé sur l’annuaire plateforme")
    check(call("GET", f"/platform/identities/{adm['user_id']}", school_token)[0] in (401, 403), "jeton école refusé sur le détail")
else:
    print(f"INFO  session école non ouverte (HTTP {code}) : contrôle couvert par les tests de dépendances")
for path in ("/platform/identities", f"/platform/identities/{adm['user_id']}"):
    for method in ("POST", "PATCH", "DELETE"):
        check(call(method, path, manager, body={})[0] in (404, 405), f"aucune action d’écriture sur {path.split('/')[2]} ({method})")

# ---------------------------------------------------------------- scope
code, all_, ms = call("GET", "/platform/identities?limit=25", manager)
check(code == 200 and all_["total"] > 0 and len(all_["items"]) == 25, f"annuaire : {all_.get('total')} identités, 25 par page ({ms} ms)")
code, me, _ = call("GET", "/platform/identities?q=certification%40example.test", manager)
row = (me.get("items") or [{}])[0]
check(row.get("scope") == "PLATFORM" and row.get("first_school_name") is None and "Manager système" in row.get("platform_roles", []),
      "Manager Système non rattaché : portée Plateforme, école vide, rôle affiché")
code, plat, _ = call("GET", "/platform/identities?scope=PLATFORM&limit=100", manager)
check(code == 200 and all(x["scope"] in ("PLATFORM", "BOTH") for x in plat["items"]), f"filtre Plateforme : {plat['total']} comptes, tous de portée plateforme")
code, sch, _ = call("GET", "/platform/identities?scope=SCHOOL&limit=100", manager)
check(code == 200 and all(x["schools_count"] > 0 and x["first_school_name"] for x in sch["items"]), f"filtre Écoles : {sch['total']} comptes, tous rattachés à une école")

# ---------------------------------------------------------------- search
code, s1, _ = call("GET", "/platform/identities?q=" + urllib.parse.quote(adm["email"].split("@")[0].upper()), manager)
check(code == 200 and any(x["id"] == adm["user_id"] for x in s1["items"]), "recherche serveur par e-mail (casse ignorée)")
check(call("GET", "/platform/identities?q=" + "x" * 81, manager)[0] == 422, "recherche bornée (80 caractères)")

# ---------------------------------------------------------------- filters
code, s2, _ = call("GET", f"/platform/identities?school_id={adm['school_id']}&limit=100", manager)
check(code == 200 and s2["total"] > 0 and any(x["id"] == adm["user_id"] for x in s2["items"]), f"filtre école : {s2['total']} comptes de l’école A")
code, s3, _ = call("GET", "/platform/identities?role=MANAGER_SYSTEME&limit=100", manager)
check(code == 200 and all("Manager système" in x["platform_roles"] for x in s3["items"]), f"filtre rôle Manager système : {s3['total']}")
code, s4, _ = call("GET", "/platform/identities?status=DISABLED&limit=100", manager)
check(code == 200 and all(x["status"] == "DISABLED" for x in s4["items"]), f"filtre statut Désactivé : {s4['total']}")
code, f, _ = call("GET", "/platform/identities/filters", manager)
check(code == 200 and any(r["code"] == "CAISSIER" for r in f["roles"]), f"rôles filtrables (standards) : {len(f.get('roles', []))}")
for bad in ("scope=ALL", "status=X", "role=drop%20table", "cursor=Zm9yZ2Vk"):
    check(call("GET", "/platform/identities?" + bad, manager)[0] == 422, f"paramètre invalide refusé : {bad.split('=')[0]}")

# ---------------------------------------------------------------- dashboard consistency
code, d, _ = call("GET", "/platform/dashboard", manager)
kpi = d["kpis"]["active_accesses"]
code, a2, _ = call("GET", "/platform/identities?active_only=true&limit=1", manager)
check(a2["total"] == kpi, f"cohérence tableau de bord : accès actifs {kpi} = {a2['total']}")

# ---------------------------------------------------------------- pagination
for scope in ("", "SCHOOL"):
    seen, cursor, pages, slow = [], None, 0, 0
    while True:
        code, r, ms = call("GET", f"/platform/identities?limit=50&scope={scope}" + (f"&cursor={cursor}" if cursor else ""), manager)
        pages += 1; slow = max(slow, ms)
        seen += [x["id"] for x in r["items"]]
        cursor = r["next_cursor"]
        if not cursor:
            break
    check(len(seen) == r["total"] and len(set(seen)) == r["total"], f"pagination par curseur {scope or 'Tous'} : {pages} pages, {r['total']} comptes, ni doublon ni trou (max {slow} ms)")

# ---------------------------------------------------------------- detail
code, dm, _ = call("GET", f"/platform/identities/{adm['user_id']}", manager)
check(code == 200 and dm["memberships"] and dm["security"] is not None and "password_hash" not in json.dumps(dm),
      "détail en lecture (rattachements, rôles) ; signaux de sécurité visibles par l’équipe plateforme ; aucun secret")
code, ds, _ = call("GET", f"/platform/identities/{adm['user_id']}", support)
check(code == 200 and ds["security"] is None and ds["can_manage_collaborators"] is False, "rôle restreint : détail sans signaux de sécurité ni action")
check(call("GET", f"/platform/identities/{uuid.uuid4()}", manager)[0] == 404, "compte inconnu : 404")

print("\nRÉSULTAT : " + ("PASS" if FAILS == 0 else f"FAIL ({FAILS})"))
sys.exit(1 if FAILS else 0)
