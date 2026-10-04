from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass(slots=True)
class User:
    email: str
    password_hash: str
    full_name: str
    id: UUID = field(default_factory=uuid4)
    active: bool = True
    is_platform_admin: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1

    def __post_init__(self) -> None:
        self.email = self.email.strip().lower()
        self.full_name = self.full_name.strip()
        if "@" not in self.email:
            raise ValueError("Adresse e-mail invalide")
        if not self.full_name:
            raise ValueError("Nom complet obligatoire")
        if self.version < 1:
            raise ValueError("La version utilisateur doit être >= 1")


@dataclass(slots=True)
class Membership:
    user_id: UUID
    school_id: UUID
    id: UUID = field(default_factory=uuid4)
    active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("La version membership doit être >= 1")
