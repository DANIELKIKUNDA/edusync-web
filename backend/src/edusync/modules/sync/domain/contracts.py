from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class SyncOperation:
    school_id: UUID
    user_id: UUID
    device_id: UUID
    operation_type: str
    aggregate_type: str
    aggregate_id: UUID
    payload: dict[str, Any]
    idempotency_key: str
    operation_id: UUID = field(default_factory=uuid4)
    client_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    base_version: int | None = None

    def __post_init__(self) -> None:
        if not self.idempotency_key.strip() or len(self.idempotency_key) > 180:
            raise ValueError("idempotency_key obligatoire (1..180 caractères)")
        if self.base_version is not None and self.base_version < 1:
            raise ValueError("base_version doit être >= 1")


# Point 1 locks the target doctrine: cash must remain available through connectivity loss
# under bounded preauthorization. WEB-0D single-writer is only the transitional implementation;
# Point 2 industrializes the multi-cashier authorized protocol without weakening invariants.
FINANCE_OFFLINE_POLICY = {
    "final_payment_allowed": True,
    "protocol": "AUTHORIZED_PARTITIONED_CASH_V2",
    "modes_allowed": ["CASH"],
    "requires_exclusive_school_lease": False,
    "authority_scope": "DISJOINT_CHARGE_RESERVATIONS_PER_LEASE",
    "routing_default": "STUDENT",
    "routing_upgrade": "FAMILY_WHEN_FAMILY_READ_MODEL_IS_PORTED",
    "final_cash_payment_allowed": True,
    "target_protocol": "AUTHORIZED_PARTITIONED_CASH_V2",
    "current_implemented_protocol": "AUTHORIZED_PARTITIONED_CASH_V2",
    "current_implementation_transitional": False,
    "default_enabled": False,
    "final_modes_allowed_offline": ["CASH"],
    "external_confirmation_modes": ["MOBILE_MONEY", "BANK"],
    "server_auto_release": False,
    "receipt_strategy": "PREALLOCATED_UNIQUE_RECEIPT_TOKENS_PER_LEASE",
    "journal_integrity": "SHA256_HASH_CHAIN_PLUS_SERVER_CHECKPOINT",
    "local_concurrency": "WEB_LOCKS_EXCLUSIVE_PER_LEASE",
    "conflict_rule": "NO_AUTOMATIC_FINANCIAL_MERGE",
    "unexpected_server_balance_rule": "ALLOCATE_DUE_THEN_EXPLICIT_RESIDUAL_CREDIT",
    "force_release_rule": "QUARANTINE_CHARGES_UNTIL_MANUAL_INCIDENT_RESOLUTION",
    "required_before_production_enable": [
        "G1_POSTGRES_RLS_PASS",
        "G3_MULTI_CASHIER_POSTGRES_PASS",
        "canonical finance posting adapter",
        "payment+allocations+receipt+cash+audit+outbox one transaction",
        "device durable-storage + Web Locks check",
        "multi-device disconnect/reconnect operator certification",
        "reconciliation and incident runbook",
    ],
}

CONFLICT_POLICIES = {
    "STUDENT_PROFILE": "OPTIMISTIC_LOCK_AND_REVIEW",
    "CONFIGURATION": "OPTIMISTIC_LOCK_REJECT_STALE",
    "FINANCE": "NO_AUTOMATIC_MERGE",
    "STOCK": "TRANSACTIONAL_RECOMPUTE",
    "AUDIT": "APPEND_ONLY",
}
