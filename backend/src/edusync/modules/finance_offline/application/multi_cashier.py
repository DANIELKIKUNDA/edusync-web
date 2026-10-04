from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

from edusync.modules.finance_offline.domain.models import (
    OfflineFinanceConflict,
    OfflineFinanceLease,
    OfflinePaymentCommand,
    validate_batch_identity_uniqueness,
)
from edusync.modules.finance_offline.domain.multi_cashier import (
    JournalCheckpoint,
    OfflinePostingResult,
    ReceivedCommandRecord,
    validate_posting_result,
    verify_journal_segment,
)
from edusync.modules.finance_offline.ports.repositories import OfflinePaymentPostingPort


@dataclass(slots=True)
class MultiCashierOfflineFinanceCoordinator:
    """V2 synchronizer: multiple cashier leases can coexist when their charge authority is disjoint.

    The concrete repository must run this coordinator inside one caller-owned PostgreSQL
    transaction. Every new command is accepted, authority-checked, posted, receipted and
    audited atomically. Exact retries are no-ops.
    """

    repository: object
    posting: OfflinePaymentPostingPort

    def _new_suffix(self, lease: OfflineFinanceLease, rows: list[OfflinePaymentCommand]) -> list[OfflinePaymentCommand]:
        if not rows:
            return []
        verify_journal_segment(rows)
        checkpoint: JournalCheckpoint = self.repository.journal_checkpoint(lease.id)
        new_rows: list[OfflinePaymentCommand] = []
        saw_new = False
        for command in rows:
            existing: ReceivedCommandRecord | None = self.repository.received_command(
                school_id=lease.school_id, operation_id=command.operation_id
            )
            if existing is not None:
                if saw_new:
                    raise OfflineFinanceConflict("Un rejeu ancien ne peut pas apparaître après une nouvelle entrée")
                if not existing.matches(command):
                    raise OfflineFinanceConflict("Replay offline différent de l'opération déjà reçue")
                continue
            saw_new = True
            new_rows.append(command)
        if not new_rows:
            return []
        verify_journal_segment(
            new_rows,
            expected_start_seq=checkpoint.last_seq + 1,
            expected_previous_hash=checkpoint.last_hash,
        )
        return new_rows

    def sync_batch(self, *, lease: OfflineFinanceLease, commands: Iterable[OfflinePaymentCommand]) -> list[UUID]:
        rows = list(commands)
        if lease.status not in {"ACTIVE", "DRAINING"}:
            raise OfflineFinanceConflict("Lease offline non synchronisable")
        for command in rows:
            if (
                command.school_id != lease.school_id
                or command.lease_id != lease.id
                or command.device_id != lease.device_id
                or command.cashier_user_id != lease.cashier_user_id
                or command.cash_session_id != lease.cash_session_id
            ):
                raise OfflineFinanceConflict("Contexte du paiement différent de l'autorité de cette caisse")
        validate_batch_identity_uniqueness(rows)
        new_rows = self._new_suffix(lease, rows)
        if not new_rows:
            return []

        self.repository.lock_lease_for_sync(lease.id)
        posted: list[UUID] = []
        for command in new_rows:
            if not self.repository.store_received_command(command):
                # Another retry won the race. Re-read and require exact identity.
                existing = self.repository.received_command(
                    school_id=lease.school_id, operation_id=command.operation_id
                )
                if existing is None or not existing.matches(command):
                    raise OfflineFinanceConflict("Collision idempotente concurrente non équivalente")
                continue
            self.repository.assert_server_lease_limits(lease.id)
            token = self.repository.receipt_token(command.receipt_token_id)
            if token is None or token.lease_id != lease.id or token.receipt_no != command.receipt_no:
                raise OfflineFinanceConflict("Reçu préalloué invalide ou étranger à la caisse")
            if token.status != "AVAILABLE":
                raise OfflineFinanceConflict("Reçu offline déjà consommé")

            # Full-charge authority is partitioned at arming time; cumulative local use is
            # checked again in PostgreSQL here before any canonical Finance posting.
            self.repository.consume_charge_reservations(command)
            raw_result = self.posting.post(command)
            if isinstance(raw_result, UUID):
                result = OfflinePostingResult(payment_id=raw_result, allocated_amount=command.amount)
            else:
                result = raw_result
            validate_posting_result(command, result)
            self.repository.consume_receipt_token(
                token_id=command.receipt_token_id,
                lease_id=lease.id,
                operation_id=command.operation_id,
            )
            self.repository.mark_command_applied(
                command.operation_id,
                payment_id=result.payment_id,
                posting_outcome=result.outcome,
                residual_credit_amount=result.residual_credit_amount,
            )
            posted.append(result.payment_id)
        return posted
