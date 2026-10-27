"""N3-G — reports and analyses copied from the Desktop golden master.

  * terrain.financial_report_rows / _settled_only_report_rows: rows grouped by original payment (local calendar day),
    allocations filtered BEFORE aggregation per profile (fee codes, SCOLARITE / ARTICLE group, Inscription + June
    pairing), allocation status TOTAL / ACOMPTE, presentation of deposits from the payment policy (INCLUDE, SEPARATE,
    EXCLUDE_UNTIL_SETTLED — recognised on the day the charge becomes fully paid). Reversed payments never count.
  * terrain.register_generated_report: official number per academic year (PREFIX-NNN), the Excel never consumes one.
  * operations.analysis_by_fee_type / analysis_by_cashier / analysis_advance_funds.
  * financial_views.historical_recovery_status, database.student_account (relevé du compte élève).
Web mapping: a Desktop monthly fee code SCOLARITE_<MOIS> is the Web SCOLARITE charge of that schedule month; school
articles are the product sales (payments carrying a finance_product_sales row).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from sqlalchemy import text, bindparam
from sqlalchemy.engine import Connection

from edusync.adapters.postgres_settings import PostgresSettingsRepository
from edusync.shared.domain.fee_codes import canonical_fee_code, is_tuition_code
from edusync.modules.finance_reports.domain.periodic import MONTH_CODE_NAMES, PERIOD_LABELS, REPORT_PROFILES

CENT = Decimal("0.01")
LOCAL_DAY = "(p.created_at AT TIME ZONE 'Africa/Lubumbashi')::date"


def money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def _scolarite(code: str) -> bool:
    return is_tuition_code(code)


class PostgresPeriodicReportsRepository:
    def __init__(self, connection: Connection):
        self.c = connection

    # ---------- raw material ----------
    @staticmethod
    def _scope_clause(scopes):
        if scopes is None or any(t == "SCHOOL" for t, _ in scopes):
            return "TRUE", {}
        sections = sorted({str(v).upper() for t, v in scopes if t == "SECTION" and v})
        classes = sorted({str(v).upper() for t, v in scopes if t == "CLASS" and v})
        parts, params = [], {}
        if sections:
            parts.append("upper(ss_scope.code) IN :scope_sections")
            params["scope_sections"] = sections
        if classes:
            parts.append("upper(sc_scope.code) IN :scope_classes")
            params["scope_classes"] = classes
        return ("(" + " OR ".join(parts) + ")" if parts else "FALSE"), params

    @staticmethod
    def _scoped_sql(sql, params):
        stmt = text(sql)
        for key in ("scope_sections", "scope_classes"):
            if key in params:
                stmt = stmt.bindparams(bindparam(key, expanding=True))
        return stmt

    def _allocations(self, school_id: UUID, *, end_date: date, start_date: date | None, year_id: UUID | None, scopes=None) -> list[dict[str, Any]]:
        scope_where, scope_params = self._scope_clause(scopes)
        rows = self.c.execute(self._scoped_sql(f"""
            SELECT p.id AS payment_id, {LOCAL_DAY} AS paid_day, p.created_at, p.currency, a.amount AS allocation_amount, fc.id AS charge_id, fc.net_amount,
                   upper(coalesce(ft.code,'')) AS fee_code, coalesce(fsch.period_code,'') AS period_code, coalesce(ft.label, fc.label) AS fee_label,
                   coalesce(fc.period_label, '') AS period_label, st.id AS student_id, st.matricule, st.last_name, st.middle_name, st.first_name,
                   sc.label AS class_label
              FROM finance_payments p JOIN finance_payment_allocations a ON a.payment_id=p.id JOIN finance_charges fc ON fc.id=a.charge_id
              LEFT JOIN fee_types ft ON ft.id=fc.fee_type_id LEFT JOIN fee_schedules fsch ON fsch.id=fc.schedule_id
              JOIN enrollments e ON e.id=p.enrollment_id JOIN students st ON st.id=e.student_id LEFT JOIN school_classes sc ON sc.id=e.class_id JOIN school_classes sc_scope ON sc_scope.id=e.class_id JOIN school_sections ss_scope ON ss_scope.id=sc_scope.section_id
             WHERE p.school_id=:s AND NOT EXISTS (SELECT 1 FROM finance_payment_reversals r WHERE r.payment_id=p.id)
               AND {LOCAL_DAY} <= :end AND (CAST(:start AS date) IS NULL OR {LOCAL_DAY} >= CAST(:start AS date))
               AND (CAST(:y AS uuid) IS NULL OR e.academic_year_id=CAST(:y AS uuid))
             AND {scope_where} ORDER BY p.created_at, p.id""", scope_params), {"s": school_id, "end": end_date, "start": start_date, "y": str(year_id) if year_id else None, **scope_params}).mappings().all()
        out = []
        for r in rows:
            d = dict(r)
            code = canonical_fee_code(d["fee_code"])          # Web MINERVAL reads as Desktop SCOLARITE
            keys = {code}
            if d["period_code"] in MONTH_CODE_NAMES:
                keys.add(f"{code}_{MONTH_CODE_NAMES[d['period_code']]}")
            d["keys"] = keys
            d["observation_label"] = (f"{d['fee_label']} — {d['period_label']}" if d["period_label"] else d["fee_label"]).strip()
            out.append(d)
        has_inscription = {d["payment_id"] for d in out if d["fee_code"] == "INSCRIPTION"}
        for d in out:
            d["has_inscription"] = d["payment_id"] in has_inscription
        return out

    def _sales(self, school_id: UUID, *, start_date: date, end_date: date, year_id: UUID | None, scopes=None) -> list[dict[str, Any]]:
        scope_where, scope_params = self._scope_clause(scopes)
        rows = self.c.execute(self._scoped_sql(f"""
            SELECT p.id AS payment_id, {LOCAL_DAY} AS paid_day, p.currency, p.amount, pr.label AS product_label, ps.quantity,
                   st.id AS student_id, st.matricule, st.last_name, st.middle_name, st.first_name, sc.label AS class_label
              FROM finance_payments p JOIN finance_product_sales ps ON ps.payment_id=p.id JOIN school_products pr ON pr.id=ps.product_id
              LEFT JOIN enrollments e ON e.id=p.enrollment_id LEFT JOIN students st ON st.id=e.student_id LEFT JOIN school_classes sc ON sc.id=e.class_id LEFT JOIN school_classes sc_scope ON sc_scope.id=e.class_id LEFT JOIN school_sections ss_scope ON ss_scope.id=sc_scope.section_id
             WHERE p.school_id=:s AND NOT EXISTS (SELECT 1 FROM finance_payment_reversals r WHERE r.payment_id=p.id)
               AND {LOCAL_DAY} BETWEEN :start AND :end AND (CAST(:y AS uuid) IS NULL OR e.academic_year_id=CAST(:y AS uuid))
             AND {scope_where} ORDER BY p.created_at""", scope_params), {"s": school_id, "start": start_date, "end": end_date, "y": str(year_id) if year_id else None, **scope_params}).mappings().all()
        return [dict(r) for r in rows]

    @staticmethod
    def _eligible(profile_code: str, profile: dict, r: dict) -> bool:
        codes = profile.get("fee_codes")
        if codes and not (set(codes) & r["keys"]):
            return False
        if profile.get("report_group") == "SCOLARITE" and not _scolarite(r["fee_code"]):
            return False
        if profile.get("report_group") == "ARTICLE":
            return False                                   # articles are the product sales
        if profile_code == "INSCRIPTION_JUIN" and not r["has_inscription"]:
            return False
        if profile_code == "FRAIS_SCOLAIRES" and r["has_inscription"]:
            return False
        return True

    @staticmethod
    def _row(item: dict, key: str) -> dict[str, Any]:
        return {"payment_id": key, "paid_day": item["paid_day"], "student_id": str(item["student_id"]) if item.get("student_id") else None,
                "matricule": item.get("matricule"), "last_name": item.get("last_name"), "middle_name": item.get("middle_name"),
                "first_name": item.get("first_name"), "class_label": item.get("class_label"), "currency": item["currency"], "amount": Decimal("0"), "_labels": []}

    # ---------- Desktop financial_report_rows ----------
    def report_rows(self, school_id: UUID, *, start_date: date, end_date: date, profile_code: str = "CONSOLIDE", year_id: UUID | None = None, scopes=None) -> dict[str, Any]:
        profile = REPORT_PROFILES.get(profile_code)
        if not profile:
            raise ValueError("Profil de rapport inconnu")
        if start_date > end_date:
            raise ValueError("La date de début doit précéder la date de fin")
        mode = PostgresSettingsRepository(self.c).get_payment_policy(school_id).get("partial_reporting_mode") or "SEPARATE"
        if mode == "EXCLUDE_UNTIL_SETTLED":
            return self._settled_only(school_id, start_date=start_date, end_date=end_date, profile_code=profile_code, profile=profile, year_id=year_id, scopes=scopes)
        allocations = self._allocations(school_id, end_date=end_date, start_date=None, year_id=year_id, scopes=scopes)
        cumulative: dict[str, Decimal] = {}
        grouped: dict[str, dict] = {}
        for item in allocations:                     # chronological: cumulative paid on the charge up to this payment
            cumulative[item["charge_id"]] = cumulative.get(item["charge_id"], Decimal("0")) + money(item["allocation_amount"])
            if item["paid_day"] < start_date or not self._eligible(profile_code, profile, item):
                continue
            row = grouped.setdefault(str(item["payment_id"]), {**self._row(item, str(item["payment_id"])), "_statuses": []})
            status = "TOTAL" if cumulative[item["charge_id"]] >= money(item["net_amount"]) else "ACOMPTE"
            row["_statuses"].append(status)
            label = item["observation_label"] or "Paiement"
            if status == "ACOMPTE":
                label += " (acompte)"
            if label not in row["_labels"]:
                row["_labels"].append(label)
            row["amount"] += money(item["allocation_amount"])
        if profile_code in ("CONSOLIDE", "ARTICLES_SCOLAIRES"):
            for sale in self._sales(school_id, start_date=start_date, end_date=end_date, year_id=year_id, scopes=scopes):
                row = grouped.setdefault(str(sale["payment_id"]), {**self._row(sale, str(sale["payment_id"])), "_statuses": []})
                row["_statuses"].append("TOTAL")
                label = f"{sale['product_label']} × {money(sale['quantity']).normalize()}"
                if label not in row["_labels"]:
                    row["_labels"].append(label)
                row["amount"] += money(sale["amount"])
        rows = list(grouped.values())
        for row in rows:
            row["observation"] = " + ".join(row.pop("_labels")) or "Paiement"
            statuses = set(row.pop("_statuses"))
            row["reporting_status"] = "MIXTE" if len(statuses) > 1 else (next(iter(statuses)) if statuses else "TOTAL")
            if mode == "SEPARATE" and row["reporting_status"] == "ACOMPTE":
                row["observation"] = "Acompte · " + row["observation"]
            elif mode == "SEPARATE" and row["reporting_status"] == "MIXTE":
                row["observation"] = "Paiement mixte · " + row["observation"]
        rows.sort(key=lambda r: (r["paid_day"], r["last_name"] or "", r["middle_name"] or "", r["first_name"] or ""))
        return self._finish(profile_code, profile, start_date, end_date, rows, mode)

    def _settled_only(self, school_id: UUID, *, start_date: date, end_date: date, profile_code: str, profile: dict, year_id: UUID | None, scopes=None) -> dict[str, Any]:
        """Desktop _settled_only_report_rows: an instalment is recognised on the day its charge becomes fully paid."""
        by_charge: dict[str, list[dict]] = {}
        for item in self._allocations(school_id, end_date=end_date, start_date=None, year_id=year_id, scopes=scopes):
            if self._eligible(profile_code, profile, item):
                by_charge.setdefault(item["charge_id"], []).append(item)
        grouped: dict[tuple, dict] = {}
        for allocs in by_charge.values():
            cumul, settled_on = Decimal("0"), None
            net = money(allocs[0]["net_amount"])
            for a in allocs:
                cumul += money(a["allocation_amount"])
                if cumul >= net:
                    settled_on = a["paid_day"]; break
            if not settled_on or settled_on < start_date or settled_on > end_date:
                continue
            base = allocs[0]
            key = (str(base["student_id"]), settled_on, base["currency"])
            row = grouped.setdefault(key, {**self._row({**base, "paid_day": settled_on}, f"SETTLED:{key[0]}:{settled_on}:{key[2]}"), "reporting_status": "SOLDE_RECONNU"})
            row["amount"] += min(cumul, net)
            label = base["observation_label"] or "Paiement"
            if label not in row["_labels"]:
                row["_labels"].append(label)
        rows = list(grouped.values())
        for row in rows:
            row["observation"] = " + ".join(row.pop("_labels")) + " · soldé"
        rows.sort(key=lambda r: (r["paid_day"], r["last_name"] or "", r["middle_name"] or "", r["first_name"] or ""))
        return self._finish(profile_code, profile, start_date, end_date, rows, "EXCLUDE_UNTIL_SETTLED")

    @staticmethod
    def _finish(profile_code, profile, start_date, end_date, rows, mode) -> dict[str, Any]:
        totals = {"CDF": Decimal("0"), "USD": Decimal("0")}
        for row in rows:
            totals[row["currency"]] = totals.get(row["currency"], Decimal("0")) + row["amount"]
            row["amount"] = str(money(row["amount"]))
        return {"profile_code": profile_code, "profile": {k: (list(v) if isinstance(v, tuple) else v) for k, v in profile.items()},
                "start_date": str(start_date), "end_date": str(end_date), "rows": rows, "totals": {k: str(money(v)) for k, v in totals.items()},
                "partial_reporting_mode": mode}

    # ---------- Desktop register_generated_report ----------
    def register(self, school_id: UUID, *, user_id: UUID, profile_code: str, period_type: str, start_date: date, end_date: date, report: dict, request_key: str | None = None) -> dict[str, Any]:
        if profile_code not in REPORT_PROFILES:
            raise ValueError("Profil de rapport inconnu")
        if period_type not in PERIOD_LABELS:
            raise ValueError("Type de période invalide")
        year = self.c.execute(text("SELECT id FROM academic_years WHERE school_id=:s AND status='ACTIVE' LIMIT 1"), {"s": school_id}).scalar_one_or_none()
        if not year:
            raise ValueError("Aucune année scolaire active")
        n = self.c.execute(text("""INSERT INTO finance_report_sequences(school_id,academic_year_id,last_number) VALUES(:s,:y,1)
            ON CONFLICT(school_id,academic_year_id) DO UPDATE SET last_number=finance_report_sequences.last_number+1 RETURNING last_number"""),
            {"s": school_id, "y": year}).scalar_one()
        prefix = (self.c.execute(text("SELECT report_prefix FROM school_print_settings WHERE school_id=:s"), {"s": school_id}).scalar_one_or_none() or "RAP").strip().upper()
        label = f"{prefix}-{int(n):03d}"
        import json
        rid = self.c.execute(text("""INSERT INTO finance_generated_reports(school_id,academic_year_id,report_no,report_label,profile_code,period_type,start_date,end_date,
                partial_reporting_mode,totals,generated_by,request_key) VALUES(:s,:y,:n,:l,:p,:t,:a,:b,:m,CAST(:tot AS jsonb),:u,:rk) RETURNING id"""),
            {"s": school_id, "y": year, "n": n, "l": label, "p": profile_code, "t": period_type, "a": start_date, "b": end_date,
             "m": report["partial_reporting_mode"], "tot": json.dumps(report["totals"]), "u": user_id, "rk": request_key}).scalar_one()
        return {"id": str(rid), "number": int(n), "label": label}

    def generated(self, school_id: UUID, limit: int = 200) -> list[dict[str, Any]]:
        return [dict(r) for r in self.c.execute(text("""SELECT * FROM finance_generated_reports WHERE school_id=:s ORDER BY generated_at DESC LIMIT :l"""),
                                                {"s": school_id, "l": max(1, min(int(limit), 2000))}).mappings().all()]

    # ---------- Desktop analyses ----------
    def _year(self, school_id: UUID, year_id: UUID | None):
        return self.c.execute(text("""SELECT id FROM academic_years WHERE school_id=:s AND (CAST(:y AS uuid) IS NULL OR id=CAST(:y AS uuid))
            ORDER BY (status='ACTIVE') DESC, start_date DESC LIMIT 1"""), {"s": school_id, "y": str(year_id) if year_id else None}).scalar_one_or_none()

    def analysis_by_fee_type(self, school_id: UUID, year_id: UUID | None = None) -> list[dict[str, Any]]:
        y = self._year(school_id, year_id)
        rows = self.c.execute(text("""SELECT upper(coalesce(ft.code,'')) AS fee_code, coalesce(ft.label, 'Autres frais') AS fee_name, fc.currency,
                count(DISTINCT fc.enrollment_id) AS students, sum(coalesce(fc.gross_amount, fc.net_amount)) AS gross_expected,
                sum(coalesce(fc.discount_amount,0)) + sum(finance_charge_decision_amount(fc.id)) AS discounts,
                sum(fc.net_amount - finance_charge_decision_amount(fc.id)) AS net_expected, sum(fc.paid_amount) AS paid
              FROM finance_charges fc JOIN enrollments e ON e.id=fc.enrollment_id LEFT JOIN fee_types ft ON ft.id=fc.fee_type_id
             WHERE fc.school_id=:s AND e.academic_year_id=:y AND e.status='VALIDATED' AND fc.status='ACTIVE'
             GROUP BY 1,2,3 ORDER BY 2,3"""), {"s": school_id, "y": y}).mappings().all()
        return [{**{k: (str(money(v)) if isinstance(v, Decimal) else v) for k, v in dict(r).items()}, "balance": str(money(r["net_expected"]) - money(r["paid"]))} for r in rows]

    def analysis_by_cashier(self, school_id: UUID, year_id: UUID | None = None) -> list[dict[str, Any]]:
        y = self._year(school_id, year_id)
        rows = self.c.execute(text("""SELECT p.actor_user_id AS cashier_id, p.currency, count(*) AS payment_count, sum(p.amount) AS amount
              FROM finance_payments p JOIN enrollments e ON e.id=p.enrollment_id
             WHERE p.school_id=:s AND e.academic_year_id=:y AND NOT EXISTS (SELECT 1 FROM finance_payment_reversals r WHERE r.payment_id=p.id)
             GROUP BY 1,2 ORDER BY 1,2"""), {"s": school_id, "y": y}).mappings().all()
        return [{**dict(r), "cashier_id": str(r["cashier_id"]), "amount": str(money(r["amount"]))} for r in rows]

    def analysis_advance_funds(self, school_id: UUID, year_id: UUID | None = None) -> list[dict[str, Any]]:
        y = self._year(school_id, year_id)
        rows = self.c.execute(text("""SELECT f.currency, count(*) AS fund_count, sum(f.amount) AS received_total,
                sum(CASE WHEN f.status IN ('ACTIF','EPUISE') THEN f.amount ELSE 0 END) AS retained_total,
                sum(CASE WHEN f.status IN ('ACTIF','EPUISE') THEN f.allocated_amount ELSE 0 END) AS allocated_total,
                sum(CASE WHEN f.status='ACTIF' THEN f.available_amount ELSE 0 END) AS available_total,
                sum(CASE WHEN f.status IN ('ANNULE','REMBOURSE') THEN f.amount ELSE 0 END) AS reversed_total
              FROM finance_advance_fund_state f JOIN enrollments e ON e.id=f.enrollment_id
             WHERE f.school_id=:s AND e.academic_year_id=:y GROUP BY f.currency ORDER BY f.currency"""), {"s": school_id, "y": y}).mappings().all()
        return [{k: (str(money(v)) if isinstance(v, Decimal) else v) for k, v in dict(r).items()} for r in rows]

    # ---------- Desktop historical_recovery_status ----------
    def historical_recovery_status(self, school_id: UUID, *, year_id: UUID | None, currency: str) -> dict[str, int]:
        """Desktop: PRET / A_VERIFIER / DEJA_IMPORTE counts of the historical import, per year and currency (Web: VALID /
        WARNING + ERROR / IMPORTED rows of the financial history import, year read through the target charge)."""
        y = self._year(school_id, year_id)
        rows = self.c.execute(text("""SELECT r.status, count(*) AS n FROM financial_history_import_rows r
              LEFT JOIN finance_charges fc ON fc.id = CAST(NULLIF(r.normalized_payload->>'charge_id','') AS uuid)
              LEFT JOIN enrollments e ON e.id = fc.enrollment_id
              JOIN financial_history_import_batches b ON b.id = r.batch_id AND b.status <> 'CANCELLED'
             WHERE r.school_id=:s AND (e.academic_year_id IS NULL OR e.academic_year_id=:y)
               AND upper(coalesce(r.normalized_payload->>'currency', fc.currency, ''))=:cur GROUP BY r.status"""),
            {"s": school_id, "y": y, "cur": currency}).mappings().all()
        counts = {r["status"]: int(r["n"]) for r in rows}
        return {"ready": counts.get("VALID", 0), "to_verify": counts.get("WARNING", 0) + counts.get("ERROR", 0),
                "posted": counts.get("IMPORTED", 0), "total": sum(counts.values())}

    # ---------- Desktop student_account (relevé du compte élève) ----------
    def student_account(self, school_id: UUID, student_id: UUID) -> dict[str, Any]:
        st = self.c.execute(text("""SELECT s.id, s.matricule, s.last_name, s.middle_name, s.first_name, e.id AS enrollment_id, sc.label AS class_label,
                sec.label AS section_label, y.label AS year_label
              FROM students s JOIN enrollments e ON e.student_id=s.id JOIN academic_years y ON y.id=e.academic_year_id
              JOIN school_classes sc ON sc.id=e.class_id LEFT JOIN school_sections sec ON sec.id=sc.section_id
             WHERE s.school_id=:sch AND s.id=:st ORDER BY (y.status='ACTIVE') DESC, y.start_date DESC LIMIT 1"""), {"sch": school_id, "st": student_id}).mappings().first()
        if not st:
            raise LookupError("Élève introuvable")
        charges = [dict(r) for r in self.c.execute(text("""SELECT fc.id, coalesce(fc.period_label, fc.label) AS fee_name, fc.label, fc.currency,
                (fc.net_amount - finance_charge_decision_amount(fc.id)) AS net_amount, fc.paid_amount AS paid,
                GREATEST(fc.net_amount - finance_charge_decision_amount(fc.id) - fc.paid_amount, 0) AS balance, fc.due_date
              FROM finance_charges fc WHERE fc.school_id=:s AND fc.enrollment_id=:e AND fc.status='ACTIVE'
             ORDER BY fc.due_date NULLS FIRST, fc.created_at"""), {"s": school_id, "e": st["enrollment_id"]}).mappings().all()]
        payments = [dict(r) for r in self.c.execute(text("""SELECT CAST(p.id AS text) AS payment_id, p.receipt_number AS receipt_no, p.created_at AS paid_at, p.payment_mode AS mode, p.amount, p.currency,
                CASE WHEN r.reversal_type='ANNULATION' THEN 'ANNULE' WHEN r.reversal_type='REMBOURSEMENT' THEN 'REMBOURSE' ELSE 'VALIDE' END AS status
              FROM finance_payments p LEFT JOIN finance_payment_reversals r ON r.payment_id=p.id
             WHERE p.school_id=:s AND p.enrollment_id=:e ORDER BY p.created_at DESC"""), {"s": school_id, "e": st["enrollment_id"]}).mappings().all()]
        summary: dict[str, dict[str, Decimal]] = {}
        for ch in charges:
            b = summary.setdefault(ch["currency"], {"net_expected": Decimal("0"), "paid": Decimal("0"), "balance": Decimal("0")})
            b["net_expected"] += money(ch["net_amount"]); b["paid"] += money(ch["paid"]); b["balance"] += money(ch["balance"])
        summ = [{"currency": cur, **{k: str(v) for k, v in b.items()}, "recovery_rate": float(round(b["paid"] / b["net_expected"] * 100, 1)) if b["net_expected"] else 0.0}
                for cur, b in sorted(summary.items())]
        return {"student": {k: (str(v) if isinstance(v, UUID) else v) for k, v in dict(st).items()}, "summary": summ,
                "charges": [{**c, "id": str(c["id"]), "net_amount": str(money(c["net_amount"])), "paid": str(money(c["paid"])), "balance": str(money(c["balance"]))} for c in charges],
                "payments": [{**p, "amount": str(money(p["amount"]))} for p in payments]}
