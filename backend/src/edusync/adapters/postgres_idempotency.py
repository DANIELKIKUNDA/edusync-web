from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from edusync.shared.domain.concurrency import IdempotencyConflict, IdempotencyInProgress
from edusync.shared.ports.idempotency import StoredIdempotencyResult


@dataclass(slots=True)
class PostgresIdempotencyRepository:
    connection: Connection

    @staticmethod
    def _row(row) -> StoredIdempotencyResult:
        m = row._mapping
        body = m["response_json"]
        if isinstance(body, str):
            body = json.loads(body)
        return StoredIdempotencyResult(
            scope_key=m["scope_key"], idempotency_key=m["idempotency_key"],
            request_hash=m["request_hash"], operation=m["operation"], status=m["status"],
            response_status=m["response_status"], response_json=body, error_code=m["error_code"],
        )

    def get(self, *, scope_key: str, idempotency_key: str) -> StoredIdempotencyResult | None:
        row = self.connection.execute(text("""
            SELECT scope_key,idempotency_key,request_hash,operation,status,response_status,response_json,error_code
            FROM idempotency_registry WHERE scope_key=:s AND idempotency_key=:k
        """), {"s": scope_key, "k": idempotency_key}).first()
        return None if row is None else self._row(row)

    def reserve(self, *, scope_key: str, idempotency_key: str, request_hash: str,
                operation: str, school_id: str | None, actor_user_id: str | None) -> StoredIdempotencyResult:
        inserted = self.connection.execute(text("""
            INSERT INTO idempotency_registry(scope_key,school_id,actor_user_id,idempotency_key,request_hash,operation,status)
            VALUES (:scope_key,:school_id,:actor_user_id,:key,:hash,:operation,'PROCESSING')
            ON CONFLICT (scope_key,idempotency_key) DO NOTHING
            RETURNING scope_key,idempotency_key,request_hash,operation,status,response_status,response_json,error_code
        """), {
            "scope_key": scope_key, "school_id": school_id, "actor_user_id": actor_user_id,
            "key": idempotency_key, "hash": request_hash, "operation": operation,
        }).first()
        if inserted is not None:
            return self._row(inserted)

        # Serialize replays/races on the registry row. Same key+different hash is always rejected.
        row = self.connection.execute(text("""
            SELECT scope_key,idempotency_key,request_hash,operation,status,response_status,response_json,error_code
            FROM idempotency_registry
            WHERE scope_key=:s AND idempotency_key=:k
            FOR UPDATE
        """), {"s": scope_key, "k": idempotency_key}).first()
        if row is None:
            raise RuntimeError("Réservation idempotente introuvable après conflit UNIQUE")
        state = self._row(row)
        if state.request_hash != request_hash or state.operation != operation:
            raise IdempotencyConflict("Idempotency-Key réutilisée avec une requête différente")
        if state.status == "PROCESSING":
            raise IdempotencyInProgress("Une requête identique est déjà en cours")
        if state.status == "FAILED":
            row = self.connection.execute(text("""
                UPDATE idempotency_registry
                   SET status='PROCESSING', error_code=NULL, response_status=NULL,
                       response_json=NULL, completed_at=NULL
                 WHERE scope_key=:s AND idempotency_key=:k
                 RETURNING scope_key,idempotency_key,request_hash,operation,status,
                           response_status,response_json,error_code
            """), {"s": scope_key, "k": idempotency_key}).first()
            if row is None:
                raise RuntimeError("Impossible de reprendre l'opération idempotente en échec")
            return self._row(row)
        return state

    def succeed(self, *, scope_key: str, idempotency_key: str,
                response_status: int, response_json: dict[str, Any]) -> StoredIdempotencyResult:
        row = self.connection.execute(text("""
            UPDATE idempotency_registry
               SET status='SUCCEEDED', response_status=:status,
                   response_json=CAST(:body AS jsonb), completed_at=now(), error_code=NULL
             WHERE scope_key=:s AND idempotency_key=:k
             RETURNING scope_key,idempotency_key,request_hash,operation,status,response_status,response_json,error_code
        """), {"status": response_status, "body": json.dumps(response_json, ensure_ascii=False),
                 "s": scope_key, "k": idempotency_key}).first()
        if row is None:
            raise RuntimeError("Impossible de finaliser l'idempotence")
        return self._row(row)

    def fail(self, *, scope_key: str, idempotency_key: str, error_code: str) -> StoredIdempotencyResult:
        row = self.connection.execute(text("""
            UPDATE idempotency_registry
               SET status='FAILED', error_code=:error, completed_at=now()
             WHERE scope_key=:s AND idempotency_key=:k
             RETURNING scope_key,idempotency_key,request_hash,operation,status,response_status,response_json,error_code
        """), {"error": error_code, "s": scope_key, "k": idempotency_key}).first()
        if row is None:
            raise RuntimeError("Impossible de marquer l'idempotence en échec")
        return self._row(row)
