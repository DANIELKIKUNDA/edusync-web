from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from edusync.adapters.postgres_idempotency import PostgresIdempotencyRepository
from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.modules.subscriptions.application.payment_provider import PaymentProviderUnavailable, initiate_mobile_money
from edusync.shared.application.context import ActorContext
from edusync.shared.application.idempotency import IdempotentExecutor
from edusync.shared.domain.concurrency import IdempotencyConflict, IdempotencyInProgress

router = APIRouter(tags=["Abonnement EduSync de l’école"])


class MobileMoneyPayment(BaseModel):
    phone: str = Field(min_length=9, max_length=24)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)

    @field_validator("phone")
    @classmethod
    def normalize_drc_phone(cls, value: str) -> str:
        digits = "".join(c for c in value if c.isdigit())
        if digits.startswith("0"):
            digits = "243" + digits[1:]
        if not (digits.startswith("243") and len(digits) == 12):
            raise ValueError("Numéro Mobile Money congolais invalide")
        return "+" + digits


def _idempotency_key(value: str | None) -> str:
    key = (value or "").strip()
    if not key or len(key) > 180:
        raise HTTPException(400, "En-tête Idempotency-Key obligatoire et limité à 180 caractères")
    return key


def _json(row) -> dict:
    return {key: (format(value, "f") if isinstance(value, Decimal)
                  else value.isoformat() if hasattr(value, "isoformat") else value)
            for key, value in dict(row).items()}


@router.get("/account")
def school_subscription_account(actor: ActorContext = Depends(require_school_actor),
                                services: AppServices = Depends(get_services)):
    """Read model bound to the school in the signed token; never accepts a school_id from the client."""
    actor.require("subscription.account.read")
    if actor.school_id is None:
        raise HTTPException(403, "Espace école requis")
    school_id = actor.school_id
    with services.platform_db.platform_transaction() as conn:
        subscription = conn.execute(text("""SELECT s.id,s.status,s.billing_cycle,s.current_period_start,s.current_period_end,
            s.next_billing_on,s.grace_days,s.auto_renew,s.version,p.name AS plan_name,p.description AS plan_description,
            v.amount,v.currency,v.trial_days FROM saas_subscriptions s
            JOIN saas_plan_versions v ON v.id=s.plan_version_id JOIN saas_plans p ON p.id=v.plan_id
            WHERE s.school_id=:school AND s.status NOT IN ('CANCELLED','EXPIRED')
            ORDER BY s.created_at DESC LIMIT 1"""), {"school": school_id}).mappings().first()
        if subscription is None:
            return {"subscription": None, "modules": [], "invoices": [], "payments": []}
        subscription_id = subscription["id"]
        modules = conn.execute(text("""SELECT e.module_code,m.label,m.description,e.status,e.ends_at,e.limits
            FROM saas_entitlements e JOIN saas_modules m ON m.code=e.module_code
            WHERE e.school_id=:school AND e.subscription_id=:subscription ORDER BY m.label,m.code"""),
            {"school": school_id, "subscription": subscription_id}).mappings().all()
        invoices = conn.execute(text("""SELECT id,invoice_number,status,currency,period_start,period_end,issued_at,due_at,
            subtotal,discount_total,fee_total,total,paid_total,version FROM saas_invoices
            WHERE school_id=:school AND subscription_id=:subscription ORDER BY created_at DESC LIMIT 100"""),
            {"school": school_id, "subscription": subscription_id}).mappings().all()
        payments = conn.execute(text("""SELECT p.id,p.payment_reference,p.invoice_id,i.invoice_number,p.provider,p.provider_reference,
            p.channel,p.status,p.currency,p.amount,p.confirmed_at,p.created_at,p.expires_at,p.failure_message FROM saas_payments p
            JOIN saas_invoices i ON i.id=p.invoice_id
            WHERE p.school_id=:school AND i.subscription_id=:subscription ORDER BY p.created_at DESC LIMIT 100"""),
            {"school": school_id, "subscription": subscription_id}).mappings().all()
    return {"subscription": _json(subscription), "modules": [_json(row) for row in modules],
            "invoices": [_json(row) for row in invoices], "payments": [_json(row) for row in payments]}


@router.post("/invoices/{invoice_id}/mobile-money", status_code=202)
def initiate_school_payment(invoice_id: UUID, body: MobileMoneyPayment, response: Response,
                            idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                            actor: ActorContext = Depends(require_school_actor),
                            services: AppServices = Depends(get_services)):
    """Initiate only for the token school. Success is never trusted here; only a signed webhook settles money."""
    actor.require("subscription.payment.create")
    if actor.school_id is None:
        raise HTTPException(403, "Espace école requis")
    key = _idempotency_key(idempotency_key)
    payment_id = uuid4()
    try:
        with services.platform_db.platform_transaction() as conn:
            def action():
                invoice = conn.execute(text("""SELECT * FROM saas_invoices WHERE id=:id AND school_id=:school FOR UPDATE"""),
                                       {"id": invoice_id, "school": actor.school_id}).mappings().first()
                if not invoice or invoice["status"] in {"DRAFT", "VOID", "REFUNDED", "PAID"}:
                    raise HTTPException(404, "Facture payable introuvable pour votre école")
                remaining = Decimal(invoice["total"]) - Decimal(invoice["paid_total"])
                if body.amount > remaining:
                    raise HTTPException(409, f"Le montant dépasse le solde de {remaining} {invoice['currency']}")
                reference = f"MOB-{date.today():%Y%m%d}-{str(payment_id)[:8].upper()}"
                expires = datetime.now(UTC) + timedelta(minutes=services.settings.mobile_money_payment_ttl_minutes)
                provider = services.settings.mobile_money_provider.strip().upper()
                conn.execute(text("""INSERT INTO saas_payments(id,payment_reference,invoice_id,school_id,provider,channel,status,
                    currency,amount,payer_phone_masked,expires_at) VALUES(:id,:reference,:invoice,:school,:provider,
                    'MOBILE_MONEY','CREATED',:currency,:amount,:phone,:expires)"""),
                    {"id": payment_id, "reference": reference, "invoice": invoice_id, "school": actor.school_id,
                     "provider": provider, "currency": invoice["currency"], "amount": body.amount,
                     "phone": body.phone[:4] + "•••••" + body.phone[-3:], "expires": expires})
                try:
                    initiated = initiate_mobile_money(services.settings, payment_reference=reference, phone=body.phone,
                                                      amount=body.amount, currency=invoice["currency"])
                except PaymentProviderUnavailable as exc:
                    conn.execute(text("""UPDATE saas_payments SET status='FAILED',failure_code='PROVIDER_UNAVAILABLE',
                        failure_message=:message,version=version+1,updated_at=now() WHERE id=:id"""),
                        {"id": payment_id, "message": str(exc)[:240]})
                    raise HTTPException(503, str(exc)) from exc
                conn.execute(text("""UPDATE saas_payments SET status='PENDING',provider_reference=:provider_reference,
                    provider_payload_sha256=:hash,last_provider_update_at=now(),version=version+1,updated_at=now()
                    WHERE id=:id"""), {"id": payment_id, "provider_reference": initiated.provider_reference,
                                       "hash": initiated.raw_sha256})
                return 202, {"id": str(payment_id), "payment_reference": reference,
                             "provider_reference": initiated.provider_reference, "status": "PENDING",
                             "amount": format(body.amount, "f"), "currency": invoice["currency"],
                             "message": "Confirmez la demande sur votre téléphone. La facture sera mise à jour automatiquement."}
            result = IdempotentExecutor(PostgresIdempotencyRepository(conn)).execute(
                scope_key=f"school:{actor.school_id}", idempotency_key=key, operation="SAAS_MOBILE_MONEY_INITIATE",
                payload={"invoice_id": str(invoice_id), "amount": format(body.amount, "f"), "phone": body.phone},
                school_id=str(actor.school_id), actor_user_id=str(actor.user_id), action=action)
        response.status_code = result.status_code
        response.headers["Idempotent-Replayed"] = "true" if result.replayed else "false"
        return result.body
    except (IdempotencyConflict, IdempotencyInProgress, IntegrityError) as exc:
        raise HTTPException(409, "Cette demande de paiement existe déjà ou est en cours") from exc

