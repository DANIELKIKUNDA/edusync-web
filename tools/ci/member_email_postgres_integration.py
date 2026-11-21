"""Modifier l'adresse e-mail d'un membre — real HTTP + real PostgreSQL (owner, 2026-11-21).

The e-mail is the sign-in address and where the automatic reports go. Checks: the change is saved and audited with the
reason and the old address; every open session of the member ends; an address already used, a shared account, one's own
account and a role without the right are refused.

    python tools/local/isolated_db.py env <db> -- ../.venv/Scripts/python.exe ../tools/ci/member_email_postgres_integration.py

CI=true, localhost only (three_roles_postgres_integration). Exits 1 on any FAIL.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_roles_postgres_integration as H  # noqa: E402
from three_roles_postgres_integration import RUN, actor_for, as_, check, key, one, school, sql  # noqa: E402

A_ = "/api/v1/access/members"


def member(sid, name):
    uid, mid = uuid.uuid4(), uuid.uuid4()
    sql("INSERT INTO users(id,email,full_name,password_hash,active,version) VALUES(:i,:e,:n,'x',true,1)",
        i=uid, e=f"{name.lower()}-{uid.hex[:8]}@example.test", n=name)
    sql("INSERT INTO school_memberships(id,school_id,user_id,active,version) VALUES(:i,:s,:u,true,1)", i=mid, s=sid, u=uid)
    return uid, mid


def run(A: dict, B: dict) -> None:
    print("\n== Modifier l'adresse e-mail d'un membre (21/11/2026)")
    sid = A["id"]
    admin = actor_for("ADMIN_SYSTEME_ECOLE", sid)
    uid, mid = member(sid, "CAISSIERE")
    sql("""INSERT INTO user_device_sessions(user_id,school_id,membership_id,token_hash,user_version)
           VALUES(:u,:s,:m,:h,1)""", u=uid, s=sid, m=mid, h=uuid.uuid4().hex + uuid.uuid4().hex)
    new = f"nouvelle-{RUN}@example.test".lower()

    r = as_(admin).post(f"{A_}/{mid}/email", json={"email": f"  {new.upper()} ", "reason": "Adresse erronée à la création"}, headers=key())
    check("l'adresse est modifiée (en minuscules)", r.status_code == 200 and one("SELECT email FROM users WHERE id=:u", u=uid)[0] == new,
          r.text[:200])
    check("les sessions ouvertes du membre sont fermées", one(
        "SELECT count(*) FROM user_device_sessions WHERE user_id=:u AND revoked_at IS NULL", u=uid)[0] == 0
          and r.json().get("sessions_revoked") == 1, r.text[:200])
    aud = one("""SELECT reason, old_json::text FROM audit_events WHERE action='ACCESS_MEMBER_EMAIL_CHANGED' AND entity_id=:m
                 ORDER BY occurred_at DESC LIMIT 1""", m=mid)
    check("journal d'audit : motif et ancienne adresse", bool(aud) and aud[0] == "Adresse erronée à la création"
          and "caissiere-" in aud[1], aud)

    other_uid, _ = member(sid, "AUTRE")
    taken = one("SELECT email FROM users WHERE id=:u", u=other_uid)[0]
    r = as_(admin).post(f"{A_}/{mid}/email", json={"email": taken, "reason": "Essai doublon"}, headers=key())
    check("adresse déjà utilisée → refusée", r.status_code == 409, (r.status_code, r.text[:120]))
    r = as_(admin).post(f"{A_}/{mid}/email", json={"email": "pas-une-adresse", "reason": "Essai invalide"}, headers=key())
    check("adresse invalide → refusée", r.status_code == 422, r.status_code)

    s_uid, s_mid = member(sid, "PARTAGE")
    sql("INSERT INTO school_memberships(id,school_id,user_id,active,version) VALUES(:i,:s,:u,true,1)", i=uuid.uuid4(), s=B["id"], u=s_uid)
    r = as_(admin).post(f"{A_}/{s_mid}/email", json={"email": f"partage-{RUN}@example.test", "reason": "Essai partagé"}, headers=key())
    check("compte partagé avec une autre école → refusé", r.status_code == 409, (r.status_code, r.text[:120]))

    r = as_(admin).post(f"{A_}/{admin.membership_id}/email", json={"email": f"moi-{RUN}@example.test", "reason": "Essai soi-même"}, headers=key())
    check("sa propre adresse → refusée", r.status_code == 403, r.status_code)

    r = as_(actor_for("CAISSIER", sid)).post(f"{A_}/{mid}/email", json={"email": f"x-{RUN}@example.test", "reason": "Sans droit"}, headers=key())
    check("sans le droit de modifier les membres → refusé", r.status_code == 403, r.status_code)


def main() -> int:
    A, B = school("A"), school("B")
    run(A, B)
    H.CLIENT.__exit__(None, None, None)
    fails = [r for r in H.RESULTS if r[0] == "FAIL"]
    print(f"\n{len(H.RESULTS) - len(fails)}/{len(H.RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
