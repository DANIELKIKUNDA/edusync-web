"""Send the weekly / monthly report to the school's responsibles by e-mail, PDF attached (owner, 2026-11-19).

Recipients are chosen by their RIGHTS, never by name: every active member who reads the recovery AND either supervises
the cash desks (promoteur, gestionnaire, chargé financier, assistant…) or produces the periodic reports (préfet,
directeur de section…). Each one receives HIS report, rebuilt with his own rights: the whole school (money part only
if he supervises the desks) or his section. Weekly reports go only to the whole-school responsibles. One message per
person and period (idempotent): sending twice the same week never sends twice.
"""
from __future__ import annotations

from datetime import date
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import text

READ = "finance.recovery.monthly.read"
LEADERS = ("finance.cash.other.read", "finance.reports.periodic.generate")


def recipients(conn, school_id) -> list[dict]:
    rows = conn.execute(text("""SELECT DISTINCT m.id AS membership_id, m.user_id
          FROM school_memberships m
          JOIN rbac_assignments a ON a.membership_id=m.id AND a.school_id=m.school_id AND a.active
               AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now())
          JOIN rbac_role_capabilities rc ON rc.role_id=a.role_id
         WHERE m.school_id=:s AND m.active AND rc.capability_code=:read"""), {"s": str(school_id), "read": READ}).mappings().all()
    return [dict(r) for r in rows]


def actor_of(conn, school_id, member: dict):
    """The recipient's own rights, re-evaluated now (same rule as the signed document links)."""
    from edusync.adapters.postgres_authorization import PostgresAuthorizationRepository
    from edusync.adapters.postgres_repositories import PostgresMembershipRepository
    from edusync.shared.application.context import ActorContext
    permissions = PostgresMembershipRepository(conn).permissions(member["membership_id"])
    grants = PostgresAuthorizationRepository(conn).effective_capability_grants(UUID(str(member["user_id"])), UUID(str(school_id)))
    return ActorContext(user_id=UUID(str(member["user_id"])), school_id=UUID(str(school_id)), membership_id=member["membership_id"],
                        permissions=permissions, capability_scopes=grants)


def letter_text(greeting: str, paragraphs: list[tuple[str, str]], signature: str) -> str:
    lines = [greeting, ""]
    for heading, body in paragraphs:
        lines += [f"{heading} : {body}" if heading else body, ""]
    lines += ["Vous trouverez le rapport complet en pièce jointe.", "", signature]
    return "\n".join(lines)


def send_digest(services, sender, *, kind: str, as_of: date | None, currency: str, load) -> dict:
    """`load(actor, services, kind, as_of, currency)` builds (year, digest, greeting, classes) for one reader."""
    from edusync.modules.alerts.application.school_alerts import _identities
    from edusync.modules.communications.application.messaging import Recipient, request_message
    from edusync.modules.finance_recovery.application.digest_document import digest_pdf
    from edusync.modules.finance_recovery.domain.digest import paragraphs, title
    with services.tenant_db.tenant_transaction(school_id=sender.school_id, user_id=sender.user_id) as conn:
        people = []
        for m in recipients(conn, sender.school_id):
            a = actor_of(conn, sender.school_id, m)
            if READ not in a.permissions or not any(c in a.permissions for c in LEADERS):
                continue                                           # e.g. a cashier: reads the recovery, not a leader
            whole = any(t == "SCHOOL" for t, _ in a.scopes_for(READ))
            if kind == "WEEK" and not whole:
                continue                                           # the weekly letter is for the whole-school leaders
            people.append(a)
    ids = _identities(services, [a.user_id for a in people])
    sent, already, skipped = [], [], []
    for a in people:
        email, name = ids.get(str(a.user_id), (None, None))
        if not email:
            skipped.append(name or str(a.user_id)); continue
        _, d, hello, classes = load(a, services, kind, as_of, currency)
        signature = f"EduSync — pour {d.school_name}"
        pdf = digest_pdf(digest=d, greeting=hello, classes=classes, signature=signature)
        file_name = f"rapport_{'semaine' if kind == 'WEEK' else 'mois'}_{d.start.isoformat()}.pdf"
        with services.tenant_db.tenant_transaction(school_id=sender.school_id, user_id=sender.user_id) as conn:
            res = request_message(conn, school_id=sender.school_id, kind="REPORT", channels=["EMAIL", "PUSH"], subject=title(d)[:120],
                            body=letter_text(hello, paragraphs(d), signature)[:2000], link_path="/finance",
                            idempotency_key=f"digest:{kind}:{d.start.isoformat()}:{a.user_id}"[:180], created_by=sender.user_id,
                            recipients=[Recipient("USER", uuid5(NAMESPACE_URL, f"{a.user_id}:{sender.school_id}"), name, email=email, user_id=a.user_id)],
                            attachments=[(file_name, "application/pdf", pdf)])
        (already if res.get("replayed") else sent).append(name or email)
    return {"sent": sent, "already_sent": already, "without_email": skipped}

