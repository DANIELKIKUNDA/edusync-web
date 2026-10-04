from __future__ import annotations
from typing import Protocol
from edusync.modules.audit.domain.audit import AuditRecord

class AuditRepository(Protocol):
    def append(self, record: AuditRecord) -> None: ...
