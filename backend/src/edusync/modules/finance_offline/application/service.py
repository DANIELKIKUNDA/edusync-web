from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable
from uuid import UUID

from edusync.modules.finance_offline.domain.models import (
    OfflineFinanceConflict,
    OfflineFinanceLease,
    OfflinePaymentCommand,
    enforce_lease_limits,
    validate_batch_against_snapshots,
    validate_batch_identity_uniqueness,
    verify_journal_chain,
)
from edusync.modules.finance_offline.ports.repositories import (
    OfflineChargeSnapshotRepository,
    OfflineFinanceRepository,
    OfflinePaymentPostingPort,
)


@dataclass(slots=True)
class OfflineFinanceCoordinator:
    repository: OfflineFinanceRepository
    snapshots: OfflineChargeSnapshotRepository
    posting: OfflinePaymentPostingPort

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
                raise OfflineFinanceConflict("Contexte du paiement différent du lease exclusif")
        validate_batch_identity_uniqueness(rows)
        verify_journal_chain(rows)
        enforce_lease_limits(commands=rows, lease=lease)
        snapshots = list(self.snapshots.snapshots_for_lease(lease.id))
        validate_batch_against_snapshots(rows, snapshots)

        posted: list[UUID] = []
        # Exact-once: store_received_command must return False for a replayed operation_id/key.
        # The concrete PostgreSQL adapter serializes this inside the same transaction as posting.
        for command in rows:
            if not self.repository.store_received_command(command):
                continue
            token = self.repository.receipt_token(command.receipt_token_id)
            if token is None or token.lease_id != lease.id or token.receipt_no != command.receipt_no:
                raise OfflineFinanceConflict("Reçu préalloué invalide ou étranger au lease")
            if token.status != "AVAILABLE":
                raise OfflineFinanceConflict("Reçu offline déjà consommé")
            payment_id = self.posting.post(command)
            self.repository.consume_receipt_token(
                token_id=command.receipt_token_id, lease_id=lease.id, operation_id=command.operation_id
            )
            self.repository.mark_command_applied(command.operation_id, payment_id=payment_id)
            posted.append(payment_id)
        return posted


def totals(commands: Iterable[OfflinePaymentCommand]) -> tuple[int, Decimal, Decimal, str | None]:
    rows = list(commands)
    cdf = sum((x.amount for x in rows if x.currency == "CDF"), Decimal("0.00"))
    usd = sum((x.amount for x in rows if x.currency == "USD"), Decimal("0.00"))
    final_hash = rows[-1].entry_hash if rows else None
    return len(rows), cdf, usd, final_hash
