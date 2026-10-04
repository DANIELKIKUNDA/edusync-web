from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    event_type: str
    aggregate_type: str
    aggregate_id: UUID
    payload: dict[str, Any]
    school_id: UUID | None = None
    correlation_id: UUID | None = None
    causation_id: UUID | None = None
    deduplication_key: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
