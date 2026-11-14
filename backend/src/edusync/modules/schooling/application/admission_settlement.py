"""Atomic enrollment against the school's enrollment conditions (owner report 2026-11-06).

« On ne peut pas enregistrer un élève inscrit qui n'a pas rempli les conditions fixées par l'école. »

The conditions are the school's AT_ENROLLMENT obligations (settings → Inscriptions: e.g. Inscription + juin), read by
PostgresFeeScheduleRepository.registration_bundle_due once the pupils and their charges exist *inside the current
transaction*. This module decides, per child, what must be paid now and who is exempted:

* the school's policy (ENROLLMENT document) may exempt the children of staff members and/or the benefit beneficiaries;
* the direction may grant a waiver (« dérogation ») child by child, with a reason (finance.decisions.create);
* a child whose obligations are fully covered by a benefit has nothing to pay anyway (balance 0).

Everything else must be paid in full in the same transaction (family basket: one payment per child, one receipt per
child), otherwise the caller raises ConditionsNotPaid and the whole enrollment is rolled back: no pupil, no family,
no charge is left behind.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text


class ConditionsNotPaid(ValueError):
    """The enrollment conditions are due and no complete payment was given: nothing is enrolled."""


def money(v: Any) -> Decimal:
    return Decimal(str(v or "0")).quantize(Decimal("0.01"))


def fmt_totals(totals: dict[str, Decimal]) -> str:
    def one(cur: str, amount: Decimal) -> str:
        s = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
        return f"{s[:-3] if s.endswith(',00') else s} {'FC' if cur == 'CDF' else '$'}"
    return " + ".join(one(c, a) for c, a in sorted(totals.items()) if a > 0)


def conditions_due(conn, school_id: UUID, enrollments: list[dict[str, Any]], *, policy: dict[str, Any],
                   waivers: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Per child: obligations required at enrollment, still unpaid, and the exemption that applies (if any).

    ``enrollments`` lists, in form order, {index, enrollment_id, child} where child is the submitted child dict."""
    from edusync.adapters.postgres_fee_schedules import PostgresFeeScheduleRepository
    fees = PostgresFeeScheduleRepository(conn)
    exempt_staff = bool(policy.get("conditions_exempt_staff_children"))
    exempt_benefit = bool(policy.get("conditions_exempt_benefit_beneficiaries"))
    out_children: list[dict[str, Any]] = []
    totals: dict[str, Decimal] = {}
    for e in enrollments:
        child, eid, idx = e["child"], UUID(str(e["enrollment_id"])), int(e["index"])
        info = conn.execute(text("""SELECT s.id AS student_id, trim(concat_ws(' ',s.last_name,s.middle_name,s.first_name)) AS name,
                c.label AS class_label FROM enrollments en JOIN students s ON s.id=en.student_id AND s.school_id=en.school_id
                JOIN school_classes c ON c.id=en.class_id WHERE en.school_id=:s AND en.id=:e"""), {"s": school_id, "e": eid}).mappings().first()
        due = fees.registration_bundle_due(school_id, eid)
        items = [{"charge_id": i["charge_id"], "label": i["label"], "currency": i["currency"], "amount": str(money(i["balance"]))}
                 for i in due.get("items", []) if money(i["balance"]) > 0]
        exemption = None
        if idx in waivers:
            exemption = {"kind": "WAIVER", "label": "Dérogation de la direction", "reason": waivers[idx].get("reason")}
        elif exempt_benefit and (child.get("large_family_beneficiary") or child.get("staff_beneficiary")):
            exemption = {"kind": "BENEFIT", "label": "Bénéficiaire d’un avantage (exempté par la politique de l’école)"}
        elif exempt_staff and child.get("staff_member_id"):
            exemption = {"kind": "STAFF_CHILD", "label": "Enfant du personnel (exempté par la politique de l’école)"}
        # A condition this class should carry but no fee of the class bills (e.g. June not configured for 4ème HP):
        # the child is NOT free — the enrollment is refused until the fees are configured or the direction waives it.
        missing = [m["label"] for m in due.get("missing", [])]
        child_totals: dict[str, Decimal] = {}
        for i in items:
            child_totals[i["currency"]] = child_totals.get(i["currency"], Decimal("0")) + money(i["amount"])
        if exemption is None:
            for cur, amount in child_totals.items():
                totals[cur] = totals.get(cur, Decimal("0")) + amount
        out_children.append({
            "index": idx, "enrollment_id": str(eid), "student_id": str(info["student_id"]) if info else None,
            "name": info["name"] if info else "", "class_label": info["class_label"] if info else "",
            "items": items, "totals": {k: str(v) for k, v in child_totals.items()},
            "exemption": exemption, "to_pay": exemption is None and bool(items),
            "missing": missing, "blocked": exemption is None and bool(missing),
            "configured": bool(due.get("bundle")), "complete": bool(due.get("ready")),
        })
    blocked = [c for c in out_children if c["blocked"]]
    return {"children": out_children, "totals": {k: str(v) for k, v in totals.items() if v > 0},
            "requires_payment": any(v > 0 for v in totals.values()), "blocked": bool(blocked),
            "blocked_message": blocked_message(blocked) if blocked else None}


def blocked_message(blocked: list[dict[str, Any]]) -> str:
    """French, child by child: which required fee is not configured for which class, and what to do."""
    def one(c: dict[str, Any]) -> str:
        return f"{' et '.join(dict.fromkeys(c['missing']))} pour {c['name'] or 'l’enfant'} ({c['class_label'] or 'classe'})"
    return ("Conditions d’inscription non configurées : " + " ; ".join(one(c) for c in blocked)
            + ". Aucun enfant n’a été inscrit : configurez ces frais pour la classe (Finances → Frais) ou accordez une dérogation.")


def basket_lines(due: dict[str, Any]) -> list[dict[str, Any]]:
    """One family-basket line per child and currency: exactly the unpaid enrollment obligations (no more, no less)."""
    lines = []
    for c in due["children"]:
        if not c["to_pay"]:
            continue
        by_cur: dict[str, list[dict[str, Any]]] = {}
        for i in c["items"]:
            by_cur.setdefault(i["currency"], []).append(i)
        for cur, items in sorted(by_cur.items()):
            lines.append({"enrollment_id": c["enrollment_id"], "charge_ids": [i["charge_id"] for i in items],
                          "amount": str(sum(money(i["amount"]) for i in items)), "currency": cur})
    return lines
