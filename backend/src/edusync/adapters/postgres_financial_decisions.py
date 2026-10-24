"""N3-C — financial decisions copied from the Desktop golden master (app/db/financial_decisions.py).

  * create_financial_decision: scope ALL_FEES / FEE_CODE / FEE_CATEGORY / CHARGE (target required except ALL_FEES), nature
    DISCOUNT / EXEMPTION / INDIVIDUAL_FREE / COLLECTIVE_EXEMPTION / DIRECTION_EXCEPTION / THIRD_PARTY_COVERAGE, value PERCENT
    (0..100) or FIXED (>= 0), exemptions forced to 100 %, reason required, priority, cumulative, effective dates; the
    enrollment's decisions are recalculated at once.
  * cancel_financial_decision: active decision only, reason required, recalculation.
  * recalculate_enrollment_financial_decisions: per charge, in priority order, each matching decision reduces the
    current amount (PERCENT of the current amount, FIXED capped by it); a non-cumulative decision stops the
    non-cumulative ones after it; applications are rebuilt (financial_decision_applications).
  * charge_financial_explanation, student_financial_operator_view, financial_operator_follow_up, set_charge_responsibility.
Web mapping: the charge net (after the benefit discount, L3) is the base and is never rewritten; what remains payable is
net minus the applications (finance_charge_decision_amount). A FIXED decision carries a currency and applies only to the
charges of that currency (CDF and USD are never converted). The credit a decision creates when more was already settled than
the new net is a « fonds anticipé » of origin DECISION_CREDIT (N3-D, postgres_advance_funds.py).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

CENT = Decimal("0.01")
SCOPES = {"ALL_FEES", "FEE_CODE", "FEE_CATEGORY", "CHARGE"}
KINDS = {"DISCOUNT", "EXEMPTION", "INDIVIDUAL_FREE", "COLLECTIVE_EXEMPTION", "DIRECTION_EXCEPTION", "THIRD_PARTY_COVERAGE"}
FULL = {"EXEMPTION", "INDIVIDUAL_FREE", "COLLECTIVE_EXEMPTION"}
RESPONSIBILITIES = {"FAMILY_CASH", "PAYROLL_DEDUCTION", "THIRD_PARTY"}


def money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


class PostgresFinancialDecisionsRepository:
    def __init__(self, connection: Connection):
        self.c = connection

    # ---------- decisions ----------
    def create_decision(self, school_id: UUID, *, user_id: UUID, enrollment_id: UUID, decision_kind: str, scope_type: str = "ALL_FEES",
                        scope_ref: str | None = None, value_type: str = "PERCENT", value_amount: Decimal = Decimal("0"), currency: str = "CDF",
                        priority: int = 100, cumulative: bool = True, period_start: date | None = None, period_end: date | None = None,
                        effective_from: date | None = None, effective_to: date | None = None, reason: str = "",
                        reference: str | None = None) -> dict[str, Any]:
        scope_type = (scope_type or "").strip().upper(); decision_kind = (decision_kind or "").strip().upper()
        value_type = (value_type or "").strip().upper(); reason = (reason or "").strip()
        if scope_type not in SCOPES or decision_kind not in KINDS:
            raise ValueError("Portée ou nature de décision financière invalide")
        if value_type not in ("PERCENT", "FIXED"):
            raise ValueError("La valeur doit être un pourcentage ou un montant fixe")
        amount = money(value_amount)
        if amount < 0 or (value_type == "PERCENT" and amount > 100):
            raise ValueError("Valeur de décision financière invalide")
        if decision_kind in FULL:
            value_type, amount = "PERCENT", Decimal("100.00")
        if not reason:
            raise ValueError("Le motif de la décision financière est obligatoire")
        if currency not in ("CDF", "USD"):
            raise ValueError("Devise invalide")
        enr = self.c.execute(text("SELECT id FROM enrollments WHERE id=:e AND school_id=:s"), {"e": enrollment_id, "s": school_id}).first()
        if enr is None:
            raise ValueError("Inscription annuelle introuvable pour cette décision")
        ref = (scope_ref or "").strip() or None
        if scope_type in ("FEE_CODE", "FEE_CATEGORY", "CHARGE") and not ref:
            raise ValueError("La cible de la décision financière est obligatoire")
        charge_id = None
        if scope_type == "CHARGE":
            ch = self.c.execute(text("SELECT id, currency FROM finance_charges WHERE id=CAST(:c AS uuid) AND enrollment_id=:e AND school_id=:s"),
                                {"c": ref, "e": enrollment_id, "s": school_id}).mappings().first()
            if ch is None:
                raise ValueError("Ce frais n'appartient pas à cette inscription")
            charge_id = ch["id"]
        if scope_type == "FEE_CODE":
            ref = ref.upper()
        row = self.c.execute(text("""INSERT INTO finance_decisions(school_id,enrollment_id,charge_id,decision_type,currency,amount,reason,effective_date,created_by,
                scope_type,scope_ref,period_start,period_end,value_type,value_amount,priority,cumulative,effective_to,reference,model)
            VALUES(:s,:e,:ch,:k,:cur,:a,:r,COALESCE(:ef,CURRENT_DATE),:u,:st,:sr,:ps,:pe,:vt,:va,:p,:cu,:et,:ref,'DESKTOP') RETURNING *"""),
            {"s": school_id, "e": enrollment_id, "ch": charge_id, "k": decision_kind, "cur": currency, "a": amount, "r": reason, "ef": effective_from,
             "u": user_id, "st": scope_type, "sr": ref, "ps": period_start, "pe": period_end, "vt": value_type, "va": amount, "p": int(priority),
             "cu": bool(cumulative), "et": effective_to, "ref": (reference or "").strip() or None}).mappings().one()
        self.recalculate(school_id, enrollment_id)
        return dict(row)

    def cancel_decision(self, school_id: UUID, decision_id: UUID, *, user_id: UUID, reason: str) -> dict[str, Any]:
        reason = (reason or "").strip()
        d = self.c.execute(text("SELECT * FROM finance_decisions WHERE id=:id AND school_id=:s FOR UPDATE"), {"id": decision_id, "s": school_id}).mappings().first()
        if not d or d["status"] != "ACTIVE":
            raise ValueError("Décision financière active introuvable")
        if not reason:
            raise ValueError("Le motif d'annulation est obligatoire")
        from edusync.adapters.postgres_advance_funds import PostgresAdvanceFundsRepository
        PostgresAdvanceFundsRepository(self.c).close_decision_credits(school_id, decision_id, user_id=user_id, reason=reason)   # Desktop: refused if used
        row = self.c.execute(text("""UPDATE finance_decisions SET status='CANCELLED',cancelled_by=:u,cancelled_at=now(),cancel_reason=:r
            WHERE id=:id RETURNING *"""), {"u": user_id, "r": reason, "id": decision_id}).mappings().one()
        self.recalculate(school_id, d["enrollment_id"])
        return dict(row)

    def _charges(self, school_id: UUID, enrollment_id: UUID) -> list[dict[str, Any]]:
        rows = self.c.execute(text("""SELECT fc.id, fc.label, fc.currency, fc.net_amount, fc.gross_amount, fc.discount_amount, fc.paid_amount, fc.due_date,
                   fc.period_label, fc.status, upper(coalesce(ft.code,'')) AS fee_code, upper(coalesce(cat.code,'')) AS fee_category,
                   ft.label AS fee_label
              FROM finance_charges fc LEFT JOIN fee_types ft ON ft.id=fc.fee_type_id LEFT JOIN fee_categories cat ON cat.id=ft.category_id
             WHERE fc.school_id=:s AND fc.enrollment_id=:e ORDER BY fc.due_date NULLS FIRST, fc.period_order NULLS FIRST, fc.created_at"""),
            {"s": school_id, "e": enrollment_id}).mappings().all()
        return [dict(r) for r in rows]

    @staticmethod
    def _matches(d: dict, ch: dict) -> bool:
        scope = d["scope_type"]
        if scope == "CHARGE":
            return str(d.get("charge_id") or d.get("scope_ref")) == str(ch["id"])
        if scope == "FEE_CODE":
            return (d.get("scope_ref") or "").upper() == ch["fee_code"]
        if scope == "FEE_CATEGORY":
            return (d.get("scope_ref") or "").upper() == ch["fee_category"]
        return True

    def recalculate(self, school_id: UUID, enrollment_id: UUID) -> list[dict[str, Any]]:
        """Desktop recalculate_enrollment_financial_decisions (applications rebuilt; charge net never rewritten)."""
        decisions = [dict(r) for r in self.c.execute(text("""SELECT * FROM finance_decisions WHERE school_id=:s AND enrollment_id=:e AND status='ACTIVE'
            ORDER BY priority, id"""), {"s": school_id, "e": enrollment_id}).mappings().all()]
        charges = self._charges(school_id, enrollment_id)
        self.c.execute(text("""DELETE FROM finance_decision_applications WHERE school_id=:s AND charge_id IN
            (SELECT id FROM finance_charges WHERE school_id=:s AND enrollment_id=:e)"""), {"s": school_id, "e": enrollment_id})
        out = []
        from edusync.adapters.postgres_advance_funds import PostgresAdvanceFundsRepository
        funds = PostgresAdvanceFundsRepository(self.c)
        for ch in charges:
            base = money(ch["net_amount"]); current = base; non_cumulative_applied = False; last_decision = None
            due = ch["due_date"]
            for d in decisions:
                if not self._matches(d, ch):
                    continue
                if due and ((d.get("period_start") and due < d["period_start"]) or (d.get("period_end") and due > d["period_end"])
                            or (d.get("effective_date") and d.get("model") == "DESKTOP" and due < d["effective_date"])
                            or (d.get("effective_to") and due > d["effective_to"])):
                    continue
                if non_cumulative_applied and not d["cumulative"]:
                    continue
                if d["value_type"] == "PERCENT":
                    reduction = money(current * money(d["value_amount"]) / Decimal(100))
                else:
                    if d["currency"] != ch["currency"]:
                        continue                                   # FIXED: no implicit CDF / USD conversion
                    reduction = money(min(current, money(d["value_amount"] if d["value_amount"] is not None else d["amount"])))
                if reduction <= 0:
                    continue
                current = money(max(Decimal("0"), current - reduction))
                self.c.execute(text("""INSERT INTO finance_decision_applications(school_id,decision_id,charge_id,base_amount,applied_amount,net_after)
                    VALUES(:s,:d,:c,:b,:a,:n)"""), {"s": school_id, "d": d["id"], "c": ch["id"], "b": base, "a": reduction, "n": current})
                out.append({"decision_id": str(d["id"]), "charge_id": str(ch["id"]), "applied": str(reduction), "net_after": str(current)})
                last_decision = d["id"]
                if not d["cumulative"]:
                    non_cumulative_applied = True
            # G-DEC-6 — Desktop: settled above the new net becomes a credit (advance fund of origin DECISION_CREDIT).
            outside = self.c.execute(text("SELECT COALESCE(sum(amount),0) FROM finance_charge_regularizations WHERE charge_id=:c"), {"c": ch["id"]}).scalar_one()
            credit = money(ch["paid_amount"]) + money(outside) - current
            if credit > 0:
                funds.ensure_decision_credit(school_id, enrollment_id=enrollment_id, charge=ch, credit=credit, decision_id=last_decision)
        return out

    # ---------- read models ----------
    def explanation(self, school_id: UUID, charge_id: UUID) -> dict[str, Any]:
        ch = self.c.execute(text("""SELECT fc.*, e.student_id FROM finance_charges fc JOIN enrollments e ON e.id=fc.enrollment_id
            WHERE fc.id=:c AND fc.school_id=:s"""), {"c": charge_id, "s": school_id}).mappings().first()
        if not ch:
            raise LookupError("Charge introuvable")
        apps = [dict(r) for r in self.c.execute(text("""SELECT a.base_amount, a.applied_amount, a.net_after, d.id AS decision_id, d.decision_type AS decision_kind,
                d.value_type, d.value_amount, d.reason, d.reference, d.priority, d.scope_type
              FROM finance_decision_applications a JOIN finance_decisions d ON d.id=a.decision_id AND d.status='ACTIVE'
             WHERE a.charge_id=:c ORDER BY d.priority, d.id"""), {"c": charge_id}).mappings().all()]
        outside = self.c.execute(text("SELECT COALESCE(sum(amount),0) FROM finance_charge_regularizations WHERE charge_id=:c"), {"c": charge_id}).scalar_one()
        resp = [dict(r) for r in self.c.execute(text("""SELECT * FROM finance_charge_responsibilities WHERE charge_id=:c AND status='PLANNED'
            ORDER BY created_at"""), {"c": charge_id}).mappings().all()]
        decided = sum((money(a["applied_amount"]) for a in apps), Decimal("0"))
        net = money(ch["net_amount"]); settled = money(ch["paid_amount"]) + money(outside)
        return {"charge": dict(ch), "gross": str(money(ch.get("gross_amount") or ch["net_amount"])), "benefit_discount": str(money(ch.get("discount_amount"))),
                "net_before_decisions": str(net), "decisions_total": str(decided), "net_after_decisions": str(max(Decimal("0"), net - decided)),
                "settled": str(settled), "remaining": str(max(Decimal("0"), net - decided - settled)), "decisions": apps, "responsibilities": resp}

    def operator_view(self, school_id: UUID, student_id: UUID, year_id: UUID | None = None) -> dict[str, Any]:
        enr = self.c.execute(text("""SELECT e.id, e.academic_year_id, y.label AS year_label, s.last_name, s.middle_name, s.first_name, s.matricule, sc.label AS class_label
              FROM enrollments e JOIN academic_years y ON y.id=e.academic_year_id JOIN students s ON s.id=e.student_id JOIN school_classes sc ON sc.id=e.class_id
             WHERE e.school_id=:s AND e.student_id=:st AND (CAST(:y AS uuid) IS NULL OR e.academic_year_id=CAST(:y AS uuid))
             ORDER BY (y.status='ACTIVE') DESC, y.start_date DESC LIMIT 1"""), {"s": school_id, "st": student_id, "y": str(year_id) if year_id else None}).mappings().first()
        if not enr:
            raise LookupError("Inscription introuvable pour cet élève")
        rows = []
        for ch in self._charges(school_id, enr["id"]):
            ex = self.explanation(school_id, ch["id"])
            life = self.c.execute(text("""SELECT ls.effective_on, ls.reason, ev.event_type FROM finance_charge_lifecycle_states ls
                JOIN student_status_events ev ON ev.id=ls.event_id WHERE ls.charge_id=:c"""), {"c": ch["id"]}).mappings().first()
            net_after = money(ex["net_after_decisions"]); remaining = money(ex["remaining"]); settled = money(ex["settled"])
            status = ("NEUTRALISEE" if life else "EXONEREE" if net_after <= 0 else "SOLDEE" if remaining <= 0 else "PARTIELLE" if settled > 0 else "A_REGLER")
            rows.append({"id": str(ch["id"]), "label": ch["label"], "period_label": ch["period_label"], "currency": ch["currency"], "due_date": ch["due_date"],
                         "gross": ex["gross"], "net": ex["net_after_decisions"], "settled": ex["settled"], "remaining": ex["remaining"], "status": status,
                         "decisions": ex["decisions"], "responsibility": ex["responsibilities"][0] if ex["responsibilities"] else None,
                         "fee_code": ch["fee_code"] or None, "fee_label": ch["fee_label"],   # multi-fee exemptions (2026-10-24)
                         "lifecycle": dict(life) if life else None})
        events = [dict(r) for r in self.c.execute(text("""SELECT event_type, effective_date, reason, destination, created_at FROM student_status_events
            WHERE school_id=:s AND student_id=:st ORDER BY created_at DESC"""), {"s": school_id, "st": student_id}).mappings().all()]
        summary: dict[str, dict[str, str]] = {}
        for r in rows:
            b = summary.setdefault(r["currency"], {"net": Decimal("0"), "settled": Decimal("0"), "remaining": Decimal("0")})
            for k in ("net", "settled", "remaining"):
                b[k] += money(r[k])
        return {"student": {k: (str(v) if isinstance(v, UUID) else v) for k, v in dict(enr).items()}, "charges": rows, "events": events,
                "summary": {cur: {k: str(v) for k, v in b.items()} for cur, b in summary.items()}}

    def follow_up(self, school_id: UUID, year_id: UUID | None = None) -> dict[str, Any]:
        y = self.c.execute(text("""SELECT id FROM academic_years WHERE school_id=:s AND (CAST(:y AS uuid) IS NULL OR id=CAST(:y AS uuid))
            ORDER BY (status='ACTIVE') DESC, start_date DESC LIMIT 1"""), {"s": school_id, "y": str(year_id) if year_id else None}).scalar_one_or_none()
        decisions = [dict(r) for r in self.c.execute(text("""SELECT d.*, s.matricule, concat_ws(' ', s.last_name, s.middle_name, s.first_name) AS student,
                sc.label AS class_label, (SELECT count(*) FROM finance_decision_applications a WHERE a.decision_id=d.id) AS application_count
              FROM finance_decisions d JOIN enrollments e ON e.id=d.enrollment_id JOIN students s ON s.id=e.student_id JOIN school_classes sc ON sc.id=e.class_id
             WHERE d.school_id=:s AND e.academic_year_id=:y ORDER BY (d.status='ACTIVE') DESC, d.created_at DESC"""), {"s": school_id, "y": y}).mappings().all()]
        responsibilities = [dict(r) for r in self.c.execute(text("""SELECT cr.*, s.matricule, concat_ws(' ', s.last_name, s.middle_name, s.first_name) AS student,
                fc.label AS fee_label, fc.due_date
              FROM finance_charge_responsibilities cr JOIN finance_charges fc ON fc.id=cr.charge_id JOIN enrollments e ON e.id=fc.enrollment_id
              JOIN students s ON s.id=e.student_id WHERE cr.school_id=:s AND e.academic_year_id=:y
             ORDER BY (cr.status='PLANNED') DESC, fc.due_date, cr.created_at DESC"""), {"s": school_id, "y": y}).mappings().all()]
        return {"year_id": str(y) if y else None, "decisions": decisions, "responsibilities": responsibilities}

    # ---------- Desktop set_charge_responsibility ----------
    def set_charge_responsibility(self, school_id: UUID, *, user_id: UUID, charge_id: UUID, responsibility_type: str, planned_amount: Decimal,
                                  responsible_name: str | None = None, reference: str | None = None, reason: str = "") -> tuple[dict[str, Any], dict[str, Any] | None]:
        responsibility_type = (responsibility_type or "").strip().upper(); reason = (reason or "").strip()
        if responsibility_type not in RESPONSIBILITIES:
            raise ValueError("Responsabilité de règlement invalide")
        amount = money(planned_amount)
        ch = self.c.execute(text("SELECT * FROM finance_charges WHERE id=:c AND school_id=:s FOR UPDATE"), {"c": charge_id, "s": school_id}).mappings().first()
        if not ch or amount <= 0 or not reason:
            raise ValueError("Charge, montant et motif sont obligatoires")
        ex = self.explanation(school_id, charge_id)
        if amount > money(ex["remaining"]):
            raise ValueError("La responsabilité prévue ne peut pas dépasser le restant réel de ce frais")
        old = self.c.execute(text("""UPDATE finance_charge_responsibilities SET status='CANCELLED',cancelled_at=now(),cancelled_by=:u,cancellation_reason='Remplacée'
            WHERE charge_id=:c AND status='PLANNED' RETURNING *"""), {"u": user_id, "c": charge_id}).mappings().first()
        row = self.c.execute(text("""INSERT INTO finance_charge_responsibilities(school_id,charge_id,responsibility_type,responsible_name,planned_amount,currency,reference,reason,created_by)
            VALUES(:s,:c,:t,:n,:a,:cur,:ref,:r,:u) RETURNING *"""), {"s": school_id, "c": charge_id, "t": responsibility_type, "n": (responsible_name or "").strip() or None,
                                                                   "a": amount, "cur": ch["currency"], "ref": (reference or "").strip() or None, "r": reason, "u": user_id}).mappings().one()
        return dict(row), dict(old) if old else None
