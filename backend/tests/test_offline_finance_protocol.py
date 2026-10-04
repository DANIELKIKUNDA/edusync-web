from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from edusync.bootstrap.settings import Settings
from edusync.modules.finance_offline.application.service import OfflineFinanceCoordinator, totals
from edusync.modules.finance_offline.domain.models import (
    ChargeSnapshot,
    OfflineAllocation,
    OfflineFinanceConflict,
    OfflineFinanceError,
    OfflineFinanceLease,
    OfflineFinanceLimitExceeded,
    OfflinePaymentCommand,
    ReceiptToken,
    enforce_lease_limits,
    validate_batch_against_snapshots,
    validate_batch_identity_uniqueness,
    verify_journal_chain,
)
from edusync.modules.sync.domain.contracts import FINANCE_OFFLINE_POLICY


SCHOOL = UUID("00000000-0000-0000-0000-000000000001")
USER = UUID("00000000-0000-0000-0000-000000000002")
DEVICE = UUID("00000000-0000-0000-0000-000000000003")
SESSION = UUID("00000000-0000-0000-0000-000000000004")
LEASE_ID = UUID("00000000-0000-0000-0000-000000000005")
STUDENT = UUID("00000000-0000-0000-0000-000000000006")
ENROLLMENT = UUID("00000000-0000-0000-0000-000000000007")
CHARGE1 = UUID("00000000-0000-0000-0000-000000000008")
CHARGE2 = UUID("00000000-0000-0000-0000-000000000009")
TOKEN1 = UUID("00000000-0000-0000-0000-000000000010")
TOKEN2 = UUID("00000000-0000-0000-0000-000000000011")
OP1 = UUID("00000000-0000-0000-0000-000000000012")
OP2 = UUID("00000000-0000-0000-0000-000000000013")
PAY1 = UUID("00000000-0000-0000-0000-000000000014")
PAY2 = UUID("00000000-0000-0000-0000-000000000015")


def lease(**patch):
    base = OfflineFinanceLease(
        id=LEASE_ID, school_id=SCHOOL, cashier_user_id=USER, device_id=DEVICE,
        cash_session_id=SESSION, status="ACTIVE",
        local_stop_at=datetime.now(timezone.utc) + timedelta(hours=4),
        max_payments=10, max_cdf=Decimal("500000.00"), max_usd=Decimal("1000.00"),
    )
    return replace(base, **patch)


def snapshots():
    return [
        ChargeSnapshot(CHARGE1, ENROLLMENT, STUDENT, "CDF", Decimal("100000.00"), 3),
        ChargeSnapshot(CHARGE2, ENROLLMENT, STUDENT, "CDF", Decimal("50000.00"), 2),
    ]


def command(*, seq=1, op=OP1, token=TOKEN1, receipt="OFF-TEST-2026-00000001",
            amount="40000.00", allocations=None, previous=None, idem="offline:op1", mode="CASH"):
    allocations = allocations or (OfflineAllocation(CHARGE1, Decimal(amount)),)
    cmd = OfflinePaymentCommand(
        school_id=SCHOOL, lease_id=LEASE_ID, device_id=DEVICE, cashier_user_id=USER,
        cash_session_id=SESSION, student_id=STUDENT, enrollment_id=ENROLLMENT,
        currency="CDF", amount=Decimal(amount), receipt_token_id=token, receipt_no=receipt,
        allocations=tuple(allocations), journal_seq=seq, operation_id=op,
        idempotency_key=idem, mode=mode,
        client_time=datetime(2026, 9, 11, 10, 0, seq, 123456, tzinfo=timezone.utc),
        previous_entry_hash=previous,
    )
    return cmd.with_computed_hash()


def chain2():
    a = command()
    b = command(seq=2, op=OP2, token=TOKEN2, receipt="OFF-TEST-2026-00000002",
                amount="30000.00", previous=a.entry_hash, idem="offline:op2")
    return [a, b]


def test_offline_policy_is_guarded_not_open_ended():
    assert FINANCE_OFFLINE_POLICY["final_payment_allowed"] is True
    assert FINANCE_OFFLINE_POLICY["default_enabled"] is False
    assert FINANCE_OFFLINE_POLICY["modes_allowed"] == ["CASH"]
    assert FINANCE_OFFLINE_POLICY["requires_exclusive_school_lease"] is False
    assert FINANCE_OFFLINE_POLICY["protocol"] == "AUTHORIZED_PARTITIONED_CASH_V2"
    assert FINANCE_OFFLINE_POLICY["server_auto_release"] is False


def test_non_cash_is_rejected():
    with pytest.raises(OfflineFinanceError, match="uniquement CASH"):
        command(mode="MOBILE_MONEY")


def test_amount_must_equal_exact_allocations():
    with pytest.raises(OfflineFinanceError, match="somme des allocations"):
        command(amount="50000", allocations=(OfflineAllocation(CHARGE1, Decimal("40000")),))


def test_duplicate_charge_inside_one_payment_is_rejected():
    with pytest.raises(OfflineFinanceError, match="qu'une fois"):
        command(amount="20000", allocations=(OfflineAllocation(CHARGE1, Decimal("10000")), OfflineAllocation(CHARGE1, Decimal("10000"))))


def test_hash_is_deterministic_and_uses_millisecond_utc():
    a = command()
    b = command()
    assert a.entry_hash == b.entry_hash
    assert a.canonical_payload()["client_time"] == "2026-09-11T10:00:01.123Z"


def test_valid_chain_passes():
    verify_journal_chain(chain2())


def test_tampered_chain_fails():
    a, b = chain2()
    bad = replace(b, previous_entry_hash="0" * 64).with_computed_hash()
    with pytest.raises(OfflineFinanceConflict, match="Chaîne"):
        verify_journal_chain([a, bad])


def test_skipped_sequence_fails():
    a = command()
    b = command(seq=3, op=OP2, token=TOKEN2, receipt="R2", amount="1000", previous=a.entry_hash, idem="op2")
    with pytest.raises(OfflineFinanceConflict, match="Séquence"):
        verify_journal_chain([a, b])


def test_snapshot_rejects_other_student_or_currency():
    wrong = ChargeSnapshot(CHARGE1, ENROLLMENT, uuid4(), "CDF", Decimal("100000"), 1)
    with pytest.raises(OfflineFinanceConflict, match="autre inscription"):
        validate_batch_against_snapshots([command()], [wrong])


def test_batch_cumulative_overpayment_is_rejected():
    a = command(amount="70000")
    b = command(seq=2, op=OP2, token=TOKEN2, receipt="R2", amount="40000", previous=a.entry_hash, idem="op2")
    with pytest.raises(OfflineFinanceConflict, match="cumulées"):
        validate_batch_against_snapshots([a, b], snapshots())


def test_batch_with_two_charges_within_snapshot_passes():
    a = command(amount="70000")
    b = command(seq=2, op=OP2, token=TOKEN2, receipt="R2", amount="60000",
                allocations=(OfflineAllocation(CHARGE1, Decimal("30000")), OfflineAllocation(CHARGE2, Decimal("30000"))),
                previous=a.entry_hash, idem="op2")
    validate_batch_against_snapshots([a, b], snapshots())


def test_duplicate_operation_or_receipt_is_rejected_before_posting():
    a = command()
    b = command(seq=2, op=OP1, token=TOKEN2, receipt="R2", amount="1000", previous=a.entry_hash, idem="op2")
    with pytest.raises(OfflineFinanceConflict, match="operation_id"):
        validate_batch_identity_uniqueness([a, b])


def test_lease_limits_are_per_currency_and_count():
    a, b = chain2()
    enforce_lease_limits(commands=[a, b], lease=lease())
    with pytest.raises(OfflineFinanceLimitExceeded, match="Nombre"):
        enforce_lease_limits(commands=[a, b], lease=lease(max_payments=1))
    with pytest.raises(OfflineFinanceLimitExceeded, match="CDF"):
        enforce_lease_limits(commands=[a, b], lease=lease(max_cdf=Decimal("60000")))


def test_local_stop_only_stops_new_payments_not_server_lease_release():
    expired = lease(local_stop_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    assert expired.can_create_new_local_payment() is False
    assert expired.status == "ACTIVE"  # server stays locked until reconcile/force release


class MemoryProtocolRepo:
    def __init__(self):
        self.tokens = {
            TOKEN1: ReceiptToken(TOKEN1, LEASE_ID, SCHOOL, "OFF-TEST-2026-00000001"),
            TOKEN2: ReceiptToken(TOKEN2, LEASE_ID, SCHOOL, "OFF-TEST-2026-00000002"),
        }
        self.seen = {}
        self.applied = {}

    def store_received_command(self, cmd):
        prior = self.seen.get(cmd.operation_id)
        if prior:
            if prior.entry_hash != cmd.entry_hash:
                raise OfflineFinanceConflict("replay différent")
            return False
        if any(x.idempotency_key == cmd.idempotency_key for x in self.seen.values()):
            raise OfflineFinanceConflict("idempotency duplicate")
        self.seen[cmd.operation_id] = cmd
        return True

    def receipt_token(self, token_id):
        return self.tokens.get(token_id)

    def consume_receipt_token(self, *, token_id, lease_id, operation_id):
        token = self.tokens[token_id]
        if token.status != "AVAILABLE" or token.lease_id != lease_id:
            raise OfflineFinanceConflict("token consumed")
        self.tokens[token_id] = replace(token, status="CONSUMED")

    def mark_command_applied(self, operation_id, *, payment_id=None):
        self.applied[operation_id] = payment_id


class MemorySnapshots:
    def snapshots_for_lease(self, lease_id):
        assert lease_id == LEASE_ID
        return snapshots()


class MemoryPosting:
    def __init__(self):
        self.ids = [PAY1, PAY2]
        self.calls = []

    def post(self, cmd):
        self.calls.append(cmd.operation_id)
        return self.ids[len(self.calls) - 1]


def test_coordinator_posts_each_operation_once_and_replay_is_zero_effect():
    repo = MemoryProtocolRepo()
    posting = MemoryPosting()
    svc = OfflineFinanceCoordinator(repo, MemorySnapshots(), posting)
    rows = chain2()
    first = svc.sync_batch(lease=lease(), commands=rows)
    second = svc.sync_batch(lease=lease(), commands=rows)
    assert first == [PAY1, PAY2]
    assert second == []
    assert posting.calls == [OP1, OP2]
    assert repo.tokens[TOKEN1].status == "CONSUMED"
    assert repo.tokens[TOKEN2].status == "CONSUMED"


def test_coordinator_rejects_foreign_device_before_any_post():
    repo = MemoryProtocolRepo()
    posting = MemoryPosting()
    svc = OfflineFinanceCoordinator(repo, MemorySnapshots(), posting)
    bad = replace(command(), device_id=uuid4()).with_computed_hash()
    with pytest.raises(OfflineFinanceConflict, match="Contexte"):
        svc.sync_batch(lease=lease(), commands=[bad])
    assert posting.calls == []


def test_totals_keep_cdf_usd_separate():
    a = command()
    usd = OfflinePaymentCommand(
        school_id=SCHOOL, lease_id=LEASE_ID, device_id=DEVICE, cashier_user_id=USER,
        cash_session_id=SESSION, student_id=STUDENT, enrollment_id=ENROLLMENT,
        currency="USD", amount=Decimal("10.00"), receipt_token_id=TOKEN2, receipt_no="USD-1",
        allocations=(OfflineAllocation(CHARGE2, Decimal("10.00")),), journal_seq=2, operation_id=OP2,
        idempotency_key="usd-2", previous_entry_hash=a.entry_hash,
        client_time=datetime(2026,9,11,10,0,2,tzinfo=timezone.utc),
    ).with_computed_hash()
    count, cdf, usd_total, final_hash = totals([a, usd])
    assert count == 2 and cdf == Decimal("40000.00") and usd_total == Decimal("10.00")
    assert final_hash == usd.entry_hash


def test_production_cannot_enable_offline_finance_without_g2_certification():
    settings = Settings(
        env="production",
        jwt_secret="x" * 40,
        tenant_database_url="postgresql+psycopg://edusync_tenant:strong@db/edusync",
        platform_database_url="postgresql+psycopg://edusync_platform:strong@db/edusync",
        owner_database_url="postgresql+psycopg://edusync_owner:strong@db/edusync",
        cors_origins="https://edusync.example",
        offline_finance_enabled=True,
        offline_finance_certified=False,
    )
    with pytest.raises(RuntimeError, match="sans certification G2"):
        settings.assert_runtime_safe()
