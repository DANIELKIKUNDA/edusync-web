"""N3-H — schooling parity copied from the Desktop golden master.

  * schooling.find_probable_students: likely existing pupils before a new record (name parts, birth date), 8 at most.
  * schooling.student_historical_arrears: outstanding balances by earlier year and currency, never mixed with a new year.
  * schooling.family_contact_diagnostics, family_overview_summary, family_kpi_details (LARGE_ELIGIBLE, BENEFICIARIES,
    STAFF_CHILDREN).
  * schooling.product_sales_report: article sales of a period, totals per currency.
  * terrain.contribution_register: required / delivered / remaining per pupil and contribution item.
  * services.documents._match_existing_student / preview_enrollment_date_repair (read-only diagnostic).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from difflib import SequenceMatcher
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

CENT = Decimal("0.01")


def money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def match_key(*values) -> str:
    """Desktop _student_match_key: accents removed, lower case, letters and digits only."""
    s = unicodedata.normalize("NFKD", " ".join(str(v or "") for v in values)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def _plain(row) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, (UUID, Decimal)) else v) for k, v in dict(row).items()}


class PostgresSchoolingParityRepository:
    def __init__(self, connection: Connection):
        self.c = connection

    def probable_students(self, school_id: UUID, *, last_name: str, middle_name: str = "", first_name: str = "", birth_date: date | None = None) -> list[dict]:
        last_name = (last_name or "").strip()
        if not last_name:
            return []
        rows = self.c.execute(text("""SELECT s.id, s.matricule, s.last_name, s.middle_name, s.first_name, s.birth_date, s.status, f.display_name AS family_name
              FROM students s LEFT JOIN families f ON f.id=s.family_id
             WHERE s.school_id=:sid AND upper(s.last_name) LIKE upper(:ln)
               AND (:mn = '' OR upper(coalesce(s.middle_name,'')) LIKE upper(:mnl)) AND (:fn = '' OR upper(coalesce(s.first_name,'')) LIKE upper(:fnl))
               AND (CAST(:bd AS date) IS NULL OR s.birth_date = CAST(:bd AS date))
             ORDER BY s.last_name, s.middle_name, s.first_name LIMIT 8"""),
            {"sid": school_id, "ln": f"%{last_name}%", "mn": (middle_name or "").strip(), "mnl": f"%{(middle_name or '').strip()}%",
             "fn": (first_name or "").strip(), "fnl": f"%{(first_name or '').strip()}%", "bd": birth_date}).mappings().all()
        return [_plain(r) for r in rows]

    def historical_arrears(self, school_id: UUID, student_id: UUID, *, excluding_year_id: UUID | None = None) -> list[dict]:
        if excluding_year_id is None:
            excluding_year_id = self.c.execute(text("SELECT id FROM academic_years WHERE school_id=:s AND status='ACTIVE' LIMIT 1"), {"s": school_id}).scalar_one_or_none()
        rows = self.c.execute(text("""SELECT ay.id AS year_id, ay.label AS year_label, fc.currency,
                sum(GREATEST(fc.net_amount - finance_charge_decision_amount(fc.id) - fc.paid_amount
                    - COALESCE((SELECT sum(r.amount) FROM finance_charge_regularizations r WHERE r.charge_id=fc.id),0), 0)) AS balance
              FROM enrollments e JOIN academic_years ay ON ay.id=e.academic_year_id JOIN finance_charges fc ON fc.enrollment_id=e.id AND fc.status='ACTIVE'
             WHERE e.school_id=:s AND e.student_id=:st AND e.status='VALIDATED' AND (CAST(:x AS uuid) IS NULL OR ay.id<>CAST(:x AS uuid))
             GROUP BY ay.id, ay.label, ay.start_date, fc.currency HAVING sum(GREATEST(fc.net_amount - finance_charge_decision_amount(fc.id) - fc.paid_amount
                    - COALESCE((SELECT sum(r.amount) FROM finance_charge_regularizations r WHERE r.charge_id=fc.id),0), 0)) > 0
             ORDER BY ay.start_date DESC, fc.currency"""), {"s": school_id, "st": student_id, "x": str(excluding_year_id) if excluding_year_id else None}).mappings().all()
        return [{**_plain(r), "balance": str(money(r["balance"]))} for r in rows]

    def family_contact_diagnostics(self, school_id: UUID) -> dict[str, int]:
        one = lambda sql: int(self.c.execute(text(sql), {"s": school_id}).scalar_one() or 0)
        return {
            "without_responsible": one("""SELECT count(*) FROM families f WHERE f.school_id=:s AND NOT EXISTS
                (SELECT 1 FROM family_guardians fg WHERE fg.family_id=f.id AND fg.active)"""),
            "multiple_primary": one("""SELECT count(*) FROM (SELECT family_id FROM family_guardians WHERE school_id=:s AND active AND is_primary
                GROUP BY family_id HAVING count(*)>1) x"""),
            "responsible_without_phone": one("""SELECT count(*) FROM family_guardians fg JOIN guardians g ON g.id=fg.guardian_id
                WHERE fg.school_id=:s AND fg.active AND coalesce(btrim(g.phone),'')=''"""),
            "shared_phones": one("""SELECT count(*) FROM (SELECT coalesce(g.normalized_phone, g.phone) AS ph FROM family_guardians fg JOIN guardians g ON g.id=fg.guardian_id
                WHERE fg.school_id=:s AND fg.active AND coalesce(btrim(g.phone),'')<>'' GROUP BY 1 HAVING count(DISTINCT fg.family_id)>1) x"""),
        }

    def _year(self, school_id: UUID, year_id: UUID | None):
        return self.c.execute(text("""SELECT id FROM academic_years WHERE school_id=:s AND (CAST(:y AS uuid) IS NULL OR id=CAST(:y AS uuid))
            ORDER BY (status='ACTIVE') DESC, start_date DESC LIMIT 1"""), {"s": school_id, "y": str(year_id) if year_id else None}).scalar_one_or_none()

    def _large_min(self, school_id: UUID, year) -> int:
        r = self.c.execute(text("""SELECT min_children FROM school_benefit_policies WHERE school_id=:s AND academic_year_id=:y AND benefit_type='LARGE_FAMILY'"""),
                           {"s": school_id, "y": year}).scalar_one_or_none() if self.c.execute(text("SELECT to_regclass('school_benefit_policies') IS NOT NULL")).scalar_one() else None
        return int(r or 5)

    def family_overview(self, school_id: UUID, year_id: UUID | None = None) -> dict[str, int]:
        y = self._year(school_id, year_id); minimum = self._large_min(school_id, y)
        one = lambda sql, **p: int(self.c.execute(text(sql), {"s": school_id, "y": y, **p}).scalar_one() or 0)
        return {
            "families": one("""SELECT count(DISTINCT s.family_id) FROM enrollments e JOIN students s ON s.id=e.student_id
                WHERE e.school_id=:s AND e.academic_year_id=:y AND e.status='VALIDATED' AND s.status='ACTIVE'"""),
            "large_eligible": one("""SELECT count(*) FROM (SELECT s.family_id FROM enrollments e JOIN students s ON s.id=e.student_id
                WHERE e.school_id=:s AND e.academic_year_id=:y AND e.status='VALIDATED' AND s.status='ACTIVE' GROUP BY s.family_id HAVING count(DISTINCT s.id)>=:m) x""", m=minimum),
            "beneficiaries": one("SELECT count(DISTINCT student_id) FROM student_benefits WHERE school_id=:s AND academic_year_id=:y AND active"),
            "staff_children": one("""SELECT count(DISTINCT l.student_id) FROM staff_student_links l JOIN enrollments e ON e.student_id=l.student_id
                WHERE l.school_id=:s AND l.active AND e.academic_year_id=:y AND e.status='VALIDATED'"""),
            "large_family_min_children": minimum,
        }

    def family_kpi_details(self, school_id: UUID, *, metric: str, year_id: UUID | None = None) -> list[dict]:
        y = self._year(school_id, year_id)
        if metric == "LARGE_ELIGIBLE":
            rows = self.c.execute(text("""SELECT f.id AS family_id, f.code AS family_code, f.display_name AS family_name, f.phone,
                    (SELECT g.full_name FROM family_guardians fg JOIN guardians g ON g.id=fg.guardian_id WHERE fg.family_id=f.id AND fg.active ORDER BY fg.is_primary DESC, fg.created_at LIMIT 1) AS primary_responsible,
                    (SELECT g.phone FROM family_guardians fg JOIN guardians g ON g.id=fg.guardian_id WHERE fg.family_id=f.id AND fg.active ORDER BY fg.is_primary DESC, fg.created_at LIMIT 1) AS primary_responsible_phone,
                    count(DISTINCT s.id) AS enrolled_children, string_agg(DISTINCT s.matricule || ' - ' || s.last_name || ' ' || coalesce(s.first_name,''), ', ') AS children
                  FROM families f JOIN students s ON s.family_id=f.id JOIN enrollments e ON e.student_id=s.id
                 WHERE f.school_id=:s AND e.academic_year_id=:y AND e.status='VALIDATED' AND s.status='ACTIVE'
                 GROUP BY f.id HAVING count(DISTINCT s.id)>=:m ORDER BY f.display_name"""), {"s": school_id, "y": y, "m": self._large_min(school_id, y)}).mappings().all()
        elif metric == "BENEFICIARIES":
            rows = self.c.execute(text("""SELECT s.id AS student_id, s.matricule, s.last_name, s.middle_name, s.first_name, f.code AS family_code, f.display_name AS family_name,
                    sb.kind AS benefit_type, sb.configured_percent, sb.applies_to_fee_code, sc.label AS class_label
                  FROM student_benefits sb JOIN students s ON s.id=sb.student_id
                  JOIN enrollments e ON e.student_id=s.id AND e.academic_year_id=sb.academic_year_id AND e.status='VALIDATED'
                  LEFT JOIN families f ON f.id=s.family_id LEFT JOIN school_classes sc ON sc.id=e.class_id
                 WHERE sb.school_id=:s AND sb.academic_year_id=:y AND sb.active ORDER BY sb.kind, s.last_name, s.first_name"""), {"s": school_id, "y": y}).mappings().all()
        elif metric == "STAFF_CHILDREN":
            rows = self.c.execute(text("""SELECT s.id AS student_id, s.matricule, s.last_name, s.middle_name, s.first_name, f.code AS family_code, f.display_name AS family_name,
                    sm.employee_no AS employee_code, concat_ws(' ', sm.last_name, sm.first_name) AS staff_name, coalesce(p.responsibility_mode,'FAMILY') AS finance_mode,
                    l.relationship, sc.label AS class_label
                  FROM staff_student_links l JOIN students s ON s.id=l.student_id
                  JOIN enrollments e ON e.student_id=s.id AND e.academic_year_id=:y AND e.status='VALIDATED'
                  JOIN staff_members sm ON sm.id=l.staff_id LEFT JOIN families f ON f.id=s.family_id LEFT JOIN school_classes sc ON sc.id=e.class_id
                  LEFT JOIN staff_student_finance_preferences p ON p.staff_student_link_id=l.id
                 WHERE l.school_id=:s AND l.active ORDER BY staff_name, s.last_name, s.first_name"""), {"s": school_id, "y": y}).mappings().all()
        else:
            raise ValueError("Indicateur familial inconnu")
        return [_plain(r) for r in rows]

    def product_sales_report(self, school_id: UUID, *, start_date: date, end_date: date) -> dict[str, Any]:
        if start_date > end_date:
            raise ValueError("La date de début doit précéder la date de fin")
        rows = self.c.execute(text("""SELECT ps.id, (p.created_at AT TIME ZONE 'Africa/Lubumbashi') AS sold_at, ps.quantity, ps.unit_price, p.amount AS total_amount, p.currency,
                pr.code AS product_code, pr.label AS product_label, s.matricule, s.last_name, s.middle_name, s.first_name, p.actor_user_id AS cashier_id, p.receipt_number,
                EXISTS (SELECT 1 FROM finance_payment_reversals r WHERE r.payment_id=p.id) AS reversed
              FROM finance_product_sales ps JOIN finance_payments p ON p.id=ps.payment_id JOIN school_products pr ON pr.id=ps.product_id
              LEFT JOIN enrollments e ON e.id=p.enrollment_id LEFT JOIN students s ON s.id=e.student_id
             WHERE ps.school_id=:s AND (p.created_at AT TIME ZONE 'Africa/Lubumbashi')::date BETWEEN :a AND :b ORDER BY p.created_at, s.last_name"""),
            {"s": school_id, "a": start_date, "b": end_date}).mappings().all()
        totals: dict[str, Decimal] = {}
        for r in rows:
            if not r["reversed"]:
                totals[r["currency"]] = totals.get(r["currency"], Decimal("0")) + money(r["total_amount"])
        return {"rows": [_plain(r) for r in rows], "totals": [{"currency": c, "amount": str(a)} for c, a in sorted(totals.items())]}

    def contribution_register(self, school_id: UUID, *, year_id: UUID | None = None, class_id: UUID | None = None) -> dict[str, Any]:
        y = self._year(school_id, year_id)
        items = [_plain(r) for r in self.c.execute(text("""SELECT id, code, label, unit, required_quantity FROM contribution_types WHERE school_id=:s AND enabled ORDER BY label"""),
                                                   {"s": school_id}).mappings().all()]
        students = [_plain(r) for r in self.c.execute(text("""SELECT s.id AS student_id, s.matricule, s.last_name, s.middle_name, s.first_name, s.gender, sc.id AS class_id,
                sc.label AS class_label, ss.label AS section_label
              FROM enrollments e JOIN students s ON s.id=e.student_id JOIN school_classes sc ON sc.id=e.class_id JOIN school_sections ss ON ss.id=sc.section_id
             WHERE e.school_id=:s AND e.academic_year_id=:y AND e.status='VALIDATED' AND (CAST(:c AS uuid) IS NULL OR e.class_id=CAST(:c AS uuid))
             ORDER BY ss.label, sc.label, s.last_name, s.middle_name"""), {"s": school_id, "y": y, "c": str(class_id) if class_id else None}).mappings().all()]
        delivered = {(str(r["student_id"]), str(r["contribution_type_id"])): Decimal(str(r["q"])) for r in self.c.execute(text("""SELECT mc.student_id, mc.contribution_type_id, sum(mc.quantity) AS q
              FROM material_contributions mc JOIN enrollments e ON e.id=mc.enrollment_id WHERE mc.school_id=:s AND mc.academic_year_id=:y
               AND (CAST(:c AS uuid) IS NULL OR e.class_id=CAST(:c AS uuid)) GROUP BY 1,2"""), {"s": school_id, "y": y, "c": str(class_id) if class_id else None}).mappings().all()}
        for st in students:
            st["items"] = {}
            for it in items:
                got = delivered.get((st["student_id"], it["id"]), Decimal("0")); req = Decimal(str(it["required_quantity"] or 0))
                st["items"][it["id"]] = {"required": str(req), "delivered": str(got), "remaining": str(max(Decimal("0"), req - got))}
        return {"items": items, "rows": students}

    # ---------- Desktop _match_existing_student / preview_enrollment_date_repair ----------
    def enrollments_for_year(self, school_id: UUID, year_id) -> list[dict]:
        return [_plain(r) for r in self.c.execute(text("""SELECT e.id AS enrollment_id, e.enrolled_on, e.class_id, s.id AS student_id, s.matricule, s.last_name, s.middle_name,
                s.first_name, s.gender, sc.label AS class_label, sc.code AS class_code
              FROM enrollments e JOIN students s ON s.id=e.student_id LEFT JOIN school_classes sc ON sc.id=e.class_id
             WHERE e.school_id=:s AND e.academic_year_id=:y AND e.status<>'CANCELLED'"""), {"s": school_id, "y": year_id}).mappings().all()]

    @staticmethod
    def match_existing(entries: list[dict], *, name: str, gender: str = "", class_hint: str = "") -> dict[str, Any]:
        key = match_key(name)
        exact = [e for e in entries if match_key(e["last_name"], e["middle_name"], e["first_name"]) == key and (not gender or (e.get("gender") or "") == gender)]
        hint = match_key(class_hint)
        class_matches = [e for e in exact if not hint or hint in (match_key(e.get("class_label")), match_key(e.get("class_code")))]
        candidates = class_matches or exact
        if len(candidates) == 1 and class_matches and hint:
            status = "MATCH_CERTAIN"
        elif len(candidates) == 1:
            status = "MATCH_PROBABLE"
        elif len(candidates) > 1:
            return {"status": "AMBIGU", "confidence": "FAIBLE", "candidates": len(candidates)}
        else:
            return {"status": "NON_TROUVE", "confidence": "NULLE", "candidates": 0}
        e = candidates[0]
        return {"status": status, "confidence": "FORTE" if status == "MATCH_CERTAIN" else "MOYENNE", "candidates": 1, "student_id": e["student_id"],
                "enrollment_id": e["enrollment_id"], "matricule": e["matricule"], "current_enrolled_on": e.get("enrolled_on")}

    def date_repair_preview(self, school_id: UUID, rows: list[dict], *, year_id: UUID | None = None) -> dict[str, Any]:
        y = self._year(school_id, year_id); entries = self.enrollments_for_year(school_id, y)
        summary = {"examined": 0, "certain": 0, "probable": 0, "ambiguous": 0, "not_found": 0, "unchanged": 0}
        items = []
        for r in rows:
            hdate = r.get("date")
            if not hdate:
                items.append({"row": r["row"], "student_name": r["name"], "status": "A_VERIFIER", "warning": r.get("warning") or "Date historique absente"})
                summary["ambiguous"] += 1
                continue
            m = self.match_existing(entries, name=r["name"], gender=r.get("gender") or "", class_hint=r.get("class") or "")
            summary["examined"] += 1
            if m["status"] == "MATCH_CERTAIN":
                summary["unchanged" if str(m.get("current_enrolled_on")) == str(hdate) else "certain"] += 1
            elif m["status"] == "MATCH_PROBABLE":
                summary["probable"] += 1
            elif m["status"] == "AMBIGU":
                summary["ambiguous"] += 1
            else:
                summary["not_found"] += 1
            items.append({"row": r["row"], "student_name": r["name"], **m, "historical_date": str(hdate),
                          "action": "Corriger la date d'inscription" if m["status"] == "MATCH_CERTAIN" and str(m.get("current_enrolled_on")) != str(hdate) else "Aucune"})
        return {"summary": summary, "items": items}

    # ---------- Desktop historical_student_suggestions (Web: the import line carries a matricule) ----------
    def history_suggestions(self, school_id: UUID, *, matricule: str, year_label: str | None, limit: int = 8) -> list[dict]:
        y = self.c.execute(text("""SELECT id FROM academic_years WHERE school_id=:s AND (lower(code)=lower(:l) OR lower(label)=lower(:l)) LIMIT 1"""),
                           {"s": school_id, "l": year_label or ""}).scalar_one_or_none() or self._year(school_id, None)
        source = match_key(matricule)
        out = []
        for e in self.enrollments_for_year(school_id, y):
            cand = match_key(e["matricule"])
            if not source or not cand:
                continue
            score = SequenceMatcher(None, source, cand).ratio()
            confidence = "FORTE" if source == cand or score >= 0.9 else "MOYENNE" if score >= 0.72 else "FAIBLE"
            out.append({"student_id": e["student_id"], "matricule": e["matricule"], "name": " ".join(x for x in (e["last_name"], e["middle_name"], e["first_name"]) if x),
                        "class_label": e.get("class_label"), "score": round(score, 3), "confidence": confidence})
        out.sort(key=lambda x: -x["score"])
        return out[:limit]
