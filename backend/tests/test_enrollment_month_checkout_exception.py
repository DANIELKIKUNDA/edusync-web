"""The enrollment tuition month may be collected before earlier monthly tuition, and only that month."""
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from edusync.adapters.postgres_finance_checkout import PostgresFinanceCheckoutRepository
from edusync.modules.finance_checkout.domain.models import DueCharge, validate_selection


def _month(label, order):
    return DueCharge(uuid4(), label, "CDF", Decimal("55000"), periodicity="MONTHLY",
                     period_label=label, period_order=order, sequence_group="MONTHLY:SCOLARITE")


def test_enrollment_june_bypasses_predecessors_but_october_does_not():
    september, october, june = _month("Septembre", 1), _month("Octobre", 2), _month("Juin", 10)
    with pytest.raises(ValueError, match="Septembre"):
        validate_selection([september, october, june], [june.id])
    assert validate_selection([september, october, june], [june.id],
                              exempt_predecessors={june.id}) == Decimal("55000")
    with pytest.raises(ValueError, match="Septembre"):
        validate_selection([september, october, june], [october.id],
                           exempt_predecessors={june.id})


def test_exception_comes_only_from_ready_enrollment_bundle_with_configured_tuition_month():
    repo = PostgresFinanceCheckoutRepository(None)
    june, registration = uuid4(), uuid4()
    due = {"ready": True, "bundle": [{"fee_code": "SCOLARITE", "month": "06"},
                                      {"fee_code": "INSCRIPTION", "month": None}],
           "items": [{"charge_id": str(june), "fee_code": "SCOLARITE", "balance": "55000"},
                     {"charge_id": str(registration), "fee_code": "INSCRIPTION", "balance": "15000"}]}
    assert repo._enrollment_month_exceptions(uuid4(), uuid4(), due) == {june}
    assert repo._enrollment_month_exceptions(uuid4(), uuid4(), {**due, "ready": False}) == set()
    assert repo._enrollment_month_exceptions(uuid4(), uuid4(),
             {**due, "bundle": [{"fee_code": "SCOLARITE", "month": None}]}) == set()
    assert repo._enrollment_month_exceptions(uuid4(), uuid4(),
             {**due, "items": [{**due["items"][0], "balance": "0"}]}) == set()


def test_future_payment_policy_exempts_only_required_enrollment_month(monkeypatch):
    from edusync.adapters.postgres_settings import PostgresSettingsRepository
    policy = {"accepted_modes": ["CASH"], "advance_payments_enabled": False,
              "future_charge_payments_enabled": False, "partial_min_amount": "0",
              "partial_payments_enabled": True}
    monkeypatch.setattr(PostgresSettingsRepository, "get_payment_policy", lambda *_: policy)
    repo = PostgresFinanceCheckoutRepository(None)
    june, october = _month("Juin", 10), _month("Octobre", 2)
    rows = [{"id": str(c.id), "due_date": date.today() + timedelta(days=30)} for c in (june, october)]
    repo._apply_payment_policy(uuid4(), rows, [june, october], [june.id],
                               june.remaining, "CASH", False, {june.id})
    with pytest.raises(ValueError, match="mois futur"):
        repo._apply_payment_policy(uuid4(), rows, [june, october], [october.id],
                                   october.remaining, "CASH", False, {june.id})


def test_balance_unlocks_only_the_enrollment_month(monkeypatch):
    september, october, june = _month("Septembre", 1), _month("Octobre", 2), _month("Juin", 10)

    class Result:
        def mappings(self):
            return self
        def all(self):
            return [{"id": c.id, "label": c.label} for c in (september, october, june)]

    class Connection:
        def execute(self, *_args, **_kwargs):
            return Result()

    repo = PostgresFinanceCheckoutRepository(Connection())
    monkeypatch.setattr(repo, "_cash_payable", lambda *_: [september, october, june])
    monkeypatch.setattr(repo, "_enrollment_month_exceptions", lambda *_: {june.id})
    balance = {row["id"]: row for row in repo.charges(uuid4(), uuid4())}
    assert balance[june.id]["eligible"] is True
    assert balance[june.id]["requires"] == []
    assert balance[june.id]["lock_reason"] is None
    assert balance[october.id]["eligible"] is False
    assert balance[october.id]["requires"] == [str(september.id)]
