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


def login(email: str, password: str, scope: str = "SCHOOL", code: str | None = None) -> httpx.Client:
    c = httpx.Client(base_url=BASE + "/", timeout=60)
    body = {"email": email, "password": password, "scope": scope}
    if code:
        body["school_code"] = code
    r = must(c, "POST", "auth/login", 200, json=body)
    c.headers["Authorization"] = "Bearer " + r.json()["access_token"]
    return c


def platform() -> httpx.Client:
    return login(os.environ["EDUSYNC_PLATFORM_ADMIN_EMAIL"], os.environ["EDUSYNC_PLATFORM_ADMIN_PASSWORD"], "PLATFORM")


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
