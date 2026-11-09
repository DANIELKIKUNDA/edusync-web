"""Vigie EduSync — deterministic school supervision.

The engine measures facts, opens one durable incident per fingerprint, resolves it when the condition disappears,
and routes notifications by capability + RBAC scope. Role names are deliberately absent: a custom/delegated role
inherits the alerts as soon as it receives the corresponding capability.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text

from edusync.modules.alerts.application.school_alerts import capability_alert

log = logging.getLogger("edusync.supervision")
LOCK_KEY = 7_202_611_009
_started = False


@dataclass(frozen=True)
class Finding:
    rule: str
    fingerprint: str
    domain: str
    severity: str
    title: str
    summary: str
    explanation: str
    recommendation: str
    capability: str
    target: str
    metric: dict
    scope_type: str | None = None
    scope_value: str | None = None


def measure(conn, school_id: UUID) -> list[Finding]:
    findings: list[Finding] = []
    # A class is unusual when at least 3 pupils and 35% of its validated enrolments have >=2 overdue monthly charges.
    rows = conn.execute(text("""
      WITH enrolled AS (
        SELECT e.class_id, count(*)::int total
          FROM enrollments e WHERE e.school_id=:s AND e.status='VALIDATED' GROUP BY e.class_id
      ), late AS (
        SELECT e.class_id, fc.enrollment_id
          FROM finance_charges fc JOIN enrollments e ON e.id=fc.enrollment_id
         WHERE fc.school_id=:s AND e.status='VALIDATED' AND fc.status='ACTIVE'
           AND fc.periodicity='MONTHLY' AND fc.due_date<CURRENT_DATE AND fc.net_amount>fc.paid_amount
         GROUP BY e.class_id, fc.enrollment_id HAVING count(*)>=2
      )
      SELECT c.id, c.label, sec.code section_code, en.total, count(l.enrollment_id)::int late,
             round(100.0*count(l.enrollment_id)/greatest(en.total,1),1) rate
        FROM enrolled en JOIN school_classes c ON c.id=en.class_id
        LEFT JOIN school_sections sec ON sec.id=c.section_id LEFT JOIN late l ON l.class_id=en.class_id
       GROUP BY c.id,c.label,sec.code,en.total
      HAVING count(l.enrollment_id)>=3 AND 100.0*count(l.enrollment_id)/greatest(en.total,1)>=35
    """), {"s": str(school_id)}).mappings()
    for r in rows:
        findings.append(Finding("FINANCE_CLASS_INSOLVENCY", str(r["id"]), "FINANCE",
            "CRITICAL" if float(r["rate"]) >= 60 else "WARNING", f"Risque financier élevé — {r['label']}",
            f"{r['late']} élève(s) sur {r['total']} ont au moins deux mensualités impayées ({r['rate']} %).",
            "La proportion dépasse le seuil de surveillance de 35 % et concerne au moins trois élèves.",
            "Ouvrez le recouvrement de cette classe, vérifiez les causes et assignez une action de relance.",
            "finance.recovery.monthly.read", f"/finance?view=recovery&class={r['id']}",
            {"late": r["late"], "total": r["total"], "rate": str(r["rate"])}, "SECTION", r["section_code"]))

    rows = conn.execute(text("""SELECT cs.id,cs.opened_at,m.user_id,coalesce(nullif(trim(u.full_name),''),'Caissier') cashier
      FROM finance_cash_sessions cs JOIN school_memberships m ON m.id=cs.membership_id
      LEFT JOIN users u ON u.id=m.user_id
      WHERE cs.school_id=:s AND cs.status='OPEN' AND cs.opened_at < date_trunc('day',now())"""), {"s": str(school_id)}).mappings()
    for r in rows:
        hours = max(1, int((datetime.now(timezone.utc) - r["opened_at"]).total_seconds() // 3600))
        findings.append(Finding("CASH_SESSION_NOT_CLOSED", str(r["id"]), "CASH", "CRITICAL",
            "Caisse non clôturée", f"La caisse de {r['cashier']} est ouverte depuis {hours} heure(s).",
            "Une caisse d'une journée antérieure est toujours ouverte et compromet le contrôle quotidien.",
            "Demandez la clôture et vérifiez le journal avant toute réouverture.", "finance.cash.other.read",
            f"/finance?view=cash&session={r['id']}", {"hours_open": hours, "cashier": r["cashier"]}))

    row = conn.execute(text("""SELECT count(*)::int n FROM enrollments e WHERE e.school_id=:s AND e.status='VALIDATED'
      AND NOT EXISTS (SELECT 1 FROM finance_charges fc WHERE fc.school_id=e.school_id AND fc.enrollment_id=e.id AND fc.status='ACTIVE')"""),
      {"s": str(school_id)}).mappings().one()
    if row["n"]:
        findings.append(Finding("ENROLLMENTS_WITHOUT_CHARGES", "school", "CONFIGURATION", "CRITICAL",
            "Obligations financières manquantes", f"{row['n']} inscription(s) validée(s) n'ont aucune obligation financière active.",
            "Ces élèves peuvent apparaître comme en ordre alors qu'aucun frais n'a été généré.",
            "Vérifiez les barèmes et régénérez les obligations avant les prochains encaissements.",
            "settings.tariffs.read", "/settings?view=tariffs", {"enrollments": row["n"]}))

    # Operational backlogs are aggregated: the Vigie opens one actionable incident instead of flooding managers.
    row = conn.execute(text("""SELECT count(*)::int n, min(created_at) oldest
      FROM enrollment_dossiers WHERE school_id=:s AND status='PENDING' AND created_at < now()-interval '48 hours'"""),
      {"s": str(school_id)}).mappings().one()
    if row["n"]:
        age = max(2, (datetime.now(timezone.utc) - row["oldest"]).days)
        findings.append(Finding("STALE_ENROLLMENT_DOSSIERS", "school", "SCHOOLING",
            "CRITICAL" if age >= 7 else "WARNING", "Dossiers d'inscription en attente",
            f"{row['n']} dossier(s) attendent depuis plus de 48 heures ; le plus ancien a {age} jour(s).",
            "Un dossier non finalisé peut cacher un paiement attendu, une pièce manquante ou une famille sans réponse.",
            "Ouvrez les dossiers, attribuez chaque blocage et clôturez ou relancez les familles concernées.",
            "students.read", "/enrollments?view=pending", {"pending": row["n"], "oldest_days": age}))

    row = conn.execute(text("""SELECT count(*)::int n,
        count(*) FILTER (WHERE status='FAILED')::int failed,
        min(queued_at) FILTER (WHERE status='PENDING') oldest
      FROM finance_receipt_print_jobs WHERE school_id=:s AND
        (status='FAILED' OR (status='PENDING' AND queued_at < now()-interval '24 hours'))"""),
      {"s": str(school_id)}).mappings().one()
    if row["n"]:
        findings.append(Finding("RECEIPT_PRINT_BACKLOG", "school", "FINANCE", "WARNING",
            "Reçus à imprimer ou en échec", f"{row['n']} reçu(s) demandent une intervention, dont {row['failed']} en échec.",
            "La preuve papier d'un encaissement n'est pas confirmée tant que le travail d'impression reste en attente ou en échec.",
            "Relancez l'impression, vérifiez l'imprimante puis confirmez la remise des reçus.",
            "finance.receipts.read", "/finance?view=receipts", {"backlog": row["n"], "failed": row["failed"]}))

    row = conn.execute(text("""SELECT count(*)::int n, coalesce(sum(attempts),0)::int attempts
      FROM communication_deliveries WHERE school_id=:s AND status='FAILED' AND failed_at >= now()-interval '24 hours'"""),
      {"s": str(school_id)}).mappings().one()
    if row["n"] >= 3:
        findings.append(Finding("COMMUNICATION_DELIVERY_FAILURES", "school", "TECHNICAL", "CRITICAL",
            "Messages non remis", f"{row['n']} envoi(s) ont échoué pendant les dernières 24 heures.",
            "Plusieurs échecs rapprochés indiquent un problème de fournisseur, de crédit ou de coordonnées destinataires.",
            "Vérifiez le fournisseur, le solde et les erreurs, puis relancez uniquement les envois corrigés.",
            "communications.read", "/communications?view=deliveries", {"failed": row["n"], "attempts": row["attempts"]}))

    row = conn.execute(text("""SELECT count(*)::int n FROM sync_inbox
      WHERE school_id=:s AND status IN ('CONFLICT','REJECTED') AND received_at >= now()-interval '7 days'"""),
      {"s": str(school_id)}).mappings().one()
    if row["n"] >= 3:
        findings.append(Finding("SYNC_CONFLICT_BACKLOG", "school", "TECHNICAL", "CRITICAL",
            "Conflits de synchronisation à traiter", f"{row['n']} opération(s) hors ligne ont été rejetées ou mises en conflit cette semaine.",
            "Ces opérations ne sont pas silencieusement perdues, mais leur résultat métier doit être arbitré.",
            "Ouvrez les conflits, comparez les versions et réconciliez prioritairement les opérations financières.",
            "sync.conflicts.read", "/settings?view=sync-conflicts", {"conflicts": row["n"]}))

    row = conn.execute(text("""SELECT count(*)::int n, coalesce(sum(amount),0) amount
      FROM finance_payment_reversals WHERE school_id=:s AND performed_at >= now()-interval '24 hours'"""),
      {"s": str(school_id)}).mappings().one()
    if row["n"] >= 3:
        findings.append(Finding("PAYMENT_REVERSAL_SPIKE", "school", "FINANCE", "CRITICAL",
            "Volume inhabituel d'annulations", f"{row['n']} annulation(s) ou remboursement(s) ont été enregistrés en 24 heures.",
            "Une concentration d'annulations peut être légitime, mais elle exige une revue du journal et des motifs.",
            "Contrôlez les auteurs, les motifs et les pièces justificatives avant la clôture de caisse.",
            "audit.school.read", "/finance?view=audit", {"reversals": row["n"], "amount": str(row["amount"])}))
    return findings


def evaluate_school(conn, school_id: UUID, *, services=None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    findings = measure(conn, school_id)
    keys = {(f.rule, f.fingerprint) for f in findings}
    opened = notified = resolved = 0
    existing = {(r["rule_code"], r["fingerprint"]): dict(r) for r in conn.execute(text(
        "SELECT * FROM supervision_incidents WHERE school_id=:s AND condition_status='OPEN' FOR UPDATE"), {"s": str(school_id)}).mappings()}
    for f in findings:
        old = existing.get((f.rule, f.fingerprint))
        if old:
            conn.execute(text("""UPDATE supervision_incidents SET last_seen_at=:now,severity=:sev,title=:title,summary=:summary,
              explanation=:ex,recommendation=:rec,metric_json=CAST(:metric AS jsonb),target_path=:target WHERE id=:id"""),
              {"now": now, "sev": f.severity, "title": f.title, "summary": f.summary, "ex": f.explanation,
               "rec": f.recommendation, "metric": __import__('json').dumps(f.metric), "target": f.target, "id": old["id"]})
            # Unacknowledged incidents escalate after 48 h and remind every 12 h; owned work remains on a daily cadence.
            unowned = old["response_status"] == "NEW"
            overdue = unowned and (now-old["opened_at"]).total_seconds() >= 172800
            reminder_delay = 43200 if overdue else 86400
            should_notify = old["last_notified_at"] is None or (now-old["last_notified_at"]).total_seconds() >= reminder_delay
            if overdue and f.severity != "CRITICAL":
                conn.execute(text("UPDATE supervision_incidents SET severity='CRITICAL' WHERE id=:id"), {"id": old["id"]})
            incident_id = old["id"]
        else:
            incident_id = conn.execute(text("""INSERT INTO supervision_incidents(school_id,rule_code,fingerprint,domain,severity,title,summary,
              explanation,recommendation,metric_json,target_path,required_capability,scope_type,scope_value,opened_at,last_seen_at)
              VALUES(:s,:rule,:fp,:domain,:sev,:title,:summary,:ex,:rec,CAST(:metric AS jsonb),:target,:cap,:st,:sv,:now,:now) RETURNING id"""),
              {"s": str(school_id), "rule": f.rule, "fp": f.fingerprint, "domain": f.domain, "sev": f.severity,
               "title": f.title, "summary": f.summary, "ex": f.explanation, "rec": f.recommendation,
               "metric": __import__('json').dumps(f.metric), "target": f.target, "cap": f.capability,
               "st": f.scope_type, "sv": f.scope_value, "now": now}).scalar_one()
            opened += 1; should_notify = True
        if should_notify:
            count = capability_alert(conn, services=services, school_id=school_id, required_capability=f.capability,
                title=f.title, body=f"{f.summary}\n{f.recommendation}", link_path=f.target, severity=f.severity,
                scope_type=f.scope_type, scope_value=f.scope_value, dedupe_key=f"vigie:{incident_id}:{now.date()}")
            conn.execute(text("UPDATE supervision_incidents SET last_notified_at=:now,reminder_count=reminder_count+1 WHERE id=:id"),
                         {"now": now, "id": incident_id})
            notified += count
    for key, old in existing.items():
        if key not in keys:
            conn.execute(text("""UPDATE supervision_incidents SET condition_status='RESOLVED',resolved_at=:now,
              response_status=CASE WHEN response_status='NEW' THEN 'CLOSED' ELSE response_status END,
              closed_at=CASE WHEN response_status='NEW' THEN :now ELSE closed_at END WHERE id=:id"""), {"now": now, "id": old["id"]})
            resolved += 1
    return {"findings": len(findings), "opened": opened, "notified": notified, "resolved": resolved}


def evaluate_all(services) -> dict:
    # Session-level advisory lock stays held for the complete cross-school pass; multiple API replicas cannot race.
    with services.platform_db.engine.connect() as pc:
        if not pc.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar():
            return {"skipped": True, "schools": 0}
        try:
            schools = [r[0] for r in pc.execute(text("SELECT id FROM schools WHERE status='ACTIVE' ORDER BY id"))]
            out = {"skipped": False, "schools": 0, "opened": 0, "notified": 0, "resolved": 0}
            for sid in schools:
                try:
                    with services.tenant_db.tenant_transaction(school_id=sid) as conn:
                        r = evaluate_school(conn, sid, services=services)
                    out["schools"] += 1
                    for k in ("opened", "notified", "resolved"): out[k] += r[k]
                except Exception:
                    log.exception("Vigie evaluation failed school=%s", sid)
            return out
        finally:
            pc.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})


def start_supervision_loop(services) -> None:
    global _started
    if _started or not services.settings.supervision_enabled: return
    _started = True
    def loop():
        time.sleep(30)
        while True:
            try: evaluate_all(services)
            except Exception: log.exception("Vigie evaluation failed")
            time.sleep(max(300, services.settings.supervision_interval_seconds))
    threading.Thread(target=loop, name="edusync-vigie", daemon=True).start()
