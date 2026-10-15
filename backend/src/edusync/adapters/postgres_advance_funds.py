"""N3-D — « fonds anticipés » copied from the Desktop golden master (app/db/operations.py:290-470).

  * receive_advance_fund: refused when the school disabled advance payments or the mode is not accepted; active
    enrollment of the active year; amount > 0; CDF / USD; refused on a closed cash day; own receipt number (same sequence
    as payments); cash entry FONDS_ANTICIPE.
  * allocate_advance_fund: active fund with an available amount; requested <= available; imputed on the enrollment's
    charges of the same currency, oldest due date first, never above what each charge still owes; status EPUISE at 0.
  * reverse_advance_fund: ANNULATION / REMBOURSEMENT, reason >= 3, only a fund with nothing imputed and still active;
    cash outflow RESTITUTION_FONDS_ANTICIPE; refused on a closed cash day.
  * decision credit (financial_decisions.recalculate / cancel): a fund of origin DECISION_CREDIT, without cash nor
    receipt, when more was settled than the new net; cancelling the decision closes its unused credits and is refused
    once a credit was used.
Plan anticipé ≠ fonds anticipé: nothing here reads or writes the payment plans tables.
Web transposition (owner decision 2026-10-15): the fund is received in the cashier's open session; the refund belongs to
the superior authority and its outflow is booked in the school's cash day (no personal session).
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection

from edusync.adapters.postgres_cash_integrity import PostgresCashIntegrityRepository
from edusync.adapters.postgres_finance_checkout import PostgresFinanceCheckoutRepository
from edusync.adapters.postgres_settings import PostgresSettingsRepository

CENT = Decimal("0.01")


def money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


class PostgresAdvanceFundsRepository:
    def __init__(self, connection: Connection):
        self.c = connection
        self.checkout = PostgresFinanceCheckoutRepository(connection)
        self.cash = PostgresCashIntegrityRepository(connection)

    def _lock(self, key: str) -> None:
        self.c.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"advance-fund:{key}"})

    def fund(self, school_id: UUID, fund_id: UUID) -> dict[str, Any]:
        r = self.c.execute(text("""SELECT f.*, s.matricule, s.last_name, s.middle_name, s.first_name, sc.label AS class_label
              FROM finance_advance_fund_state f JOIN students s ON s.id=f.student_id JOIN enrollments e ON e.id=f.enrollment_id
              JOIN school_classes sc ON sc.id=e.class_id WHERE f.id=:id AND f.school_id=:s"""), {"id": fund_id, "s": school_id}).mappings().first()
        if not r:
            raise LookupError("Fonds anticipé introuvable")
        return dict(r)

    def list(self, school_id: UUID, *, enrollment_id: UUID | None = None, student_id: UUID | None = None, include_closed: bool = True) -> list[dict[str, Any]]:
        rows = self.c.execute(text("""SELECT f.*, s.matricule, s.last_name, s.middle_name, s.first_name, sc.label AS class_label
              FROM finance_advance_fund_state f JOIN students s ON s.id=f.student_id JOIN enrollments e ON e.id=f.enrollment_id
              JOIN school_classes sc ON sc.id=e.class_id
             WHERE f.school_id=:s AND (CAST(:e AS uuid) IS NULL OR f.enrollment_id=CAST(:e AS uuid)) AND (CAST(:st AS uuid) IS NULL OR f.student_id=CAST(:st AS uuid))
               AND (:all OR f.status='ACTIF') ORDER BY f.received_at DESC"""),
            {"s": school_id, "e": str(enrollment_id) if enrollment_id else None, "st": str(student_id) if student_id else None, "all": include_closed}).mappings().all()
        return [dict(r) for r in rows]

    # ---------- receive ----------
    def receive(self, school_id: UUID, *, user_id: UUID, membership_id: UUID, enrollment_id: UUID, amount: Decimal, currency: str,
                mode: str = "CASH", reference: str | None = None, idempotency_key: str) -> dict[str, Any]:
        self._lock(f"{school_id}:{idempotency_key}")
        existing = self.c.execute(text("SELECT id FROM finance_advance_funds WHERE school_id=:s AND idempotency_key=:k"), {"s": school_id, "k": idempotency_key}).scalar_one_or_none()
        if existing:
            return {**self.fund(school_id, existing), "replayed": True}
        policy = PostgresSettingsRepository(self.c).get_payment_policy(school_id)
        if not policy["advance_payments_enabled"]:
            raise ValueError("Les fonds anticipés sont désactivés dans la configuration de l'école")
        if mode not in set(policy["accepted_modes"]):
            raise ValueError("Ce mode de paiement n'est pas autorisé par la configuration de l'école")
        enr = self.c.execute(text("""SELECT e.id, e.student_id FROM enrollments e JOIN academic_years y ON y.id=e.academic_year_id
            WHERE e.id=:e AND e.school_id=:s AND e.status='VALIDATED' AND y.status='ACTIVE'"""), {"e": enrollment_id, "s": school_id}).mappings().first()
        if not enr:
            raise ValueError("Inscription active introuvable")
        amount = money(amount)
        if amount <= 0:
            raise ValueError("Montant invalide")
        if currency not in ("CDF", "USD"):
            raise ValueError("Devise invalide")
        if mode not in ("CASH", "MOBILE_MONEY", "BANQUE", "AUTRE"):
            raise ValueError("Mode de paiement invalide")
        session = self.c.execute(text("""SELECT id, business_date FROM finance_cash_sessions WHERE school_id=:s AND membership_id=:m AND status='OPEN'
            ORDER BY opened_at DESC LIMIT 1 FOR UPDATE"""), {"s": school_id, "m": membership_id}).mappings().first()
        if not session:
            raise ValueError("Aucune caisse ouverte pour cet utilisateur")
        self.cash.require_day_open(school_id, session["business_date"])
        receipt = self.checkout.next_receipt_number(school_id)
        fid = uuid4()
        self.c.execute(text("""INSERT INTO finance_advance_funds(id,school_id,student_id,enrollment_id,amount,currency,mode,reference,origin_type,
                receipt_number,cash_session_id,received_by,idempotency_key)
            VALUES(:id,:s,:st,:e,:a,:cur,:m,:ref,'PAYMENT_ADVANCE',:r,:cs,:u,:k)"""),
            {"id": fid, "s": school_id, "st": enr["student_id"], "e": enrollment_id, "a": amount, "cur": currency, "m": mode,
             "ref": (reference or "").strip()[:120] or None, "r": receipt, "cs": session["id"], "u": user_id, "k": idempotency_key})
        return {**self.fund(school_id, fid), "replayed": False}

    # ---------- allocate ----------
    def allocate(self, school_id: UUID, fund_id: UUID, *, user_id: UUID, amount: Decimal | None = None) -> dict[str, Any]:
        self._lock(str(fund_id))
        f = self.fund(school_id, fund_id)
        if f["status"] != "ACTIF" or money(f["available_amount"]) <= 0:
            raise ValueError("Ce fonds anticipé n'a plus de solde disponible")
        requested = money(f["available_amount"] if amount is None else amount)
        if requested <= 0 or requested > money(f["available_amount"]):
            raise ValueError("Montant d'allocation invalide")
        rows = self.c.execute(text("""SELECT * FROM finance_charges WHERE school_id=:s AND enrollment_id=:e AND currency=:cur AND status='ACTIVE'
            ORDER BY due_date NULLS LAST, period_order NULLS LAST, created_at FOR UPDATE"""), {"s": school_id, "e": f["enrollment_id"], "cur": f["currency"]}).mappings().all()
        payable = [c for c in self.checkout._cash_payable(school_id, rows) if c.remaining > 0]
        total_due = money(sum((c.remaining for c in payable), Decimal("0")))
        if total_due <= 0:
            raise ValueError("Aucune charge exigible n'est disponible pour cette allocation")
        requested = min(requested, total_due)
        left, allocations = requested, []
        for ch in payable:
            if left <= 0:
                break
            take = money(min(left, ch.remaining))
            self.c.execute(text("INSERT INTO finance_advance_fund_allocations(school_id,fund_id,charge_id,amount,allocated_by) VALUES(:s,:f,:c,:a,:u)"),
                           {"s": school_id, "f": fund_id, "c": str(ch.id), "a": take, "u": user_id})
            self.c.execute(text("UPDATE finance_charges SET paid_amount=paid_amount+:a, updated_at=now() WHERE id=:c AND school_id=:s"),
                           {"a": take, "c": str(ch.id), "s": school_id})
            allocations.append({"charge_id": str(ch.id), "label": ch.period_label or ch.label, "amount": str(take)})
            left = money(left - take)
        after = self.fund(school_id, fund_id)
        return {"fund_id": str(fund_id), "applied": str(money(requested - left)), "available_amount": str(after["available_amount"]),
                "status": after["status"], "allocations": allocations, "old_available": str(f["available_amount"])}

    # ---------- cancel / refund ----------
    def close(self, school_id: UUID, fund_id: UUID, *, user_id: UUID, reversal_type: str, reason: str) -> dict[str, Any]:
        if reversal_type not in ("ANNULATION", "REMBOURSEMENT"):
            raise ValueError("Type de contre-opération invalide")
        reason = (reason or "").strip()
        if len(reason) < 3:
            raise ValueError("Le motif est obligatoire")
        self._lock(str(fund_id))
        f = self.fund(school_id, fund_id)
        if money(f["allocated_amount"]) > 0:
            raise ValueError("Un fonds déjà alloué ne peut pas être annulé/remboursé globalement sans correction détaillée")
        if f["status"] != "ACTIF":
            raise ValueError("Ce fonds n'est plus actif")
        day = self.cash.today()
        self.cash.require_day_open(school_id, day)
        self.c.execute(text("""INSERT INTO finance_advance_fund_closures(school_id,fund_id,closure_type,amount,reason,business_date,performed_by)
            VALUES(:s,:f,:t,:a,:r,:d,:u)"""), {"s": school_id, "f": fund_id, "t": reversal_type, "a": f["amount"], "r": reason, "d": day, "u": user_id})
        return {**self.fund(school_id, fund_id), "old_status": f["status"]}

    # ---------- decision credits (G-DEC-6) ----------
    def ensure_decision_credit(self, school_id: UUID, *, enrollment_id: UUID, charge: dict, credit: Decimal, decision_id) -> Decimal:
        existing = self.c.execute(text("""SELECT COALESCE(sum(amount),0) FROM finance_advance_fund_state WHERE source_charge_id=:c AND origin_type='DECISION_CREDIT'
            AND status<>'ANNULE'"""), {"c": charge["id"]}).scalar_one()
        missing = money(max(Decimal("0"), money(credit) - money(existing)))
        if missing > 0:
            st = self.c.execute(text("SELECT student_id FROM enrollments WHERE id=:e"), {"e": enrollment_id}).scalar_one()
            self.c.execute(text("""INSERT INTO finance_advance_funds(school_id,student_id,enrollment_id,amount,currency,mode,reference,origin_type,source_charge_id,origin_decision_id)
                VALUES(:s,:st,:e,:a,:cur,'AUTRE','Crédit issu d''une décision financière','DECISION_CREDIT',:c,:d)"""),
                {"s": school_id, "st": st, "e": enrollment_id, "a": missing, "cur": charge["currency"], "c": charge["id"], "d": decision_id})
        return missing

    def close_decision_credits(self, school_id: UUID, decision_id, *, user_id: UUID, reason: str) -> int:
        used = self.c.execute(text("""SELECT 1 FROM finance_advance_funds f JOIN finance_advance_fund_allocations a ON a.fund_id=f.id
            WHERE f.origin_decision_id=:d LIMIT 1"""), {"d": decision_id}).first()
        if used:
            raise ValueError("Cette décision a produit un crédit déjà utilisé; une régularisation explicite est requise")
        open_credits = self.c.execute(text("SELECT id, amount FROM finance_advance_fund_state WHERE origin_decision_id=:d AND status='ACTIF'"), {"d": decision_id}).mappings().all()
        for f in open_credits:
            self.c.execute(text("""INSERT INTO finance_advance_fund_closures(school_id,fund_id,closure_type,amount,reason,business_date,performed_by)
                VALUES(:s,:f,'DECISION_ANNULEE',:a,:r,CURRENT_DATE,:u)"""), {"s": school_id, "f": f["id"], "a": f["amount"], "r": reason, "u": user_id})
        return len(open_credits)
