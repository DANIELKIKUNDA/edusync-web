"""N3-B — payment and cash-desk integrity, copied from the Desktop golden master.

Desktop reference: app/db/operations.py (EduSync École Offline 0.11.0-rc.1)
  * reverse_payment (225-287): ANNULATION / REMBOURSEMENT, reason >= 3 characters, only a valid payment, refused when the
    cash day is closed; the payment stops counting (charges become payable again) and a SORTIE is booked.
  * record_expense (518-553): category, reason >= 3, amount > 0, CDF / USD, refused when the cash day is closed.
  * close_cash_day (555-579): snapshot per currency (entries, outflows, net); idempotent when already closed.
  * reopen_cash_day (581-598): reason >= 5 characters, only today's closed day.
  * daily_financial_report (737-748): totals per currency and detail per source / direction / currency.
Web transposition (owner decision 2026-10-15, G-ROLE-1 / G-CAI-4):
  * individual cash sessions per cashier are kept; the school's cash day is closed globally on top of them, once every
    individual session of that day is closed, by the superior authority (finance.cash.day.close), reopened likewise;
  * a cashier corrects only his own payment while his session is open (finance.payments.reverse); any other payment
    needs the superior authority (finance.payments.reverse.supervisor);
  * nothing is updated nor deleted on a payment: the reversal is an append-only row (finance_payment_reversals).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection

CENT = Decimal("0.01")
SOURCE_LABELS = {"PAIEMENT_ELEVE": "Paiement élève", "VENTE_ARTICLE": "Vente article", "DEPENSE_JOURNALIERE": "Dépense",
                 "ANNULATION": "Annulation", "REMBOURSEMENT": "Remboursement", "FONDS_ANTICIPE": "Fonds anticipé",
                 "RESTITUTION_FONDS_ANTICIPE": "Restitution fonds anticipé"}


def money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


class SupervisorRequired(PermissionError):
    pass


class PostgresCashIntegrityRepository:
    def __init__(self, connection: Connection):
        self.c = connection

    # ---------- school cash day ----------
    def day_row(self, school_id: UUID, day: date) -> dict[str, Any] | None:
        r = self.c.execute(text("SELECT * FROM finance_cash_days WHERE school_id=:s AND business_date=:d"), {"s": school_id, "d": day}).mappings().first()
        return dict(r) if r else None

    def require_day_open(self, school_id: UUID, day: date) -> None:
        row = self.day_row(school_id, day)
        if row and row["status"] == "CLOSED":
            raise ValueError("La journée de caisse de l'école est clôturée. Seule l'autorité supérieure peut la rouvrir.")

    def today(self) -> date:
        return self.c.execute(text("SELECT CURRENT_DATE")).scalar_one()

    # ---------- daily report (Desktop daily_financial_report / cash_day_summary) ----------
    def day_operations(self, school_id: UUID, day: date) -> list[dict[str, Any]]:
        rows = self.c.execute(text("""
            SELECT p.created_at, 'ENTREE' AS direction,
                   CASE WHEN EXISTS (SELECT 1 FROM finance_product_sales ps WHERE ps.payment_id=p.id) THEN 'VENTE_ARTICLE' ELSE 'PAIEMENT_ELEVE' END AS source,
                   p.amount, p.currency, p.payment_mode AS mode, p.receipt_number AS reference, NULL::text AS reason, u.full_name AS user_name,
                   s.membership_id, p.actor_user_id AS user_id, CAST(p.id AS text) AS payment_id,
                   EXISTS (SELECT 1 FROM finance_payment_reversals x WHERE x.payment_id=p.id) AS reversed
              FROM finance_payments p JOIN finance_cash_sessions s ON s.id=p.cash_session_id LEFT JOIN users u ON u.id=p.actor_user_id
             WHERE p.school_id=:s AND s.business_date=:d
            UNION ALL
            SELECT e.created_at, 'SORTIE', 'DEPENSE_JOURNALIERE', e.amount, e.currency, 'CASH', coalesce(e.reference, e.label), coalesce(e.reason, e.label),
                   u.full_name, s.membership_id, e.actor_user_id, NULL, false
              FROM finance_cash_expenses e JOIN finance_cash_sessions s ON s.id=e.cash_session_id LEFT JOIN users u ON u.id=e.actor_user_id
             WHERE e.school_id=:s AND s.business_date=:d
            UNION ALL
            SELECT r.performed_at, 'SORTIE', r.reversal_type, r.amount, r.currency, p.payment_mode, p.receipt_number, r.reason, u.full_name, NULL, r.performed_by, NULL, false
              FROM finance_payment_reversals r JOIN finance_payments p ON p.id=r.payment_id LEFT JOIN users u ON u.id=r.performed_by
             WHERE r.school_id=:s AND r.business_date=:d
            UNION ALL
            SELECT f.received_at, 'ENTREE', 'FONDS_ANTICIPE', f.amount, f.currency, f.mode, f.receipt_number, NULL, u.full_name, s.membership_id, f.received_by, NULL, false
              FROM finance_advance_funds f JOIN finance_cash_sessions s ON s.id=f.cash_session_id LEFT JOIN users u ON u.id=f.received_by
             WHERE f.school_id=:s AND f.origin_type='PAYMENT_ADVANCE' AND s.business_date=:d
            UNION ALL
            SELECT c.performed_at, 'SORTIE', 'RESTITUTION_FONDS_ANTICIPE', c.amount, f.currency, f.mode, coalesce(f.receipt_number, f.reference), c.reason, u.full_name, NULL, c.performed_by, NULL, false
              FROM finance_advance_fund_closures c JOIN finance_advance_funds f ON f.id=c.fund_id LEFT JOIN users u ON u.id=c.performed_by
             WHERE c.school_id=:s AND c.business_date=:d AND c.closure_type IN ('ANNULATION','REMBOURSEMENT')
            ORDER BY 1"""), {"s": school_id, "d": day}).mappings().all()
        return [dict(r) for r in rows]

    def day_report(self, school_id: UUID, day: date) -> dict[str, Any]:
        ops = self.day_operations(school_id, day)
        buckets: dict[str, dict[str, Decimal]] = {}
        detail: dict[tuple[str, str, str], Decimal] = {}
        for op in ops:
            b = buckets.setdefault(op["currency"], {"entries": Decimal("0"), "outflows": Decimal("0")})
            b["entries" if op["direction"] == "ENTREE" else "outflows"] += money(op["amount"])
            key = (op["source"], op["direction"], op["currency"])
            detail[key] = detail.get(key, Decimal("0")) + money(op["amount"])
        totals = [{"currency": cur, "entries": str(v["entries"]), "outflows": str(v["outflows"]), "net": str(v["entries"] - v["outflows"])}
                  for cur, v in sorted(buckets.items())]
        details = [{"source": s, "label": SOURCE_LABELS.get(s, s), "direction": d, "currency": cur, "amount": str(a)}
                   for (s, d, cur), a in sorted(detail.items())]
        row = self.day_row(school_id, day)
        sessions = self.c.execute(text("""SELECT count(*) FILTER (WHERE status='OPEN') AS open, count(*) AS total FROM finance_cash_sessions
            WHERE school_id=:s AND business_date=:d"""), {"s": school_id, "d": day}).mappings().one()
        snapshots = [dict(r) for r in self.c.execute(text("""SELECT sn.currency, sn.entries, sn.outflows, sn.net, sn.sessions, sn.closed_at, u.full_name AS closed_by_name
            FROM finance_cash_day_snapshots sn JOIN finance_cash_days d ON d.id=sn.cash_day_id LEFT JOIN users u ON u.id=sn.closed_by
            WHERE d.school_id=:s AND d.business_date=:d ORDER BY sn.closed_at, sn.currency"""), {"s": school_id, "d": day}).mappings().all()]
        return {"day": day.isoformat(), "status": row["status"] if row else "OPEN", "closed": bool(row and row["status"] == "CLOSED"),
                "closed_at": row["closed_at"] if row else None, "reopened_at": row["reopened_at"] if row else None,
                "reopen_reason": row["reopen_reason"] if row else None, "open_sessions": int(sessions["open"]), "sessions": int(sessions["total"]),
                "totals": totals, "details": details, "operations": ops, "closure_snapshots": snapshots}

    # ---------- G-CAI-1 expense ----------
    def record_expense(self, school_id: UUID, *, user_id: UUID, membership_id: UUID, category: str, amount: Decimal, currency: str,
                       reason: str, reference: str | None = None) -> dict[str, Any]:
        category = (category or "").strip(); reason = (reason or "").strip(); amount = money(amount)
        if not category or len(reason) < 3:
            raise ValueError("Catégorie et motif de dépense obligatoires")
        if amount <= 0 or currency not in ("CDF", "USD"):
            raise ValueError("Montant ou devise invalide")
        session = self.c.execute(text("""SELECT id, business_date FROM finance_cash_sessions WHERE school_id=:s AND membership_id=:m AND status='OPEN'
            ORDER BY opened_at DESC LIMIT 1 FOR UPDATE"""), {"s": school_id, "m": membership_id}).mappings().first()
        if not session:
            raise ValueError("Aucune caisse ouverte pour cet utilisateur")
        self.require_day_open(school_id, session["business_date"])
        eid = uuid4()
        self.c.execute(text("""INSERT INTO finance_cash_expenses(id,school_id,cash_session_id,actor_user_id,label,amount,currency,category,reason,reference)
            VALUES(:id,:s,:cs,:u,:l,:a,:cur,:cat,:r,:ref)"""), {"id": eid, "s": school_id, "cs": session["id"], "u": user_id, "l": category[:180],
                                                             "a": amount, "cur": currency, "cat": category[:80], "r": reason, "ref": (reference or "").strip()[:80] or None})
        self.c.execute(text("""INSERT INTO finance_cash_events(school_id,cash_session_id,actor_user_id,event_type,payload)
            VALUES(:s,:cs,:u,'EXPENSE',jsonb_build_object('expense_id',CAST(:e AS text),'amount',CAST(:a AS text),'currency',CAST(:cur AS text)))"""),
            {"s": school_id, "cs": session["id"], "u": user_id, "e": str(eid), "a": str(amount), "cur": currency})
        return {"id": str(eid), "cash_session_id": str(session["id"]), "category": category, "amount": str(amount), "currency": currency,
                "reason": reason, "reference": (reference or "").strip() or None}

    # ---------- G-REV-1 counter-operation ----------
    def reverse_payment(self, school_id: UUID, payment_id: UUID, *, user_id: UUID, membership_id: UUID, reversal_type: str, reason: str,
                        can_own: bool, can_supervisor: bool) -> dict[str, Any]:
        if reversal_type not in ("ANNULATION", "REMBOURSEMENT"):
            raise ValueError("Type de contre-opération invalide")
        reason = (reason or "").strip()
        if len(reason) < 3:
            raise ValueError("Le motif est obligatoire et doit être explicite")
        p = self.c.execute(text("""SELECT p.*, s.membership_id AS session_membership, s.status AS session_status, s.business_date
            FROM finance_payments p JOIN finance_cash_sessions s ON s.id=p.cash_session_id WHERE p.id=:id AND p.school_id=:s"""),
            {"id": payment_id, "s": school_id}).mappings().first()
        if not p:
            raise LookupError("Paiement introuvable")
        if self.c.execute(text("SELECT 1 FROM finance_payment_reversals WHERE payment_id=:id"), {"id": payment_id}).first():
            raise ValueError("Ce paiement a déjà fait l'objet d'une contre-opération")
        own = str(p["actor_user_id"]) == str(user_id) and str(p["session_membership"]) == str(membership_id) and p["session_status"] == "OPEN"
        if own and can_own:
            authority, session_id, day = "OWN", p["cash_session_id"], p["business_date"]
        elif can_supervisor:
            authority, session_id, day = "SUPERVISOR", None, self.today()
        else:
            raise SupervisorRequired("Paiement d'un autre caissier ou caisse déjà clôturée : la contre-opération relève de l'autorité supérieure")
        self.require_day_open(school_id, day)
        rid = uuid4()
        self.c.execute(text("""INSERT INTO finance_payment_reversals(id,school_id,payment_id,reversal_type,amount,currency,reason,authority,cash_session_id,business_date,performed_by)
            VALUES(:id,:s,:p,:t,:a,:cur,:r,:auth,:cs,:d,:u)"""), {"id": rid, "s": school_id, "p": payment_id, "t": reversal_type, "a": p["amount"],
                                                             "cur": p["currency"], "r": reason, "auth": authority, "cs": session_id, "d": day, "u": user_id})
        # The payment stops counting: what it settled becomes payable again (Desktop balances only count VALIDE payments).
        allocations = self.c.execute(text("SELECT charge_id, amount FROM finance_payment_allocations WHERE payment_id=:p"), {"p": payment_id}).mappings().all()
        for a in allocations:
            self.c.execute(text("UPDATE finance_charges SET paid_amount=paid_amount-:a, updated_at=now() WHERE id=:c AND school_id=:s"),
                           {"a": a["amount"], "c": a["charge_id"], "s": school_id})
        if session_id:
            self.c.execute(text("""INSERT INTO finance_cash_events(school_id,cash_session_id,actor_user_id,event_type,payload)
                VALUES(:s,:cs,:u,'REVERSAL',jsonb_build_object('payment_id',CAST(:p AS text),'type',CAST(:t AS text)))"""),
                {"s": school_id, "cs": session_id, "u": user_id, "p": str(payment_id), "t": reversal_type})
        return {"id": str(rid), "payment_id": str(payment_id), "receipt_number": p["receipt_number"], "reversal_type": reversal_type,
                "status": "ANNULE" if reversal_type == "ANNULATION" else "REMBOURSE", "amount": str(p["amount"]), "currency": p["currency"],
                "authority": authority, "business_date": day.isoformat(), "charges_reopened": len(allocations), "old": dict(p)}

    # ---------- G-CAI-4 global day closure / reopening ----------
    def close_day(self, school_id: UUID, *, user_id: UUID, day: date | None = None) -> tuple[dict[str, Any], bool]:
        day = day or self.today()
        row = self.c.execute(text("SELECT * FROM finance_cash_days WHERE school_id=:s AND business_date=:d FOR UPDATE"), {"s": school_id, "d": day}).mappings().first()
        if row and row["status"] == "CLOSED":
            return self.day_report(school_id, day), False          # Desktop: closing a closed day returns its summary
        open_sessions = self.c.execute(text("SELECT count(*) FROM finance_cash_sessions WHERE school_id=:s AND business_date=:d AND status='OPEN'"),
                                       {"s": school_id, "d": day}).scalar_one()
        if open_sessions:
            raise ValueError(f"Clôturez d'abord les caisses individuelles encore ouvertes ({open_sessions}) avant la clôture de la journée de l'école")
        if row is None:
            day_id = self.c.execute(text("INSERT INTO finance_cash_days(school_id,business_date) VALUES(:s,:d) RETURNING id"), {"s": school_id, "d": day}).scalar_one()
        else:
            day_id = row["id"]
        report = self.day_report(school_id, day)
        closed_at = self.c.execute(text("SELECT now()")).scalar_one()
        for t in report["totals"]:
            self.c.execute(text("""INSERT INTO finance_cash_day_snapshots(school_id,cash_day_id,currency,entries,outflows,net,sessions,closed_by,closed_at)
                VALUES(:s,:d,:cur,:e,:o,:n,:k,:u,:at)"""), {"s": school_id, "d": day_id, "cur": t["currency"], "e": t["entries"], "o": t["outflows"],
                                                        "n": t["net"], "k": report["sessions"], "u": user_id, "at": closed_at})
        self.c.execute(text("UPDATE finance_cash_days SET status='CLOSED',closed_at=:at,closed_by=:u WHERE id=:id"), {"at": closed_at, "u": user_id, "id": day_id})
        return self.day_report(school_id, day), True

    def reopen_day(self, school_id: UUID, *, user_id: UUID, reason: str) -> dict[str, Any]:
        reason = (reason or "").strip()
        if len(reason) < 5:
            raise ValueError("Un motif explicite est obligatoire pour rouvrir la caisse")
        day = self.today()
        row = self.c.execute(text("SELECT * FROM finance_cash_days WHERE school_id=:s AND business_date=:d FOR UPDATE"), {"s": school_id, "d": day}).mappings().first()
        if not row or row["status"] != "CLOSED":
            raise ValueError("La caisse du jour n'est pas clôturée")
        self.c.execute(text("UPDATE finance_cash_days SET status='OPEN',reopened_at=now(),reopened_by=:u,reopen_reason=:r WHERE id=:id"),
                       {"u": user_id, "r": reason, "id": row["id"]})
        return self.day_report(school_id, day)

    # ---------- session figures (individual sessions keep their own expected cash) ----------
    def session_reversals(self, session_id) -> dict[str, str]:
        rows = self.c.execute(text("SELECT currency, COALESCE(sum(amount),0) AS amount FROM finance_payment_reversals WHERE cash_session_id=:s GROUP BY currency"),
                              {"s": str(session_id)}).mappings().all()
        return {str(r["currency"]): str(r["amount"]) for r in rows}

    def session_advance_funds(self, session_id) -> dict[str, str]:
        rows = self.c.execute(text("SELECT currency, COALESCE(sum(amount),0) AS amount FROM finance_advance_funds WHERE cash_session_id=:s GROUP BY currency"),
                              {"s": str(session_id)}).mappings().all()
        return {str(r["currency"]): str(r["amount"]) for r in rows}

    def supervisor_reversals(self, school_id: UUID, day) -> dict[str, str]:
        rows = self.c.execute(text("""SELECT currency, COALESCE(sum(amount),0) AS amount FROM finance_payment_reversals
            WHERE school_id=:s AND business_date=COALESCE(CAST(:d AS date),CURRENT_DATE) AND cash_session_id IS NULL GROUP BY currency
            UNION ALL
            SELECT f.currency, c.amount FROM finance_advance_fund_closures c JOIN finance_advance_funds f ON f.id=c.fund_id
            WHERE c.school_id=:s AND c.business_date=COALESCE(CAST(:d AS date),CURRENT_DATE) AND c.closure_type IN ('ANNULATION','REMBOURSEMENT')"""),
            {"s": str(school_id), "d": day}).mappings().all()
        out: dict[str, Decimal] = {}
        for r in rows:
            out[str(r["currency"])] = out.get(str(r["currency"]), Decimal("0")) + money(r["amount"])
        return {k: str(v) for k, v in out.items()}
