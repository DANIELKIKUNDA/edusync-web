"""Monthly tuition fee code — one definition for every finance rule (2026-10-25).

The Desktop golden master codes the monthly tuition « SCOLARITE » (and SCOLARITE_<MOIS> per month). The Web setup
assistant creates the same fee as « MINERVAL » (Frais scolaires mensuels). Both mean the monthly tuition: sequential
payment (no month skipped), the month required at enrollment, staff-child / large-family benefits, the « frais
scolaires » report group. Every rule compares through canonical_fee_code / is_tuition_code, never against a literal.
"""
from __future__ import annotations

TUITION = "SCOLARITE"
TUITION_ALIASES = frozenset({"SCOLARITE", "MINERVAL"})


def canonical_fee_code(code: str | None) -> str:
    """« MINERVAL » and « MINERVAL_<X> » read as « SCOLARITE » / « SCOLARITE_<X> »; every other code is unchanged."""
    c = (code or "").upper()
    for alias in TUITION_ALIASES:
        if c == alias:
            return TUITION
        if c.startswith(f"{alias}_"):
            return f"{TUITION}{c[len(alias):]}"
    return c


def is_tuition_code(code: str | None) -> bool:
    c = canonical_fee_code(code)
    return c == TUITION or c.startswith(f"{TUITION}_")


def same_fee(rule_code: str | None, fee_code: str | None) -> bool:
    """A rule code (benefit, bundle) matches a fee code exactly or as prefix CODE_, tuition aliases included."""
    r, f = canonical_fee_code(rule_code), canonical_fee_code(fee_code)
    return bool(r) and (f == r or f.startswith(f"{r}_"))
