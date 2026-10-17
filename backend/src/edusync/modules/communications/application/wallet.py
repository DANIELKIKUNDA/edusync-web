"""Single Python entry point to the SMS wallet (SMS_WALLET_MODEL.md). Every movement goes through the database function
school_sms_wallet_apply (row lock, idempotency key, role checks, no negative balance); this helper only types the call."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text

_SQL = text("""SELECT * FROM school_sms_wallet_apply(
    CAST(:school AS uuid), CAST(:movement AS text), CAST(:quantity AS integer), CAST(:key AS text), CAST(:actor AS uuid),
    CAST(:source_type AS text), CAST(:source_id AS uuid), CAST(:reference AS text), CAST(:reason AS text),
    CAST(:provider_message_id AS text), CAST(:direction AS text), CAST(:provider_cost AS numeric), CAST(:provider_cost_currency AS text),
    CAST(:commercial_price AS numeric), CAST(:commercial_currency AS text))""")


def wallet_apply(conn, *, school_id: UUID | str, movement: str, quantity: int, key: str, actor: UUID | str | None = None,
                 source_type: str | None = None, source_id: UUID | str | None = None, reference: str | None = None, reason: str | None = None,
                 provider_message_id: str | None = None, direction: str | None = None, provider_cost=None, provider_cost_currency: str | None = None,
                 commercial_price=None, commercial_currency: str | None = None) -> dict:
    row = conn.execute(_SQL, {"school": str(school_id), "movement": movement, "quantity": int(quantity), "key": key,
                              "actor": str(actor) if actor else None, "source_type": source_type, "source_id": str(source_id) if source_id else None,
                              "reference": reference, "reason": reason, "provider_message_id": provider_message_id, "direction": direction,
                              "provider_cost": provider_cost, "provider_cost_currency": provider_cost_currency,
                              "commercial_price": commercial_price, "commercial_currency": commercial_currency}).mappings().one()
    return dict(row)
