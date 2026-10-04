from __future__ import annotations

import concurrent.futures
import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from edusync.bootstrap.settings import Settings


@dataclass
class HttpResult:
    status: int
    headers: dict[str, str]
    body: object


def call(method: str, url: str, *, headers: dict[str, str] | None = None, body: dict | None = None) -> HttpResult:
    raw = None if body is None else json.dumps(body).encode("utf-8")
    h = {"Accept": "application/json", **(headers or {})}
    if raw is not None:
        h["Content-Type"] = "application/json"
    req = Request(url, data=raw, headers=h, method=method)
    try:
        with urlopen(req, timeout=15) as r:
            payload = r.read()
            return HttpResult(r.status, dict(r.headers.items()), json.loads(payload) if payload else None)
    except HTTPError as e:
        payload = e.read()
        try:
            parsed = json.loads(payload) if payload else None
        except Exception:
            parsed = payload.decode("utf-8", errors="replace")
        return HttpResult(e.code, dict(e.headers.items()), parsed)


def must(r: HttpResult, code: int, label: str) -> HttpResult:
    if r.status != code:
        raise SystemExit(f"FAIL | {label} | HTTP {r.status} | {r.body}")
    print(f"PASS | {label}")
    return r


def main() -> None:
    s = Settings()
    if s.env.lower() in {"prod", "production"} and os.environ.get("EDUSYNC_ALLOW_G1_PROBE_PRODUCTION") != "YES":
        raise SystemExit("Refus d'exécuter G1 API probe en production sans EDUSYNC_ALLOW_G1_PROBE_PRODUCTION=YES")
    base = os.environ.get("EDUSYNC_API_BASE_URL", "http://localhost:8000/api/v1").rstrip("/")

    must(call("GET", f"{base}/platform/schools"), 401, "platform_requires_bearer")
    login = must(call("POST", f"{base}/auth/login", body={
        "email": s.platform_admin_email,
        "password": s.platform_admin_password,
        "scope": "PLATFORM",
    }), 200, "platform_jwt_login").body
    assert isinstance(login, dict)
    token = str(login["access_token"])
    h = {"Authorization": f"Bearer {token}"}
    must(call("GET", f"{base}/platform/schools", headers=h), 200, "platform_jwt_authorized")

    code = f"G1API-{uuid4().hex[:8].upper()}"
    idem = f"g1api-create:{uuid4()}"
    school_body = {"name": "G1 API Probe School", "code": code}
    def concurrent_create(_: int) -> HttpResult:
        return call("POST", f"{base}/platform/schools", headers={**h, "Idempotency-Key": idem}, body=school_body)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        pair = list(pool.map(concurrent_create, range(2)))
    for i, r in enumerate(pair, start=1):
        must(r, 201, f"concurrent_create_school_{i}")
    assert isinstance(pair[0].body, dict) and isinstance(pair[1].body, dict)
    if pair[0].body["id"] != pair[1].body["id"]:
        raise SystemExit("FAIL | concurrent_idempotent_same_school")
    replay_flags = [next((v for k, v in r.headers.items() if k.lower() == "idempotent-replayed"), None) for r in pair]
    if sorted(replay_flags) != ["false", "true"]:
        raise SystemExit(f"FAIL | concurrent_idempotent_replay_flags | {replay_flags}")
    print("PASS | concurrent_idempotent_same_school")
    r1 = pair[0]

    must(call("POST", f"{base}/platform/schools", headers={**h, "Idempotency-Key": idem}, body={
        "name": "Different", "code": f"{code}-X",
    }), 409, "same_key_different_payload_rejected")

    school_id = str(r1.body["id"])
    admin_email = f"g1.{uuid4().hex[:10]}@example.test"
    admin_password = "G1-school-admin-Strong-123!"
    must(call("POST", f"{base}/platform/schools/{school_id}/bootstrap-admin", headers={
        **h, "Idempotency-Key": f"g1api-admin:{uuid4()}"
    }, body={"email": admin_email, "full_name": "G1 School Admin", "password": admin_password}), 201, "bootstrap_school_admin")

    school_login = must(call("POST", f"{base}/auth/login", body={
        "email": admin_email, "password": admin_password, "scope": "SCHOOL", "school_code": code,
    }), 200, "school_jwt_login").body
    assert isinstance(school_login, dict)
    school_token = str(school_login["access_token"])
    sh = {"Authorization": f"Bearer {school_token}"}
    me = must(call("GET", f"{base}/auth/me", headers=sh), 200, "school_actor_rls_rbac_resolution").body
    assert isinstance(me, dict)
    # Point 3B replaced the legacy broad school.manage grant with capabilities.
    if me["school_id"] != school_id or "settings.school_identity.read" not in me["permissions"]:
        raise SystemExit("FAIL | school_actor_context_mismatch")
    print("PASS | school_actor_context_mismatch")
    must(call("GET", f"{base}/platform/schools", headers=sh), 403, "school_token_cannot_use_atelier_pro")

    must(call("POST", f"{base}/platform/schools/{school_id}/suspend", headers={
        **h, "Idempotency-Key": f"g1api-suspend:{uuid4()}"
    }, body={"reason": "Fin du probe G1 WEB-0C"}), 200, "probe_school_suspended")

    print("G1 API PASS")


if __name__ == "__main__":
    main()
