"""School programme of an official class — pure rules (V2 lot 2, owner 2026-11-22), unit-tested.

DRAFT → VALIDATED → ARCHIVED (parent project): one programme in use per class and year; a validated programme is never
edited, a new version replaces it. Owner rules: « l'examen est toujours le double de la période », a course without exam
has no exam points, and the two periods of a term weigh the same. So the school enters ONE number per term (the points
of a period): EduSync derives the second period and the exam — nothing to compute, no way to break the rule.
"""
from __future__ import annotations

from edusync.modules.pedagogy.domain.referential import MAX_KEYS, ReferentialError, check_line

STATUSES = ("DRAFT", "VALIDATED", "ARCHIVED")


class ProgrammeError(ValueError):
    pass


def maxima_from_terms(structure: str, term_points: list[int], has_exam: bool) -> list[int]:
    """[p1, p2(, p3)] points per period of each term → the 9 maxima P1 P2 EX1 P3 P4 EX2 P5 P6 EX3."""
    terms = 3 if structure == "TRIMESTRIEL" else 2 if structure == "SEMESTRIEL" else 0
    if not terms:
        raise ProgrammeError("Structure inconnue")
    if len(term_points) != terms or any(not isinstance(v, int) or v < 0 or v > 500 for v in term_points):
        raise ProgrammeError(f"Indiquez les points d’une période pour chacun des {terms} {'trimestres' if terms == 3 else 'semestres'} (0 à 500)")
    if sum(term_points) == 0:
        raise ProgrammeError("Un cours doit avoir des points")
    out: list[int] = []
    for t in range(3):
        p = term_points[t] if t < terms else 0
        out += [p, p, 2 * p if has_exam else 0]
    return out


def terms_from_maxima(structure: str, maxima: list[int]) -> list[int]:
    return [maxima[0], maxima[3]] + ([maxima[6]] if structure == "TRIMESTRIEL" else [])


def check(structure: str, course: str, maxima: list[int], has_exam: bool) -> None:
    try:
        check_line("programme", structure, {"course": course, "exam": has_exam, "max": maxima})
    except ReferentialError as exc:
        raise ProgrammeError(str(exc)) from exc
    if not (maxima[0] == maxima[1] and maxima[3] == maxima[4] and maxima[6] == maxima[7]):
        raise ProgrammeError("Les deux périodes d’un même trimestre ou semestre valent la même chose")


def can_remove(line: dict) -> None:
    """An official compulsory course stays; an optional one or a course added by the school may go."""
    if line["source"] == "OFFICIEL" and line["mandatory"]:
        raise ProgrammeError("Cours obligatoire du programme officiel : il ne peut pas être retiré")


def differs_from_official(line: dict, official: dict | None) -> bool:
    if official is None:
        return True
    return any(int(line[k]) != int(official[k]) for k in MAX_KEYS) or bool(line["has_exam"]) != bool(official["has_exam"]) \
        or bool(line["mandatory"]) != bool(official["mandatory"])
