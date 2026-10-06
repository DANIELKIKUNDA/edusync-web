"""Live probe: first Manager Système on a truly empty installation (real HTTP API + PostgreSQL).

Run against a blank database only:  EDUSYNC_DB=edusync_closure_blank EDUSYNC_API_PORT=58200
"""
import json
import os
import secrets
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text

BASE = os.environ["EDUSYNC_API_BASE_URL"]
DB = os.environ["EDUSYNC_OWNER_DATABASE_URL"]
assert BASE.startswith("http://127.0.0.1:") and "@127.0.0.1:55432/edusync_closure_blank" in DB, "blank isolated database required"
owner = create_engine(DB)
results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


def q(sql):
    with owner.connect() as c:
        return c.execute(text(sql)).all()


managers_before = q("SELECT count(*) FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id WHERE r.code='MANAGER_SYSTEME'")[0][0]
check("base vierge : aucun Manager Système", managers_before == 0, managers_before)

s = httpx.get(BASE + "/setup/status").json()
check("statut : installation requise et disponible en local", s == {"setup_required": True, "setup_available": True, "token_required": False}, s)

r = httpx.post(BASE + "/setup/first-manager", json={"full_name": "Daniel", "email": "a@b.cd", "password": "court"})
check("mot de passe trop court refusé (422)", r.status_code == 422, r.status_code)
r = httpx.post(BASE + "/setup/first-manager", json={"full_name": "Daniel", "email": "pas-un-email", "password": "x" * 14})
check("adresse e-mail invalide refusée (422)", r.status_code == 422, r.status_code)

password = "Ed!" + secrets.token_urlsafe(18)
candidates = [{"full_name": f"Candidat {i}", "email": f"manager{i}@edusync.test", "password": password} for i in range(6)]
with ThreadPoolExecutor(6) as pool:
    codes = list(pool.map(lambda b: httpx.post(BASE + "/setup/first-manager", json=b, timeout=60).status_code, candidates))
check("6 créations simultanées : exactement une réussit", codes.count(201) == 1 and codes.count(409) == 5, codes)
winner = candidates[codes.index(201)]

s = httpx.get(BASE + "/setup/status").json()
check("statut après création : fermé", s == {"setup_required": False, "setup_available": False, "token_required": False}, s)
r = httpx.post(BASE + "/setup/first-manager", json={"full_name": "Attaquant", "email": "evil@x.test", "password": "y" * 16})
check("second bootstrap public refusé (409)", r.status_code == 409, r.status_code)

managers = q("SELECT u.email FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id JOIN users u ON u.id=a.user_id WHERE r.code='MANAGER_SYSTEME'")
check("un seul Manager Système en base", len(managers) == 1 and managers[0][0] == winner["email"], managers)
check("aucun compte créé pour les perdants ni l'attaquant", q("SELECT count(*) FROM users")[0][0] == 1)
lock = q("SELECT method, manager_user_id IS NOT NULL FROM platform_setup_completion")
check("verrou irréversible posé (SETUP_PAGE)", lock == [("SETUP_PAGE", True)], lock)
audit = q("SELECT count(*) FROM audit_events WHERE action='PLATFORM_FIRST_MANAGER_CREATED'")[0][0]
check("création auditée", audit == 1, audit)

login = httpx.post(BASE + "/auth/login", json={"email": winner["email"], "password": password, "scope": "PLATFORM"})
check("le Manager créé se connecte à l'Atelier Pro", login.status_code == 200 and login.json().get("scope") == "PLATFORM", login.status_code)

platform_url = os.environ["EDUSYNC_PLATFORM_DATABASE_URL"]
try:
    with create_engine(platform_url).begin() as c:
        c.execute(text("DELETE FROM platform_setup_completion"))
    check("le rôle applicatif ne peut pas rouvrir l'installation", False, "DELETE accepté")
except Exception as exc:  # permission denied expected
    # SQLSTATE 42501 = insufficient_privilege (message is localised, the code is not).
    check("le rôle applicatif ne peut pas rouvrir l'installation", getattr(getattr(exc, "orig", None), "sqlstate", "") == "42501", type(exc).__name__)

# Deactivating the manager must NOT reopen the public page.
with owner.begin() as c:
    c.execute(text("UPDATE users SET active=false WHERE email=:e"), {"e": winner["email"]})
s = httpx.get(BASE + "/setup/status").json()
check("Manager désactivé : la page publique reste fermée", s["setup_required"] is False and s["setup_available"] is False, s)
with owner.begin() as c:
    c.execute(text("UPDATE users SET active=true WHERE email=:e"), {"e": winner["email"]})

out = Path(__file__).with_name("setup-live.json")
out.write_text(json.dumps({"passed": sum(r["pass"] for r in results), "total": len(results), "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"{sum(r['pass'] for r in results)}/{len(results)} PASS")
sys.exit(0 if all(r["pass"] for r in results) else 1)
