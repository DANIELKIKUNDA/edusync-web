"""Conduct as a points licence (owner decision 2026-11-22: « rendre ça automatique ») — pure rules, unit-tested.

Nobody types a conduct mark. Every pupil starts each period at 100; the staff report facts from the school's scale
(late −2, fight −15, exemplary +5…); EduSync computes 100 − lost points (0…100) and the bulletin mention with the parent
project's scale (E ≥ 80, TB ≥ 70, B ≥ 60, AB ≥ 50, ME ≥ 40, MA < 40). Automatic rules: N lates in the period count as one
indiscipline, a serious fact alerts the discipline director, under a threshold the pupil is flagged « à suivre ».
"""
from __future__ import annotations

from dataclasses import dataclass

START = 100
MENTIONS = (("E", 80, "Élite"), ("TB", 70, "Très bien"), ("B", 60, "Bien"), ("AB", 50, "Assez bien"), ("ME", 40, "Médiocre"), ("MA", 0, "Mauvais"))


class ConductError(ValueError):
    pass


@dataclass(frozen=True)
class Rule:
    code: str
    label: str
    points: int          # negative: lost; positive: regained (never above 100)
    grave: bool = False  # reported only by the discipline director / préfet; alerts at once


DEFAULT_RULES: tuple[Rule, ...] = (
    Rule("RETARD", "Retard", -2),
    Rule("TENUE", "Tenue non conforme", -2),
    Rule("DEVOIR", "Devoir non fait", -3),
    Rule("INDISCIPLINE", "Bavardage ou indiscipline en classe", -5),
    Rule("ABSENCE", "Absence non justifiée", -5),
    Rule("INSOLENCE", "Insolence envers un adulte", -10),
    Rule("BAGARRE", "Bagarre", -15, grave=True),
    Rule("FRAUDE", "Fraude à l’examen", -20, grave=True),
    Rule("EXEMPLAIRE", "Comportement exemplaire, aide aux autres", 5),
)
DEFAULT_SETTINGS = {"late_rule_code": "RETARD", "late_threshold": 5, "late_penalty": 5, "alert_below": 50}


def mention(points: int) -> tuple[str, str]:
    if not isinstance(points, int) or points < 0 or points > 100:
        raise ConductError("Conduite hors barème (0 à 100)")
    for code, floor, label in MENTIONS:
        if points >= floor:
            return code, label
    return "MA", "Mauvais"


def check_rule(code: str, label: str, points: int) -> None:
    if not code or len(code) > 32 or not code.replace("_", "").isalnum():
        raise ConductError("Code du fait invalide")
    if len(label.strip()) < 3:
        raise ConductError("Nom du fait trop court")
    if not isinstance(points, int) or points == 0 or points < -50 or points > 20:
        raise ConductError("Points d’un fait : de −50 à +20, jamais 0")


def check_settings(late_threshold: int, late_penalty: int, alert_below: int) -> None:
    if not 0 <= late_threshold <= 20:
        raise ConductError("Nombre de retards : de 0 (règle désactivée) à 20")
    if not 0 <= late_penalty <= 50:
        raise ConductError("Pénalité des retards répétés : de 0 à 50 points")
    if not 0 <= alert_below <= 100:
        raise ConductError("Seuil d’alerte : de 0 à 100")


def compute(facts: list[dict], *, late_rule_code: str, late_threshold: int, late_penalty: int, alert_below: int,
            adjustment: int = 0) -> dict:
    """facts: [{code, points}] of one pupil for one period (cancelled facts excluded). Returns the conduct and why."""
    total = START + sum(int(f["points"]) for f in facts)
    lates = sum(1 for f in facts if f["code"] == late_rule_code)
    repeated = (lates // late_threshold) if late_threshold else 0
    total -= repeated * late_penalty
    total += adjustment
    points = max(0, min(START, total))
    code, label = mention(points)
    return {"points": points, "mention": code, "mention_label": label, "facts": len(facts), "lates": lates,
            "repeated_late_penalties": repeated, "to_follow": points < alert_below}
