"""Pedagogical calendar — pure rules (V2 lot 2, owner 2026-11-22), unit-tested.

Two calendars per school and year, because one school usually has both structures:
  TRIMESTRIEL (maternelle, primaire): P1 P2 EX1 · P3 P4 EX2 · P5 P6 EX3
  SEMESTRIEL  (7e-8e EB, humanités):  P1 P2 EX1 · P3 P4 EX2
EduSync PROPOSES every date from the school year (the user only checks and adjusts — users with no computer experience);
the rules come from the parent project: inside the year, chronological, no overlap; uncovered days are shown, not refused.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

CODES = {"TRIMESTRIEL": ("P1", "P2", "EX1", "P3", "P4", "EX2", "P5", "P6", "EX3"),
         "SEMESTRIEL": ("P1", "P2", "EX1", "P3", "P4", "EX2")}
TERM_WORD = {"TRIMESTRIEL": "trimestre", "SEMESTRIEL": "semestre"}
ORDINAL = {1: "1re", 2: "2e", 3: "3e", 4: "4e", 5: "5e", 6: "6e"}
TERM_ORDINAL = {1: "1er", 2: "2e", 3: "3e"}
EXAM_DAYS = 10            # proposed length of an exam session (adjustable by the school)


class CalendarError(ValueError):
    pass


@dataclass(frozen=True)
class Period:
    code: str
    starts_on: date
    ends_on: date

    @property
    def is_exam(self) -> bool:
        return self.code.startswith("EX")


def label(structure: str, code: str) -> str:
    if code.startswith("EX"):
        return f"Examen du {TERM_ORDINAL[int(code[2:])]} {TERM_WORD[structure]}"
    return f"{ORDINAL[int(code[1:])]} période"


def term_of(code: str) -> int:
    """P1, P2, EX1 → 1 ; P3, P4, EX2 → 2 ; P5, P6, EX3 → 3."""
    return int(code[2:]) if code.startswith("EX") else (int(code[1:]) + 1) // 2


def propose(structure: str, year_start: date, year_end: date) -> list[Period]:
    """Every term the same length; in each term two periods of equal length then the exam session (EXAM_DAYS)."""
    if structure not in CODES:
        raise CalendarError("Structure inconnue")
    if year_end <= year_start:
        raise CalendarError("Année scolaire invalide")
    terms = len(CODES[structure]) // 3
    total = (year_end - year_start).days + 1
    out: list[Period] = []
    cursor = year_start
    for t in range(terms):
        length = total // terms + (1 if t < total % terms else 0)
        term_end = cursor + timedelta(days=length - 1)
        exam_days = min(EXAM_DAYS, max(3, length // 6))
        exam_start = term_end - timedelta(days=exam_days - 1)
        teaching = (exam_start - cursor).days
        p_mid = cursor + timedelta(days=teaching // 2)
        codes = CODES[structure][t * 3:t * 3 + 3]
        out += [Period(codes[0], cursor, p_mid - timedelta(days=1)), Period(codes[1], p_mid, exam_start - timedelta(days=1)),
                Period(codes[2], exam_start, term_end)]
        cursor = term_end + timedelta(days=1)
    return out


def validate(structure: str, periods: list[Period], year_start: date, year_end: date) -> list[dict]:
    """Raises CalendarError on a blocking problem; returns the uncovered stretches (warnings, never blocking)."""
    expected = CODES.get(structure)
    if expected is None:
        raise CalendarError("Structure inconnue")
    codes = [p.code for p in periods]
    if sorted(codes) != sorted(expected) or len(set(codes)) != len(codes):
        missing = [c for c in expected if c not in codes]
        extra = sorted({c for c in codes if c not in expected})
        detail = "; ".join(x for x in (f"manque : {', '.join(missing)}" if missing else "", f"en trop : {', '.join(extra)}" if extra else "") if x)
        raise CalendarError("Périodes attendues : " + ", ".join(expected) + (f" ({detail})" if detail else ""))
    ordered = sorted(periods, key=lambda p: expected.index(p.code))
    gaps = []
    previous: Period | None = None
    for p in ordered:
        name = label(structure, p.code)
        if p.ends_on < p.starts_on:
            raise CalendarError(f"{name} : la fin est avant le début")
        if p.starts_on < year_start or p.ends_on > year_end:
            raise CalendarError(f"{name} : en dehors de l’année scolaire ({year_start:%d/%m/%Y} – {year_end:%d/%m/%Y})")
        if previous is not None:
            if p.starts_on <= previous.ends_on:
                raise CalendarError(f"{name} : commence avant la fin de « {label(structure, previous.code)} »")
            gap = (p.starts_on - previous.ends_on).days - 1
            if gap > 0:
                gaps.append({"after": previous.code, "before": p.code, "from": (previous.ends_on + timedelta(days=1)).isoformat(),
                             "to": (p.starts_on - timedelta(days=1)).isoformat(), "days": gap})
        previous = p
    return gaps


def entry_state(p: Period, *, validated: bool, closed: bool, today: date) -> str:
    """State of grade entry for one period (used by the grades, lot 3)."""
    if not validated:
        return "DRAFT"
    if closed:
        return "CLOSED"
    if today < p.starts_on:
        return "UPCOMING"
    if today <= p.ends_on:
        return "ONGOING"
    return "OPEN"            # period over, entry still open until the préfet closes it


def entry_allowed(state: str) -> bool:
    return state in ("ONGOING", "OPEN")
