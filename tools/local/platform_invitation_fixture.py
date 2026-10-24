"""LOCAL ONLY — fixture of the platform activation E2E (fix 2026-10-24, browser-tests/platform_activation_pwa.mjs).

Creates a platform member exactly as « Nouvelle identité » does (unusable random password, MANAGER_SYSTEME role, open
invitation link) without sending the e-mail, so the browser test can open the invitation link like the recipient.
The raw token goes to stdout for the calling test only; it is never logged. Refuses any non-local database.

    python tools/local/platform_invitation_fixture.py create      -> {"token","email","user_id"}
    python tools/local/platform_invitation_fixture.py expire <user_id>
    python tools/local/platform_invitation_fixture.py status <user_id>   -> {"status": "PENDING"|"ACTIVE", ...}
"""
from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("EDUSYNC_LOCAL_PG_PORT", "55432")

import edusync_local as L  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from edusync.modules.iam.application import account_links  # noqa: E402
from edusync.shared.infrastructure.security import hash_password  # noqa: E402


def engine():
    profile = (L.RUN / "profile").read_text().strip() if (L.RUN / "profile").exists() else "demo"
    url = L.load_env(profile)["EDUSYNC_OWNER_DATABASE_URL"]
    if "@127.0.0.1:" not in url and "@localhost:" not in url:
        raise SystemExit("Base non locale : refusé.")
    return create_engine(url)


class _Cfg:
    invitation_ttl_hours = 48
    password_reset_ttl_minutes = 30


def create() -> dict:
    email = f"e2e-manager-{secrets.token_hex(4)}@edusync.test"
    with engine().begin() as c:
        uid = c.execute(text("""INSERT INTO users(email,full_name,password_hash,active,is_platform_admin,must_change_password,password_set_by)
            VALUES(:e,'Second Manager E2E',:p,true,true,false,'PLATFORM') RETURNING id"""),
            {"e": email, "p": hash_password(secrets.token_urlsafe(32))}).scalar_one()
        role = c.execute(text("SELECT id FROM rbac_roles WHERE code='MANAGER_SYSTEME' AND level='PLATFORM' AND school_id IS NULL")).scalar_one()
        aid = c.execute(text("INSERT INTO rbac_assignments(user_id,role_id,reason) VALUES(:u,:r,'E2E activation PWA') RETURNING id"),
                        {"u": str(uid), "r": str(role)}).scalar_one()
        c.execute(text("INSERT INTO rbac_assignment_scopes(assignment_id,scope_type,scope_value) VALUES(:id,'PLATFORM',NULL)"), {"id": str(aid)})
        c.execute(text("""INSERT INTO platform_account_status(user_id,status,reason) VALUES(:u,'ACTIVE','E2E')
            ON CONFLICT (user_id) DO NOTHING"""), {"u": str(uid)})
        raw = account_links.issue(c, _Cfg(), user_id=uid, purpose=account_links.INVITATION)
    return {"token": raw, "email": email, "user_id": str(uid)}


def expire(user_id: str) -> dict:
    with engine().begin() as c:
        n = c.execute(text("UPDATE account_tokens SET created_at=now()-interval '3 days', expires_at=now()-interval '1 minute' WHERE user_id=:u AND purpose='INVITATION' AND used_at IS NULL"),
                      {"u": user_id}).rowcount
    return {"expired": n}


def status(user_id: str) -> dict:
    with engine().begin() as c:
        open_link = c.execute(text("""SELECT count(*) FROM account_tokens WHERE user_id=:u AND purpose='INVITATION' AND school_id IS NULL
            AND used_at IS NULL AND revoked_at IS NULL AND expires_at>now()"""), {"u": user_id}).scalar_one()
        used = c.execute(text("SELECT count(*) FROM account_tokens WHERE user_id=:u AND purpose='INVITATION' AND used_at IS NOT NULL"), {"u": user_id}).scalar_one()
        sessions = c.execute(text("SELECT count(*) FROM user_device_sessions WHERE user_id=:u AND revoked_at IS NULL"), {"u": user_id}).scalar_one()
        mfa = c.execute(text("SELECT count(*) FROM user_mfa_factors WHERE user_id=:u"), {"u": user_id}).scalar_one()
    return {"status": "PENDING" if open_link else "ACTIVE", "invitation_used": used > 0, "open_sessions": sessions, "mfa_factors": mfa}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    out = create() if cmd == "create" else expire(sys.argv[2]) if cmd == "expire" else status(sys.argv[2]) if cmd == "status" else None
    if out is None:
        raise SystemExit(__doc__)
    print(json.dumps(out))
