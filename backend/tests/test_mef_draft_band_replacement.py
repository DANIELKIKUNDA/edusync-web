"""Contract: a DRAFT annual exigibility policy can have its day bands replaced (migration 0106)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "migrations" / "0106_mef_draft_band_replacement.sql").read_text(encoding="utf-8")
DOWN = (ROOT / "migrations" / "rollback" / "0106_mef_draft_band_replacement.down.sql").read_text(encoding="utf-8")
PROVISION = (ROOT / "scripts" / "provision_database.py").read_text(encoding="utf-8")


def test_delete_is_granted_only_through_a_restrictive_draft_policy():
    assert "GRANT DELETE ON finance_exigibility_day_bands TO edusync_tenant" in SQL
    assert "AS RESTRICTIVE FOR DELETE" in SQL
    assert "p.status = 'DRAFT'" in SQL


def test_migration_is_provisioned_after_0105_and_reversible():
    assert PROVISION.index("0105_") < PROVISION.index("0106_mef_draft_band_replacement")
    assert "REVOKE DELETE ON finance_exigibility_day_bands FROM edusync_tenant" in DOWN


def test_policy_errors_reach_the_administrator_in_french():
    from edusync.modules.finance_fee_tracking.domain.annual_policy_validation import french_policy_error

    assert "chevauchent" in str(french_policy_error(ValueError("Overlapping bands")))
    assert str(french_policy_error(ValueError("autre"))) == "autre"
