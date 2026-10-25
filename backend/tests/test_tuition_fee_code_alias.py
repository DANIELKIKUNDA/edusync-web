"""2026-10-25 — owner report « on ne doit jamais sauter un mois impayé »: the Web monthly tuition « MINERVAL » follows
every rule of the Desktop « SCOLARITE » (sequential months, month required at enrollment, benefits, report group)."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from edusync.modules.finance_checkout.domain.models import DueCharge, sequential_eligibility, validate_selection
from edusync.shared.domain.fee_codes import canonical_fee_code, is_tuition_code, same_fee

ROOT = Path(__file__).resolve().parents[2]


def test_canonical_codes():
    assert canonical_fee_code("minerval") == "SCOLARITE" and canonical_fee_code("MINERVAL_JUIN") == "SCOLARITE_JUIN"
    assert canonical_fee_code("INSCRIPTION") == "INSCRIPTION" and canonical_fee_code(None) == ""
    assert is_tuition_code("MINERVAL") and is_tuition_code("SCOLARITE_MARS") and not is_tuition_code("ETAT_MINERVAL")


def test_same_fee_keeps_exact_and_prefix_matching():
    assert same_fee("SCOLARITE", "MINERVAL") and same_fee("MINERVAL", "SCOLARITE_JUIN") and same_fee("ETAT", "ETAT_MINERVAL")
    assert not same_fee("INSCRIPTION", "MINERVAL") and not same_fee("", "MINERVAL")


def _month(order, paid=Decimal("0")):
    return DueCharge(id=uuid4(), label=f"Frais scolaires mensuels — M{order}", currency="CDF", net=Decimal("15000"), paid=paid,
                     periodicity="MONTHLY", period_label=f"M{order}", period_order=order, sequence_group="MONTHLY:SCOLARITE", sequence_order=order)


def test_repaired_monthly_tuition_cannot_skip_a_month():
    sep, oct_, nov = _month(1), _month(2), _month(3)
    elig = sequential_eligibility([sep, oct_, nov])
    assert elig[sep.id][0] and not elig[oct_.id][0] and not elig[nov.id][0]
    with pytest.raises(ValueError, match="ne peut pas être encaissée avant"):
        validate_selection([sep, oct_, nov], [nov.id])
    assert validate_selection([sep, oct_, nov], [sep.id, oct_.id]) == Decimal("30000")


def test_generator_bundle_and_repair_use_the_shared_rule():
    fees = (ROOT / "backend/src/edusync/adapters/postgres_fee_schedules.py").read_text(encoding="utf-8")
    assert "scolarite = is_tuition_code(s[\"fee_code\"])" in fees and "is_tuition_code(code) and month" in fees
    mig = (ROOT / "backend/migrations/0092_tuition_alias_minerval_sequence.sql").read_text(encoding="utf-8")
    assert "SET sequence_group = 'MONTHLY:SCOLARITE'" in mig and "DELETE" not in mig.upper()
    assert "0092_tuition_alias_minerval_sequence.sql" in (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")
