from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from edusync.shared.domain.concurrency import IdempotencyConflict, IdempotencyInProgress
from edusync.shared.ports.idempotency import IdempotencyRepository

T = TypeVar("T")


def canonical_request_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class IdempotentResponse:
    status_code: int
    body: dict[str, Any]
    replayed: bool


class IdempotentExecutor:
    """Executes one logical mutation at most once for a given scope/key/hash.

    The persistent repository is the authoritative guard. In production its reserve()
    must be backed by a UNIQUE constraint and one transaction.
    """

    def __init__(self, repository: IdempotencyRepository):
        self.repository = repository

    def execute(self, *, scope_key: str, idempotency_key: str, operation: str,
                payload: Any, school_id: str | None, actor_user_id: str | None,
                action: Callable[[], tuple[int, dict[str, Any]]]) -> IdempotentResponse:
        key = (idempotency_key or "").strip()
        if not key or len(key) > 180:
            raise ValueError("Idempotency-Key obligatoire (1..180 caractères)")
        request_hash = canonical_request_hash(payload)
        state = self.repository.reserve(
            scope_key=scope_key, idempotency_key=key, request_hash=request_hash,
            operation=operation, school_id=school_id, actor_user_id=actor_user_id,
        )
        if state.request_hash != request_hash or state.operation != operation:
            raise IdempotencyConflict("Cette Idempotency-Key correspond à une autre requête")
        if state.status == "SUCCEEDED":
            return IdempotentResponse(state.response_status or 200, state.response_json or {}, True)
        if state.status != "PROCESSING":
            raise IdempotencyConflict("État d'idempotence incompatible")
        if getattr(state, "_already_reserved", False):
            raise IdempotencyInProgress("Cette opération est déjà en cours")
        try:
            status, body = action()
        except Exception as exc:
            try:
                self.repository.fail(scope_key=scope_key, idempotency_key=key, error_code=type(exc).__name__)
            except Exception:  # noqa: BLE001 — the transaction is already aborted (e.g. a unique violation under
                pass  # concurrency): the whole transaction rolls back anyway; keep the original error (-> 409, not 500)
            raise exc
        stored = self.repository.succeed(
            scope_key=scope_key, idempotency_key=key,
            response_status=status, response_json=body,
        )
        return IdempotentResponse(stored.response_status or status, stored.response_json or body, False)
