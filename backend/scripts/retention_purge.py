"""EduSync — purge des données périmées (lot 2026-10). DÉSACTIVÉE PAR DÉFAUT : sans --apply, rien n'est supprimé,
le script compte seulement ce qui serait purgé.

Les durées sont des PROPOSITIONS techniques en attente de validation par le propriétaire (BUSINESS_DECISION_REQUIRED,
docs/architecture/RETENTION.md). Aucune donnée métier (élèves, paiements, documents) n'est concernée.
  * sessions d'appareil révoquées ou expirées depuis plus de 90 jours ;
  * étapes de connexion à usage unique (codes, MFA) expirées depuis plus de 30 jours ;
  * liens de compte (invitation, mot de passe) utilisés, révoqués ou expirés depuis plus de 90 jours ;
  * accusés de réception des fournisseurs appliqués depuis plus de 180 jours ;
  * incidents de la plateforme résolus depuis plus de 2 ans ;
  * messagerie : envois / destinataires / messages techniques plateforme et compte terminés depuis plus de 180 jours,
    appareils push révoqués depuis plus de 90 jours (l'historique des communications d'une école n'est jamais purgé).
Le journal d'audit est en ajout seul (trigger trg_audit_no_update) : sa purge (proposition 5 ans) n'est JAMAIS faite
par ce script tant que la durée légale n'est pas décidée ; --audit-years affiche seulement le volume concerné.

Identifiants PROPRIÉTAIRE de la base (EDUSYNC_OWNER_DATABASE_URL), jamais détenus par l'API.
Usage :  python backend/scripts/retention_purge.py            (comptage)
         python backend/scripts/retention_purge.py --apply    (suppression, journalisée)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from sqlalchemy import create_engine, text

RULES = (
    ("Sessions d'appareil révoquées / expirées", "user_device_sessions",
     "coalesce(revoked_at, expires_at) < now() - interval '90 days'"),
    ("Étapes de connexion expirées", "mfa_challenges", "expires_at < now() - interval '30 days'"),
    ("Liens de compte utilisés / révoqués / expirés", "account_tokens",
     "coalesce(used_at, revoked_at, expires_at) < now() - interval '90 days'"),
    ("Accusés de réception appliqués", "provider_receipts", "applied_at < now() - interval '180 days'"),
    ("Incidents de la plateforme résolus", "platform_incidents", "resolved_at < now() - interval '2 years'"),
    # Messagerie (lot 2026-10) : uniquement les messages techniques plateforme / compte, jamais l'historique d'une école.
    ("Envois plateforme et compte terminés", "communication_deliveries",
     "school_id IS NULL AND status IN ('SENT','DELIVERED','FAILED_PERMANENT','CANCELLED') AND created_at < now() - interval '180 days'"),
    ("Destinataires des messages plateforme et compte", "communication_recipients",
     "school_id IS NULL AND created_at < now() - interval '180 days' AND NOT EXISTS (SELECT 1 FROM communication_deliveries d WHERE d.recipient_id=communication_recipients.id)"),
    ("Messages plateforme et compte", "communication_messages",
     "school_id IS NULL AND created_at < now() - interval '180 days' AND NOT EXISTS (SELECT 1 FROM communication_deliveries d WHERE d.message_id=communication_messages.id)"
     " AND NOT EXISTS (SELECT 1 FROM communication_recipients x WHERE x.message_id=communication_messages.id)"),
    ("Appareils push révoqués", "push_subscriptions", "revoked_at < now() - interval '90 days'"),
)


def run(url: str, apply: bool, audit_years: int) -> dict:
    eng = create_engine(url)
    report = {"apply": apply, "rules": []}
    with eng.begin() as c:
        for label, table, where in RULES:
            n = c.execute(text(f"SELECT count(*) FROM {table} WHERE {where}")).scalar()
            deleted = c.execute(text(f"DELETE FROM {table} WHERE {where}")).rowcount if apply and n else 0
            report["rules"].append({"label": label, "table": table, "eligible": int(n), "deleted": int(deleted)})
        report["audit_older_than_years"] = {"years": audit_years, "rows": int(c.execute(text(
            "SELECT count(*) FROM audit_events WHERE occurred_at < now() - make_interval(years => :y)"), {"y": audit_years}).scalar()),
            "purged": False, "reason": "BUSINESS_DECISION_REQUIRED : durée légale de conservation du journal d'audit non décidée"}
        if apply:
            c.execute(text("""INSERT INTO audit_events(school_id, actor_user_id, action, entity_type, entity_id, source, result, new_json)
                VALUES (NULL, NULL, 'RETENTION_PURGE_APPLIED', 'Retention', NULL, 'SYSTEM', 'SUCCESS', CAST(:d AS jsonb))"""),
                      {"d": json.dumps({r["table"]: r["deleted"] for r in report["rules"]})})
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Purge des données périmées (comptage par défaut)")
    ap.add_argument("--apply", action="store_true", help="supprimer réellement (sinon : comptage seul)")
    ap.add_argument("--audit-years", type=int, default=5, help="volume du journal d'audit plus ancien (affiché, jamais purgé)")
    a = ap.parse_args(argv)
    url = os.environ.get("EDUSYNC_OWNER_DATABASE_URL")
    if not url:
        print("EDUSYNC_OWNER_DATABASE_URL requis (identifiants propriétaire)", file=sys.stderr)
        return 2
    report = run(url, a.apply, a.audit_years)
    print(("PURGE APPLIQUÉE" if a.apply else "COMPTAGE SEUL (aucune suppression ; --apply pour purger)"))
    for r in report["rules"]:
        print(f"  {r['label']:<48} éligibles {r['eligible']:>8}   supprimés {r['deleted']:>8}")
    au = report["audit_older_than_years"]
    print(f"  Journal d'audit > {au['years']} ans : {au['rows']} ligne(s) — non purgé ({au['reason']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
