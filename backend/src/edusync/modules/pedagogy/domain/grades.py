"""Grade entry — pure rules (V2 lot 3b, owner 2026-11-22: « les enseignants ne doivent pas se plaindre »), unit-tested.

Parent project: an integer from 0 to the programme maximum; no exam mark for a course without exam; entry follows the
calendar; nothing is ever deleted (a mark is emptied, with history); concurrent edits are detected; below half → red.
Speed (research: Infinite Campus, Canvas, teachers' complaints): the cell accepts short codes — « a » = absent,
« d » = dispensé, empty = no mark yet; a pasted column (Excel, WhatsApp, notes) fills the class in order.
"""
from __future__ import annotations

import re
from datetime import date

STATUSES = ("NOTE", "ABSENT", "DISPENSE")
CODES = {"A": "ABSENT", "ABS": "ABSENT", "ABSENT": "ABSENT", "D": "DISPENSE", "DISP": "DISPENSE", "DISPENSE": "DISPENSE"}
COLUMN_OF = {"P1": "max_p1", "P2": "max_p2", "EX1": "max_ex1", "P3": "max_p3", "P4": "max_p4", "EX2": "max_ex2",
             "P5": "max_p5", "P6": "max_p6", "EX3": "max_ex3"}


class GradeError(ValueError):
    pass


def parse_cell(raw: str | None, maximum: int) -> tuple[str | None, int | None]:
    """What the teacher typed → (status, value). (None, None) = empty cell (no mark yet)."""
    text = (raw or "").strip().upper().replace(",", ".")
    if not text:
        return None, None
    if text in CODES:
        return CODES[text], None
    if not re.fullmatch(r"\d{1,3}", text):
        raise GradeError("Tapez un nombre entier, « a » (absent) ou « d » (dispensé)")
    value = int(text)
    if value > maximum:
        raise GradeError(f"Maximum {maximum}")
    return "NOTE", value


def check(status: str | None, value: int | None, maximum: int, *, has_exam: bool, period: str) -> None:
    if period not in COLUMN_OF:
        raise GradeError("Période inconnue")
    if period.startswith("EX") and not has_exam:
        raise GradeError("Ce cours n’a pas d’examen")
    if maximum <= 0:
        raise GradeError("Aucun point prévu pour cette période dans le programme")
    if status is None:
        if value is not None:
            raise GradeError("Cote sans statut")
        return
    if status not in STATUSES:
        raise GradeError("Statut inconnu")
    if status == "NOTE":
        if not isinstance(value, int) or value < 0 or value > maximum:
            raise GradeError(f"Une cote va de 0 à {maximum}")
    elif value is not None:
        raise GradeError("Un élève absent ou dispensé n’a pas de cote")


def is_failing(value: int | None, maximum: int) -> bool:
    """Parent rule: under half of the maximum → shown in red."""
    return value is not None and maximum > 0 and value * 2 < maximum


def parse_pasted(text: str, maximum: int) -> list[tuple[str | None, int | None]]:
    """A pasted column, one line per pupil in class order (Excel, WhatsApp, notes). Tolerates « 12/20 », « 12 », « a »,
    blank lines inside the list (= no mark), and a trailing « ; » or tab-separated name before the mark."""
    out = []
    lines = text.replace("\r", "").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    for n, line in enumerate(lines, start=1):
        cell = line.strip()
        if "\t" in cell or ";" in cell:
            cell = re.split(r"[\t;]", cell)[-1].strip()
        cell = re.sub(r"\s*/\s*\d+\s*$", "", cell)               # « 12/20 » → « 12 »
        try:
            out.append(parse_cell(cell, maximum))
        except GradeError as exc:
            raise GradeError(f"Ligne {n} : {exc}") from exc
    return out


def conduct_period(structure_periods: list[dict], day: date) -> str | None:
    """The simple period (P1…P6) a conduct fact belongs to: the period containing the day; during an exam session, the
    period just before it (conduct exists only on simple periods — parent project)."""
    ordered = sorted(structure_periods, key=lambda p: p["sort_order"])
    for i, p in enumerate(ordered):
        if p["starts_on"] <= day <= p["ends_on"]:
            if not p["code"].startswith("EX"):
                return p["code"]
            previous = [q for q in ordered[:i] if not q["code"].startswith("EX")]
            return previous[-1]["code"] if previous else None
    return None
