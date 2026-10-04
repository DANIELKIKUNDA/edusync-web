from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any

from edusync.shared.domain.concurrency import IdempotencyConflict, IdempotencyInProgress
from edusync.shared.ports.idempotency import StoredIdempotencyResult


@dataclass(slots=True)
class _Record:
    scope_key: str
    idempotency_key: str
    request_hash: str
    operation: str
    status: str = "PROCESSING"
    response_status: int | None = None
    response_json: dict[str, Any] | None = None
    error_code: str | None = None


class MemoryIdempotencyRepository:
    """Thread-safe test adapter mirroring the PostgreSQL uniqueness semantics."""

    def __init__(self):
        self._lock = RLock()
        self._items: dict[tuple[str, str], _Record] = {}
        self._owners: set[tuple[str, str]] = set()

    @staticmethod
    def _result(r: _Record) -> StoredIdempotencyResult:
        return StoredIdempotencyResult(r.scope_key, r.idempotency_key, r.request_hash,
            r.operation, r.status, r.response_status, r.response_json, r.error_code)

    def reserve(self, *, scope_key: str, idempotency_key: str, request_hash: str,
                operation: str, school_id: str | None, actor_user_id: str | None) -> StoredIdempotencyResult:
        k = (scope_key, idempotency_key)
        with self._lock:
            r = self._items.get(k)
            if r is None:
                r = _Record(scope_key, idempotency_key, request_hash, operation)
                self._items[k] = r
                self._owners.add(k)
                return self._result(r)
            if r.request_hash != request_hash or r.operation != operation:
                raise IdempotencyConflict("Idempotency-Key réutilisée avec une requête différente")
            if r.status == "PROCESSING":
                raise IdempotencyInProgress("Opération déjà en cours")
            if r.status == "FAILED":
                # Safe retry contract: critical side effects must be transactional/outbox-only.
                r.status = "PROCESSING"
                r.error_code = None
                r.response_status = None
                r.response_json = None
                self._owners.add(k)
            return self._result(r)

    def succeed(self, *, scope_key: str, idempotency_key: str,
                response_status: int, response_json: dict[str, Any]) -> StoredIdempotencyResult:
        k = (scope_key, idempotency_key)
        with self._lock:
            r = self._items[k]
            r.status = "SUCCEEDED"
            r.response_status = response_status
            r.response_json = dict(response_json)
            self._owners.discard(k)
            return self._result(r)

    def fail(self, *, scope_key: str, idempotency_key: str, error_code: str) -> StoredIdempotencyResult:
        k = (scope_key, idempotency_key)
        with self._lock:
            r = self._items[k]
            r.status = "FAILED"
            r.error_code = error_code
            self._owners.discard(k)
            return self._result(r)

    def get(self, *, scope_key: str, idempotency_key: str) -> StoredIdempotencyResult | None:
        with self._lock:
            r = self._items.get((scope_key, idempotency_key))
            return None if r is None else self._result(r)
