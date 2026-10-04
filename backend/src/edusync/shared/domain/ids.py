from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class EntityId:
    value: UUID

    @classmethod
    def new(cls) -> "EntityId":
        return cls(uuid4())

    @classmethod
    def parse(cls, raw: str | UUID) -> "EntityId":
        return cls(raw if isinstance(raw, UUID) else UUID(str(raw)))

    def __str__(self) -> str:
        return str(self.value)
