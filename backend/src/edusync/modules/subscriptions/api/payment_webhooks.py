from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import text

from edusync.bootstrap.dependencies import get_services
from edusync.bootstrap.services import AppServices
from edusync.modules.subscriptions.application.payment_provider import verify_signature
from edusync.modules.subscriptions.application.settlement import settle_payment

router = APIRouter(tags=["Webhooks de paiement d’abonnement"])


@router.post("/{provider}")
async def receive_payment_webhook(provider: str, request: Request,
                                  event_id: str | None = Header(None, alias="X-Provider-Event-Id"),
                                  signature: str | None = Header(None, alias="X-EduSync-Signature"),
                                  services: AppServices = Depends(get_services)):
    raw = await request.body()
    provider = provider.strip().upper()
    digest = hashlib.sha256(raw).hexdigest()
    event_id = (event_id or digest).strip()[:180]
    verified = verify_signature(services.settings.mobile_money_webhook_secret, raw, signature)
    if not verified:
        with services.platform_db.platform_transaction() as conn:
            conn.execute(text("""INSERT INTO saas_payment_webhooks(provider,provider_event_id,signature_verified,body_sha256,
                processing_status,error_code,processed_at) VALUES(:provider,:event,false,:hash,'REJECTED','INVALID_SIGNATURE',now())
                ON CONFLICT(provider,provider_event_id) DO NOTHING"""),
                {"provider": provider, "event": event_id, "hash": digest})
        raise HTTPException(401, "Signature du fournisseur de paiement invalide")
    with services.platform_db.platform_transaction() as conn:
        inserted = conn.execute(text("""INSERT INTO saas_payment_webhooks(provider,provider_event_id,signature_verified,body_sha256,
                processing_status,error_code) VALUES(:provider,:event,:verified,:hash,:status,:error)
                ON CONFLICT(provider,provider_event_id) DO NOTHING RETURNING id"""),
                {"provider": provider, "event": event_id, "verified": True, "hash": digest,
                 "status": "RECEIVED", "error": None}).scalar()
        if inserted is None:
            return {"accepted": True, "replayed": True}
        try:
            data = json.loads(raw)
            provider_reference = str(data["provider_reference"])
            status = str(data["status"]).upper()
            amount = Decimal(str(data["amount"]))
            currency = str(data["currency"]).upper()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            conn.execute(text("""UPDATE saas_payment_webhooks SET processing_status='REJECTED',error_code='INVALID_PAYLOAD',
                processed_at=now() WHERE provider=:provider AND provider_event_id=:event"""),
                {"provider": provider, "event": event_id})
            raise HTTPException(400, "Événement de paiement invalide") from exc
        payment = conn.execute(text("""SELECT id,amount,currency,status FROM saas_payments
            WHERE provider=:provider AND provider_reference=:reference FOR UPDATE"""),
            {"provider": provider, "reference": provider_reference}).mappings().first()
        if not payment or Decimal(payment["amount"]) != amount or payment["currency"] != currency:
            conn.execute(text("""UPDATE saas_payment_webhooks SET processing_status='REJECTED',error_code='PAYMENT_MISMATCH',
                processed_at=now() WHERE provider=:provider AND provider_event_id=:event"""),
                {"provider": provider, "event": event_id})
            raise HTTPException(409, "Le paiement ne correspond pas à la demande enregistrée")
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
    return {"accepted": True, **settled}
