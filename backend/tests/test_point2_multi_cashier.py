from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from edusync.modules.finance_offline.application.multi_cashier import MultiCashierOfflineFinanceCoordinator
from edusync.modules.finance_offline.domain.models import (
    ChargeSnapshot,
    OfflineAllocation,
    OfflineFinanceConflict,
    OfflineFinanceLease,
    OfflinePaymentCommand,
    ReceiptToken,
    money,
)
from edusync.modules.finance_offline.domain.multi_cashier import (
    JournalCheckpoint,
    OfflinePostingResult,
    ReceivedCommandRecord,
    partition_charge_snapshots,
    validate_posting_result,
    verify_journal_segment,
)
from edusync.modules.sync.domain.contracts import FINANCE_OFFLINE_POLICY

SCHOOL = UUID("10000000-0000-0000-0000-000000000001")
USER_A = UUID("10000000-0000-0000-0000-000000000002")
USER_B = UUID("10000000-0000-0000-0000-000000000003")
DEVICE_A = UUID("10000000-0000-0000-0000-000000000004")
DEVICE_B = UUID("10000000-0000-0000-0000-000000000005")
LEASE_A = UUID("10000000-0000-0000-0000-000000000006")
LEASE_B = UUID("10000000-0000-0000-0000-000000000007")
SESSION_A = UUID("10000000-0000-0000-0000-000000000008")
SESSION_B = UUID("10000000-0000-0000-0000-000000000009")
STUDENT_A = UUID("10000000-0000-0000-0000-000000000010")
STUDENT_B = UUID("10000000-0000-0000-0000-000000000011")
ENROLL_A = UUID("10000000-0000-0000-0000-000000000012")
ENROLL_B = UUID("10000000-0000-0000-0000-000000000013")
CHARGE_A = UUID("10000000-0000-0000-0000-000000000014")
CHARGE_A2 = UUID("10000000-0000-0000-0000-000000000015")
CHARGE_B = UUID("10000000-0000-0000-0000-000000000016")
TOKEN_A1 = UUID("10000000-0000-0000-0000-000000000017")
TOKEN_A2 = UUID("10000000-0000-0000-0000-000000000018")
TOKEN_B1 = UUID("10000000-0000-0000-0000-000000000019")


def lease_a() -> OfflineFinanceLease:
    return OfflineFinanceLease(
        id=LEASE_A, school_id=SCHOOL, cashier_user_id=USER_A, device_id=DEVICE_A,
        cash_session_id=SESSION_A, status="ACTIVE",
        local_stop_at=datetime.now(timezone.utc) + timedelta(hours=4), max_payments=20,
        max_cdf=Decimal("1000000"), max_usd=Decimal("1000"),
    )


def lease_b() -> OfflineFinanceLease:
    return OfflineFinanceLease(
        id=LEASE_B, school_id=SCHOOL, cashier_user_id=USER_B, device_id=DEVICE_B,
        cash_session_id=SESSION_B, status="ACTIVE",
        local_stop_at=datetime.now(timezone.utc) + timedelta(hours=4), max_payments=20,
        max_cdf=Decimal("1000000"), max_usd=Decimal("1000"),
    )


def snap_a() -> ChargeSnapshot:
    return ChargeSnapshot(CHARGE_A, ENROLL_A, STUDENT_A, "CDF", Decimal("100000"), 4)


def snap_a2() -> ChargeSnapshot:
    return ChargeSnapshot(CHARGE_A2, ENROLL_A, STUDENT_A, "CDF", Decimal("50000"), 1)


def snap_b() -> ChargeSnapshot:
    return ChargeSnapshot(CHARGE_B, ENROLL_B, STUDENT_B, "CDF", Decimal("80000"), 2)


def cmd(*, lease=LEASE_A, user=USER_A, device=DEVICE_A, session=SESSION_A,
        student=STUDENT_A, enrollment=ENROLL_A, charge=CHARGE_A, token=TOKEN_A1,
        receipt="OFF-A-1", seq=1, previous=None, amount="30000", op=None, idem=None):
    operation = op or uuid4()
    command = OfflinePaymentCommand(
        school_id=SCHOOL, lease_id=lease, device_id=device, cashier_user_id=user,
        cash_session_id=session, student_id=student, enrollment_id=enrollment,
        currency="CDF", amount=Decimal(amount), receipt_token_id=token, receipt_no=receipt,
        allocations=(OfflineAllocation(charge, Decimal(amount)),), journal_seq=seq,
        operation_id=operation, idempotency_key=idem or f"point2:{operation}", mode="CASH",
        client_time=datetime(2026, 9, 11, 12, 0, seq, tzinfo=timezone.utc),
        previous_entry_hash=previous,
    )
    return command.with_computed_hash()


def test_policy_point2_is_multi_writer_and_charge_partitioned():
    assert FINANCE_OFFLINE_POLICY["protocol"] == "AUTHORIZED_PARTITIONED_CASH_V2"
    assert FINANCE_OFFLINE_POLICY["requires_exclusive_school_lease"] is False
    assert FINANCE_OFFLINE_POLICY["authority_scope"] == "DISJOINT_CHARGE_RESERVATIONS_PER_LEASE"
    assert FINANCE_OFFLINE_POLICY["server_auto_release"] is False


def test_partition_is_deterministic_and_never_duplicates_charge():
    rows = [snap_a(), snap_a2(), snap_b()]
    first = partition_charge_snapshots(rows, [DEVICE_A, DEVICE_B])
    second = partition_charge_snapshots(list(reversed(rows)), [DEVICE_B, DEVICE_A])
    assert first == second
    flattened = [x.charge_id for part in first.values() for x in part]
    assert sorted(map(str, flattened)) == sorted(map(str, [CHARGE_A, CHARGE_A2, CHARGE_B]))
    assert len(flattened) == len(set(flattened))


def test_partition_keeps_all_charges_of_same_student_on_same_cashier():
    parts = partition_charge_snapshots([snap_a(), snap_a2(), snap_b()], [DEVICE_A, DEVICE_B])
    owners = {
        snap.charge_id: device
        for device, values in parts.items()
        for snap in values
    }
    assert owners[CHARGE_A] == owners[CHARGE_A2]


def test_partition_can_route_by_family_key_when_family_model_is_available():
    family = uuid4()
    parts = partition_charge_snapshots(
        [snap_a(), snap_b()], [DEVICE_A, DEVICE_B], routing_keys={STUDENT_A: family, STUDENT_B: family}
    )
    owners = [device for device, values in parts.items() if values]
    assert len(owners) == 1
    assert len(parts[owners[0]]) == 2


def test_incremental_segment_can_start_after_server_checkpoint():
    a = cmd(seq=1)
    b = cmd(seq=2, token=TOKEN_A2, receipt="OFF-A-2", previous=a.entry_hash)
    verify_journal_segment([b], expected_start_seq=2, expected_previous_hash=a.entry_hash)


def test_incremental_segment_rejects_gap_or_wrong_anchor():
    a = cmd(seq=1)
    b = cmd(seq=3, token=TOKEN_A2, receipt="OFF-A-2", previous=a.entry_hash)
    with pytest.raises(OfflineFinanceConflict, match="hors séquence"):
        verify_journal_segment([b], expected_start_seq=2, expected_previous_hash=a.entry_hash)
    b2 = replace(b, journal_seq=2).with_computed_hash()
    with pytest.raises(OfflineFinanceConflict, match="Ancre"):
        verify_journal_segment([b2], expected_start_seq=2, expected_previous_hash="f" * 64)


def test_posting_result_must_explain_all_physical_cash():
    c = cmd(amount="50000")
    validate_posting_result(c, OfflinePostingResult(uuid4(), Decimal("45000"), Decimal("5000"), "APPLIED_WITH_RESIDUAL_CREDIT"))
    with pytest.raises(OfflineFinanceConflict, match="100% du cash"):
        validate_posting_result(c, OfflinePostingResult(uuid4(), Decimal("45000"), Decimal("0"), "APPLIED"))


class MemoryV2Repo:
    def __init__(self):
        self.tokens = {
            TOKEN_A1: ReceiptToken(TOKEN_A1, LEASE_A, SCHOOL, "OFF-A-1"),
            TOKEN_A2: ReceiptToken(TOKEN_A2, LEASE_A, SCHOOL, "OFF-A-2"),
            TOKEN_B1: ReceiptToken(TOKEN_B1, LEASE_B, SCHOOL, "OFF-B-1"),
        }
        self.authority = {
            (LEASE_A, CHARGE_A): Decimal("100000"),
            (LEASE_A, CHARGE_A2): Decimal("50000"),
            (LEASE_B, CHARGE_B): Decimal("80000"),
        }
        self.used = {}
        self.rows = {}
        self.by_lease = {LEASE_A: [], LEASE_B: []}
        self.applied = {}

    def journal_checkpoint(self, lease_id):
        rows = self.by_lease[lease_id]
        if not rows:
            return JournalCheckpoint()
        last = max(rows, key=lambda x: x.journal_seq)
        return JournalCheckpoint(last.journal_seq, last.entry_hash)

    def received_command(self, *, school_id, operation_id):
        row = self.rows.get(operation_id)
        if row is None:
            return None
        return ReceivedCommandRecord(
            row.operation_id, row.idempotency_key, row.receipt_no, row.journal_seq,
            row.entry_hash, "APPLIED" if operation_id in self.applied else "RECEIVED",
            self.applied.get(operation_id),
        )

    def lock_lease_for_sync(self, lease_id):
        return None

    def store_received_command(self, command):
        prior = self.rows.get(command.operation_id)
        if prior is not None:
            if prior.entry_hash != command.entry_hash:
                raise OfflineFinanceConflict("replay différent")
            return False
        if any(x.idempotency_key == command.idempotency_key for x in self.rows.values()):
            raise OfflineFinanceConflict("idempotency collision")
        if any(x.receipt_no == command.receipt_no for x in self.rows.values()):
            raise OfflineFinanceConflict("receipt collision")
        self.rows[command.operation_id] = command
        self.by_lease[command.lease_id].append(command)
        return True

    def assert_server_lease_limits(self, lease_id):
        rows = self.by_lease[lease_id]
        if len(rows) > 20:
            raise OfflineFinanceConflict("limit")

    def receipt_token(self, token_id):
        return self.tokens.get(token_id)

    def consume_charge_reservations(self, command):
        for allocation in command.allocations:
            key = (command.lease_id, allocation.charge_id)
            if key not in self.authority:
                raise OfflineFinanceConflict("Autorité offline absente")
            projected = self.used.get(key, Decimal("0")) + money(allocation.amount)
            if projected > self.authority[key]:
                raise OfflineFinanceConflict("montant réservé dépassé")
            self.used[key] = projected

    def consume_receipt_token(self, *, token_id, lease_id, operation_id):
        token = self.tokens[token_id]
        if token.lease_id != lease_id or token.status != "AVAILABLE":
            raise OfflineFinanceConflict("token")
        self.tokens[token_id] = replace(token, status="CONSUMED")

    def mark_command_applied(self, operation_id, *, payment_id=None, posting_outcome="APPLIED", residual_credit_amount="0"):
        self.applied[operation_id] = payment_id


class Posting:
    def __init__(self, residual: Decimal = Decimal("0")):
        self.calls = []
        self.residual = residual

    def post(self, command):
        self.calls.append(command.operation_id)
        pid = uuid4()
        if self.residual:
            return OfflinePostingResult(
                pid, money(command.amount) - self.residual, self.residual, "APPLIED_WITH_RESIDUAL_CREDIT"
            )
        return OfflinePostingResult(pid, command.amount)


def test_multi_cashier_same_school_can_post_disjoint_charges():
    repo = MemoryV2Repo()
    posting = Posting()
    svc = MultiCashierOfflineFinanceCoordinator(repo, posting)
    a = cmd()
    b = cmd(lease=LEASE_B, user=USER_B, device=DEVICE_B, session=SESSION_B,
            student=STUDENT_B, enrollment=ENROLL_B, charge=CHARGE_B, token=TOKEN_B1,
            receipt="OFF-B-1", amount="25000")
    assert len(svc.sync_batch(lease=lease_a(), commands=[a])) == 1
    assert len(svc.sync_batch(lease=lease_b(), commands=[b])) == 1
    assert len(posting.calls) == 2


def test_retry_after_timeout_is_exact_noop_then_incremental_next_entry_posts():
    repo = MemoryV2Repo()
    posting = Posting()
    svc = MultiCashierOfflineFinanceCoordinator(repo, posting)
    first = cmd(seq=1)
    assert len(svc.sync_batch(lease=lease_a(), commands=[first])) == 1
    assert svc.sync_batch(lease=lease_a(), commands=[first]) == []
    second = cmd(seq=2, charge=CHARGE_A2, token=TOKEN_A2, receipt="OFF-A-2", previous=first.entry_hash)
    assert len(svc.sync_batch(lease=lease_a(), commands=[second])) == 1
    assert len(posting.calls) == 2


def test_server_rejects_charge_owned_by_another_cashier():
    repo = MemoryV2Repo()
    posting = Posting()
    svc = MultiCashierOfflineFinanceCoordinator(repo, posting)
    bad = cmd(lease=LEASE_B, user=USER_B, device=DEVICE_B, session=SESSION_B,
              student=STUDENT_A, enrollment=ENROLL_A, charge=CHARGE_A, token=TOKEN_B1,
              receipt="OFF-B-1")
    with pytest.raises(OfflineFinanceConflict, match="Autorité offline absente"):
        svc.sync_batch(lease=lease_b(), commands=[bad])
    assert posting.calls == []


def test_server_cumulative_authority_prevents_overcollection():
    repo = MemoryV2Repo()
    posting = Posting()
    svc = MultiCashierOfflineFinanceCoordinator(repo, posting)
    first = cmd(seq=1, amount="70000")
    svc.sync_batch(lease=lease_a(), commands=[first])
    second = cmd(seq=2, amount="40000", token=TOKEN_A2, receipt="OFF-A-2", previous=first.entry_hash)
    with pytest.raises(OfflineFinanceConflict, match="montant réservé dépassé"):
        svc.sync_batch(lease=lease_a(), commands=[second])


def test_legitimate_server_drift_can_be_booked_as_residual_credit_without_losing_cash():
    repo = MemoryV2Repo()
    posting = Posting(residual=Decimal("5000"))
    svc = MultiCashierOfflineFinanceCoordinator(repo, posting)
    result = svc.sync_batch(lease=lease_a(), commands=[cmd(amount="30000")])
    assert len(result) == 1
    assert len(posting.calls) == 1


def test_point2_migration_drops_school_global_writer_and_adds_charge_guard():
    migration = (Path(__file__).parents[1] / "migrations" / "0005_offline_finance_multi_cashier.sql").read_text()
    assert "DROP INDEX IF EXISTS uq_offline_finance_one_writer_per_school" in migration
    assert "uq_offline_charge_one_live_authority" in migration
    assert "assert_finance_charge_writer_allowed" in migration
    assert "QUARANTINED" in migration
    assert "Aucune attribution role_permissions" in migration


def test_point2_frontend_requires_web_locks_and_durable_storage():
    frontend = (Path(__file__).parents[2] / "frontend" / "src" / "offline" / "financeJournal.ts").read_text()
    assert "withFinanceWriteLock" in frontend
    assert "navigator.storage.persist" in frontend
    assert "Web Locks" in frontend
    assert "const VERSION=2" in frontend
