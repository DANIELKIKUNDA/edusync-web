from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from sqlalchemy import text


def settle_payment(conn, *, payment_id, actor_user_id=None, reason="Paiement Mobile Money confirmé") -> dict:
    """Exactly-once settlement. The payment and invoice are locked before any balance changes."""
    payment = conn.execute(text("SELECT * FROM saas_payments WHERE id=:id FOR UPDATE"), {"id": payment_id}).mappings().first()
    if not payment:
        raise ValueError("Paiement introuvable")
    invoice = conn.execute(text("SELECT * FROM saas_invoices WHERE id=:id FOR UPDATE"), {"id": payment["invoice_id"]}).mappings().one()
    if payment["status"] == "SUCCEEDED":
        return {"replayed": True, "invoice_status": invoice["status"], "paid_total": invoice["paid_total"]}
    remaining = Decimal(invoice["total"]) - Decimal(invoice["paid_total"])
    amount = Decimal(payment["amount"])
    if payment["currency"] != invoice["currency"] or amount <= 0 or amount > remaining:
        raise ValueError("Montant ou devise incompatible avec la facture")
    conn.execute(text("""UPDATE saas_payments SET status='SUCCEEDED',confirmed_at=now(),last_provider_update_at=now(),
        failure_code=NULL,failure_message=NULL,version=version+1,updated_at=now() WHERE id=:id"""), {"id": payment_id})
    paid = Decimal(invoice["paid_total"]) + amount
    state = "PAID" if paid == Decimal(invoice["total"]) else "PARTIALLY_PAID"
    conn.execute(text("UPDATE saas_invoices SET paid_total=:paid,status=:status,version=version+1,updated_at=now() WHERE id=:id"),
                 {"paid": paid, "status": state, "id": invoice["id"]})
    if state == "PAID" and invoice["subscription_id"]:
        subscription = conn.execute(text("SELECT * FROM saas_subscriptions WHERE id=:id FOR UPDATE"),
                                    {"id": invoice["subscription_id"]}).mappings().first()
        if subscription and subscription["status"] != "CANCELLED":
            new_start = max(subscription["current_period_start"], invoice["period_start"])
            new_end = max(subscription["current_period_end"], invoice["period_end"])
            conn.execute(text("""UPDATE saas_subscriptions SET status='ACTIVE',current_period_start=:start,
                current_period_end=:end,next_billing_on=:end,version=version+1,updated_at=now() WHERE id=:id"""),
                         {"start": new_start, "end": new_end, "id": subscription["id"]})
            entitlement_end = new_end + timedelta(days=int(subscription["grace_days"]))
            conn.execute(text("""UPDATE saas_entitlements SET status='ACTIVE',ends_at=:end,
                version=version+1,updated_at=now(),reason=:reason WHERE subscription_id=:id AND status IN ('ACTIVE','SUSPENDED')"""),
                         {"end": entitlement_end, "reason": reason, "id": subscription["id"]})
            if subscription["status"] != "ACTIVE":
                conn.execute(text("""INSERT INTO saas_subscription_events(subscription_id,school_id,actor_user_id,
                    from_status,to_status,reason,correlation_id) VALUES(:id,:school,:actor,:old,'ACTIVE',:reason,gen_random_uuid())"""),
                             {"id": subscription["id"], "school": subscription["school_id"], "actor": actor_user_id,
                              "old": subscription["status"], "reason": reason})
    return {"replayed": False, "invoice_status": state, "paid_total": paid}
