from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
from typing import Any, Iterable
from uuid import UUID, uuid4

CENT = Decimal("0.01")


def money(value: str | int | float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def utc_millis(value: datetime) -> str:
    dt = value.astimezone(timezone.utc)
    millis = dt.microsecond // 1000
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{millis:03d}Z"


class OfflineFinanceError(ValueError):
    pass


class OfflineFinanceConflict(OfflineFinanceError):
    pass


class OfflineFinanceLimitExceeded(OfflineFinanceError):
    pass


@dataclass(frozen=True, slots=True)
class OfflineFinanceLease:
    id: UUID
    school_id: UUID
    cashier_user_id: UUID
    device_id: UUID
    cash_session_id: UUID
    status: str = "ACTIVE"
    local_stop_at: datetime | None = None
    max_payments: int = 100
    max_cdf: Decimal = Decimal("0.00")
    max_usd: Decimal = Decimal("0.00")

    def __post_init__(self) -> None:
        if self.status not in {"PREPARING", "ACTIVE", "DRAINING", "CLOSED", "FORCE_RELEASED"}:
            raise OfflineFinanceError("Statut de lease financier offline invalide")
        if self.max_payments < 1:
            raise OfflineFinanceError("max_payments doit être >= 1")
        if money(self.max_cdf) < 0 or money(self.max_usd) < 0:
            raise OfflineFinanceError("Les plafonds offline ne peuvent pas être négatifs")

    def can_create_new_local_payment(self, now: datetime | None = None) -> bool:
        if self.status != "ACTIVE":
            return False
        if self.local_stop_at is None:
            return True
        moment = now or datetime.now(timezone.utc)
        return moment <= self.local_stop_at


@dataclass(frozen=True, slots=True)
class ReceiptToken:
    id: UUID
    lease_id: UUID
    school_id: UUID
    receipt_no: str
    status: str = "AVAILABLE"

    def __post_init__(self) -> None:
        if not self.receipt_no.strip():
            raise OfflineFinanceError("Numéro de reçu préalloué obligatoire")
        if self.status not in {"AVAILABLE", "CONSUMED", "VOID"}:
            raise OfflineFinanceError("Statut de reçu offline invalide")


@dataclass(frozen=True, slots=True)
class ChargeSnapshot:
    charge_id: UUID
    enrollment_id: UUID
    student_id: UUID
    currency: str
    remaining_amount: Decimal
    version: int

    def __post_init__(self) -> None:
        if self.currency not in {"CDF", "USD"}:
            raise OfflineFinanceError("Devise de charge invalide")
        if money(self.remaining_amount) < 0:
            raise OfflineFinanceError("Solde restant invalide")
        if self.version < 1:
            raise OfflineFinanceError("Version de charge invalide")


@dataclass(frozen=True, slots=True)
class OfflineAllocation:
    charge_id: UUID
    amount: Decimal

    def __post_init__(self) -> None:
        if money(self.amount) <= 0:
            raise OfflineFinanceError("Une allocation doit être strictement positive")


@dataclass(frozen=True, slots=True)
class OfflinePaymentCommand:
    school_id: UUID
    lease_id: UUID
    device_id: UUID
    cashier_user_id: UUID
    cash_session_id: UUID
    student_id: UUID
    enrollment_id: UUID
    currency: str
    amount: Decimal
    receipt_token_id: UUID
    receipt_no: str
    allocations: tuple[OfflineAllocation, ...]
    journal_seq: int
    operation_id: UUID = field(default_factory=uuid4)
    idempotency_key: str = ""
    mode: str = "CASH"
    client_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    previous_entry_hash: str | None = None
    entry_hash: str | None = None

    def __post_init__(self) -> None:
        if self.journal_seq < 1:
            raise OfflineFinanceError("journal_seq doit être >= 1")
        if self.currency not in {"CDF", "USD"}:
            raise OfflineFinanceError("Devise offline invalide")
        if self.mode != "CASH":
            raise OfflineFinanceError("WEB-0D autorise uniquement CASH pour un encaissement offline définitif")
        if money(self.amount) <= 0:
            raise OfflineFinanceError("Montant offline strictement positif requis")
        key = self.idempotency_key.strip()
        if not key or len(key) > 180:
            raise OfflineFinanceError("idempotency_key obligatoire (1..180)")
        if not self.allocations:
            raise OfflineFinanceError("Au moins une allocation exacte est requise")
        if len({a.charge_id for a in self.allocations}) != len(self.allocations):
            raise OfflineFinanceError("Une charge ne peut apparaître qu'une fois dans un paiement offline")
        total = sum((money(a.amount) for a in self.allocations), Decimal("0.00"))
        if total != money(self.amount):
            raise OfflineFinanceError("La somme des allocations doit être égale au montant du paiement")
        if not self.receipt_no.strip():
            raise OfflineFinanceError("Numéro de reçu offline préalloué obligatoire")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "school_id": str(self.school_id),
            "lease_id": str(self.lease_id),
            "device_id": str(self.device_id),
            "cashier_user_id": str(self.cashier_user_id),
            "cash_session_id": str(self.cash_session_id),
            "student_id": str(self.student_id),
            "enrollment_id": str(self.enrollment_id),
            "currency": self.currency,
            "amount": str(money(self.amount)),
            "receipt_token_id": str(self.receipt_token_id),
            "receipt_no": self.receipt_no,
            "journal_seq": self.journal_seq,
            "allocations": [
                {"charge_id": str(a.charge_id), "amount": str(money(a.amount))}
                for a in sorted(self.allocations, key=lambda x: str(x.charge_id))
            ],
            "operation_id": str(self.operation_id),
            "idempotency_key": self.idempotency_key,
            "mode": self.mode,
            "client_time": utc_millis(self.client_time),
            "previous_entry_hash": self.previous_entry_hash,
        }

    def compute_entry_hash(self) -> str:
        raw = json.dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return sha256(raw).hexdigest()

    def with_computed_hash(self) -> "OfflinePaymentCommand":
        from dataclasses import replace
        return replace(self, entry_hash=self.compute_entry_hash())


def validate_command_against_snapshots(
    command: OfflinePaymentCommand,
    snapshots: Iterable[ChargeSnapshot],
) -> None:
    by_id = {x.charge_id: x for x in snapshots}
    seen_currency: set[str] = set()
    for allocation in command.allocations:
        snap = by_id.get(allocation.charge_id)
        if snap is None:
            raise OfflineFinanceConflict(f"Charge {allocation.charge_id} absente du snapshot offline")
        if snap.student_id != command.student_id or snap.enrollment_id != command.enrollment_id:
            raise OfflineFinanceConflict("Allocation vers une autre inscription/élève interdite")
        seen_currency.add(snap.currency)
        if money(allocation.amount) > money(snap.remaining_amount):
            raise OfflineFinanceConflict("Montant supérieur au solde gelé de la charge")
    if seen_currency != {command.currency}:
        raise OfflineFinanceConflict("Mélange de devises interdit dans un paiement offline")


def validate_batch_against_snapshots(
    commands: Iterable[OfflinePaymentCommand], snapshots: Iterable[ChargeSnapshot]
) -> None:
    rows = list(commands)
    snaps = list(snapshots)
    for command in rows:
        validate_command_against_snapshots(command, snaps)
    by_id = {x.charge_id: x for x in snaps}
    totals: dict[UUID, Decimal] = {}
    for command in rows:
        for allocation in command.allocations:
            totals[allocation.charge_id] = totals.get(allocation.charge_id, Decimal("0.00")) + money(allocation.amount)
    for charge_id, total in totals.items():
        snap = by_id.get(charge_id)
        if snap is None or money(total) > money(snap.remaining_amount):
            raise OfflineFinanceConflict("Allocations offline cumulées supérieures au solde gelé d'une charge")


def validate_batch_identity_uniqueness(commands: Iterable[OfflinePaymentCommand]) -> None:
    rows = list(commands)
    checks = {
        "operation_id": [str(x.operation_id) for x in rows],
        "idempotency_key": [x.idempotency_key for x in rows],
        "receipt_token_id": [str(x.receipt_token_id) for x in rows],
        "receipt_no": [x.receipt_no for x in rows],
        "journal_seq": [str(x.journal_seq) for x in rows],
    }
    for label, values in checks.items():
        if len(values) != len(set(values)):
            raise OfflineFinanceConflict(f"Doublon {label} dans le journal offline")


def verify_journal_chain(commands: Iterable[OfflinePaymentCommand]) -> None:
    previous: str | None = None
    expected_seq = 1
    for index, command in enumerate(commands, start=1):
        if command.journal_seq != expected_seq:
            raise OfflineFinanceConflict(f"Séquence du journal offline invalide à l'entrée {index}")
        if command.previous_entry_hash != previous:
            raise OfflineFinanceConflict(f"Chaîne de journal offline rompue à l'entrée {index}")
        expected = command.compute_entry_hash()
        if command.entry_hash != expected:
            raise OfflineFinanceConflict(f"Empreinte du journal offline invalide à l'entrée {index}")
        previous = expected
        expected_seq += 1


def enforce_lease_limits(
    *, commands: Iterable[OfflinePaymentCommand], lease: OfflineFinanceLease
) -> None:
    rows = list(commands)
    if len(rows) > lease.max_payments:
        raise OfflineFinanceLimitExceeded("Nombre maximal d'encaissements offline dépassé")
    cdf = sum((money(x.amount) for x in rows if x.currency == "CDF"), Decimal("0.00"))
    usd = sum((money(x.amount) for x in rows if x.currency == "USD"), Decimal("0.00"))
    if cdf > money(lease.max_cdf):
        raise OfflineFinanceLimitExceeded("Plafond CDF offline dépassé")
    if usd > money(lease.max_usd):
        raise OfflineFinanceLimitExceeded("Plafond USD offline dépassé")
