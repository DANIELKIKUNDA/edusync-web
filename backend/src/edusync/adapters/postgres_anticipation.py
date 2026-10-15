"""Payment plans (« plans de paiement anticipé ») — parity lot L6, copied from the Desktop golden master.

Desktop reference: app/db/anticipation.py (EduSync École Offline 0.11.0-rc.1).
  * A plan routes part of a current monthly payment to NAMED future months of one monthly fee. It never creates money,
    never holds a provision (Plan anticipé ≠ Fonds anticipé) and never allocates to a month the plan does not name.
  * save: name, scope (school / section / Humanities group / academic class / class), monthly fee, target months,
    contribution months (disjoint), OPTIONAL or MANDATORY participation, effective date; a plan with memberships cannot
    change its structure ("désactivez-le et créez une nouvelle version").
  * membership ENROLLED / DECLINED / PAUSED: ENROLLED needs every target charge generated, one currency; it freezes the
    remaining target amount and splits it equally to the cent over the contribution months (installments).
  * payment with plan: only in a contribution month; current month first, then only the plan's target months, in the
    plan order; a mandatory plan enrols the student at the first plan payment; the plan authorises the payment (no
    deposit / future-month rule of the cash-desk policy); allocations to targets are linked; COMPLETED when nothing remains.
Web mapping: a monthly due charge is identified by its fee type and its schedule month (fee_schedules.period_code).
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection

from edusync.adapters.postgres_finance_checkout import PostgresFinanceCheckoutRepository
from edusync.adapters.postgres_settings import PostgresSettingsRepository

MONTHS = ("09", "10", "11", "12", "01", "02", "03", "04", "05", "06", "07", "08")
MONTH_NAMES = {"01": "Janvier", "02": "Février", "03": "Mars", "04": "Avril", "05": "Mai", "06": "Juin", "07": "Juillet",
               "08": "Août", "09": "Septembre", "10": "Octobre", "11": "Novembre", "12": "Décembre"}
CENT = Decimal("0.01")


def money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def month_list(values) -> list[str]:
    out: list[str] = []
    for v in values or []:
        mm = str(v).zfill(2)
        if mm not in MONTH_NAMES:
            raise ValueError("Mois invalide dans le plan de paiement anticipé")
        if mm not in out:
            out.append(mm)
    return out


def split_equal(total: Decimal, count: int) -> list[Decimal]:
    """Desktop _split_equal: cents distributed equally, the first months take the remainder cents."""
    if count <= 0:
        raise ValueError("Le plan doit contenir au moins un mois de contribution")
    cents = int((money(total) * 100).to_integral_value())
    base, remainder = divmod(cents, count)
    return [Decimal(base + (1 if i < remainder else 0)) / Decimal(100) for i in range(count)]


class PostgresAnticipationRepository:
    PLAN_COLUMNS = ("id,academic_year_id,name,scope_type,scope_ref,fee_type_id,target_months,contribution_months,participation_mode,"
                    "allocation_strategy,effective_from,active,version")

    def __init__(self, connection: Connection):
        self.connection = connection
        self.settings = PostgresSettingsRepository(connection)
        self.checkout = PostgresFinanceCheckoutRepository(connection)

    # ---------- plans (Paramètres) ----------
    def list_plans(self, school_id: UUID, year_id: UUID, *, include_inactive: bool = True) -> list[dict[str, Any]]:
        rows = self.connection.execute(text(f"""SELECT p.{self.PLAN_COLUMNS.replace(',', ',p.')},f.code AS fee_code,f.label AS fee_label,
                (SELECT count(*) FROM anticipation_memberships m WHERE m.plan_id=p.id AND m.status IN ('ENROLLED','COMPLETED')) AS memberships
              FROM anticipation_plans p JOIN fee_types f ON f.id=p.fee_type_id
             WHERE p.school_id=:sid AND p.academic_year_id=:y {'' if include_inactive else 'AND p.active'}
             ORDER BY p.active DESC,p.effective_from,p.name"""), {"sid": school_id, "y": year_id}).all()
        return [dict(r._mapping) for r in rows]

    def save_plan(self, school_id: UUID, *, academic_year_id: UUID, name: str, fee_type_id: UUID, target_months: list[str],
                  contribution_months: list[str], participation_mode: str = "OPTIONAL", scope_type: str = "SCHOOL",
                  scope_ref: str | None = None, effective_from: date | None = None, active: bool = True,
                  plan_id: UUID | None = None) -> tuple[dict[str, Any], dict[str, Any] | None]:
        year = self.settings._editable_year(school_id, academic_year_id)
        name = (name or "").strip()
        if not name:
            raise ValueError("Le nom du plan est obligatoire")
        if participation_mode not in ("OPTIONAL", "MANDATORY"):
            raise ValueError("Mode de participation invalide")
        if scope_type not in ("SCHOOL", "SECTION", "OPTION_GROUP", "ACADEMIC_CLASS", "CLASS"):
            raise ValueError("Portée du plan invalide")
        ref = "*" if scope_type == "SCHOOL" else (scope_ref or "").strip()
        if not ref:
            raise ValueError("Choisissez la cible du plan")
        if scope_type in ("OPTION_GROUP", "ACADEMIC_CLASS"):
            ref = ref.upper()
        if scope_type == "OPTION_GROUP" and ref not in self.settings.TARIFF_GROUPS:
            raise ValueError("Groupe tarifaire invalide")
        targets, contributions = month_list(target_months), month_list(contribution_months)
        if not targets or not contributions:
            raise ValueError("Sélectionnez au moins un mois cible et un mois de contribution")
        if set(targets) & set(contributions):
            raise ValueError("Un mois cible ne peut pas être aussi un mois de contribution dans le même plan")
        fee = self.connection.execute(text("SELECT periodicity FROM fee_types WHERE id=:f AND school_id=:sid"), {"f": fee_type_id, "sid": school_id}).first()
        if fee is None:
            raise ValueError("Type de frais introuvable")
        if fee._mapping["periodicity"] != "MONTHLY":
            raise ValueError("Un plan anticipé doit porter sur un frais mensuel")
        eff = effective_from or year["start_date"]
        values = {"sid": school_id, "y": academic_year_id, "n": name, "st": scope_type, "sr": ref, "f": fee_type_id, "t": json.dumps(targets),
                  "c": json.dumps(contributions), "pm": participation_mode, "eff": eff, "a": bool(active)}
        if plan_id is not None:
            old = self.connection.execute(text(f"SELECT {self.PLAN_COLUMNS} FROM anticipation_plans WHERE id=:id AND school_id=:sid FOR UPDATE"),
                                          {"id": plan_id, "sid": school_id}).first()
            if old is None:
                raise LookupError("Plan anticipé introuvable")
            o = dict(old._mapping)
            members = self.connection.execute(text("SELECT count(*) FROM anticipation_memberships WHERE plan_id=:id AND status IN ('ENROLLED','COMPLETED')"),
                                              {"id": plan_id}).scalar_one()
            structural = (str(o["fee_type_id"]) != str(fee_type_id) or list(o["target_months"]) != targets or list(o["contribution_months"]) != contributions
                          or o["scope_type"] != scope_type or o["scope_ref"] != ref)
            if members and structural:
                raise ValueError("Ce plan possède déjà des adhésions. Désactivez-le et créez une nouvelle version pour modifier sa structure.")
            row = self.connection.execute(text(f"""UPDATE anticipation_plans SET name=:n,scope_type=:st,scope_ref=:sr,fee_type_id=:f,
                target_months=CAST(:t AS jsonb),contribution_months=CAST(:c AS jsonb),participation_mode=:pm,effective_from=:eff,active=:a
                WHERE id=:id RETURNING {self.PLAN_COLUMNS}"""), {**values, "id": plan_id}).first()
            return dict(row._mapping), o
        row = self.connection.execute(text(f"""INSERT INTO anticipation_plans(school_id,academic_year_id,name,scope_type,scope_ref,fee_type_id,
            target_months,contribution_months,participation_mode,effective_from,active)
            VALUES (:sid,:y,:n,:st,:sr,:f,CAST(:t AS jsonb),CAST(:c AS jsonb),:pm,:eff,:a) RETURNING {self.PLAN_COLUMNS}"""), values).first()
        return dict(row._mapping), None

    def set_plan_active(self, school_id: UUID, plan_id: UUID, *, active: bool) -> tuple[dict[str, Any], dict[str, Any]]:
        old = self.connection.execute(text(f"SELECT {self.PLAN_COLUMNS} FROM anticipation_plans WHERE id=:id AND school_id=:sid FOR UPDATE"),
                                      {"id": plan_id, "sid": school_id}).first()
        if old is None:
            raise LookupError("Plan anticipé introuvable")
        self.settings._editable_year(school_id, old._mapping["academic_year_id"])
        row = self.connection.execute(text(f"UPDATE anticipation_plans SET active=:a WHERE id=:id RETURNING {self.PLAN_COLUMNS}"),
                                      {"a": bool(active), "id": plan_id}).first()
        return dict(row._mapping), dict(old._mapping)

    # ---------- enrollment context ----------
    def _context(self, school_id: UUID, enrollment_id: UUID) -> dict[str, Any]:
        row = self.connection.execute(text("""SELECT e.id AS enrollment_id,e.student_id,e.class_id,e.academic_year_id,c.section_id,
                   upper(coalesce(c.reference_code,'')) AS level,coalesce(o.tariff_group_code,'OTHER') AS tariff_group,y.status AS year_status
              FROM enrollments e JOIN school_classes c ON c.id=e.class_id JOIN academic_years y ON y.id=e.academic_year_id
              LEFT JOIN school_options o ON o.id=c.option_id
             WHERE e.school_id=:sid AND e.id=:id AND e.status='VALIDATED'"""), {"sid": school_id, "id": enrollment_id}).first()
        if row is None:
            raise ValueError("Inscription active introuvable")
        return dict(row._mapping)

    @staticmethod
    def _scope_matches(plan: dict, ctx: dict) -> bool:
        scope, ref = plan["scope_type"], plan["scope_ref"]
        return (scope == "SCHOOL" or (scope == "SECTION" and ref == str(ctx["section_id"])) or (scope == "OPTION_GROUP" and ref == ctx["tariff_group"])
                or (scope == "ACADEMIC_CLASS" and ref == ctx["level"]) or (scope == "CLASS" and ref == str(ctx["class_id"])))

    def _plan(self, school_id: UUID, plan_id: UUID) -> dict[str, Any]:
        row = self.connection.execute(text(f"""SELECT p.{self.PLAN_COLUMNS.replace(',', ',p.')},f.code AS fee_code,f.label AS fee_label
              FROM anticipation_plans p JOIN fee_types f ON f.id=p.fee_type_id WHERE p.id=:id AND p.school_id=:sid"""),
            {"id": plan_id, "sid": school_id}).first()
        if row is None:
            raise LookupError("Plan anticipé introuvable")
        return dict(row._mapping)

    def _require_effective_active(self, plan: dict, ctx: dict) -> None:
        if ctx["year_status"] != "ACTIVE" or str(plan["academic_year_id"]) != str(ctx["academic_year_id"]):
            raise ValueError("Ce plan n'appartient pas à l'année scolaire active de l'élève")
        if not plan["active"]:
            raise ValueError("Ce plan de paiement anticipé est désactivé")
        if plan["effective_from"] > date.today():
            raise ValueError(f"Ce plan sera disponible à partir du {plan['effective_from'].isoformat()}")

    def _month_charges(self, school_id: UUID, enrollment_id: UUID, fee_type_id: UUID, months: list[str]) -> list[dict[str, Any]]:
        """Due charges of this monthly fee for these months (plan order), with the cash-desk remaining amount."""
        if not months:
            return []
        rows = self.connection.execute(text("""SELECT fc.*,s.period_code AS month FROM finance_charges fc JOIN fee_schedules s ON s.id=fc.schedule_id
             WHERE fc.school_id=:sid AND fc.enrollment_id=:e AND s.fee_type_id=:f AND s.period_code=ANY(:m) AND fc.status='ACTIVE'"""),
            {"sid": school_id, "e": enrollment_id, "f": fee_type_id, "m": list(months)}).mappings().all()
        payable = {str(c.id): c for c in self.checkout._cash_payable(school_id, rows)}
        out = [{"charge_id": str(r["id"]), "month": r["month"], "label": r["label"], "currency": r["currency"],
                "balance": payable[str(r["id"])].remaining} for r in rows]
        return sorted(out, key=lambda x: months.index(x["month"]))

    # ---------- memberships ----------
    def applicable_plans(self, school_id: UUID, enrollment_id: UUID) -> list[dict[str, Any]]:
        ctx = self._context(school_id, enrollment_id)
        out = []
        for plan in self.list_plans(school_id, ctx["academic_year_id"], include_inactive=False):
            if plan["effective_from"] > date.today() or not self._scope_matches(plan, ctx):
                continue
            out.append({**plan, **self.status(school_id, enrollment_id, plan["id"])})
        return out

    def status(self, school_id: UUID, enrollment_id: UUID, plan_id: UUID) -> dict[str, Any]:
        plan = self._plan(school_id, plan_id)
        m = self.connection.execute(text("SELECT * FROM anticipation_memberships WHERE school_id=:sid AND plan_id=:p AND enrollment_id=:e"),
                                    {"sid": school_id, "p": plan_id, "e": enrollment_id}).mappings().first()
        installments = [] if m is None else [dict(r) for r in self.connection.execute(text(
            "SELECT contribution_month,planned_amount,sort_order FROM anticipation_installments WHERE membership_id=:m ORDER BY sort_order"),
            {"m": m["id"]}).mappings().all()]
        targets = self._month_charges(school_id, enrollment_id, plan["fee_type_id"], list(plan["target_months"]))
        return {"membership": dict(m) if m else None, "installments": installments, "target_rows": targets,
                "remaining_target": sum((t["balance"] for t in targets), Decimal("0"))}

    def set_membership(self, school_id: UUID, enrollment_id: UUID, plan_id: UUID, *, status: str, user_id: UUID,
                       notes: str | None = None) -> tuple[dict[str, Any], dict[str, Any] | None]:
        if status not in ("ENROLLED", "DECLINED", "PAUSED"):
            raise ValueError("Décision de participation invalide")
        ctx = self._context(school_id, enrollment_id)
        plan = self._plan(school_id, plan_id)
        self._require_effective_active(plan, ctx)
        if not self._scope_matches(plan, ctx):
            raise ValueError("Ce plan ne s'applique pas à la classe de cet élève")
        targets = self._month_charges(school_id, enrollment_id, plan["fee_type_id"], list(plan["target_months"]))
        if status == "ENROLLED" and len(targets) < len(plan["target_months"]):
            raise ValueError("Les mensualités cibles ne sont pas encore générées. Appliquez d'abord les barèmes aux classes ouvertes.")
        currencies = {t["currency"] for t in targets if t["balance"] > 0}
        if len(currencies) > 1:
            raise ValueError("Les mensualités cibles du plan doivent utiliser une seule devise")
        currency = next(iter(currencies), targets[0]["currency"] if targets else "CDF")
        total = money(sum((t["balance"] for t in targets), Decimal("0"))) if status == "ENROLLED" else Decimal("0")
        old = self.connection.execute(text("SELECT * FROM anticipation_memberships WHERE school_id=:sid AND plan_id=:p AND enrollment_id=:e FOR UPDATE"),
                                      {"sid": school_id, "p": plan_id, "e": enrollment_id}).mappings().first()
        values = {"sid": school_id, "p": plan_id, "e": enrollment_id, "s": status, "t": total, "cur": currency, "u": user_id, "n": (notes or "").strip() or None}
        if old is not None:
            mid = old["id"]
            self.connection.execute(text("""UPDATE anticipation_memberships SET status=:s,snapshot_target_amount=:t,currency=:cur,decided_at=now(),
                decided_by=:u,notes=:n WHERE id=:id"""), {**values, "id": mid})
        else:
            mid = uuid4()
            self.connection.execute(text("""INSERT INTO anticipation_memberships(id,school_id,plan_id,enrollment_id,status,snapshot_target_amount,currency,decided_by,notes)
                VALUES (:id,:sid,:p,:e,:s,:t,:cur,:u,:n)"""), {**values, "id": mid})
        self.connection.execute(text("DELETE FROM anticipation_installments WHERE membership_id=:m"), {"m": mid})
        if status == "ENROLLED":
            for idx, (month, amount) in enumerate(zip(plan["contribution_months"], split_equal(total, len(plan["contribution_months"]))), 1):
                self.connection.execute(text("""INSERT INTO anticipation_installments(school_id,membership_id,contribution_month,planned_amount,sort_order)
                    VALUES (:sid,:m,:mm,:a,:o)"""), {"sid": school_id, "m": mid, "mm": month, "a": amount, "o": idx * 10})
        new = self.connection.execute(text("SELECT * FROM anticipation_memberships WHERE id=:id"), {"id": mid}).mappings().one()
        return dict(new), dict(old) if old else None

    # ---------- preview and payment ----------
    def preview(self, school_id: UUID, enrollment_id: UUID, plan_id: UUID, contribution_month: str) -> dict[str, Any]:
        mm = str(contribution_month).zfill(2)
        ctx = self._context(school_id, enrollment_id)
        plan = self._plan(school_id, plan_id)
        self._require_effective_active(plan, ctx)
        st = self.status(school_id, enrollment_id, plan_id)
        current = self._month_charges(school_id, enrollment_id, plan["fee_type_id"], [mm])
        current_due = sum((c["balance"] for c in current), Decimal("0"))
        currency = current[0]["currency"] if current else (st["membership"]["currency"] if st["membership"] else (st["target_rows"][0]["currency"] if st["target_rows"] else "CDF"))
        contributions = list(plan["contribution_months"])
        potential = Decimal("0")
        if mm in contributions and st["remaining_target"] > 0:
            potential = split_equal(st["remaining_target"], len(contributions))[contributions.index(mm)]
        membership = st["membership"]
        suggested = Decimal("0")
        if membership and membership["status"] == "ENROLLED":
            inst = next((i for i in st["installments"] if i["contribution_month"] == mm), None)
            suggested = min(money(inst["planned_amount"]) if inst else Decimal("0"), st["remaining_target"])
            if membership["currency"] != currency and current_due > 0 and st["remaining_target"] > 0:
                raise ValueError("Le mois courant et les mois anticipés doivent utiliser la même devise pour un encaissement combiné")
        return {**st, "plan": plan, "current_month": mm, "current_due": current_due, "currency": currency,
                "participation_required": plan["participation_mode"] == "MANDATORY", "suggested_extra": suggested,
                "suggested_extra_if_joined": potential, "suggested_total": current_due + suggested, "contribution_month_allowed": mm in contributions}

    def collect_with_plan(self, school_id: UUID, *, user_id: UUID, membership_id: UUID, enrollment_id: UUID, plan_id: UUID,
                          contribution_month: str, amount: Decimal, currency: str, idempotency_key: str, mode: str = "CASH",
                          reference: str | None = None) -> dict[str, Any]:
        """Desktop record_monthly_payment_with_anticipation."""
        co = self.checkout
        co._lock_idempotency_key(school_id, idempotency_key)
        existing = self.connection.execute(text("SELECT id,receipt_number,amount,currency,enrollment_id FROM finance_payments WHERE school_id=:sid AND idempotency_key=:k"),
                                           {"sid": str(school_id), "k": idempotency_key}).mappings().first()
        if existing:
            if str(existing["enrollment_id"]) != str(enrollment_id) or money(existing["amount"]) != money(amount) or existing["currency"] != currency:
                raise ValueError("Idempotency-Key déjà utilisée pour un autre encaissement")
            out = dict(existing); out.pop("enrollment_id"); return {**out, "replayed": True}
        mm = str(contribution_month).zfill(2)
        policy = self.settings.get_payment_policy(school_id)
        if mode not in self.settings.PAYMENT_MODES:
            raise ValueError("Mode de paiement invalide")
        if mode not in set(policy["accepted_modes"]):
            raise ValueError("Ce mode de paiement n'est pas autorisé par la configuration de l'école")
        pv = self.preview(school_id, enrollment_id, plan_id, mm)
        plan, membership = pv["plan"], pv["membership"]
        if membership is None and plan["participation_mode"] == "MANDATORY":
            membership, _ = self.set_membership(school_id, enrollment_id, plan_id, status="ENROLLED", user_id=user_id,
                                                notes="Adhésion automatique : plan obligatoire")
            pv = self.preview(school_id, enrollment_id, plan_id, mm)
        if membership is None or membership["status"] != "ENROLLED":
            raise ValueError("Cet élève n'adhère pas à ce plan anticipé")
        if not pv["contribution_month_allowed"]:
            raise ValueError("Ce mois ne fait pas partie de la période de contribution du plan")
        session = self.connection.execute(text("""SELECT id FROM finance_cash_sessions WHERE school_id=:sid AND membership_id=:mid AND status='OPEN'
            ORDER BY opened_at DESC LIMIT 1 FOR UPDATE"""), {"sid": str(school_id), "mid": str(membership_id)}).scalar_one_or_none()
        if not session:
            raise ValueError("Aucune caisse ouverte pour cet utilisateur")
        amount = money(amount)
        if amount <= 0:
            raise ValueError("Montant invalide")
        # Current month first, then only the plan's target months: no spill to a month the plan does not name.
        lines = self._month_charges(school_id, enrollment_id, plan["fee_type_id"], [mm]) + pv["target_rows"]
        if any(line["currency"] != currency for line in lines if line["balance"] > 0):
            raise ValueError("CDF et USD restent séparés : aucune conversion implicite")
        left, alloc = amount, []
        for line in lines:
            take = min(left, line["balance"])
            if take > 0:
                alloc.append((line, take)); left -= take
        if left > 0:
            raise ValueError("Le montant dépasse le mois courant et les mois cibles du plan : aucun autre mois ne peut être alimenté")
        pid = uuid4(); receipt = co.next_receipt_number(school_id)
        self.connection.execute(text("""INSERT INTO finance_payments(id,school_id,enrollment_id,cash_session_id,actor_user_id,amount,currency,receipt_number,
            idempotency_key,payment_mode,payment_reference) VALUES(:id,:sid,:eid,:cs,:uid,:a,:cur,:r,:k,:mode,:ref)"""),
            {"id": str(pid), "sid": str(school_id), "eid": str(enrollment_id), "cs": str(session), "uid": str(user_id), "a": amount, "cur": currency,
             "r": receipt, "k": idempotency_key, "mode": mode, "ref": (reference or "").strip()[:80] or None})
        targets = {t["charge_id"] for t in pv["target_rows"]}
        details = []
        for line, take in alloc:
            aid = uuid4()
            self.connection.execute(text("INSERT INTO finance_payment_allocations(id,school_id,payment_id,charge_id,amount) VALUES(:id,:sid,:p,:c,:a)"),
                                    {"id": str(aid), "sid": str(school_id), "p": str(pid), "c": line["charge_id"], "a": take})
            self.connection.execute(text("UPDATE finance_charges SET paid_amount=paid_amount+:a,updated_at=now() WHERE id=:c AND school_id=:sid"),
                                    {"a": take, "c": line["charge_id"], "sid": str(school_id)})
            if line["charge_id"] in targets:
                self.connection.execute(text("""INSERT INTO anticipation_payment_links(school_id,membership_id,payment_id,payment_allocation_id,
                    contribution_month,target_charge_id,target_month,amount) VALUES (:sid,:m,:p,:a,:mm,:c,:tm,:amt)"""),
                    {"sid": school_id, "m": membership["id"], "p": pid, "a": aid, "mm": mm, "c": line["charge_id"], "tm": line["month"], "amt": take})
            details.append({"charge_id": line["charge_id"], "label": line["label"], "month": line["month"], "amount": str(take),
                            "target": line["charge_id"] in targets})
        if self.status(school_id, enrollment_id, plan_id)["remaining_target"] <= 0:
            self.connection.execute(text("UPDATE anticipation_memberships SET status='COMPLETED' WHERE id=:id"), {"id": membership["id"]})
        return {"id": str(pid), "receipt_number": receipt, "amount": str(amount), "currency": currency, "replayed": False, "allocations": details,
                "anticipation": {"plan_id": str(plan_id), "contribution_month": mm, "target_months": list(plan["target_months"])}}
