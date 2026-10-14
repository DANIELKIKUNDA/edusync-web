"""Shared helpers for the Claude certification probes (isolated local instance only).

Secrets come from the environment loaded by the private runner; nothing secret is printed or stored here.
State (generated test accounts) is kept privately under .local/claude-fixtures.json.
"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
BASE = os.environ["EDUSYNC_API_BASE_URL"]
assert BASE.startswith("http://127.0.0.1:"), "Local certification API required"
DB_URL = os.environ["EDUSYNC_OWNER_DATABASE_URL"]
assert "@127.0.0.1:55432/" in DB_URL, "Isolated certification PostgreSQL required"
PRIVATE = ROOT / ".local" / f"claude-fixtures-{DB_URL.rsplit('/', 1)[1]}.json"
state: dict = json.loads(PRIVATE.read_text(encoding="utf-8")) if PRIVATE.exists() else {}
results: list[dict] = []
owner = create_engine(DB_URL, pool_size=2)


def save() -> None:
    PRIVATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append({"check": name, "pass": bool(ok), "detail": detail[:300]})
    print(f"{'PASS' if ok else 'FAIL'} {name}{': ' + detail[:300] if detail else ''}", flush=True)
    return ok


def call(client: httpx.Client, method: str, path: str, **kw) -> httpx.Response:
    headers = kw.pop("headers", {})
    if method not in ("GET", "HEAD"):
        headers.setdefault("Idempotency-Key", str(uuid4()))
    return client.request(method, path, headers=headers, **kw)


def must(client, method, path, expected=(200, 201), **kw) -> httpx.Response:
    r = call(client, method, path, **kw)
    exp = (expected,) if isinstance(expected, int) else expected
    if r.status_code not in exp:
        raise RuntimeError(f"{method} {path}: HTTP {r.status_code}; {r.text[:300]}")
    return r


# ---------------------------------------------------------------- second factor of platform test accounts (option B)
# Probes pass the real second factor: no bypass exists. Codes are computed here with an implementation written
# independently of the application (RFC 6238), from secrets enrolled through the public API and kept privately.
MFA_STATE = "MFA_TOTP"


def totp(secret: str, step: int) -> str:
    import base64, hashlib, hmac, struct
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return str((struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000).zfill(6)


def fresh_code(secret: str, last_step: int) -> tuple[str, int]:
    """A code for a step never used before (the server refuses replay): waits for the next 30 s step if needed."""
    import time
    step = int(time.time() // 30)
    if step <= last_step:
        time.sleep(max(0.0, (last_step + 1) * 30 - time.time()) + 0.5)
        step = int(time.time() // 30)
    return totp(secret, step), step


def complete_login(data: dict, email: str, client: httpx.Client | None = None) -> dict:
    """Finishes a platform sign-in that asks for the second factor. A test account is enrolled the first time."""
    if "mfa_token" not in data:
        return data
    return complete_login_response(data, email, client).json()


def complete_login_response(data: dict, email: str, client: httpx.Client | None = None) -> httpx.Response:
    """Same, returning the final HTTP response (the one that opens the session and sets the device cookie)."""
    http = client or httpx.Client(base_url=BASE + "/", timeout=60)
    store = state.setdefault(MFA_STATE, {})
    key = email.strip().lower()
    if data.get("mfa_enrollment_required"):
        started = http.post("auth/mfa/enroll/start", json={"mfa_token": data["mfa_token"]})
        if started.status_code != 200:
            raise RuntimeError(f"enrolment start: HTTP {started.status_code}")
        secret = started.json()["secret"]
        code, step = fresh_code(secret, 0)
        done = http.post("auth/mfa/enroll/confirm", json={"mfa_token": data["mfa_token"], "code": code})
        if done.status_code != 200:
            raise RuntimeError(f"enrolment confirm: HTTP {done.status_code}")
        store[key] = {"secret": secret, "last_step": step, "recovery_codes": done.json()["recovery_codes"]}
        save()
        return done
    entry = store.get(key)
    if not entry:
        raise RuntimeError("Second facteur inconnu pour ce compte de test (réinitialisez-le depuis l'Atelier Pro)")
    for _ in range(2):
        code, step = fresh_code(entry["secret"], int(entry.get("last_step", 0)))
        entry["last_step"] = step
        save()
        r = http.post("auth/mfa/verify", json={"mfa_token": data["mfa_token"], "code": code})
        if r.status_code == 200:
            return r
        if r.status_code != 400:  # 400 = step already used elsewhere (UI, another probe): take the next one
            break
    raise RuntimeError(f"second factor: HTTP {r.status_code}")


def login(email: str, password: str, scope: str = "SCHOOL", code: str | None = None) -> httpx.Client:
    c = httpx.Client(base_url=BASE + "/", timeout=60)
    body = {"email": email, "password": password, "scope": scope}
    if code:
        body["school_code"] = code
    r = must(c, "POST", "auth/login", 200, json=body)
    data = complete_login(r.json(), email, c)
    c.headers["Authorization"] = "Bearer " + data["access_token"]
    return c


_platform_token: dict = {}


def platform() -> httpx.Client:
    """Manager système client. The access token is reused for a few minutes inside one probe run, so a run does not
    wait for a new 30 s TOTP step at every call (the server never accepts the same code twice)."""
    import time
    if _platform_token.get("until", 0) > time.time():
        c = httpx.Client(base_url=BASE + "/", timeout=60)
        c.headers["Authorization"] = "Bearer " + _platform_token["token"]
        if c.get("platform/team/me").status_code == 200:  # revoked meanwhile (suspension, logout-all): sign in again
            return c
        _platform_token.clear()
    c = login(os.environ["EDUSYNC_PLATFORM_ADMIN_EMAIL"], os.environ["EDUSYNC_PLATFORM_ADMIN_PASSWORD"], "PLATFORM")
    # A sign-in that passed the code counts as a fresh step-up for 5 minutes: reuse the token for 4 at most, so the
    # sensitive actions of a probe (suspension, team governance, global notification) always run inside that window.
    _platform_token.update(token=c.headers["Authorization"].split(" ", 1)[1], until=time.time() + 4 * 60)
    return c


def platform_login(email: str, password: str, **extra) -> httpx.Response:
    """Raw sign-in response of a platform account, second factor completed (same object as before option B)."""
    r = httpx.post(BASE + "/auth/login", json={"email": email, "password": password, **extra}, timeout=30)
    if r.status_code == 200 and "mfa_token" in r.json():
        return complete_login_response(r.json(), email)
    return r


def sql(statement: str, params: dict | None = None):
    with owner.begin() as c:
        res = c.execute(text(statement), params or {})
        return res.mappings().all() if res.returns_rows else None


def ensure_school(name: str, roles: tuple[str, ...]) -> dict:
    """School + admin user + requested standard roles, created only through the public platform API."""
    mgr = platform()
    fx = state.setdefault(name, {})
    if "code" not in fx:
        suffix = uuid4().hex[:8]
        fx.update(code=f"CL-{name}-{suffix}", users={})
        save()
    if "school_id" not in fx:
        r = must(mgr, "POST", "platform/schools", 201, json={"code": fx["code"], "name": f"École {name} — recette Claude"})
        fx["school_id"] = r.json()["id"]
        save()
    mgr.close()
    return fx


def settle_first_password(account: dict) -> bool:
    """A password typed by someone else (platform bootstrap, school creation/reset) only opens the "choose your password"
    step (owner decisions 2026-10-14). Replace it once with a new private password stored in the fixtures; never printed.
    Returns True when a replacement was needed."""
    r = httpx.post(BASE + "/auth/login", json={"email": account["email"], "password": account["password"]}, timeout=30)
    d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200 or not d.get("password_change_required"):
        return False
    new = secrets.token_urlsafe(24)
    c = httpx.post(BASE + "/auth/password/first-change", json={"change_token": d["change_token"], "new_password": new}, timeout=30)
    assert c.status_code in (200, 204), (c.status_code, c.text[:160])
    account["password"] = new
    save()
    return True


def ensure_user(school: dict, key: str, roles: tuple[str, ...]) -> dict:
    mgr = platform()
    users = school.setdefault("users", {})
    u = users.setdefault(key, {})
    if "email" not in u:
        u.update(email=f"{key.lower()}-{uuid4().hex[:8]}@example.test", password=secrets.token_urlsafe(24))
        save()
    if "membership_id" not in u:
        r = must(mgr, "POST", f"platform/schools/{school['school_id']}/bootstrap-admin", (200, 201),
                 json={"email": u["email"], "full_name": f"Agent {key}", "password": u["password"]})
        u.update(r.json())
        save()
        settle_first_password(u)
    for role in roles:
        if role not in u.setdefault("roles", []):
            must(mgr, "POST", f"platform/memberships/{u['membership_id']}/roles", (200, 201),
                 json={"role_code": role, "reason": "Recette Claude isolée — certification"})
            u["roles"].append(role)
            save()
    # bootstrap-admin always grants ADMIN_SYSTEME_ECOLE. Realistic members keep only the roles asked for:
    # the school's access manager is the "ADMIN" key (or whoever explicitly requests the role).
    if key != "ADMIN" and "ADMIN_SYSTEME_ECOLE" not in roles and not u.get("admin_role_removed"):
        r = call(mgr, "POST", f"platform/memberships/{u['membership_id']}/roles/ADMIN_SYSTEME_ECOLE/revoke",
                 json={"reason": "Recette : membre sans rôle d'administration"})
        if r.status_code in (200, 204, 404):
            u["admin_role_removed"] = True
            save()
    mgr.close()
    return u


def user_client(school: dict, key: str) -> httpx.Client:
    u = school["users"][key]
    return login(u["email"], u["password"], "SCHOOL", school["code"])


def dump(path: str) -> None:
    out = Path(__file__).with_name(path)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    passed = sum(r["pass"] for r in results)
    print(f"== {passed}/{len(results)} PASS -> {out.name}")


def grant_test_role(school: dict, user_key: str, code: str, caps: tuple[str, ...]) -> None:
    """Test-only SCHOOL_CUSTOM role (owner SQL); standard roles are never modified."""
    u = school["users"][user_key]
    with owner.begin() as c:
        rid = c.execute(text("SELECT id FROM rbac_roles WHERE school_id=:s AND code=:c"), {"s": school["school_id"], "c": code}).scalar_one_or_none()
        if rid is None:
            rid = c.execute(text("INSERT INTO rbac_roles(school_id,code,label,level,kind,status) VALUES(:s,:c,'Recette Claude','SCHOOL','SCHOOL_CUSTOM','ACTIVE') RETURNING id"),
                            {"s": school["school_id"], "c": code}).scalar_one()
        for cap in caps:
            c.execute(text("INSERT INTO rbac_role_capabilities(role_id,capability_code) VALUES(:r,:p) ON CONFLICT DO NOTHING"), {"r": rid, "p": cap})
        has = c.execute(text("SELECT 1 FROM rbac_assignments WHERE role_id=:r AND membership_id=:m"), {"r": rid, "m": u["membership_id"]}).first()
        if not has:
            aid = c.execute(text("INSERT INTO rbac_assignments(user_id,role_id,school_id,membership_id,reason) VALUES(:u,:r,:s,:m,'Recette Claude isolée') RETURNING id"),
                            {"u": u["user_id"], "r": rid, "s": school["school_id"], "m": u["membership_id"]}).scalar_one()
            c.execute(text("INSERT INTO rbac_assignment_scopes(assignment_id,scope_type) VALUES(:a,'SCHOOL')"), {"a": aid})
