from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


class OptimisticConcurrencyError(RuntimeError):
    """The aggregate changed after the caller read it."""


class IdempotencyConflict(RuntimeError):
    """Same idempotency key reused for a different logical request."""


class IdempotencyInProgress(RuntimeError):
    """Another worker currently owns the same logical mutation."""


@dataclass(frozen=True, slots=True)
class VersionToken:
    aggregate_type: str
    aggregate_id: UUID
    version: int

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("La version d'un agrégat doit être >= 1")
