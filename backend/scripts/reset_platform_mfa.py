"""Operator recovery of a platform account's second factor (MFA option B) — last resort, run on the server.

    python backend/scripts/reset_platform_mfa.py --email manager@example.cd --operator "Nom de l'opérateur" \
        --reason "Téléphone et codes de secours perdus, identité vérifiée en personne le 13/10/2026" --confirm manager@example.cd

Normal path: another Manager système resets the factor from Atelier Pro (« Équipe plateforme »). This script exists
for the case where no other Manager can do it (last Manager who lost both phone and recovery codes). It is not a
backdoor: it needs the database OWNER credentials (EDUSYNC_OWNER_DATABASE_URL), which the API never holds and only
the infrastructure operator has; it gives no access by itself (the password is still required and a new factor
must be enrolled at the next sign-in); it revokes the account's platform sessions and is written to the audit
journal with the operator's name and the reason. Identity must be verified out of band before running it.
"""
from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import create_engine, text

from edusync.bootstrap.settings import Settings
from edusync.modules.iam.application import platform_mfa


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Réinitialisation opérateur du second facteur d'un compte plateforme")
    ap.add_argument("--email", required=True)
    ap.add_argument("--operator", required=True, help="nom de la personne qui exécute la procédure (audit)")
    ap.add_argument("--reason", required=True, help="motif et vérification d'identité effectuée (audit)")
    ap.add_argument("--confirm", required=True, help="ressaisir l'adresse e-mail du compte")
    a = ap.parse_args(argv)
    email = a.email.strip().lower()
    if a.confirm.strip().lower() != email:
        print("Refus : la confirmation ne correspond pas à l'adresse du compte.", file=sys.stderr)
        return 2
    if len(a.reason.strip()) < 15 or len(a.operator.strip()) < 3:
        print("Refus : motif (15 caractères minimum) et nom de l'opérateur obligatoires.", file=sys.stderr)
        return 2
    settings = Settings()
    engine = create_engine(settings.owner_database_url, future=True, pool_pre_ping=True)
    with engine.begin() as conn:
        user = conn.execute(text("SELECT id, active FROM users WHERE lower(email::text)=:e FOR UPDATE"), {"e": email}).mappings().first()
        if user is None or not user["active"]:
            print("Refus : compte introuvable ou désactivé.", file=sys.stderr)
            return 3
        platform = conn.execute(text("""SELECT 1 FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id
            WHERE a.user_id=:u AND a.school_id IS NULL AND a.active AND r.level='PLATFORM' AND r.status='ACTIVE' LIMIT 1"""), {"u": user["id"]}).first()
        if platform is None:
            print("Refus : ce compte n'a aucun rôle plateforme actif (les comptes école n'ont pas de second facteur).", file=sys.stderr)
            return 3
        removed = platform_mfa.reset(conn, user_id=user["id"], reason="RESET_BY_OPERATOR")
        sessions = conn.execute(text("""UPDATE user_device_sessions SET revoked_at=coalesce(revoked_at,now()),revoked_reason=coalesce(revoked_reason,'MFA_RESET_BY_OPERATOR')
            WHERE user_id=:u AND school_id IS NULL AND revoked_at IS NULL"""), {"u": user["id"]}).rowcount
        detail = {"operator": a.operator.strip(), "sessions_revoked": sessions, **removed}
        conn.execute(text("""INSERT INTO audit_events(school_id,actor_user_id,action,entity_type,entity_id,source,result,reason,new_json)
            VALUES(NULL,NULL,'PLATFORM_USER_MFA_RESET_BY_OPERATOR','UserSecurity',:u,'SYSTEM','SUCCESS',:r,CAST(:d AS jsonb))"""),
            {"u": user["id"], "r": a.reason.strip(), "d": json.dumps(detail, ensure_ascii=False)})
    print(f"Second facteur réinitialisé ({removed['factors_revoked']} facteur, {sessions} session(s) plateforme coupée(s)). "
          "Le compte configurera une nouvelle application à sa prochaine connexion. Action auditée.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
