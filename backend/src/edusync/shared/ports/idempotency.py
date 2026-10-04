from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class StoredIdempotencyResult:
    scope_key: str
    idempotency_key: str
    request_hash: str
    operation: str
    status: str
    response_status: int | None = None
    response_json: dict[str, Any] | None = None
    error_code: str | None = None


class IdempotencyRepository(Protocol):
    def reserve(self, *, scope_key: str, idempotency_key: str, request_hash: str,
                operation: str, school_id: str | None, actor_user_id: str | None) -> StoredIdempotencyResult: ...
    def succeed(self, *, scope_key: str, idempotency_key: str,
                response_status: int, response_json: dict[str, Any]) -> StoredIdempotencyResult: ...
    def fail(self, *, scope_key: str, idempotency_key: str, error_code: str) -> StoredIdempotencyResult: ...
    def get(self, *, scope_key: str, idempotency_key: str) -> StoredIdempotencyResult | None: ...
