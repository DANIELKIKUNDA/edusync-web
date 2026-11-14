"""Rapport de recouvrement de direction — 14/11/2026 (owner: « un rapport par type de frais, comme celui d'octobre »).

Pure computation, no I/O. Input: one row per (enrollment, charge) in the chosen scope, plus the pupils for whom the
period is not due (arrival after the cut-off day, exemption). Same settlement rule as the class register (VF-01):
settled = min(paid + allocated advance + regularised outside the cash desk, net). A pupil is « concerned » when he owes
something in the scope; « à jour » when everything he owes in the scope is settled.

Mixing fees is only meaningful at a date: the caller keeps, for « tous les frais », only the obligations already due at
the situation date (an unpaid May instalment is not a delay in November)."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Iterable

MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre")
REASON_LABEL = {"ARRIVAL": "Inscrit après la date limite", "EXEMPTION": "Exonéré"}
ZERO = Decimal("0")


def _d(v: Any) -> Decimal:
    return Decimal(str(v or 0))


def french_date(d: date) -> str:
    return f"{d.day} {MOIS[d.month - 1]} {d.year}" if d.day != 1 else f"1er {MOIS[d.month - 1]} {d.year}"


def natural_key(label: str | None) -> tuple:
    """« 2MAT » before « 10MAT », « 7EB » before « 8EB »: numbers compared as numbers."""
    return tuple(int(p) if p.isdigit() else p.upper() for p in re.split(r"(\d+)", label or "") if p)


def rate(collected: Decimal, expected: Decimal) -> Decimal:
    return ZERO if expected <= 0 else (collected * 100 / expected).quantize(Decimal("0.1"))


def _blank() -> dict[str, Any]:
    return {"concerned": 0, "in_order": 0, "not_in_order": 0, "partial": 0, "expected": ZERO, "collected": ZERO, "remaining": ZERO}


def _add(acc: dict[str, Any], st: dict[str, Any]) -> None:
    acc["concerned"] += 1
    acc["expected"] += st["expected"]; acc["collected"] += st["settled"]; acc["remaining"] += st["remaining"]
    if st["remaining"] <= 0:
        acc["in_order"] += 1
    else:
        acc["not_in_order"] += 1
        if st["settled"] > 0:
            acc["partial"] += 1


def _finish(acc: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {**extra, **acc, "rate": rate(acc["collected"], acc["expected"])}


def _students(charges: Iterable[dict[str, Any]], multi: bool = False, key=lambda r: True) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in charges:
        net = _d(r.get("net"))
        if net <= 0 or not key(r):
            continue
        sid = str(r["enrollment_id"])
        st = out.setdefault(sid, {"enrollment_id": sid, "student_name": r.get("student_name") or "", "matricule": r.get("matricule") or "",
                                  "enrolled_on": r.get("enrolled_on"), "class_id": str(r.get("class_id")), "class_label": r.get("class_label") or "",
                                  "section_id": str(r.get("section_id")), "section_label": r.get("section_label") or "",
                                  "contact_name": r.get("contact_name") or "", "contact_phone": r.get("contact_phone") or "",
                                  "expected": ZERO, "settled": ZERO, "missing": []})
        got = min(_d(r.get("paid")) + _d(r.get("advance")) + _d(r.get("outside")), net)
        st["expected"] += net; st["settled"] += got
        if got < net:
            label = r.get("period_label") or r.get("fee_label") or ""
            if multi and r.get("fee_label") and r.get("period_label") and r["period_label"] != r["fee_label"]:
                label = f"{r['fee_label']} {r['period_label']}"
            st["missing"].append(label if got == 0 else f"{label} (partiel)")
    for st in out.values():
        st["remaining"] = max(st["expected"] - st["settled"], ZERO)
    return out


def build_direction_report(charges: list[dict[str, Any]], exemptions: list[dict[str, Any]], *, as_of: date, currency: str,
                           fee_label: str | None = None, period_label: str | None = None, min_class_size: int = 4) -> dict[str, Any]:
    fees_in_scope = {r.get("fee_label") or "" for r in charges if _d(r.get("net")) > 0}
    multi = fee_label is None and len(fees_in_scope) > 1
    students = _students(charges, multi)
    order = lambda st: (natural_key(st["section_label"]), natural_key(st["class_label"]), st["student_name"].upper())

    total, by_section, by_class = _blank(), defaultdict(_blank), defaultdict(_blank)
    class_meta: dict[str, tuple[str, str]] = {}
    for st in students.values():
        _add(total, st); _add(by_section[st["section_label"]], st); _add(by_class[st["class_id"]], st)
        class_meta[st["class_id"]] = (st["class_label"], st["section_label"])

    sections = [_finish(by_section[s], label=s) for s in sorted(by_section, key=natural_key)]
    classes = sorted((_finish(acc, class_id=cid, label=class_meta[cid][0], section_label=class_meta[cid][1]) for cid, acc in by_class.items()),
                     key=lambda c: (natural_key(c["section_label"]), natural_key(c["label"])))

    # Synthèse par type de frais (only meaningful when several fees are mixed).
    fees = []
    if multi:
        for f in sorted(fees_in_scope, key=natural_key):
            acc = _blank()
            for st in _students(charges, multi, key=lambda r, f=f: (r.get("fee_label") or "") == f).values():
                _add(acc, st)
            fees.append(_finish(acc, label=f))

    full = [c["label"] for c in classes if c["concerned"] and c["not_in_order"] == 0]
    eligible = [c for c in classes if c["remaining"] > 0 and c["concerned"] >= min_class_size] or [c for c in classes if c["remaining"] > 0]
    lowest = sorted(eligible, key=lambda c: (c["rate"], -c["remaining"]))[:5]
    biggest = sorted((c for c in classes if c["remaining"] > 0), key=lambda c: -c["remaining"])[:5]
    unpaid = sorted((st for st in students.values() if st["remaining"] > 0), key=order)

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for x in exemptions:
        k = (str(x["enrollment_id"]), x["reason"])
        g = grouped.setdefault(k, {"student_name": x.get("student_name") or "", "matricule": x.get("matricule") or "", "class_label": x.get("class_label") or "",
                                   "section_label": x.get("section_label") or "", "enrolled_on": x.get("enrolled_on"), "reason": x["reason"],
                                   "reason_label": REASON_LABEL.get(x["reason"], x["reason"]), "periods": []})
        p = x.get("period_label")
        if p and p not in g["periods"]:
            g["periods"].append(p)
    exempted = sorted(grouped.values(), key=lambda g: (g["reason"] != "ARRIVAL", natural_key(g["section_label"]), natural_key(g["class_label"]), g["student_name"].upper()))

    if fee_label and period_label:
        month = period_label.lower()
        title = f"{fee_label} — {period_label}"
        scope = (f"« {fee_label} {'d’' if month[0] in 'aeiouéè' else 'de '}{month} »" if month in MOIS else f"« {title} »")
    elif fee_label:
        title, scope = f"{fee_label} — périodes échues", f"« {fee_label} », périodes échues au {french_date(as_of)}"
    else:
        title, scope = "Tous les frais échus", f"l’ensemble des frais échus au {french_date(as_of)}"
    return {"title": title, "scope_label": scope, "fee_label": fee_label, "period_label": period_label, "as_of": as_of, "as_of_label": french_date(as_of),
            "currency": currency, "total": _finish(total, label="Ensemble de l’école"), "sections": sections, "classes": classes, "fees": fees,
            "analysis": {"full_classes": full, "lowest": lowest, "biggest": biggest, "biggest_sum": sum((c["remaining"] for c in biggest), ZERO),
                         "without_contact": sum(1 for st in unpaid if not st["contact_phone"])},
            "unpaid": unpaid, "exempted": exempted,
            "exempted_counts": {r: sum(1 for g in exempted if g["reason"] == r) for r in REASON_LABEL}}
