from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import text

from edusync.bootstrap.dependencies import get_services
from edusync.bootstrap.services import AppServices
from edusync.modules.subscriptions.application.payment_provider import verify_signature
from edusync.modules.subscriptions.application.settlement import settle_payment

router = APIRouter(tags=["Webhooks de paiement d’abonnement"])
log = logging.getLogger("edusync.subscriptions.webhooks")


@router.post("/{provider}")
async def receive_payment_webhook(provider: str, request: Request,
                                  signature: str | None = Header(None, alias="X-EduSync-Signature"),
                                  services: AppServices = Depends(get_services)):
    raw = await request.body()
    provider = provider.strip().upper()
    digest = hashlib.sha256(raw).hexdigest()
    verified = verify_signature(services.settings.mobile_money_webhook_secret, raw, signature)
    if not verified:
        # Nothing is written for an unsigned request (an open endpoint must not fill the database); a log is enough.
        log.warning("webhook de paiement refusé : signature invalide (fournisseur %s, empreinte %s)", provider[:40], digest[:16])
        raise HTTPException(401, "Signature du fournisseur de paiement invalide")
    # The event identity is taken from the signed body only. The X-Provider-Event-Id header is not covered by the
    # signature: trusting it would let a captured message be replayed under a new identity (review 2026-11-21).
    try:
        signed_event = json.loads(raw).get("event_id")
    except (ValueError, AttributeError):
        signed_event = None
    event_id = (str(signed_event).strip() if signed_event else digest)[:180]
    with services.platform_db.platform_transaction() as conn:
        outcome = _process(conn, provider=provider, event_id=event_id, digest=digest, raw=raw)
    # Raised only AFTER the commit: a rejection stays recorded (it was rolled back when raised inside the transaction).
    if outcome[0] != 200:
        raise HTTPException(outcome[0], outcome[1])
    return {"accepted": True, **outcome[1]}


def _reject(conn, *, provider: str, event_id: str, code: str) -> None:
    conn.execute(text("""UPDATE saas_payment_webhooks SET processing_status='REJECTED',error_code=:code,
        processed_at=now() WHERE provider=:provider AND provider_event_id=:event"""),
        {"provider": provider, "event": event_id, "code": code})


def _process(conn, *, provider: str, event_id: str, digest: str, raw: bytes) -> tuple[int, object]:
    inserted = conn.execute(text("""INSERT INTO saas_payment_webhooks(provider,provider_event_id,signature_verified,body_sha256,
            processing_status,error_code) VALUES(:provider,:event,true,:hash,'RECEIVED',NULL)
            ON CONFLICT(provider,provider_event_id) DO NOTHING RETURNING id"""),
            {"provider": provider, "event": event_id, "hash": digest}).scalar()
    if inserted is None:
        return 200, {"replayed": True}
    try:
        data = json.loads(raw)
        provider_reference = str(data["provider_reference"])
        status = str(data["status"]).upper()
        amount = Decimal(str(data["amount"]))
        currency = str(data["currency"]).upper()
    except (KeyError, TypeError, ValueError, AttributeError, ArithmeticError, json.JSONDecodeError):
        _reject(conn, provider=provider, event_id=event_id, code="INVALID_PAYLOAD")
        return 400, "Événement de paiement invalide"
    payment = conn.execute(text("""SELECT id,amount,currency,status FROM saas_payments
        WHERE provider=:provider AND provider_reference=:reference FOR UPDATE"""),
        {"provider": provider, "reference": provider_reference}).mappings().first()
    if not payment or Decimal(payment["amount"]) != amount or payment["currency"] != currency:
        _reject(conn, provider=provider, event_id=event_id, code="PAYMENT_MISMATCH")
        return 409, "Le paiement ne correspond pas à la demande enregistrée"
    if status == "SUCCEEDED":
        settled = settle_payment(conn, payment_id=payment["id"])
    elif status in {"FAILED", "CANCELLED", "EXPIRED"}:
        if payment["status"] != "SUCCEEDED":
            conn.execute(text("""UPDATE saas_payments SET status=:status,failure_code=:code,
                failure_message=:message,last_provider_update_at=now(),version=version+1,updated_at=now() WHERE id=:id"""),
                {"status": status, "code": str(data.get("failure_code") or status)[:80],
                 "message": str(data.get("message") or "Paiement non abouti")[:240], "id": payment["id"]})
        settled = {"replayed": payment["status"] == "SUCCEEDED"}
    else:
        settled = {"replayed": payment["status"] == "PENDING"}
    conn.execute(text("""UPDATE saas_payment_webhooks SET processing_status='PROCESSED',processed_at=now()
        WHERE provider=:provider AND provider_event_id=:event"""), {"provider": provider, "event": event_id})
    return 200, settled
