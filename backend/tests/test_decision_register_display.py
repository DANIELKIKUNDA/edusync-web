"""Decision register (owner, 2026-11-16): a 100 % exemption of the minerval was shown « 100 FC · Périmètre global »."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = (ROOT / "backend/src/edusync/modules/finance_controls/api/router.py").read_text(encoding="utf-8")
FINANCE = (ROOT / "frontend/src/finance.tsx").read_text(encoding="utf-8")


def test_fee_label_comes_from_the_scope_when_the_decision_targets_a_fee_code_or_category():
    assert "WHEN d.scope_type='FEE_CODE' THEN (SELECT f2.label FROM fee_types f2" in ROUTER
    assert "WHEN d.scope_type='FEE_CATEGORY' THEN (SELECT fcat.label FROM fee_categories fcat" in ROUTER


def test_percent_decisions_are_shown_in_percent_and_global_only_for_all_fees():
    assert "x.value_type==='PERCENT'?`${Number(x.amount).toLocaleString('fr-FR')} %`" in FINANCE
    assert "'Périmètre global'" not in FINANCE and "x.scope_type==='ALL_FEES'" in FINANCE
