from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from edusync.shared.domain.events import DomainEvent


class SchoolStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DISABLED = "DISABLED"


@dataclass(slots=True)
class School:
    name: str
    code: str
    id: UUID = field(default_factory=uuid4)
    status: SchoolStatus = SchoolStatus.ACTIVE
    logo_url: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    province: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.code = self.code.strip().upper()
        if self.version < 1:
            raise ValueError("La version doit être >= 1")
        if not self.name:
            raise ValueError("Le nom de l'école est obligatoire")
        if not self.code or len(self.code) > 32:
            raise ValueError("Le code école est obligatoire et limité à 32 caractères")

    def suspend(self, reason: str) -> None:
        reason = (reason or "").strip()
        if not reason:
            raise ValueError("Un motif de suspension est obligatoire")
        if self.status == SchoolStatus.DISABLED:
            raise ValueError("Une école désactivée ne peut pas être suspendue")
        self.status = SchoolStatus.SUSPENDED
        self.updated_at = datetime.now(timezone.utc)
        self._events.append(DomainEvent(
            event_type="SCHOOL_SUSPENDED",
            aggregate_type="School",
            aggregate_id=self.id,
            school_id=self.id,
            payload={"reason": reason},
        ))

    def reactivate(self) -> None:
        if self.status == SchoolStatus.DISABLED:
            raise ValueError("Une école désactivée doit être réactivée par une procédure dédiée")
        self.status = SchoolStatus.ACTIVE
        self.updated_at = datetime.now(timezone.utc)
        self._events.append(DomainEvent(
            event_type="SCHOOL_REACTIVATED",
            aggregate_type="School",
            aggregate_id=self.id,
            school_id=self.id,
        ))

    def pull_events(self) -> list[DomainEvent]:
        events = self._events[:]
        self._events.clear()
        return events
