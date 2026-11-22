"""Rules of the modules of a school (owner decisions, 2026-11-22). Pure: no database, unit-tested.

* V1 modules: every school has them (existing schools by migration 0123, new schools at creation). They are RECORDED,
  not enforced — enforcing them belongs to the subscription work, paused until the owner has his company documents.
  They cannot be withdrawn from the platform: withdrawing a module nobody checks would only mislead.
* PEDAGOGY (catalogue code ACADEMIC): the V2, sold separately. No school has it by default; the platform activates or
  withdraws it school by school. It is the one module the server enforces.
"""
from __future__ import annotations

V1_MODULES: tuple[str, ...] = ("CORE_SCHOOL", "ENROLLMENT", "FINANCE", "RECOVERY", "REPORTS", "PERSONNEL", "DOCUMENTS", "COMMUNICATIONS")
PEDAGOGY = "ACADEMIC"
# Modules the platform may switch on and off school by school (one module at the start: owner, 2026-11-22).
SWITCHABLE: frozenset[str] = frozenset({PEDAGOGY})
# Modules whose absence the server refuses.
ENFORCED: frozenset[str] = frozenset({PEDAGOGY})

V1_REASON_AT_CREATION = "Modules V1 inclus à la création de l’école"
NOT_ACTIVE_MESSAGE = {PEDAGOGY: "Module Pédagogie non activé pour cette école. Contactez EduSync pour l’activer."}


class ModuleRuleError(ValueError):
    """A module change that the rules refuse (the API answers 409 with this message)."""


def check_activation(code: str, *, known: set[str], active: set[str], dependencies: list[str], school_status: str) -> None:
    if code not in known:
        raise LookupError("Module inconnu")
    if code not in SWITCHABLE:
        raise ModuleRuleError("Ce module fait partie de la V1 : il est déjà inclus pour toutes les écoles.")
    if school_status != "ACTIVE":
        raise ModuleRuleError("École suspendue ou désactivée : réactivez-la avant d’activer un module.")
    if code in active:
        raise ModuleRuleError("Ce module est déjà actif pour cette école.")
    missing = [d for d in dependencies if d not in active]
    if missing:
        raise ModuleRuleError("Modules requis manquants : " + ", ".join(missing))


def check_withdrawal(code: str, *, known: set[str], active: set[str], dependents: dict[str, list[str]]) -> None:
    """dependents: active module → the modules it needs."""
    if code not in known:
        raise LookupError("Module inconnu")
    if code not in SWITCHABLE:
        raise ModuleRuleError("Les modules V1 ne se retirent pas : ils restent inclus pour toutes les écoles.")
    if code not in active:
        raise ModuleRuleError("Ce module n’est pas actif pour cette école.")
    blocking = sorted(m for m, needs in dependents.items() if m in active and m != code and code in needs)
    if blocking:
        raise ModuleRuleError("D’autres modules en dépendent : " + ", ".join(blocking))


def clean_reason(reason: str) -> str:
    value = " ".join((reason or "").split())
    if len(value) < 5:
        raise ModuleRuleError("Indiquez le motif (au moins 5 caractères).")
    return value[:500]
