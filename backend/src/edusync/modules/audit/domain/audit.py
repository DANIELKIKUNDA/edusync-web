from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class AuditRecord:
    action: str
    entity_type: str
    entity_id: UUID | None
    actor_user_id: UUID | None
    school_id: UUID | None
    source: str
    result: str = "SUCCESS"
    old_data: dict[str, Any] | None = None
    new_data: dict[str, Any] | None = None
    reason: str | None = None
    membership_id: UUID | None = None
    device_id: UUID | None = None
    correlation_id: UUID | None = None
    causation_id: UUID | None = None
    idempotency_key: str | None = None
    id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
