from __future__ import annotations

import os

from sqlalchemy import create_engine, text

from edusync.bootstrap.settings import Settings
from edusync.shared.infrastructure.security import hash_password


def _ensure_manager_assignment(conn, user_id) -> None:
    role = conn.execute(text("SELECT id FROM rbac_roles WHERE code='MANAGER_SYSTEME' AND kind='PLATFORM_STANDARD' AND status='ACTIVE'")).first()
    if role is None:
        raise RuntimeError("Rôle MANAGER_SYSTEME absent/inactif; exécutez les migrations avant le bootstrap")
    existing = conn.execute(text("""
        SELECT id FROM rbac_assignments WHERE user_id=:uid AND role_id=:rid AND school_id IS NULL AND active=true
          AND valid_from<=now() AND (valid_until IS NULL OR valid_until>now()) LIMIT 1
    """), {"uid":user_id,"rid":role[0]}).first()
    if existing is not None:
        return
    aid = conn.execute(text("""
        INSERT INTO rbac_assignments(user_id,role_id,school_id,membership_id,active,reason)
        VALUES (:uid,:rid,NULL,NULL,true,'PLATFORM_BOOTSTRAP') RETURNING id
    """), {"uid":user_id,"rid":role[0]}).scalar_one()
    conn.execute(text("INSERT INTO rbac_assignment_scopes(assignment_id,scope_type,scope_value) VALUES (:aid,'PLATFORM',NULL)"), {"aid":aid})


def main() -> None:
    settings = Settings()
    settings.assert_provisioning_safe()
    email = settings.platform_admin_email.strip().lower()
    engine = create_engine(settings.platform_database_url, future=True, pool_pre_ping=True)
    with engine.begin() as conn:
        row = conn.execute(text("SELECT id,active,is_platform_admin FROM users WHERE email=:email"), {"email": email}).first()
        if row is None:
            user_id = conn.execute(text("""
                INSERT INTO users(email,full_name,password_hash,active,is_platform_admin,version)
                VALUES (:email,:name,:password_hash,true,true,1) RETURNING id
            """), {
                "email": email, "name": settings.platform_admin_name.strip(),
                "password_hash": hash_password(settings.platform_admin_password),
            }).scalar_one()
            _ensure_manager_assignment(conn,user_id)
            print(f"POINT4 platform manager created: {email}")
            return

        if not bool(row[1]) or not bool(row[2]):
            raise RuntimeError("Le compte bootstrap existe mais n'est pas un administrateur plateforme actif. Refus de l'élever automatiquement.")
        user_id=row[0]
        _ensure_manager_assignment(conn,user_id)
        if os.environ.get("EDUSYNC_ROTATE_PLATFORM_ADMIN_PASSWORD") == "YES":
            conn.execute(text("UPDATE users SET password_hash=:password_hash,full_name=:name,version=version+1 WHERE id=:id"), {
                "id": user_id, "password_hash": hash_password(settings.platform_admin_password),
                "name": settings.platform_admin_name.strip(),
            })
            print(f"POINT4 platform manager password rotated explicitly: {email}")
        else:
            print(f"POINT4 platform manager already exists; password unchanged: {email}")


if __name__ == "__main__":
    main()
