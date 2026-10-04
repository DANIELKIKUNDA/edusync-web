from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final


class OfflineDecision(str, Enum):
    """Offline execution class.

    The client may cache/read broadly, but a write is authorized according to the
    business proof required to make that write final. This avoids a blanket
    "offline = blocked" policy while keeping irreversible/external-proof actions
    fail-closed.
    """

    CACHED_READ = "CACHED_READ"
    LOCAL_SYNCABLE_WRITE = "LOCAL_SYNCABLE_WRITE"
    AUTHORIZED_CRITICAL_WRITE = "AUTHORIZED_CRITICAL_WRITE"
    ONLINE_EXTERNAL_PROOF_REQUIRED = "ONLINE_EXTERNAL_PROOF_REQUIRED"
    ONLINE_SECURITY_ADMIN_REQUIRED = "ONLINE_SECURITY_ADMIN_REQUIRED"


class ConflictStrategy(str, Enum):
    OPTIMISTIC_REVIEW = "OPTIMISTIC_REVIEW"
    REJECT_STALE = "REJECT_STALE"
    TRANSACTIONAL_RECOMPUTE = "TRANSACTIONAL_RECOMPUTE"
    NO_AUTOMATIC_MERGE = "NO_AUTOMATIC_MERGE"
    APPEND_ONLY = "APPEND_ONLY"
    IDEMPOTENT_REPLAY = "IDEMPOTENT_REPLAY"


@dataclass(frozen=True, slots=True)
class OfflineOperationPolicy:
    operation: str
    decision: OfflineDecision
    conflict: ConflictStrategy
    durable_outbox_required: bool = True
    base_version_required: bool = False
    preauthorization_required: bool = False
    external_proof_required: bool = False
    rationale: str = ""


# Locked doctrine for Point 1. Point 2 implements the multi-cashier partitioned finance path without weakening these invariants.
OFFLINE_OPERATION_POLICIES: Final[dict[str, OfflineOperationPolicy]] = {
    "REFERENCE_READ": OfflineOperationPolicy(
        operation="REFERENCE_READ",
        decision=OfflineDecision.CACHED_READ,
        conflict=ConflictStrategy.IDEMPOTENT_REPLAY,
        durable_outbox_required=False,
        rationale="Consultation autorisée depuis un read-model local tenant-scoped avec fraîcheur affichée.",
    ),
    "STUDENT_PROFILE_WRITE": OfflineOperationPolicy(
        operation="STUDENT_PROFILE_WRITE",
        decision=OfflineDecision.LOCAL_SYNCABLE_WRITE,
        conflict=ConflictStrategy.OPTIMISTIC_REVIEW,
        base_version_required=True,
        rationale="Travail scolaire courant autorisé offline; conflit humain si la version serveur a changé.",
    ),
    "ENROLLMENT_WRITE": OfflineOperationPolicy(
        operation="ENROLLMENT_WRITE",
        decision=OfflineDecision.LOCAL_SYNCABLE_WRITE,
        conflict=ConflictStrategy.REJECT_STALE,
        base_version_required=True,
        rationale="Inscription/réinscription peut être saisie offline mais une version obsolète n'est jamais écrasée.",
    ),
    "CONFIGURATION_WRITE": OfflineOperationPolicy(
        operation="CONFIGURATION_WRITE",
        decision=OfflineDecision.LOCAL_SYNCABLE_WRITE,
        conflict=ConflictStrategy.REJECT_STALE,
        base_version_required=True,
        rationale="Paramètres locaux syncables; aucune règle last-write-wins silencieuse.",
    ),
    "CASH_PAYMENT_FINAL": OfflineOperationPolicy(
        operation="CASH_PAYMENT_FINAL",
        decision=OfflineDecision.AUTHORIZED_CRITICAL_WRITE,
        conflict=ConflictStrategy.NO_AUTOMATIC_MERGE,
        preauthorization_required=True,
        rationale="Cash physiquement reçu: opération finale offline autorisée seulement avec autorité financière préarmée, reçu et preuve locale durable.",
    ),
    "MOBILE_MONEY_PAYMENT_FINAL": OfflineOperationPolicy(
        operation="MOBILE_MONEY_PAYMENT_FINAL",
        decision=OfflineDecision.ONLINE_EXTERNAL_PROOF_REQUIRED,
        conflict=ConflictStrategy.NO_AUTOMATIC_MERGE,
        external_proof_required=True,
        rationale="La finalité dépend de la confirmation du prestataire externe; offline peut saisir une intention/preuve à vérifier, pas solder définitivement.",
    ),
    "BANK_PAYMENT_FINAL": OfflineOperationPolicy(
        operation="BANK_PAYMENT_FINAL",
        decision=OfflineDecision.ONLINE_EXTERNAL_PROOF_REQUIRED,
        conflict=ConflictStrategy.NO_AUTOMATIC_MERGE,
        external_proof_required=True,
        rationale="La finalité bancaire nécessite une preuve externe vérifiable.",
    ),
    "STOCK_MOVEMENT": OfflineOperationPolicy(
        operation="STOCK_MOVEMENT",
        decision=OfflineDecision.LOCAL_SYNCABLE_WRITE,
        conflict=ConflictStrategy.TRANSACTIONAL_RECOMPUTE,
        base_version_required=True,
        rationale="Mouvement de stock autorisé offline; le serveur recalcule atomiquement le stock réel à la synchronisation.",
    ),
    "AUDIT_EVENT": OfflineOperationPolicy(
        operation="AUDIT_EVENT",
        decision=OfflineDecision.LOCAL_SYNCABLE_WRITE,
        conflict=ConflictStrategy.APPEND_ONLY,
        base_version_required=False,
        rationale="Une trace n'est jamais fusionnée ni écrasée; elle est append-only et corrélée à l'opération métier.",
    ),
    "ROLE_PERMISSION_CHANGE": OfflineOperationPolicy(
        operation="ROLE_PERMISSION_CHANGE",
        decision=OfflineDecision.ONLINE_SECURITY_ADMIN_REQUIRED,
        conflict=ConflictStrategy.REJECT_STALE,
        durable_outbox_required=False,
        rationale="Les changements de pouvoir d'accès exigent une autorité serveur actuelle.",
    ),
    "SCHOOL_LIFECYCLE_ADMIN": OfflineOperationPolicy(
        operation="SCHOOL_LIFECYCLE_ADMIN",
        decision=OfflineDecision.ONLINE_SECURITY_ADMIN_REQUIRED,
        conflict=ConflictStrategy.REJECT_STALE,
        durable_outbox_required=False,
        rationale="Création/suspension d'école Atelier Pro reste online et auditée.",
    ),
}


LOCKED_OFFLINE_INVARIANTS: Final[tuple[str, ...]] = (
    "school_id-isolation",
    "client-generated-operation-id",
    "idempotency-key",
    "durable-tenant-user-device-outbox",
    "server-inbox-deduplication",
    "no-last-write-wins-for-critical-data",
    "optimistic-version-for-mutable-aggregates",
    "cash-final-offline-requires-preauthorization",
    "financial-posting-is-one-postgresql-transaction",
    "multi-cashier-offline-authority-is-disjoint-by-charge",
    "force-release-quarantines-financial-authority",
    "incremental-sync-anchored-to-server-journal-checkpoint",
    "cdf-usd-never-implicitly-converted-or-summed",
    "audit-append-only",
    "service-worker-never-caches-authenticated-api-responses",
    "redis-never-source-of-truth",
    "server-reconciliation-after-reconnect",
)


def policy_for(operation: str) -> OfflineOperationPolicy:
    try:
        return OFFLINE_OPERATION_POLICIES[operation]
    except KeyError as exc:
        raise KeyError(f"Opération offline non classifiée: {operation}") from exc
