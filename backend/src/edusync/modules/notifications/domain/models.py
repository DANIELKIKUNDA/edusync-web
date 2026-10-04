from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

@dataclass(slots=True)
class Notification:
    user_id: UUID
    title: str
    body: str
    school_id: UUID | None = None
    category: str = "GENERAL"
    id: UUID = field(default_factory=uuid4)
    read_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def mark_read(self) -> None:
        self.read_at = datetime.now(timezone.utc)
