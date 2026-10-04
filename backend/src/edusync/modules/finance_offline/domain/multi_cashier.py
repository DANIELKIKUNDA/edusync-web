from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Iterable, Mapping
from uuid import UUID

from edusync.modules.finance_offline.domain.models import (
    ChargeSnapshot,
    OfflineFinanceConflict,
    OfflinePaymentCommand,
    money,
)

PROTOCOL_V2 = "AUTHORIZED_PARTITIONED_CASH_V2"


@dataclass(frozen=True, slots=True)
class JournalCheckpoint:
    last_seq: int = 0
    last_hash: str | None = None

    def __post_init__(self) -> None:
        if self.last_seq < 0:
            raise ValueError("last_seq doit être >= 0")
        if self.last_seq == 0 and self.last_hash is not None:
            raise ValueError("Un journal vide ne peut pas avoir de hash final")


@dataclass(frozen=True, slots=True)
class ReceivedCommandRecord:
    operation_id: UUID
    idempotency_key: str
    receipt_no: str
    journal_seq: int
    entry_hash: str
    status: str
    payment_id: UUID | None = None

    def matches(self, command: OfflinePaymentCommand) -> bool:
        return (
            self.operation_id == command.operation_id
            and self.idempotency_key == command.idempotency_key
            and self.receipt_no == command.receipt_no
            and self.journal_seq == command.journal_seq
            and self.entry_hash == command.entry_hash
        )


@dataclass(frozen=True, slots=True)
class OfflinePostingResult:
    payment_id: UUID
    allocated_amount: Decimal
    residual_credit_amount: Decimal = Decimal("0.00")
    outcome: str = "APPLIED"

    def __post_init__(self) -> None:
        allocated = money(self.allocated_amount)
        residual = money(self.residual_credit_amount)
        if allocated < 0 or residual < 0:
            raise ValueError("Les montants de posting ne peuvent pas être négatifs")
        if self.outcome not in {"APPLIED", "APPLIED_WITH_RESIDUAL_CREDIT"}:
            raise ValueError("Outcome de posting offline inconnu")
        if residual > 0 and self.outcome != "APPLIED_WITH_RESIDUAL_CREDIT":
            raise ValueError("Un crédit résiduel exige APPLIED_WITH_RESIDUAL_CREDIT")


@dataclass(frozen=True, slots=True)
class ChargePartition:
    device_id: UUID
    snapshots: tuple[ChargeSnapshot, ...]


def _routing_key(snapshot: ChargeSnapshot, routing_keys: Mapping[UUID, UUID] | None) -> UUID:
    if routing_keys is not None and snapshot.student_id in routing_keys:
        return routing_keys[snapshot.student_id]
    return snapshot.student_id


def partition_charge_snapshots(
    snapshots: Iterable[ChargeSnapshot],
    device_ids: Iterable[UUID],
    *,
    routing_keys: Mapping[UUID, UUID] | None = None,
) -> dict[UUID, tuple[ChargeSnapshot, ...]]:
    """Deterministically partitions debt authority between offline cashier devices.

    All charges of the same routing key (student by default; family can be supplied later)
    are assigned to exactly one device using rendezvous hashing. Therefore two properly
    armed offline cashiers never possess authority over the same charge.
    """
    devices = sorted(set(device_ids), key=str)
    if not devices:
        raise ValueError("Au moins un appareil caissier est requis")
    rows = list(snapshots)
    if len({x.charge_id for x in rows}) != len(rows):
        raise OfflineFinanceConflict("Une charge ne peut apparaître qu'une fois dans le plan multi-caissier")

    groups: dict[UUID, list[ChargeSnapshot]] = {}
    for snap in rows:
        groups.setdefault(_routing_key(snap, routing_keys), []).append(snap)

    result: dict[UUID, list[ChargeSnapshot]] = {device: [] for device in devices}
    for route, group in sorted(groups.items(), key=lambda x: str(x[0])):
        winner = max(
            devices,
            key=lambda device: sha256(f"{route}:{device}".encode("utf-8")).digest(),
        )
        result[winner].extend(sorted(group, key=lambda x: str(x.charge_id)))
    return {device: tuple(result[device]) for device in devices}


def verify_journal_segment(
    commands: Iterable[OfflinePaymentCommand],
    *,
    expected_start_seq: int | None = None,
    expected_previous_hash: str | None = None,
) -> None:
    """Validates a full journal or an incremental contiguous segment.

    If expected_start_seq is provided, the first command is anchored to the persisted
    server checkpoint. This makes retry-after-timeout and incremental sync safe.
    """
    rows = list(commands)
    if not rows:
        return
    if expected_start_seq is not None:
        if rows[0].journal_seq != expected_start_seq:
            raise OfflineFinanceConflict(
                f"Segment offline hors séquence: attendu {expected_start_seq}, reçu {rows[0].journal_seq}"
            )
        if rows[0].previous_entry_hash != expected_previous_hash:
            raise OfflineFinanceConflict("Ancre de hash offline différente du checkpoint serveur")
    for index, command in enumerate(rows):
        if command.entry_hash != command.compute_entry_hash():
            raise OfflineFinanceConflict("Empreinte du journal offline invalide")
        if index:
            previous = rows[index - 1]
            if command.journal_seq != previous.journal_seq + 1:
                raise OfflineFinanceConflict("Segment offline non contigu")
            if command.previous_entry_hash != previous.entry_hash:
                raise OfflineFinanceConflict("Chaîne de hash offline rompue dans le segment")


def validate_posting_result(command: OfflinePaymentCommand, result: OfflinePostingResult) -> None:
    if money(result.allocated_amount) + money(result.residual_credit_amount) != money(command.amount):
        raise OfflineFinanceConflict(
            "Le posting Finance doit expliquer 100% du cash: allocation + crédit résiduel = montant reçu"
        )
