"""N3-F — staff children finance copied from the Desktop golden master (app/db/staff_finance.py).

  * list_staff_children: per linked child (active year): finance mode, expected, settled, payroll deducted, balance, in order.
  * staff_child_open_charges: the child's charges still owed (link and active enrollment required).
  * confirm_staff_payroll_deduction: only when the child's mode is « retenue à la source »; without explicit lines every
    open charge is settled; each line <= what remains; NO payment, NO receipt, NO cash operation (accounting separation).
  * cancel_staff_noncash_settlement: reason required, only an active settlement; the charge becomes owed again.
Web mapping: the Web finance mode PAYROLL (staff_student_finance_preferences, effective today) is the Desktop
PAYROLL_DEDUCTION mode; the other Web modes (FAMILY, SCHOOL, THIRD_PARTY) are the Desktop SCHOOL_PAYMENT side.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from edusync.adapters.postgres_finance_checkout import PostgresFinanceCheckoutRepository

CENT = Decimal("0.01")


def money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


class PostgresStaffFinanceRepository:
    def __init__(self, connection: Connection):
        self.c = connection
        self.checkout = PostgresFinanceCheckoutRepository(connection)

    def _link(self, school_id: UUID, staff_id: UUID, student_id: UUID) -> dict[str, Any]:
        r = self.c.execute(text("""SELECT l.id, p.responsibility_mode, p.effective_from, p.effective_until FROM staff_student_links l
              LEFT JOIN staff_student_finance_preferences p ON p.staff_student_link_id=l.id
             WHERE l.school_id=:s AND l.staff_id=:st AND l.student_id=:p AND l.active"""), {"s": school_id, "st": staff_id, "p": student_id}).mappings().first()
        if not r:
            raise ValueError("Inscription ou lien agent-enfant introuvable")
        return dict(r)

    def _enrollment(self, school_id: UUID, student_id: UUID):
        return self.c.execute(text("""SELECT e.id FROM enrollments e JOIN academic_years y ON y.id=e.academic_year_id
            WHERE e.school_id=:s AND e.student_id=:p AND e.status='VALIDATED' AND y.status='ACTIVE'"""), {"s": school_id, "p": student_id}).scalar_one_or_none()

    def _open_rows(self, school_id: UUID, enrollment_id) -> dict[str, Any]:
        rows = self.c.execute(text("""SELECT * FROM finance_charges WHERE school_id=:s AND enrollment_id=:e AND status='ACTIVE'
            ORDER BY due_date NULLS LAST, period_order NULLS LAST, created_at FOR UPDATE"""), {"s": school_id, "e": enrollment_id}).mappings().all()
        return {str(c.id): {"charge_id": str(c.id), "label": c.period_label or c.label, "currency": c.currency, "balance": c.remaining, "due_date": r.get("due_date")}
                for r, c in zip(rows, self.checkout._cash_payable(school_id, rows)) if c.remaining > 0}

    @staticmethod
    def _payroll_mode(link: dict) -> bool:
        from datetime import date
        today = date.today()
        return (link.get("responsibility_mode") == "PAYROLL" and (not link.get("effective_from") or link["effective_from"] <= today)
                and (not link.get("effective_until") or link["effective_until"] >= today))

    def children(self, school_id: UUID, staff_id: UUID) -> list[dict[str, Any]]:
        links = self.c.execute(text("""SELECT l.id AS link_id, l.student_id, s.matricule, s.last_name, s.middle_name, s.first_name, p.responsibility_mode, p.effective_from, p.effective_until
              FROM staff_student_links l JOIN students s ON s.id=l.student_id LEFT JOIN staff_student_finance_preferences p ON p.staff_student_link_id=l.id
             WHERE l.school_id=:s AND l.staff_id=:st AND l.active ORDER BY s.last_name, s.first_name"""), {"s": school_id, "st": staff_id}).mappings().all()
        out = []
        for link in links:
            enr = self._enrollment(school_id, link["student_id"])
            row = {**dict(link), "enrollment_id": str(enr) if enr else None, "finance_mode": "PAYROLL_DEDUCTION" if self._payroll_mode(dict(link)) else "SCHOOL_PAYMENT",
                   "totals": {}}
            if enr:
                for r in self.c.execute(text("""SELECT fc.currency, sum(fc.net_amount - finance_charge_decision_amount(fc.id)) AS expected,
                        sum(fc.paid_amount) AS settled,
                        COALESCE(sum((SELECT sum(ns.amount) FROM finance_noncash_settlements ns WHERE ns.charge_id=fc.id
                          AND NOT EXISTS (SELECT 1 FROM finance_noncash_cancellations nc WHERE nc.settlement_id=ns.id))),0) AS payroll_deducted
                      FROM finance_charges fc WHERE fc.school_id=:s AND fc.enrollment_id=:e AND fc.status='ACTIVE' GROUP BY fc.currency"""),
                        {"s": school_id, "e": enr}).mappings().all():
                    balance = max(Decimal("0"), money(r["expected"]) - money(r["settled"]))
                    row["totals"][r["currency"]] = {"expected": str(money(r["expected"])), "settled": str(money(r["settled"])),
                                                    "payroll_deducted": str(money(r["payroll_deducted"])), "balance": str(balance)}
            row["in_order"] = all(Decimal(t["balance"]) <= 0 for t in row["totals"].values())
            row["settlements"] = [dict(x) for x in self.c.execute(text("""SELECT ns.id, ns.amount, ns.currency, ns.period_label, ns.reference, ns.confirmed_at,
                    coalesce(fc.period_label, fc.label) AS charge_label, (nc.id IS NOT NULL) AS cancelled
                  FROM finance_noncash_settlements ns JOIN finance_charges fc ON fc.id=ns.charge_id
                  LEFT JOIN finance_noncash_cancellations nc ON nc.settlement_id=ns.id
                 WHERE ns.school_id=:s AND ns.staff_id=:st AND ns.student_id=:p ORDER BY ns.confirmed_at DESC"""),
                {"s": school_id, "st": staff_id, "p": link["student_id"]}).mappings().all()]
            out.append(row)
        return out

    def open_charges(self, school_id: UUID, staff_id: UUID, student_id: UUID) -> list[dict[str, Any]]:
        self._link(school_id, staff_id, student_id)
        enr = self._enrollment(school_id, student_id)
        if not enr:
            raise ValueError("Inscription ou lien agent-enfant introuvable")
        return [{**r, "balance": str(r["balance"])} for r in self._open_rows(school_id, enr).values()]

    def confirm(self, school_id: UUID, *, user_id: UUID, staff_id: UUID, student_id: UUID, allocations: list[dict] | None = None,
                reference: str | None = None, period_label: str | None = None) -> dict[str, Any]:
        link = self._link(school_id, staff_id, student_id)
        if not self._payroll_mode(link):
            raise ValueError("Activez d'abord le mode « retenue à la source » pour cet enfant")
        enr = self._enrollment(school_id, student_id)
        if not enr:
            raise ValueError("Inscription annuelle introuvable")
        open_rows = self._open_rows(school_id, enr)
        lines = allocations or [{"charge_id": cid, "amount": r["balance"]} for cid, r in open_rows.items()]
        if not lines:
            return {"settlement_ids": [], "currency_totals": {}, "total": "0"}
        ids, totals = [], {}
        for a in lines:
            cid = str(a.get("charge_id") or ""); amount = money(a.get("amount"))
            r = open_rows.get(cid)
            if not r:
                raise ValueError("Une ligne choisie n'est plus due")
            if amount <= 0 or amount > r["balance"]:
                raise ValueError("Montant de retenue supérieur au reste dû")
            sid = self.c.execute(text("""INSERT INTO finance_noncash_settlements(school_id,staff_id,student_id,enrollment_id,charge_id,amount,currency,period_label,reference,confirmed_by)
                VALUES(:s,:st,:p,:e,:c,:a,:cur,:pl,:ref,:u) RETURNING id"""), {"s": school_id, "st": staff_id, "p": student_id, "e": enr, "c": cid, "a": amount,
                                                                          "cur": r["currency"], "pl": (period_label or "").strip() or None, "ref": (reference or "").strip() or None, "u": user_id}).scalar_one()
            self.c.execute(text("UPDATE finance_charges SET paid_amount=paid_amount+:a, updated_at=now() WHERE id=:c AND school_id=:s"), {"a": amount, "c": cid, "s": school_id})
            ids.append(str(sid)); totals[r["currency"]] = str(money(totals.get(r["currency"], 0)) + amount)
        return {"settlement_ids": ids, "currency_totals": totals, "total": str(sum((Decimal(v) for v in totals.values()), Decimal("0")))}

    def cancel(self, school_id: UUID, settlement_id: UUID, *, user_id: UUID, reason: str) -> dict[str, Any]:
        reason = (reason or "").strip()
        if not reason:
            raise ValueError("Le motif d'annulation est obligatoire")
        row = self.c.execute(text("SELECT * FROM finance_noncash_settlements WHERE id=:id AND school_id=:s"), {"id": settlement_id, "s": school_id}).mappings().first()
        if not row:
            raise LookupError("Régularisation hors caisse introuvable")
        if self.c.execute(text("SELECT 1 FROM finance_noncash_cancellations WHERE settlement_id=:id"), {"id": settlement_id}).first():
            raise ValueError("Cette régularisation n'est plus active")
        self.c.execute(text("INSERT INTO finance_noncash_cancellations(school_id,settlement_id,reason,cancelled_by) VALUES(:s,:id,:r,:u)"),
                       {"s": school_id, "id": settlement_id, "r": reason, "u": user_id})
        self.c.execute(text("UPDATE finance_charges SET paid_amount=paid_amount-:a, updated_at=now() WHERE id=:c AND school_id=:s"),
                       {"a": row["amount"], "c": row["charge_id"], "s": school_id})
        return {"id": str(settlement_id), "status": "CANCELLED", "charge_id": str(row["charge_id"]), "amount": str(row["amount"])}
