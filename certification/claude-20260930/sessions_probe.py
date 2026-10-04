"""Live session / JWT attack probe (real HTTP API, real PostgreSQL, real Redis)."""
import base64
import json
import os
import statistics
import sys
import time
from uuid import uuid4

import jwt

sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa: E402,F403

A, B = state["A"], state["B"]
SECRET, ISS, AUD = os.environ["EDUSYNC_JWT_SECRET"], os.environ.get("EDUSYNC_JWT_ISSUER", "edusync"), os.environ.get("EDUSYNC_JWT_AUDIENCE", "edusync-web")


def fresh_user(school, key, roles=("CAISSIER",)):
    school["users"].pop(key, None)
    return ensure_user(school, key, roles)


def raw(token, path="auth/me"):
    return httpx.get(BASE + "/" + path, headers={"Authorization": "Bearer " + token}, timeout=30)


u = fresh_user(A, "SESS")
c = user_client(A, "SESS")
tok = c.headers["Authorization"].split()[1]
claims = jwt.decode(tok, options={"verify_signature": False})
check("valid token accepted", raw(tok).status_code == 200)

# --- forged / tampered tokens -------------------------------------------------------------------
check("wrong-secret signature rejected", raw(jwt.encode(claims, "x" * 40, algorithm="HS256")).status_code == 401)
h = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
p = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
check("alg=none token rejected", raw(f"{h}.{p}.").status_code == 401)
check("expired token rejected", raw(jwt.encode({**claims, "exp": int(time.time()) - 5}, SECRET, algorithm="HS256")).status_code == 401)
check("wrong audience rejected", raw(jwt.encode({**claims, "aud": "other"}, SECRET, algorithm="HS256")).status_code == 401)
check("refresh-type token rejected as access", raw(jwt.encode({**claims, "typ": "refresh"}, SECRET, algorithm="HS256")).status_code == 401)
# Even with the real secret, swapping the school must not cross tenants (DB re-checks membership).
x = jwt.encode({**claims, "school_id": B["school_id"]}, SECRET, algorithm="HS256")
check("validly-signed token pointing at school B refused", raw(x).status_code in (401, 403), f"HTTP {raw(x).status_code}")
x = jwt.encode({**claims, "school_id": B["school_id"], "membership_id": B["users"]["CAISSIER1"]["membership_id"]}, SECRET, algorithm="HS256")
check("validly-signed token with B membership but A user refused", raw(x).status_code in (401, 403))
check("platform-scope token refused on school API", raw(jwt.encode({**claims, "scope": "platform"}, SECRET, algorithm="HS256")).status_code == 403)
check("no token -> 401", httpx.get(BASE + "/auth/me").status_code == 401)

# --- refresh / logout / device revocation ------------------------------------------------------
r = call(c, "POST", "auth/refresh")
check("refresh with device cookie", r.status_code == 200)
c2 = user_client(A, "SESS")  # second device
sessions = must(c, "GET", "auth/sessions").json()["items"]
check("sessions listed for user", len([s for s in sessions if not s["revoked_at"]]) >= 2, str(len(sessions)))
other = [s for s in sessions if not s["revoked_at"]]
r = call(c2, "POST", "auth/logout")
check("logout 204", r.status_code == 204)
r = call(c2, "POST", "auth/refresh")
check("refresh after logout refused", r.status_code == 401)
old_access = c2.headers["Authorization"].split()[1]
check("access token after logout of its device rejected", raw(old_access).status_code == 401, f"HTTP {raw(old_access).status_code}")
r = call(c, "POST", "auth/sessions/not-a-uuid/revoke")
check("revoke with malformed id is a client error, not 500", 400 <= r.status_code < 500, f"HTTP {r.status_code}")
live_id = sql("SELECT id FROM user_device_sessions WHERE user_id=:u AND revoked_at IS NULL ORDER BY created_at LIMIT 1", {"u": u["user_id"]})[0]["id"]
r = call(user_client(B, "CAISSIER1"), "POST", f"auth/sessions/{live_id}/revoke")
row = sql("SELECT revoked_at FROM user_device_sessions WHERE id=:i", {"i": live_id})[0]
check("user of B cannot revoke A's live session", row["revoked_at"] is None, f"HTTP {r.status_code}")
check("A's token still valid after B's attempt", call(c, "GET", "auth/me").status_code == 200)

# --- password change invalidates everything ----------------------------------------------------
c3 = user_client(A, "SESS")
newpw = "N3w-" + uuid4().hex
r = call(c3, "POST", "auth/password", json={"current_password": u["password"], "new_password": newpw})
check("password change", r.status_code == 200, r.text[:100])
check("old access token rejected after password change", raw(c.headers["Authorization"].split()[1]).status_code == 401)
check("old refresh cookie rejected after password change", call(c, "POST", "auth/refresh").status_code == 401)
u["password"] = newpw
save()
check("login with new password", call(httpx.Client(base_url=BASE + "/"), "POST", "auth/login", json={"email": u["email"], "password": newpw, "scope": "SCHOOL", "school_code": A["code"]}).status_code == 200)

# --- permission / membership changes take effect immediately -----------------------------------
c4 = user_client(A, "SESS")
check("cashier can open cash", call(c4, "GET", "finance/cash/current").status_code == 200)
mgr = platform()
must(mgr, "POST", f"platform/memberships/{u['membership_id']}/roles/CAISSIER/revoke", (200, 204), json={"reason": "Recette révocation de rôle"})
check("revoked role effective immediately on live token", call(c4, "GET", "finance/cash/current").status_code == 403)
must(mgr, "POST", f"platform/memberships/{u['membership_id']}/deactivate", (200, 204), json={"reason": "Recette désactivation"})
check("deactivated membership: live token rejected", call(c4, "GET", "auth/me").status_code in (401, 403))
check("deactivated membership: refresh rejected", call(c4, "POST", "auth/refresh").status_code == 401)

# --- user enumeration by timing, then brute force (counters reset between phases) -------------
import redis as _redis
rds = _redis.Redis.from_url(os.environ["EDUSYNC_REDIS_URL"], socket_timeout=3, socket_connect_timeout=3)


def reset_counters():
    for k in rds.scan_iter("edusync:auth:fail:*"):
        rds.delete(k)


def t(email):
    s = time.perf_counter()
    r = call(httpx.Client(base_url=BASE + "/", timeout=30), "POST", "auth/login", json={"email": email, "password": "Wrong-password-1", "scope": "SCHOOL", "school_code": A["code"]})
    return time.perf_counter() - s, r.status_code


known = fresh_user(A, "TIMING")
reset_counters()
samples = {"unknown": [], "known": []}
for i in range(7):  # counters reset per pair: stays under the 7-attempt lock
    reset_counters()
    samples["unknown"].append(t(f"nobody-{uuid4().hex[:6]}@example.test"))
    samples["known"].append(t(known["email"]))
mk = statistics.median(x for x, _ in samples["known"]); mu = statistics.median(x for x, _ in samples["unknown"])
ratio = mk / max(mu, 1e-6)
codes = {x for _, x in samples["known"] + samples["unknown"]}
check("no user enumeration by login timing (known/unknown median ratio < 1.5)", ratio < 1.5 and codes == {401}, f"known={mk:.3f}s unknown={mu:.3f}s ratio={ratio:.1f} codes={codes}")

reset_counters()
v = fresh_user(A, "BRUTE")
anon = httpx.Client(base_url=BASE + "/", timeout=30)
codes = [call(anon, "POST", "auth/login", json={"email": v["email"], "password": "wrong-" + str(i), "scope": "SCHOOL", "school_code": A["code"]}).status_code for i in range(9)]
check("account throttled after repeated failures (429)", codes[:7] == [401] * 7 and 429 in codes[7:], str(codes))
r = call(anon, "POST", "auth/login", json={"email": v["email"], "password": v["password"], "scope": "SCHOOL", "school_code": A["code"]})
check("correct password still refused while locked", r.status_code == 429, f"HTTP {r.status_code}")

# IP counter must not be reset by a successful login on another (attacker-owned) account.
reset_counters()
own = fresh_user(A, "ATTACKER")
for i in range(6):
    call(anon, "POST", "auth/login", json={"email": f"victim{i}-{uuid4().hex[:4]}@example.test", "password": "x" * 12, "scope": "SCHOOL", "school_code": A["code"]})
call(anon, "POST", "auth/login", json={"email": own["email"], "password": own["password"], "scope": "SCHOOL", "school_code": A["code"]})
codes = [call(anon, "POST", "auth/login", json={"email": f"victim{i}-{uuid4().hex[:4]}@example.test", "password": "x" * 12, "scope": "SCHOOL", "school_code": A["code"]}).status_code for i in range(3)]
check("IP throttle not reset by attacker's own successful login", 429 in codes, str(codes))
reset_counters()
dump("sessions-live.json")
