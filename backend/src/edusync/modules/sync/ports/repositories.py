from __future__ import annotations
from typing import Protocol
from edusync.modules.sync.domain.outbox import OutboxMessage

class OutboxRepository(Protocol):
    def add(self, message: OutboxMessage) -> None: ...
