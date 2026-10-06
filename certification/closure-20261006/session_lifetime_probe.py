"""Live probe: persistent session lifetime, rotation and theft detection (real API + PostgreSQL)."""
import json
import os
import sys
import time
from pathlib import Path

import httpx
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import BASE, owner, state, ensure_user, login  # noqa: E402

COOKIE = "edusync_session"
results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


def refresh_with(raw):
    return httpx.post(BASE + "/auth/refresh", cookies={COOKIE: raw}, timeout=30)


def session_row(sid):
    with owner.connect() as c:
        return c.execute(text("SELECT revoked_at,revoked_reason,expires_at,expires_at-created_at AS lifetime FROM user_device_sessions WHERE id=:id"), {"id": sid}).mappings().one()


A = state["A"]
u = ensure_user(A, "CLOSURE_SESS", ("CAISSIER",))
c = login(u["email"], u["password"], "SCHOOL", A["code"])
first = c.cookies.get(COOKIE)
check("connexion : cookie de session posé", bool(first))
import jwt  # noqa: E402
sid = jwt.decode(c.headers["Authorization"].split()[1], options={"verify_signature": False})["sid"]
row = session_row(sid)
check("durée maximale serveur = 90 jours (plus de session de 10 ans)", row["lifetime"].days == 90, row["lifetime"])

r1 = refresh_with(first)
second = r1.cookies.get(COOKIE)
check("renouvellement : jeton tourné", r1.status_code == 200 and second and second != first, r1.status_code)
max_age = [h for h in r1.headers.get_list("set-cookie") if h.startswith(COOKIE)]
check("cookie HttpOnly, SameSite=Lax, chemin limité, durée bornée", bool(max_age) and "HttpOnly" in max_age[0] and "SameSite=lax" in max_age[0] and "Path=/api/v1/auth" in max_age[0] and "Max-Age=" in max_age[0], max_age[0][-120:] if max_age else "")
check("onglet concurrent : ancien jeton accepté dans la fenêtre de grâce", refresh_with(first).status_code == 200)

# Age the grace window, then replay the old token: theft => whole session revoked.
with owner.begin() as conn:
    conn.execute(text("UPDATE user_device_sessions SET previous_valid_until=now()-interval '1 second' WHERE id=:id"), {"id": sid})
stolen = refresh_with(first)
check("jeton tourné rejoué après la grâce : refusé", stolen.status_code == 401, stolen.status_code)
row = session_row(sid)
check("réutilisation détectée : session entière révoquée", row["revoked_reason"] == "ROTATED_TOKEN_REUSED", row["revoked_reason"])
check("le jeton légitime ne fonctionne plus non plus", refresh_with(second).status_code == 401)
check("le jeton d'accès lié à la session est coupé", httpx.get(BASE + "/auth/me", headers={"Authorization": c.headers["Authorization"]}).status_code == 401)

# Idle timeout (30 days without activity).
c2 = login(u["email"], u["password"], "SCHOOL", A["code"])
sid2 = jwt.decode(c2.headers["Authorization"].split()[1], options={"verify_signature": False})["sid"]
with owner.begin() as conn:
    conn.execute(text("UPDATE user_device_sessions SET last_seen_at=now()-interval '31 days' WHERE id=:id"), {"id": sid2})
r = refresh_with(c2.cookies.get(COOKIE))
check("inactivité > 30 jours : renouvellement refusé", r.status_code == 401, r.status_code)
check("inactivité : session révoquée (IDLE_TIMEOUT)", session_row(sid2)["revoked_reason"] == "IDLE_TIMEOUT")

# Absolute expiry.
c3 = login(u["email"], u["password"], "SCHOOL", A["code"])
sid3 = jwt.decode(c3.headers["Authorization"].split()[1], options={"verify_signature": False})["sid"]
with owner.begin() as conn:
    conn.execute(text("UPDATE user_device_sessions SET expires_at=now()-interval '1 second' WHERE id=:id"), {"id": sid3})
check("durée maximale dépassée : jeton d'accès coupé immédiatement", httpx.get(BASE + "/auth/me", headers={"Authorization": c3.headers["Authorization"]}).status_code == 401)
r = refresh_with(c3.cookies.get(COOKIE))
check("durée maximale dépassée : renouvellement refusé et révoqué", r.status_code == 401 and session_row(sid3)["revoked_reason"] == "ABSOLUTE_EXPIRY", r.status_code)

# Normal persistence: refresh works repeatedly while active; logout kills it.
c4 = login(u["email"], u["password"], "SCHOOL", A["code"])
raw = c4.cookies.get(COOKIE)
ok = True
for _ in range(3):
    r = refresh_with(raw)
    ok = ok and r.status_code == 200
    raw = r.cookies.get(COOKIE) or raw
check("session active : renouvellements successifs (rechargement de page)", ok)
r = httpx.post(BASE + "/auth/logout", cookies={COOKIE: raw})
check("déconnexion 204", r.status_code == 204)
check("après déconnexion : renouvellement refusé", refresh_with(raw).status_code == 401)

out = Path(__file__).with_name("session-lifetime-live.json")
out.write_text(json.dumps({"passed": sum(x["pass"] for x in results), "total": len(results), "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"{sum(x['pass'] for x in results)}/{len(results)} PASS")
sys.exit(0 if all(x["pass"] for x in results) else 1)
