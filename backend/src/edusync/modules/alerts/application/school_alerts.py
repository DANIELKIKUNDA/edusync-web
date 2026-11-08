"""Automatic alerts between the school's roles (owner request 2026-11-08).

« Le système doit alerter chaque fois sur des anomalies… des messages venant de la caisse… pour permettre des suivis. »

A business operation (cash closed, receipt cancelled, pupil abandoning, waiver requested…) calls ``school_alert``
inside its own transaction. The alert:
* reaches every active member whose role holds the audience capability (section-scoped roles only get the alerts of
  their section), never the person who caused it;
* is written to their in-app inbox (the bell), and queued for push (and e-mail when asked) through the existing
  communications outbox — the NotificationPolicy then decides per device / address / school settings;
* is idempotent (same dedupe key → nothing new) and runs in a SAVEPOINT: an alert problem never blocks the operation.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import text

log = logging.getLogger("edusync.alerts")

# Audience → capabilities (standard roles, CAPABILITY_REGISTRY):
#   FINANCE   gestionnaire, promoteur, responsable financier          (finance.cash.other.read)
#   ACADEMIC  préfet des études, direction de section, directeur des études, gestionnaire, promoteur (headcounts.by_option.read)
#   DECISIONS ceux qui accordent dérogations et réductions             (finance.decisions.create)
AUDIENCES: dict[str, tuple[str, ...]] = {
    "FINANCE": ("finance.cash.other.read",),
    "ACADEMIC": ("headcounts.by_option.read",),
    "DECISIONS": ("finance.decisions.create",),
}
SEVERITIES = ("INFO", "WARNING", "CRITICAL")


def money_text(amount, currency: str) -> str:
    v = Decimal(str(amount or 0)).quantize(Decimal("0.01"))
    s = f"{v:,.2f}".replace(",", " ").replace(".", ",")
    s = s[:-3] if s.endswith(",00") else s
    return f"{s} {'FC' if currency == 'CDF' else currency}"


def recipients(conn, school_id: UUID, audience: str, *, section_code: str | None = None, exclude: tuple = ()) -> list[dict]:
    caps = list(AUDIENCES[audience])
    rows = conn.execute(text("""
        SELECT DISTINCT a.user_id
          FROM rbac_assignments a
          JOIN rbac_role_capabilities rc ON rc.role_id=a.role_id AND rc.capability_code = ANY(CAST(:caps AS text[]))
          JOIN school_memberships m ON m.id=a.membership_id AND m.school_id=a.school_id AND m.active
         WHERE a.school_id=:s AND a.active AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now())
           AND (CAST(:sec AS text) IS NULL
                OR NOT EXISTS (SELECT 1 FROM rbac_assignment_scopes x WHERE x.assignment_id=a.id AND x.scope_type='SECTION')
                OR EXISTS (SELECT 1 FROM rbac_assignment_scopes x WHERE x.assignment_id=a.id AND x.scope_type='SECTION' AND upper(x.scope_value)=upper(:sec)))
    """), {"caps": caps, "s": str(school_id), "sec": section_code}).mappings().all()
    # users is readable by the tenant role only for the caller's own row: names / addresses come from the platform role.
    skip = {str(x) for x in exclude if x}
    return [{"user_id": r["user_id"], "email": None, "name": None} for r in rows if str(r["user_id"]) not in skip]


def _identities(services, user_ids: list) -> dict[str, tuple[str | None, str | None]]:
    if services is None or not user_ids:
        return {}
    try:
        with services.platform_db.platform_transaction() as pc:
            return {str(r[0]): (r[1], r[2]) for r in pc.execute(text("""SELECT id, email, nullif(trim(full_name),'') FROM users
                WHERE id = ANY(CAST(:ids AS uuid[])) AND active"""), {"ids": [str(u) for u in user_ids]}).all()}
    except Exception:
        log.exception("alert recipients: identities unavailable")
        return {}


def school_alert(conn, *, school_id: UUID, audience: str, title: str, body: str, dedupe_key: str, link_path: str | None = None,
                 severity: str = "INFO", section_code: str | None = None, exclude_user_ids: tuple = (), email: bool = False,
                 created_by: UUID | None = None, services=None) -> int:
    """Writes the alert for its audience; returns the number of people alerted (0 on any problem, never raises)."""
    if audience not in AUDIENCES or severity not in SEVERITIES:
        raise ValueError("Alerte inconnue")
    category = f"ALERT_{audience}"
    try:
        with conn.begin_nested():
            people = recipients(conn, school_id, audience, section_code=section_code, exclude=exclude_user_ids)
            if not people:
                return 0
            fresh = []
            for p in people:
                done = conn.execute(text("""SELECT 1 FROM notifications WHERE school_id=:s AND user_id=:u AND category=:c AND title=:t AND body=:b
                    AND created_at > now() - interval '1 day' LIMIT 1"""), {"s": str(school_id), "u": str(p["user_id"]), "c": category, "t": title[:180], "b": body[:2000]}).first()
                if done:
                    continue
                conn.execute(text("""INSERT INTO notifications(school_id,user_id,category,severity,title,body,link_path)
                    VALUES(:s,:u,:c,:sev,:t,:b,:l)"""), {"s": str(school_id), "u": str(p["user_id"]), "c": category, "sev": severity,
                                                         "t": title[:180], "b": body[:2000], "l": link_path})
                fresh.append(p)
            if fresh:
                ids = _identities(services, [p["user_id"] for p in fresh]) if email else {}
                for p in fresh:
                    p["email"], p["name"] = ids.get(str(p["user_id"]), (None, None))
                from edusync.modules.communications.application.messaging import Recipient, request_message
                request_message(conn, school_id=school_id, kind="ALERT", channels=["PUSH", "EMAIL"] if email else ["PUSH"],
                                subject=title[:120], body=body[:240] if not email else body[:2000], link_path=link_path,
                                idempotency_key=f"alert:{dedupe_key}"[:180], created_by=created_by,
                                recipients=[Recipient("USER", uuid5(NAMESPACE_URL, f"{p['user_id']}:{school_id}"), p["name"] or None,
                                                      email=p["email"] if email else None, user_id=p["user_id"]) for p in fresh])
            return len(fresh)
    except Exception:  # an alert never blocks the business operation that raised it
        log.exception("school alert skipped (%s, %s)", audience, dedupe_key)
        return 0


# ------------------------------------------------------------------------------------------- ready-made alerts
def cash_session_closed(conn, *, services=None, school_id: UUID, session: dict, cashier_name: str, actor_user_id: UUID) -> int:
    lines, variance = [], []
    for cur, key in (("CDF", "cdf"), ("USD", "usd")):
        part = session.get(key) or {}
        if Decimal(str(part.get("receipts") or 0)) or Decimal(str(part.get("expenses") or 0)):
            lines.append(f"{money_text(part.get('receipts'), cur)} encaissés")
        v = part.get("variance")
        if v is not None and Decimal(str(v)) != 0:
            variance.append(f"{'manque' if Decimal(str(v)) < 0 else 'excédent'} de {money_text(abs(Decimal(str(v))), cur)}")
    n = conn.execute(text("SELECT count(*) FROM finance_payments WHERE school_id=:s AND cash_session_id=:cs"),
                     {"s": str(school_id), "cs": str(session["id"])}).scalar_one()
    body = f"{cashier_name} a clôturé sa caisse : {', '.join(lines) or 'aucun encaissement'} · {n} reçu{'s' if n > 1 else ''}."
    if variance:
        body += f" Écart au comptage : {', '.join(variance)}."
    return school_alert(conn, school_id=school_id, audience="FINANCE", severity="WARNING" if variance else "INFO",
                        title=("Écart à la clôture de caisse" if variance else "Caisse clôturée"), body=body, link_path="/finance",
                        dedupe_key=f"cash-close:{session['id']}", exclude_user_ids=(actor_user_id,), email=bool(variance), created_by=actor_user_id, services=services)


def cash_day_closed(conn, *, services=None, school_id: UUID, report: dict, actor_user_id: UUID) -> int:
    # day_report totals: [{currency, entries, outflows, net}]
    parts = [f"{money_text(t['entries'], t['currency'])} encaissés (net {money_text(t['net'], t['currency'])})"
             for t in (report.get("totals") or []) if Decimal(str(t.get("entries") or 0))]
    arrears = conn.execute(text("""SELECT count(*) FROM (SELECT fc.enrollment_id FROM finance_charges fc JOIN enrollments e ON e.id=fc.enrollment_id
        WHERE fc.school_id=:s AND fc.status='ACTIVE' AND fc.periodicity='MONTHLY' AND fc.due_date < CURRENT_DATE AND fc.net_amount > fc.paid_amount
          AND e.status='VALIDATED' GROUP BY fc.enrollment_id HAVING count(*) >= 3) x"""), {"s": str(school_id)}).scalar_one()
    body = f"Journée de caisse du {report.get('day')} clôturée : {', '.join(parts) or 'aucun encaissement'}."
    if arrears:
        body += f" {arrears} élève{'s ont' if arrears > 1 else ' a'} au moins 3 mois de retard de paiement (voir Recouvrement)."
    return school_alert(conn, school_id=school_id, audience="FINANCE", title="Journée de caisse clôturée", body=body, link_path="/finance",
                        dedupe_key=f"cash-day:{school_id}:{report.get('day')}", exclude_user_ids=(actor_user_id,), email=True, created_by=actor_user_id, services=services)


def payment_reversed(conn, *, services=None, school_id: UUID, receipt: str | None, amount, currency: str, kind: str, reason: str,
                     actor_name: str, actor_user_id: UUID, reversal_id) -> int:
    label = "annulé" if kind == "ANNULATION" else "remboursé"
    body = f"Reçu {receipt or '—'} ({money_text(amount, currency)}) {label} par {actor_name}. Motif : {reason}"
    return school_alert(conn, school_id=school_id, audience="FINANCE", severity="WARNING", title=f"Reçu {label}", body=body,
                        link_path="/finance", dedupe_key=f"reversal:{reversal_id}", exclude_user_ids=(actor_user_id,), email=True,
                        created_by=actor_user_id, services=services)


def student_left(conn, *, services=None, school_id: UUID, student_id: UUID, event: str, reason: str | None, actor_user_id: UUID) -> int:
    s = conn.execute(text("""SELECT trim(concat_ws(' ',s.last_name,s.middle_name,s.first_name)) AS name, c.label AS class_label, sec.code AS section
          FROM students s LEFT JOIN enrollments e ON e.student_id=s.id AND e.school_id=s.school_id
          LEFT JOIN academic_years y ON y.id=e.academic_year_id AND y.status='ACTIVE'
          LEFT JOIN school_classes c ON c.id=e.class_id LEFT JOIN school_sections sec ON sec.id=c.section_id
         WHERE s.school_id=:s AND s.id=:id ORDER BY (y.id IS NULL), e.created_at DESC LIMIT 1"""), {"s": str(school_id), "id": str(student_id)}).mappings().first()
    if not s:
        return 0
    word = {"ABANDON": "Abandon", "TRANSFER": "Transfert vers une autre école", "SUSPEND": "Suspension"}.get(event)
    if not word:
        return 0
    body = f"{word} : {s['name']}{f' ({s['class_label']})' if s['class_label'] else ''}.{f' Motif : {reason}' if reason else ''}"
    return school_alert(conn, school_id=school_id, audience="ACADEMIC", severity="WARNING" if event == "ABANDON" else "INFO",
                        title=word, body=body, link_path="/students", section_code=s["section"], dedupe_key=f"student-{event}:{student_id}:{reason or ''}"[:160],
                        exclude_user_ids=(actor_user_id,), created_by=actor_user_id)


def waiver_requested(conn, *, services=None, school_id: UUID, dossier_label: str, child_names: list[str], dossier_id, actor_user_id: UUID) -> int:
    body = f"Dérogation aux conditions d’inscription demandée pour {', '.join(child_names)} ({dossier_label}). À accorder ou refuser dans Élèves → dossiers en attente."
    return school_alert(conn, school_id=school_id, audience="DECISIONS", severity="WARNING", title="Dérogation demandée", body=body,
                        link_path="/students", dedupe_key=f"waiver-request:{dossier_id}", exclude_user_ids=(actor_user_id,), created_by=actor_user_id)
