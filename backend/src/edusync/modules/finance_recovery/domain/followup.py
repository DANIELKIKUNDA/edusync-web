"""Suivi financier d'un frais — 2026-10-25 (owner: « voir dans la 2e CG qui est en ordre avec le mois de mars et qui ne
l'est pas, pour renvoyer les élèves non en règle »). Built on the class register (VF-01) with the SAME settlement rule as
register_footer: settled = min(paid + allocated advance, net); a cell after an abandon / transfer is not owed.

« En ordre avec mars » means, by default, every period of that fee up to March is settled (cumulative); the strict
reading (March alone) stays available."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

STATUS_LABEL = {"OK": "En ordre", "PARTIAL": "Partiel", "NONE": "Non payé", "NA": "Non concerné"}


def _d(v: Any) -> Decimal:
    return Decimal(str(v or 0))


def fee_groups(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fees of the register (Inscription, Frais mensuels, each tranche fee) with their periods in order."""
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for c in columns:
        k = (c["group"], c["parent"] or "")
        g = groups.setdefault(k, {"key": f"{c['group']}|{c['parent'] or ''}", "label": c["parent"] or ("Inscription" if c["group"] == "REGISTRATION" else c["label"]), "periods": []})
        g["periods"].append({"key": c["key"], "label": c["label"], "order": c["order"]})
    for g in groups.values():
        g["periods"].sort(key=lambda x: x["order"])
    return list(groups.values())


def default_column(register: dict[str, Any], today: date | None = None) -> str | None:
    """The monthly period currently due (latest monthly column whose due date has passed), else the first column."""
    today = today or date.today(); cols = register.get("columns") or []
    if not cols:
        return None
    due: dict[str, date] = {}
    for st in register.get("students") or []:
        for k, cell in (st.get("cells") or {}).items():
            d = cell.get("due_date")
            if d and (k not in due or d < due[k]):
                due[k] = d
    monthly = [c for c in cols if c["group"] == "MONTHLY"]
    passed = [c for c in monthly if due.get(c["key"]) and due[c["key"]] <= today]
    if passed:
        return max(passed, key=lambda c: c["order"])["key"]
    return (monthly or cols)[0]["key"]


def class_followup(register: dict[str, Any], column_key: str, cumulative: bool = True) -> dict[str, Any]:
    cols = register.get("columns") or []
    target = next((c for c in cols if c["key"] == column_key), None)
    if target is None:
        raise LookupError("Période introuvable pour cette classe")
    scope = [c for c in cols if c["group"] == target["group"] and (c["parent"] or "") == (target["parent"] or "") and c["order"] <= target["order"]] if cumulative else [target]
    scope.sort(key=lambda c: c["order"])
    rows = []
    for st in register.get("students") or []:
        due = settled = Decimal("0"); missing: list[str] = []
        for c in scope:
            cell = (st.get("cells") or {}).get(c["key"])
            if not cell or cell.get("status_label"):
                continue
            net = _d(cell.get("net")); got = min(_d(cell.get("paid")) + _d(cell.get("advance")), net)
            due += net; settled += got
            if got < net:
                missing.append(c["label"] if got == 0 else f"{c['label']} (partiel)")
        remaining = max(due - settled, Decimal("0"))
        status = "NA" if due <= 0 else "OK" if remaining == 0 else "PARTIAL" if settled > 0 else "NONE"
        rows.append({"student_id": st["student_id"], "matricule": st.get("matricule"), "student_name": st.get("student_name"),
                     "terminal": (st.get("terminal") or {}).get("type"), "due": str(due), "settled": str(settled), "remaining": str(remaining),
                     "missing": missing, "status": status, "status_label": STATUS_LABEL[status]})
    rows.sort(key=lambda r: (r["status"] == "OK", r["status"] == "NA", (r["student_name"] or "").upper()))
    concerned = [r for r in rows if r["status"] != "NA"]
    counts = {"students": len(concerned), "in_order": sum(r["status"] == "OK" for r in concerned),
              "not_in_order": sum(r["status"] in ("PARTIAL", "NONE") for r in concerned), "partial": sum(r["status"] == "PARTIAL" for r in concerned)}
    remaining = sum((_d(r["remaining"]) for r in concerned), Decimal("0")); expected = sum((_d(r["due"]) for r in concerned), Decimal("0"))
    fee = target["parent"] or ("Inscription" if target["group"] == "REGISTRATION" else target["label"])
    return {"class_label": register.get("class_label"), "currency": register.get("currency"), "fee_label": fee, "period_label": target["label"],
            "column": target["key"], "cumulative": cumulative, "periods": [c["label"] for c in scope],
            "title": f"{fee} — {'jusqu’à ' if cumulative and len(scope) > 1 else ''}{target['label']}",
            "counts": counts, "expected": str(expected), "remaining": str(remaining),
            "rate": float(round((expected - remaining) * 100 / expected, 1)) if expected > 0 else 0.0, "rows": rows}
