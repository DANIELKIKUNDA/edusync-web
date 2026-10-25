"""Fee schedules and due charges — parity lot L2, copied from the Desktop golden master.

Desktop references (EduSync École Offline 0.11.0-rc.1):
  * app/db/configuration.py::apply_tariff_rules_to_classes — per class and fee type: MONTHLY = one line per billed
    month (due on the 1st, rule resolved at that date), TERM = tranches September / January / April, otherwise one
    line resolved at the end of the year (due on the rule's effective date); a rule not ACTIVE or without amount is
    skipped ("pendingSkipped"), never replaced by a less precise rule;
  * app/db/database.py::create_fee_schedule — a line that already received money cannot change amount or currency
    ("Créez une nouvelle règle avec une date d'effet postérieure"); every validated enrollment of the class is updated;
  * app/db/database.py::generate_charges_for_enrollment — one charge per line (gross, discount, net); a regeneration
    never sets a charge below what has been paid.
Web mapping: Desktop TERM = Web fee periodicity PERIODIC. Web OPTIONAL fees (no Desktop equivalent) are not generated
automatically.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection

from edusync.adapters.postgres_settings import PostgresSettingsRepository
from edusync.shared.domain.fee_codes import canonical_fee_code, is_tuition_code, same_fee

MONTH_LABELS = {"01": "Janvier", "02": "Février", "03": "Mars", "04": "Avril", "05": "Mai", "06": "Juin", "07": "Juillet",
                "08": "Août", "09": "Septembre", "10": "Octobre", "11": "Novembre", "12": "Décembre"}
TERMS = (("T1", "1re tranche", 9), ("T2", "2e tranche", 1), ("T3", "3e tranche", 4))
CENT = Decimal("0.01")


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def apply_discount(gross: Decimal, percent: Decimal) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Desktop app/domain/benefits.py::apply_discount (percent clamped to 0..100, cent rounding half-up)."""
    gross = _money(gross)
    pct = max(Decimal("0"), min(Decimal("100"), Decimal(str(percent or 0))))
    discount = _money(gross * pct / Decimal("100"))
    return gross, pct, discount, _money(gross - discount)


class PostgresFeeScheduleRepository:
    def __init__(self, connection: Connection):
        self.connection = connection
        self.settings = PostgresSettingsRepository(connection)

    # ---------- materialisation ----------
    def apply_tariffs(self, school_id: UUID, academic_year_id: UUID) -> dict[str, Any]:
        year = self.settings._editable_year(school_id, academic_year_id)
        months = self.settings.get_billing_policy(school_id)["billing_months"]
        start: date = year["start_date"]
        fees = [dict(r._mapping) for r in self.connection.execute(text(
            "SELECT id,code,label,periodicity FROM fee_types WHERE school_id=:sid AND enabled ORDER BY code"), {"sid": school_id}).all()]
        classes = [r[0] for r in self.connection.execute(text(
            "SELECT id FROM school_classes WHERE school_id=:sid AND academic_year_id=:y AND status<>'ARCHIVED' ORDER BY code"),
            {"sid": school_id, "y": academic_year_id}).all()]
        out = {"materialized": 0, "monthly": 0, "tranches": 0, "single": 0, "pending_skipped": 0, "charges_created": 0, "charges_updated": 0}
        for class_id in classes:
            for fee in fees:
                if fee["periodicity"] == "OPTIONAL":
                    continue
                if fee["periodicity"] == "MONTHLY":
                    lines = []
                    for order, mm in enumerate(months, 1):
                        due = date(start.year if int(mm) >= start.month else start.year + 1, int(mm), 1)
                        lines.append((mm, MONTH_LABELS[mm], order, due, due))
                    kind = "monthly"
                elif fee["periodicity"] == "PERIODIC":
                    lines = []
                    for order, (code, label, month) in enumerate(TERMS, 1):
                        due = date(start.year if month >= start.month else start.year + 1, month, 1)
                        lines.append((code, label, order, due, due))
                    kind = "tranches"
                else:
                    lines = [("*", None, None, None, year["end_date"])]
                    kind = "single"
                for code, label, order, due, as_of in lines:
                    rule = self.settings.resolve_tariff(school_id, class_id=class_id, fee_type_id=fee["id"], as_of=as_of)
                    if rule is None:
                        continue
                    if rule["status"] != "ACTIVE" or rule["amount"] is None:
                        out["pending_skipped"] += 1
                        continue
                    created, updated = self._upsert_schedule(
                        school_id, academic_year_id, class_id, fee, code, label, order,
                        due if due is not None else date.fromisoformat(str(rule["effective_from"])),
                        _money(rule["amount"]), rule["currency"], UUID(str(rule["id"])))
                    out["materialized"] += 1; out[kind] += 1
                    out["charges_created"] += created; out["charges_updated"] += updated
        return out

    def _upsert_schedule(self, school_id, year_id, class_id, fee, code, label, order, due, amount, currency, tariff_id) -> tuple[int, int]:
        old = self.connection.execute(text("""SELECT id,amount,currency FROM fee_schedules WHERE school_id=:sid AND academic_year_id=:y
            AND class_id=:c AND fee_type_id=:f AND period_code=:p FOR UPDATE"""),
            {"sid": school_id, "y": year_id, "c": class_id, "f": fee["id"], "p": code}).first()
        if old is not None:
            o = old._mapping
            if _money(o["amount"]) != amount or o["currency"] != currency:
                touched = self.connection.execute(text(
                    "SELECT count(*) FROM finance_charges WHERE school_id=:sid AND schedule_id=:s AND paid_amount>0"),
                    {"sid": school_id, "s": o["id"]}).scalar_one()
                if touched:
                    name = f"{fee['label']} — {label}" if label else fee["label"]
                    raise ValueError(f"Impossible de modifier {name} : cette échéance contient déjà un paiement. "
                                     "Créez une nouvelle règle avec une date d'effet postérieure.")
            schedule_id = o["id"]
            self.connection.execute(text("""UPDATE fee_schedules SET amount=:a,currency=:cur,due_date=:d,period_label=:l,period_order=:o,
                tariff_id=:t,active=true WHERE id=:id"""),
                {"a": amount, "cur": currency, "d": due, "l": label, "o": order, "t": tariff_id, "id": schedule_id})
        else:
            schedule_id = uuid4()
            self.connection.execute(text("""INSERT INTO fee_schedules(id,school_id,academic_year_id,class_id,fee_type_id,period_code,period_label,
                period_order,due_date,amount,currency,tariff_id) VALUES (:id,:sid,:y,:c,:f,:p,:l,:o,:d,:a,:cur,:t)"""),
                {"id": schedule_id, "sid": school_id, "y": year_id, "c": class_id, "f": fee["id"], "p": code, "l": label, "o": order,
                 "d": due, "a": amount, "cur": currency, "t": tariff_id})
        created = updated = 0
        for (enrollment_id,) in self.connection.execute(text("""SELECT id FROM enrollments WHERE school_id=:sid AND academic_year_id=:y
                AND class_id=:c AND status='VALIDATED'"""), {"sid": school_id, "y": year_id, "c": class_id}).all():
            c, u = self.generate_charges_for_enrollment(school_id, enrollment_id, only_schedule_id=schedule_id, replace=True)
            created += c; updated += u
        return created, updated

    # ---------- due charges ----------
    def benefit_percent(self, school_id: UUID, enrollment: dict[str, Any], fee_code: str) -> Decimal:
        """Desktop generate_charges_for_enrollment: the student's first active benefit of the year (ordered by type) applies
        when one of its fee codes matches the charge's fee code (exactly or as prefix CODE_); rate frozen at selection.
        Settings parity 2026-10-24: a benefit may cover several fees (applies_to_fee_codes); no code = every fee."""
        b = self.connection.execute(text("""SELECT kind,configured_percent,applies_to_fee_code,applies_to_fee_codes FROM student_benefits
            WHERE school_id=:sid AND student_id=:st AND academic_year_id=:y AND active ORDER BY kind LIMIT 1"""),
            {"sid": school_id, "st": enrollment["student_id"], "y": enrollment["academic_year_id"]}).first()
        if b is None:
            return Decimal("0")
        codes = [c for c in (b._mapping["applies_to_fee_codes"] or [b._mapping["applies_to_fee_code"]]) if c]
        if codes and not any(same_fee(c, fee_code) for c in codes):
            return Decimal("0")
        return Decimal(str(b._mapping["configured_percent"] or 0))

    def generate_charges_for_enrollment(self, school_id: UUID, enrollment_id: UUID, *, only_schedule_id: UUID | None = None,
                                        replace: bool = False) -> tuple[int, int]:
        e = self.connection.execute(text("SELECT id,student_id,academic_year_id,class_id,status FROM enrollments WHERE school_id=:sid AND id=:id"),
                                    {"sid": school_id, "id": enrollment_id}).first()
        if e is None or e._mapping["status"] != "VALIDATED" or e._mapping["class_id"] is None:
            return 0, 0
        enrollment = dict(e._mapping)
        rows = self.connection.execute(text("""SELECT s.id,s.period_code,s.period_label,s.period_order,s.due_date,s.amount,s.currency,s.tariff_id,
                   f.id AS fee_type_id,f.code AS fee_code,f.label AS fee_label,f.periodicity
              FROM fee_schedules s JOIN fee_types f ON f.id=s.fee_type_id
             WHERE s.school_id=:sid AND s.academic_year_id=:y AND s.class_id=:c AND s.active
               AND (CAST(:only AS uuid) IS NULL OR s.id=:only)"""),
            {"sid": school_id, "y": enrollment["academic_year_id"], "c": enrollment["class_id"], "only": only_schedule_id}).all()
        created = updated = 0
        for row in rows:
            s = dict(row._mapping)
            gross, pct, discount, net = apply_discount(s["amount"], self.benefit_percent(school_id, enrollment, s["fee_code"]))
            label = f"{s['fee_label']} — {s['period_label']}" if s["period_label"] else s["fee_label"]
            periodicity = {"MONTHLY": "MONTHLY", "PERIODIC": "PERIODIC"}.get(s["periodicity"], "ONE_OFF")
            # N3-E / G-FIN-1 — Desktop: only the monthly tuition (SCOLARITE family, Web code MINERVAL) and the tranches are sequential.
            scolarite = is_tuition_code(s["fee_code"])
            group = {"MONTHLY": "MONTHLY:SCOLARITE" if scolarite else "NONE", "PERIODIC": f"TERM:{s['fee_code']}"}.get(s["periodicity"])
            existing = self.connection.execute(text("""SELECT id,paid_amount FROM finance_charges WHERE school_id=:sid AND enrollment_id=:e
                AND schedule_id=:s FOR UPDATE"""), {"sid": school_id, "e": enrollment_id, "s": s["id"]}).first()
            values = {"label": label[:180], "cur": s["currency"], "net": net, "gross": gross, "pct": pct, "disc": discount, "due": s["due_date"],
                      "pl": s["period_label"], "po": s["period_order"], "sg": group, "so": s["period_order"], "t": s["tariff_id"]}
            if existing is not None and replace:
                if _money(existing._mapping["paid_amount"]) > net:
                    raise ValueError("Impossible de réduire ce barème sous le montant déjà payé. Une correction financière explicite est requise.")
                self.connection.execute(text("""UPDATE finance_charges SET label=:label,currency=:cur,net_amount=:net,gross_amount=:gross,
                    discount_percent=:pct,discount_amount=:disc,due_date=:due,period_label=:pl,period_order=:po,sequence_group=:sg,
                    sequence_order=:so,tariff_id=:t,updated_at=now() WHERE id=:id"""), {**values, "id": existing._mapping["id"]})
                updated += 1
            elif existing is None:
                self.connection.execute(text("""INSERT INTO finance_charges(id,school_id,enrollment_id,schedule_id,fee_type_id,label,currency,
                    net_amount,gross_amount,discount_percent,discount_amount,periodicity,period_label,period_order,due_date,sequence_group,
                    sequence_order,tariff_id) VALUES (:id,:sid,:e,:s,:f,:label,:cur,:net,:gross,:pct,:disc,:per,:pl,:po,:due,:sg,:so,:t)"""),
                    {**values, "id": uuid4(), "sid": school_id, "e": enrollment_id, "s": s["id"], "f": s["fee_type_id"], "per": periodicity})
                created += 1
        if (created or updated) and self.connection.execute(text("""SELECT 1 FROM finance_decisions WHERE school_id=:sid AND enrollment_id=:e
                AND status='ACTIVE' LIMIT 1"""), {"sid": school_id, "e": enrollment_id}).first():
            # Desktop generate_charges_for_enrollment ends with recalculate_enrollment_financial_decisions (N3-C).
            from edusync.adapters.postgres_financial_decisions import PostgresFinancialDecisionsRepository
            PostgresFinancialDecisionsRepository(self.connection).recalculate(school_id, enrollment_id)
        return created, updated

    # ---------- registration bundle (Desktop terrain.py::registration_bundle_codes, parity lot L4) ----------
    LEGACY_BUNDLE = (("INSCRIPTION", None), ("SCOLARITE", "06"))

    def registration_bundle(self, school_id: UUID, enrollment_id: UUID) -> list[tuple[str, str | None]]:
        """(fee code, month code or None) of the required AT_ENROLLMENT conditions that target this enrollment, in order.
        SCOLARITE stands for the month required at enrollment (billing policy). Without any matching condition, a school
        that never validated the rubric keeps the Desktop historical bundle INSCRIPTION + June school fees."""
        e = self.connection.execute(text("""SELECT e.academic_year_id,e.class_id,c.section_id,upper(coalesce(c.reference_code,'')) AS level,y.status
              FROM enrollments e JOIN school_classes c ON c.id=e.class_id JOIN academic_years y ON y.id=e.academic_year_id
             WHERE e.school_id=:sid AND e.id=:id AND e.status='VALIDATED'"""), {"sid": school_id, "id": enrollment_id}).first()
        if e is None or e._mapping["status"] != "ACTIVE":
            return []
        m = e._mapping
        rows = self.connection.execute(text("""SELECT a.scope_type,a.scope_ref,f.code AS fee_code FROM school_admission_conditions a
              LEFT JOIN fee_types f ON f.id=a.fee_type_id
             WHERE a.school_id=:sid AND a.academic_year_id=:y AND a.active AND a.required AND a.payment_timing='AT_ENROLLMENT'
             ORDER BY a.sort_order,a.label"""), {"sid": school_id, "y": m["academic_year_id"]}).all()
        month = self.settings.get_billing_policy(school_id).get("month_due_at_enrollment")
        out: list[tuple[str, str | None]] = []
        for r in rows:
            scope, ref, code = r._mapping["scope_type"], r._mapping["scope_ref"], r._mapping["fee_code"]
            hit = (scope == "SCHOOL" or (scope == "SECTION" and ref == str(m["section_id"])) or (scope == "ACADEMIC_CLASS" and ref == m["level"])
                   or (scope == "CLASS" and ref == str(m["class_id"])))
            if not hit or not code:
                continue
            item = (code, month) if is_tuition_code(code) and month else (code, None)
            if item not in out:
                out.append(item)
        if out:
            return out
        if self.settings.admission_review(school_id)["reviewed_at"] is not None:
            return []
        return list(self.LEGACY_BUNDLE)

    def registration_bundle_due(self, school_id: UUID, enrollment_id: UUID) -> dict[str, Any]:
        """Desktop registration_bundle_due: outstanding balance of the bundle per currency; ready = every bundle item exists."""
        bundle = self.registration_bundle(school_id, enrollment_id)
        if not bundle:
            return {"bundle": [], "items": [], "totals": {}, "ready": False}
        rows = self.connection.execute(text("""SELECT fc.id,f.code AS fee_code,s.period_code,fc.label,fc.currency,fc.net_amount,fc.paid_amount
              FROM finance_charges fc JOIN fee_types f ON f.id=fc.fee_type_id LEFT JOIN fee_schedules s ON s.id=fc.schedule_id
             WHERE fc.school_id=:sid AND fc.enrollment_id=:e AND fc.status='ACTIVE'"""), {"sid": school_id, "e": enrollment_id}).all()
        items = []
        for code, month in bundle:
            for r in rows:
                rm = r._mapping
                if canonical_fee_code(rm["fee_code"]) == canonical_fee_code(code) and (month is None or rm["period_code"] == month):
                    items.append({"charge_id": str(rm["id"]), "fee_code": code, "label": rm["label"], "currency": rm["currency"],
                                  "balance": str(max(Decimal("0"), _money(rm["net_amount"]) - _money(rm["paid_amount"])))})
        present = {canonical_fee_code(i["fee_code"]) for i in items}
        totals: dict[str, Decimal] = {}
        for i in items:
            totals[i["currency"]] = totals.get(i["currency"], Decimal("0")) + Decimal(i["balance"])
        return {"bundle": [{"fee_code": c, "month": mo} for c, mo in bundle], "items": items,
                "totals": {k: str(v) for k, v in totals.items()}, "ready": bool(bundle) and {canonical_fee_code(c) for c, _ in bundle} <= present}

    def list_schedules(self, school_id: UUID, academic_year_id: UUID) -> list[dict[str, Any]]:
        rows = self.connection.execute(text("""SELECT s.id,s.class_id,c.label AS class_label,s.fee_type_id,f.label AS fee_label,s.period_code,
                   s.period_label,s.period_order,s.due_date,s.amount,s.currency,s.tariff_id,
                   (SELECT count(*) FROM finance_charges fc WHERE fc.school_id=s.school_id AND fc.schedule_id=s.id) AS charge_count
              FROM fee_schedules s JOIN school_classes c ON c.id=s.class_id JOIN fee_types f ON f.id=s.fee_type_id
             WHERE s.school_id=:sid AND s.academic_year_id=:y AND s.active
             ORDER BY c.label,f.label,coalesce(s.period_order,0)"""), {"sid": school_id, "y": academic_year_id}).all()
        return [{**dict(r._mapping), "amount": str(r._mapping["amount"])} for r in rows]
