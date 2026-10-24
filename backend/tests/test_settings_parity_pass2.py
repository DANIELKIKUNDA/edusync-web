"""Settings parity pass 2 (owner request 2026-10-24):
- a staff-child / large-family benefit covers SEVERAL fees (migration 0087, list frozen on the beneficiary);
- the charge generator applies the benefit to every covered fee (exact code or CODE_ prefix), never to another fee;
- the student finance view exposes the fee of each charge so an individual exemption can target several fees.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from edusync.adapters.postgres_settings import _benefit_out, fee_code_list

ROOT = Path(__file__).resolve().parents[2]
MIG = (ROOT / "backend/migrations/0087_benefit_policies_multi_fee.sql").read_text(encoding="utf-8")
PROVISION = (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")
SCHEDULES = (ROOT / "backend/src/edusync/adapters/postgres_fee_schedules.py").read_text(encoding="utf-8")
DECISIONS = (ROOT / "backend/src/edusync/adapters/postgres_financial_decisions.py").read_text(encoding="utf-8")
USE_CASES = (ROOT / "backend/src/edusync/modules/schooling/application/use_cases.py").read_text(encoding="utf-8")


def test_migration_adds_the_list_and_keeps_the_single_code():
    assert "ADD COLUMN IF NOT EXISTS applies_to_fee_codes varchar(48)[]" in MIG
    assert MIG.count("applies_to_fee_codes varchar(48)[]") == 2           # policies AND beneficiaries
    assert "DROP COLUMN" not in MIG                                       # the 0062 column stays for existing reports
    assert '("0087_benefit_policies_multi_fee", "0087_benefit_policies_multi_fee.sql")' in PROVISION


def test_fee_code_list_is_clean_ordered_and_bounded():
    assert fee_code_list([" scolarite", "ETAT_MINERVAL", "SCOLARITE", "", None]) == ["SCOLARITE", "ETAT_MINERVAL"]
    with pytest.raises(ValueError):
        fee_code_list([f"F{i}" for i in range(31)])


def test_policy_read_model_falls_back_to_the_single_code():
    row = _benefit_out({"discount_percent": 50, "applies_to_fee_code": "SCOLARITE", "applies_to_fee_codes": None})
    assert row["applies_to_fee_codes"] == ["SCOLARITE"] and row["discount_percent"] == "50"
    row = _benefit_out({"discount_percent": 0, "applies_to_fee_code": "A", "applies_to_fee_codes": ["A", "B"]})
    assert row["applies_to_fee_codes"] == ["A", "B"]


def test_charge_generator_matches_any_covered_fee():
    body = SCHEDULES.split("def benefit_percent", 1)[1].split("def generate_charges_for_enrollment", 1)[0]
    assert "applies_to_fee_codes" in body
    assert 'any(c == fee_code or fee_code.startswith(f"{c}_") for c in codes)' in body


def test_beneficiary_freezes_the_policy_list():
    assert USE_CASES.count("applies_to_fee_codes=_fee_codes_from_policy(") == 2


def test_finance_view_exposes_the_fee_of_each_charge():
    assert '"fee_code": ch["fee_code"] or None, "fee_label": ch["fee_label"]' in DECISIONS
