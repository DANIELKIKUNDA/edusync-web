from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException

from edusync.modules.finance_checkout.api import router as checkout


SID = UUID("00000000-0000-0000-0000-000000000001")
EID = UUID("00000000-0000-0000-0000-000000000002")
CID = UUID("00000000-0000-0000-0000-000000000003")
UID = UUID("00000000-0000-0000-0000-000000000004")
MID = UUID("00000000-0000-0000-0000-000000000005")


class Result:
    def __init__(self, row=None, rows=None):
        self.row, self.rows = row, rows or []

    def mappings(self):
        return self

    def first(self):
        return self.row

    def all(self):
        return self.rows


class Connection:
    def __init__(self, prior=None):
        self.prior = prior

    def execute(self, statement, params):
        sql = str(statement)
        if "SELECT p.id payment_id" in sql:
            return Result(self.prior)
        if "SELECT charge_id FROM finance_payment_allocations" in sql:
            return Result(rows=[(CID,)])
        return Result(rows=[])


class TenantDB:
    def __init__(self, conn):
        self.conn = conn
        self.committed = self.rolled_back = False

    @contextmanager
    def tenant_transaction(self, **_):
        try:
            yield self.conn
            self.committed = True
        except Exception:
            self.rolled_back = True
            raise


def _setup(monkeypatch, *, prior=None, fund_failure=False):
    records = []
    db = TenantDB(Connection(prior))
    actor = SimpleNamespace(school_id=SID, user_id=UID, membership_id=MID,
                            require=lambda permission: records.append(("permission", permission)))
    service = SimpleNamespace(tenant_db=db)

    class Checkout:
        def __init__(self, conn):
            assert conn is db.conn

        def charges(self, school_id, enrollment_id):
            assert (school_id, enrollment_id) == (SID, EID)
            return [{"id": CID, "currency": "CDF", "remaining": "100.00"}]

        def collect(self, *args, **kwargs):
            records.append(("payment", args[5], args[7]))
            return {"id": str(CID), "receipt_number": "REC-1", "replayed": prior is not None}

    class Funds:
        def __init__(self, conn):
            assert conn is db.conn

        def receive(self, *args, **kwargs):
            records.append(("fund", kwargs["amount"], kwargs["idempotency_key"]))
            if fund_failure:
                raise ValueError("fonds refusé")
            return {"id": str(EID), "receipt_number": "REC-2", "replayed": prior is not None}

    monkeypatch.setattr(checkout, "PostgresFinanceCheckoutRepository", Checkout)
    monkeypatch.setattr(checkout, "_audit", lambda *args, **kwargs: records.append(("audit",)))
    from edusync.adapters import postgres_advance_funds
    monkeypatch.setattr(postgres_advance_funds, "PostgresAdvanceFundsRepository", Funds)
    return actor, service, db, records


def _body(amount="120.00"):
    return checkout.TenderWithFundBody(enrollment_id=EID, charge_ids=[CID],
                                       amount=Decimal(amount), currency="CDF", mode="CASH")


def test_one_tender_splits_payment_and_fund_in_same_transaction(monkeypatch):
    actor, service, db, records = _setup(monkeypatch)
    result = checkout.collect_with_fund(_body(), idempotency_key="tender-12345678", actor=actor, services=service)
    assert db.committed and not db.rolled_back
    assert result["payment_amount"] == "100.00"
    assert result["fund_amount"] == "20.00"
    assert ("payment", Decimal("100.00"), "tender-12345678:pay") in records
    assert ("fund", Decimal("20.00"), "tender-12345678:fund") in records
    assert ("audit",) in records


def test_fund_failure_rolls_back_the_whole_tender(monkeypatch):
    actor, service, db, _ = _setup(monkeypatch, fund_failure=True)
    with pytest.raises(HTTPException) as error:
        checkout.collect_with_fund(_body(), idempotency_key="tender-12345678", actor=actor, services=service)
    assert error.value.status_code == 409
    assert db.rolled_back and not db.committed


def test_same_key_with_changed_tender_is_refused_before_writes(monkeypatch):
    prior = {"payment_id": CID, "payment_amount": Decimal("100.00"), "fund_amount": Decimal("20.00"),
             "fund_id": EID, "enrollment_id": EID, "fund_enrollment_id": EID,
             "currency": "CDF", "fund_currency": "CDF", "payment_mode": "CASH",
             "fund_mode": "CASH", "payment_reference": None, "fund_reference": None}
    actor, service, db, records = _setup(monkeypatch, prior=prior)
    with pytest.raises(HTTPException) as error:
        checkout.collect_with_fund(_body("121.00"), idempotency_key="tender-12345678", actor=actor, services=service)
    assert error.value.status_code == 409
    assert not any(row[0] in ("payment", "fund") for row in records)
    assert db.rolled_back
