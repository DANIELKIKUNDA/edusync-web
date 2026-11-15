"""The amount still owed is the same everywhere (owner, 2026-11-16): alerts and old debts count the payments taken over
from the previous system, the regularizations and the decisions — not only the cash paid."""
from __future__ import annotations

from pathlib import Path

from edusync.adapters.charge_balance import still_owed

SRC = Path(__file__).resolve().parents[1] / "src" / "edusync"


def test_still_owed_deducts_decisions_cash_and_outside_cash():
    e = still_owed("fc")
    assert "fc.net_amount - fc.paid_amount - finance_charge_decision_amount(fc.id)" in e
    assert "finance_charge_regularizations rg" in e and "rg.charge_id=fc.id" in e and "rg.school_id=fc.school_id" in e


def test_alerts_and_old_debts_never_compare_net_with_cash_paid_only():
    for rel in ("modules/alerts/application/supervision.py", "modules/alerts/application/school_alerts.py", "adapters/postgres_finance_checkout.py"):
        s = (SRC / rel).read_text(encoding="utf-8")
        assert "net_amount>fc.paid_amount" not in s.replace(" ", "") or rel.endswith("checkout.py") and "fc.net_amount>fc.paid_amount" not in s, rel
        assert "still_owed('fc')" in s, rel


def test_every_paid_figure_includes_what_was_settled_outside_the_cash_desk():
    """Owner, 2026-11-16: « Qui est en ordre ? » showed pupils who had paid September and October as « Non payé »."""
    reg = (SRC / "adapters/postgres_finance_recovery.py").read_text(encoding="utf-8")
    assert "(fc.paid_amount+fc.outside_cash_amount) paid_amount" in reg       # class register → followup, printed registers
    for rel, needle in (("adapters/postgres_periodic_reports.py", "sum(fc.paid_amount+{outside_cash('fc')}) AS paid"),
                        ("adapters/postgres_periodic_reports.py", "fc.paid_amount - {outside_cash('fc')}, 0) AS balance"),
                        ("adapters/postgres_staff_finance.py", "sum(fc.paid_amount+{outside_cash('fc')}) AS settled"),
                        ("adapters/postgres_fee_schedules.py", "fc.paid_amount+{outside_cash('fc')} AS paid_amount")):
        assert needle in (SRC / rel).read_text(encoding="utf-8"), rel
