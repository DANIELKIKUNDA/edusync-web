from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.shared.application.context import ActorContext

router = APIRouter(tags=["Abonnement EduSync de l’école"])


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
            p.channel,p.status,p.currency,p.amount,p.confirmed_at,p.created_at FROM saas_payments p
            JOIN saas_invoices i ON i.id=p.invoice_id
            WHERE p.school_id=:school AND i.subscription_id=:subscription ORDER BY p.created_at DESC LIMIT 100"""),
            {"school": school_id, "subscription": subscription_id}).mappings().all()
    return {"subscription": _json(subscription), "modules": [_json(row) for row in modules],
            "invoices": [_json(row) for row in invoices], "payments": [_json(row) for row in payments]}

