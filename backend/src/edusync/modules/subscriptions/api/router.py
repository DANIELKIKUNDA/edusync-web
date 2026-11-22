from __future__ import annotations

import json
import csv
import io
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from edusync.adapters.postgres_idempotency import PostgresIdempotencyRepository
from edusync.adapters.postgres_repositories import PostgresAuditRepository
from edusync.bootstrap.dependencies import get_services, require_platform_actor, require_recent_mfa
from edusync.bootstrap.services import AppServices
from edusync.modules.audit.domain.audit import AuditRecord
from edusync.modules.subscriptions.domain.subscription import BillingCycle, SubscriptionStatus, period_end
from edusync.shared.application.context import ActorContext
from edusync.shared.application.idempotency import IdempotentExecutor
from edusync.shared.domain.concurrency import IdempotencyConflict, IdempotencyInProgress

router = APIRouter(tags=["Atelier Pro — abonnements"])


def _need(actor: ActorContext, capability: str) -> None:
    actor.require(capability)


def _key(value: str | None) -> str:
    key = (value or "").strip()
    if not key:
        raise HTTPException(400, "En-tête Idempotency-Key obligatoire pour cette mutation")
    if len(key) > 180:
        raise HTTPException(400, "Idempotency-Key trop longue")
    return key


def _audit(conn, actor: ActorContext, *, action: str, entity_type: str, entity_id: UUID,
           school_id: UUID | None = None, reason: str | None = None, old=None, new=None, key: str | None = None) -> None:
    PostgresAuditRepository(conn).append(AuditRecord(
        action=action, entity_type=entity_type, entity_id=entity_id, actor_user_id=actor.user_id,
        school_id=school_id, source=actor.source, reason=reason, old_data=old, new_data=new,
        correlation_id=actor.correlation_id, idempotency_key=key,
    ))


def _json(row) -> dict:
    return {k: (format(v, "f") if isinstance(v, Decimal) else v.isoformat() if hasattr(v, "isoformat") else v)
            for k, v in dict(row).items()}


class PlanCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64, pattern=r"^[A-Z][A-Z0-9_]*$")
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=2000)
    public_offer: bool = True


class PlanVersionCreate(BaseModel):
    billing_cycle: BillingCycle
    currency: str = Field(pattern="^(USD|CDF)$")
    amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    trial_days: int = Field(default=0, ge=0, le=90)
    grace_days: int = Field(default=10, ge=0, le=90)
    effective_from: date
    module_codes: list[str] = Field(min_length=1, max_length=30)

    @field_validator("module_codes")
    @classmethod
    def unique_modules(cls, value: list[str]) -> list[str]:
        clean = [item.strip().upper() for item in value]
        if len(clean) != len(set(clean)):
            raise ValueError("Un module ne peut apparaître qu’une fois")
        return clean


class ReasonInput(BaseModel):
    reason: str = Field(min_length=5, max_length=500)
    version: int = Field(ge=1)


class SubscriptionCreate(BaseModel):
    school_id: UUID
    plan_version_id: UUID
    starts_on: date
    initial_status: SubscriptionStatus = SubscriptionStatus.PENDING_PAYMENT
    auto_renew: bool = True
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("initial_status")
    @classmethod
    def initial_state(cls, value: SubscriptionStatus) -> SubscriptionStatus:
        if value not in {SubscriptionStatus.TRIAL, SubscriptionStatus.PENDING_PAYMENT, SubscriptionStatus.ACTIVE}:
            raise ValueError("État initial non autorisé")
        return value


class InvoiceCreate(BaseModel):
    period_start: date
    due_days: int = Field(default=7, ge=0, le=90)
    discount_total: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)
    fee_total: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)
    reason: str = Field(min_length=5, max_length=500)


class ManualPaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(pattern="^(USD|CDF)$")
    provider: str = Field(default="MANUAL", min_length=2, max_length=48)
    provider_reference: str = Field(min_length=3, max_length=180)
    reason: str = Field(min_length=5, max_length=500)


@router.get("/catalog")
def catalog(actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    _need(actor, "platform.billing.read")
    with services.platform_db.platform_transaction() as conn:
        modules = conn.execute(text("SELECT code,label,description,status,dependencies,version FROM saas_modules ORDER BY status,code")).mappings()
        plans = conn.execute(text("""SELECT p.id,p.code,p.name,p.description,p.status,p.public_offer,p.version,
          count(v.id) AS version_count FROM saas_plans p LEFT JOIN saas_plan_versions v ON v.plan_id=p.id
          GROUP BY p.id ORDER BY lower(p.name),p.code""")).mappings()
        return {"modules": [_json(r) for r in modules], "plans": [_json(r) for r in plans]}


@router.get("/plans/{plan_id}/versions")
def list_plan_versions(plan_id: UUID, actor: ActorContext = Depends(require_platform_actor),
                       services: AppServices = Depends(get_services)):
    _need(actor, "platform.billing.read")
    with services.platform_db.platform_transaction() as conn:
        if not conn.execute(text("SELECT 1 FROM saas_plans WHERE id=:id"), {"id": plan_id}).first():
            raise HTTPException(404, "Plan introuvable")
        rows = conn.execute(text("""SELECT v.*,coalesce(array_agg(m.module_code ORDER BY m.module_code)
            FILTER (WHERE m.module_code IS NOT NULL),'{}') AS module_codes FROM saas_plan_versions v
            LEFT JOIN saas_plan_modules m ON m.plan_version_id=v.id WHERE v.plan_id=:id
            GROUP BY v.id ORDER BY v.version DESC,v.billing_cycle,v.currency"""), {"id": plan_id}).mappings()
        return [_json(row) for row in rows]


@router.post("/plans", status_code=201)
def create_plan(body: PlanCreate, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    _need(actor, "platform.billing.plans.manage")
    require_recent_mfa(services, actor, "platform.billing.plans.manage")
    key = _key(idempotency_key)
    plan_id = uuid4()
    try:
        with services.platform_db.platform_transaction() as conn:
            def action():
                row = conn.execute(text("""INSERT INTO saas_plans(id,code,name,description,public_offer)
                    VALUES(:id,:code,:name,:description,:public) RETURNING id,code,name,description,status,public_offer,version,created_at"""),
                    {"id": plan_id, "code": body.code, "name": body.name.strip(), "description": body.description.strip(), "public": body.public_offer}).mappings().one()
                result = _json(row)
                _audit(conn, actor, action="SAAS_PLAN_CREATED", entity_type="SaaSPlan", entity_id=plan_id, new=result, key=key)
                return 201, result
            result = IdempotentExecutor(PostgresIdempotencyRepository(conn)).execute(
                scope_key="platform", idempotency_key=key, operation="SAAS_PLAN_CREATE",
                payload=body.model_dump(mode="json"), school_id=None, actor_user_id=str(actor.user_id), action=action,
            )
        response.status_code = result.status_code
        response.headers["Idempotent-Replayed"] = "true" if result.replayed else "false"
        return result.body
    except (IntegrityError, IdempotencyConflict, IdempotencyInProgress) as exc:
        raise HTTPException(409, "Ce code de plan existe déjà") from exc


@router.post("/plans/{plan_id}/versions", status_code=201)
def create_plan_version(plan_id: UUID, body: PlanVersionCreate,
                        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                        actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    _need(actor, "platform.billing.plans.manage")
    require_recent_mfa(services, actor, "platform.billing.plans.manage")
    key = _key(idempotency_key)
    with services.platform_db.platform_transaction() as conn:
        if not conn.execute(text("SELECT 1 FROM saas_plans WHERE id=:id AND status<>'RETIRED'"), {"id": plan_id}).first():
            raise HTTPException(404, "Plan introuvable ou retiré")
        active = set(conn.execute(text("SELECT code FROM saas_modules WHERE code=ANY(:codes) AND status='ACTIVE'"), {"codes": body.module_codes}).scalars())
        missing = sorted(set(body.module_codes) - active)
        if missing:
            raise HTTPException(409, {"message": "Modules indisponibles dans une offre commerciale", "modules": missing})
        version = int(conn.execute(text("SELECT coalesce(max(version),0)+1 FROM saas_plan_versions WHERE plan_id=:id"), {"id": plan_id}).scalar_one())
        version_id = uuid4()
        row = conn.execute(text("""INSERT INTO saas_plan_versions(id,plan_id,version,billing_cycle,currency,amount,trial_days,grace_days,effective_from)
          VALUES(:id,:plan,:version,:cycle,:currency,:amount,:trial,:grace,:effective) RETURNING *"""),
          {"id": version_id, "plan": plan_id, "version": version, "cycle": body.billing_cycle.value, "currency": body.currency,
           "amount": body.amount, "trial": body.trial_days, "grace": body.grace_days, "effective": body.effective_from}).mappings().one()
        for code in body.module_codes:
            conn.execute(text("INSERT INTO saas_plan_modules(plan_version_id,module_code) VALUES(:id,:code)"), {"id": version_id, "code": code})
        result = {**_json(row), "module_codes": body.module_codes}
        _audit(conn, actor, action="SAAS_PLAN_VERSION_CREATED", entity_type="SaaSPlanVersion", entity_id=version_id,
               new=result, key=key)
        return result


@router.post("/plan-versions/{version_id}/publish")
def publish_plan_version(version_id: UUID, body: ReasonInput,
                         actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    _need(actor, "platform.billing.plans.manage")
    require_recent_mfa(services, actor, "platform.billing.plans.manage")
    with services.platform_db.platform_transaction() as conn:
        row = conn.execute(text("""UPDATE saas_plan_versions SET status='PUBLISHED' WHERE id=:id AND status='DRAFT'
          RETURNING plan_id,version,billing_cycle,currency,amount"""), {"id": version_id}).mappings().first()
        if not row:
            raise HTTPException(409, "Version introuvable ou déjà publiée")
        conn.execute(text("UPDATE saas_plans SET status='ACTIVE',version=version+1,updated_at=now() WHERE id=:id"), {"id": row["plan_id"]})
        _audit(conn, actor, action="SAAS_PLAN_VERSION_PUBLISHED", entity_type="SaaSPlanVersion", entity_id=version_id,
               reason=body.reason, new=_json(row))
        return {"id": str(version_id), "status": "PUBLISHED"}


@router.get("/subscriptions")
def list_subscriptions(school_id: UUID | None = None, status: SubscriptionStatus | None = None,
                       limit: int = Query(50, ge=1, le=200), actor: ActorContext = Depends(require_platform_actor),
                       services: AppServices = Depends(get_services)):
    _need(actor, "platform.billing.read")
    where, params = ["TRUE"], {"limit": limit}
    if school_id:
        where.append("s.school_id=:school"); params["school"] = school_id
    if status:
        where.append("s.status=:status"); params["status"] = status.value
    with services.platform_db.platform_transaction() as conn:
        rows = conn.execute(text(f"""SELECT s.*,sc.name AS school_name,p.name AS plan_name,v.amount,v.currency
          FROM saas_subscriptions s JOIN schools sc ON sc.id=s.school_id JOIN saas_plan_versions v ON v.id=s.plan_version_id
          JOIN saas_plans p ON p.id=v.plan_id WHERE {' AND '.join(where)} ORDER BY s.updated_at DESC,s.id LIMIT :limit"""), params).mappings()
        return [_json(r) for r in rows]


@router.post("/subscriptions", status_code=201)
def create_subscription(body: SubscriptionCreate, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                        actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    _need(actor, "platform.billing.subscriptions.manage")
    require_recent_mfa(services, actor, "platform.billing.subscriptions.manage")
    key = _key(idempotency_key)
    subscription_id = uuid4()
    with services.platform_db.platform_transaction() as conn:
        version = conn.execute(text("""SELECT billing_cycle,grace_days,status FROM saas_plan_versions
          WHERE id=:id"""), {"id": body.plan_version_id}).mappings().first()
        if not version or version["status"] != "PUBLISHED":
            raise HTTPException(409, "Seule une version de plan publiée peut être attribuée")
        if not conn.execute(text("SELECT 1 FROM schools WHERE id=:id"), {"id": body.school_id}).first():
            raise HTTPException(404, "École introuvable")
        end = period_end(body.starts_on, BillingCycle(version["billing_cycle"]))
        row = conn.execute(text("""INSERT INTO saas_subscriptions(id,school_id,plan_version_id,billing_cycle,status,current_period_start,current_period_end,next_billing_on,grace_days,auto_renew)
          VALUES(:id,:school,:plan,:cycle,:status,:start,:end,:next,:grace,:renew) RETURNING *"""),
          {"id": subscription_id, "school": body.school_id, "plan": body.plan_version_id, "cycle": version["billing_cycle"],
           "status": body.initial_status.value, "start": body.starts_on, "end": end, "next": end, "grace": version["grace_days"], "renew": body.auto_renew}).mappings().one()
        conn.execute(text("""INSERT INTO saas_subscription_events(subscription_id,school_id,actor_user_id,to_status,reason,correlation_id,idempotency_key)
          VALUES(:id,:school,:actor,:status,:reason,:correlation,:key)"""), {"id": subscription_id, "school": body.school_id,
          "actor": actor.user_id, "status": body.initial_status.value, "reason": body.reason.strip(), "correlation": actor.correlation_id, "key": key})
        conn.execute(text("""INSERT INTO saas_entitlements(school_id,subscription_id,module_code,source,status,ends_at,limits,reason)
          SELECT :school,:subscription,module_code,'PLAN','ACTIVE',:ends,limits,:reason FROM saas_plan_modules WHERE plan_version_id=:plan
          ON CONFLICT (school_id,module_code) WHERE status='ACTIVE' DO NOTHING"""),   # a module already in service is kept (lot 0)
          {"school": body.school_id, "subscription": subscription_id, "ends": end + timedelta(days=int(version["grace_days"])),
           "reason": body.reason.strip(), "plan": body.plan_version_id})
        result = _json(row)
        _audit(conn, actor, action="SAAS_SUBSCRIPTION_CREATED", entity_type="SaaSSubscription", entity_id=subscription_id,
               school_id=body.school_id, reason=body.reason, new=result, key=key)
        return result


@router.post("/subscriptions/{subscription_id}/transition")
def transition_subscription(subscription_id: UUID, target: SubscriptionStatus, body: ReasonInput,
                            idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                            actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    from edusync.modules.subscriptions.domain.subscription import Subscription
    _need(actor, "platform.billing.subscriptions.manage")
    if target == SubscriptionStatus.GRACE:
        _need(actor, "platform.billing.overrides.grant")
        require_recent_mfa(services, actor, "platform.billing.overrides.grant")
    require_recent_mfa(services, actor, "platform.billing.subscriptions.manage")
    key = _key(idempotency_key)
    with services.platform_db.platform_transaction() as conn:
        current = conn.execute(text("SELECT * FROM saas_subscriptions WHERE id=:id FOR UPDATE"), {"id": subscription_id}).mappings().first()
        if not current:
            raise HTTPException(404, "Abonnement introuvable")
        if int(current["version"]) != body.version:
            raise HTTPException(409, "L’abonnement a été modifié; rechargez les données")
        aggregate = Subscription(id=current["id"], school_id=current["school_id"], plan_version_id=current["plan_version_id"],
          cycle=BillingCycle(current["billing_cycle"]), status=SubscriptionStatus(current["status"]),
          current_period_start=current["current_period_start"], current_period_end=current["current_period_end"],
          grace_days=current["grace_days"], auto_renew=current["auto_renew"], version=current["version"])
        try:
            changed = aggregate.transition(target, reason=body.reason)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        cancelled = target == SubscriptionStatus.CANCELLED
        conn.execute(text("""UPDATE saas_subscriptions SET status=:status,version=:new_version,updated_at=now(),
          cancelled_at=CASE WHEN :cancelled THEN now() ELSE NULL END,cancellation_reason=CASE WHEN :cancelled THEN :reason ELSE NULL END
          WHERE id=:id AND version=:expected"""), {"status": target.value, "new_version": changed.version, "cancelled": cancelled,
          "reason": body.reason.strip(), "id": subscription_id, "expected": body.version})
        entitlement_status = "ACTIVE" if changed.commercially_usable else "SUSPENDED"
        conn.execute(text("UPDATE saas_entitlements SET status=:status,version=version+1,updated_at=now(),reason=:reason WHERE subscription_id=:id AND status IN ('ACTIVE','SUSPENDED')"),
                     {"status": entitlement_status, "reason": body.reason.strip(), "id": subscription_id})
        conn.execute(text("""INSERT INTO saas_subscription_events(subscription_id,school_id,actor_user_id,from_status,to_status,reason,correlation_id,idempotency_key)
          VALUES(:id,:school,:actor,:old,:new,:reason,:correlation,:key)"""), {"id": subscription_id, "school": current["school_id"], "actor": actor.user_id,
          "old": current["status"], "new": target.value, "reason": body.reason.strip(), "correlation": actor.correlation_id, "key": key})
        _audit(conn, actor, action="SAAS_SUBSCRIPTION_TRANSITIONED", entity_type="SaaSSubscription", entity_id=subscription_id,
               school_id=current["school_id"], reason=body.reason, old={"status": current["status"], "version": body.version},
               new={"status": target.value, "version": changed.version}, key=key)
        return {"id": str(subscription_id), "status": target.value, "version": changed.version}


@router.get("/invoices")
def list_invoices(school_id: UUID | None = None, status: str | None = Query(None, pattern="^(DRAFT|ISSUED|PARTIALLY_PAID|PAID|OVERDUE|VOID|REFUNDED)$"),
                  limit: int = Query(50, ge=1, le=200), actor: ActorContext = Depends(require_platform_actor),
                  services: AppServices = Depends(get_services)):
    _need(actor, "platform.billing.read")
    where, params = ["TRUE"], {"limit": limit}
    if school_id:
        where.append("i.school_id=:school"); params["school"] = school_id
    if status:
        where.append("i.status=:status"); params["status"] = status
    with services.platform_db.platform_transaction() as conn:
        rows = conn.execute(text(f"""SELECT i.*,s.name AS school_name FROM saas_invoices i
            JOIN schools s ON s.id=i.school_id WHERE {' AND '.join(where)}
            ORDER BY i.created_at DESC,i.id LIMIT :limit"""), params).mappings()
        return [_json(row) for row in rows]


@router.get("/payments")
def list_payments(school_id: UUID | None = None, invoice_id: UUID | None = None,
                  limit: int = Query(50, ge=1, le=200), actor: ActorContext = Depends(require_platform_actor),
                  services: AppServices = Depends(get_services)):
    _need(actor, "platform.billing.read")
    where, params = ["TRUE"], {"limit": limit}
    if school_id:
        where.append("p.school_id=:school"); params["school"] = school_id
    if invoice_id:
        where.append("p.invoice_id=:invoice"); params["invoice"] = invoice_id
    with services.platform_db.platform_transaction() as conn:
        rows = conn.execute(text(f"""SELECT p.*,i.invoice_number,s.name AS school_name FROM saas_payments p
            JOIN saas_invoices i ON i.id=p.invoice_id JOIN schools s ON s.id=p.school_id
            WHERE {' AND '.join(where)} ORDER BY p.created_at DESC,p.id LIMIT :limit"""), params).mappings()
        return [_json(row) for row in rows]


@router.get("/export.csv")
def export_billing_csv(actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    _need(actor, "platform.billing.export")
    with services.platform_db.platform_transaction() as conn:
        rows = conn.execute(text("""SELECT sc.code AS school_code,sc.name AS school_name,s.status AS subscription_status,
            p.name AS plan_name,s.billing_cycle,s.current_period_start,s.current_period_end,
            coalesce(sum(i.total),0) AS invoiced,coalesce(sum(i.paid_total),0) AS paid,v.currency
            FROM saas_subscriptions s JOIN schools sc ON sc.id=s.school_id
            JOIN saas_plan_versions v ON v.id=s.plan_version_id JOIN saas_plans p ON p.id=v.plan_id
            LEFT JOIN saas_invoices i ON i.subscription_id=s.id
            GROUP BY sc.code,sc.name,s.status,p.name,s.billing_cycle,s.current_period_start,s.current_period_end,v.currency
            ORDER BY lower(sc.name),sc.code LIMIT 10000""")).mappings().all()
        stream = io.StringIO()
        fields = ["school_code", "school_name", "subscription_status", "plan_name", "billing_cycle",
                  "current_period_start", "current_period_end", "invoiced", "paid", "currency"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(_json(row))
        export_id = uuid4()
        _audit(conn, actor, action="SAAS_BILLING_EXPORTED", entity_type="SaaSBillingExport", entity_id=export_id,
               new={"row_count": len(rows), "format": "CSV"})
    return Response(content="\ufeff" + stream.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=abonnements-edusync.csv"})


@router.post("/subscriptions/{subscription_id}/invoices", status_code=201)
def issue_invoice(subscription_id: UUID, body: InvoiceCreate, response: Response,
                  idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                  actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    _need(actor, "platform.billing.invoices.manage")
    require_recent_mfa(services, actor, "platform.billing.invoices.manage")
    key = _key(idempotency_key)
    invoice_id = uuid4()
    try:
        with services.platform_db.platform_transaction() as conn:
            def action():
                subscription = conn.execute(text("""SELECT s.*,v.amount,v.currency,p.name AS plan_name,sc.name AS school_name,
                    sc.email,sc.phone,sc.address,sc.city,sc.province FROM saas_subscriptions s
                    JOIN saas_plan_versions v ON v.id=s.plan_version_id JOIN saas_plans p ON p.id=v.plan_id
                    JOIN schools sc ON sc.id=s.school_id WHERE s.id=:id AND s.status NOT IN ('CANCELLED','EXPIRED') FOR UPDATE"""),
                    {"id": subscription_id}).mappings().first()
                if not subscription:
                    raise HTTPException(404, "Abonnement facturable introuvable")
                period_finish = period_end(body.period_start, BillingCycle(subscription["billing_cycle"]))
                subtotal = Decimal(subscription["amount"])
                total = subtotal - body.discount_total + body.fee_total
                if total < 0:
                    raise HTTPException(409, "La remise ne peut pas dépasser le montant facturé augmenté des frais")
                number = conn.execute(text("SELECT 'EDS-'||to_char(CURRENT_DATE,'YYYY')||'-'||lpad(nextval('saas_invoice_number_seq')::text,8,'0')")).scalar_one()
                bill_to = {"school_id": str(subscription["school_id"]), "name": subscription["school_name"],
                           "email": subscription["email"], "phone": subscription["phone"], "address": subscription["address"],
                           "city": subscription["city"], "province": subscription["province"]}
                row = conn.execute(text("""INSERT INTO saas_invoices(id,invoice_number,school_id,subscription_id,status,currency,
                    period_start,period_end,issued_at,due_at,subtotal,discount_total,fee_total,total,bill_to_snapshot)
                    VALUES(:id,:number,:school,:subscription,'ISSUED',:currency,:start,:end,now(),now()+(:days||' days')::interval,
                    :subtotal,:discount,:fee,:total,CAST(:bill_to AS jsonb)) RETURNING *"""),
                    {"id": invoice_id, "number": number, "school": subscription["school_id"], "subscription": subscription_id,
                     "currency": subscription["currency"], "start": body.period_start, "end": period_finish, "days": body.due_days,
                     "subtotal": subtotal, "discount": body.discount_total, "fee": body.fee_total, "total": total,
                     "bill_to": json.dumps(bill_to, ensure_ascii=False)}).mappings().one()
                conn.execute(text("""INSERT INTO saas_invoice_lines(invoice_id,description,quantity,unit_price,line_total,metadata)
                    VALUES(:invoice,:description,1,:amount,:amount,CAST(:metadata AS jsonb))"""),
                    {"invoice": invoice_id, "description": f"Abonnement EduSync — {subscription['plan_name']}", "amount": subtotal,
                     "metadata": json.dumps({"plan_version_id": str(subscription["plan_version_id"])})})
                result = _json(row)
                _audit(conn, actor, action="SAAS_INVOICE_ISSUED", entity_type="SaaSInvoice", entity_id=invoice_id,
                       school_id=subscription["school_id"], reason=body.reason, new=result, key=key)
                return 201, result
            result = IdempotentExecutor(PostgresIdempotencyRepository(conn)).execute(
                scope_key="platform", idempotency_key=key, operation="SAAS_INVOICE_ISSUE",
                payload={"subscription_id": str(subscription_id), **body.model_dump(mode="json")}, school_id=None,
                actor_user_id=str(actor.user_id), action=action)
        response.status_code = result.status_code
        response.headers["Idempotent-Replayed"] = "true" if result.replayed else "false"
        return result.body
    except (IdempotencyConflict, IdempotencyInProgress, IntegrityError) as exc:
        raise HTTPException(409, "Cette facture existe déjà ou la demande est en cours") from exc


@router.post("/invoices/{invoice_id}/payments/manual", status_code=201)
def record_manual_payment(invoice_id: UUID, body: ManualPaymentCreate, response: Response,
                          idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                          actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    _need(actor, "platform.billing.payments.reconcile")
    require_recent_mfa(services, actor, "platform.billing.payments.reconcile")
    key = _key(idempotency_key)
    payment_id = uuid4()
    try:
        with services.platform_db.platform_transaction() as conn:
            def action():
                invoice = conn.execute(text("SELECT * FROM saas_invoices WHERE id=:id FOR UPDATE"), {"id": invoice_id}).mappings().first()
                if not invoice or invoice["status"] in {"VOID", "REFUNDED"}:
                    raise HTTPException(404, "Facture payable introuvable")
                if body.currency != invoice["currency"]:
                    raise HTTPException(409, "La devise du paiement doit être celle de la facture")
                remaining = Decimal(invoice["total"]) - Decimal(invoice["paid_total"])
                if remaining <= 0:
                    raise HTTPException(409, "Cette facture est déjà entièrement payée")
                if body.amount > remaining:
                    raise HTTPException(409, f"Le paiement dépasse le solde restant de {remaining} {invoice['currency']}")
                reference = f"PAY-{date.today():%Y%m%d}-{str(payment_id)[:8].upper()}"
                row = conn.execute(text("""INSERT INTO saas_payments(id,payment_reference,invoice_id,school_id,provider,
                    provider_reference,channel,status,currency,amount,confirmed_at)
                    VALUES(:id,:reference,:invoice,:school,:provider,:provider_reference,'MANUAL','SUCCEEDED',:currency,:amount,now()) RETURNING *"""),
                    {"id": payment_id, "reference": reference, "invoice": invoice_id, "school": invoice["school_id"],
                     "provider": body.provider.strip().upper(), "provider_reference": body.provider_reference.strip(),
                     "currency": body.currency, "amount": body.amount}).mappings().one()
                paid = Decimal(invoice["paid_total"]) + body.amount
                invoice_state = "PAID" if paid == Decimal(invoice["total"]) else "PARTIALLY_PAID"
                conn.execute(text("""UPDATE saas_invoices SET paid_total=:paid,status=:status,version=version+1,updated_at=now()
                    WHERE id=:id"""), {"paid": paid, "status": invoice_state, "id": invoice_id})
                subscription_version = None
                if invoice_state == "PAID" and invoice["subscription_id"]:
                    subscription = conn.execute(text("SELECT * FROM saas_subscriptions WHERE id=:id FOR UPDATE"),
                                                {"id": invoice["subscription_id"]}).mappings().first()
                    if subscription and subscription["status"] != "CANCELLED":
                        new_start = max(subscription["current_period_start"], invoice["period_start"])
                        new_end = max(subscription["current_period_end"], invoice["period_end"])
                        updated = conn.execute(text("""UPDATE saas_subscriptions SET status='ACTIVE',current_period_start=:start,
                            current_period_end=:end,next_billing_on=:end,version=version+1,updated_at=now()
                            WHERE id=:id RETURNING version"""), {"start": new_start, "end": new_end, "id": subscription["id"]}).scalar_one()
                        subscription_version = int(updated)
                        entitlement_end = new_end + timedelta(days=int(subscription["grace_days"]))
                        conn.execute(text("""UPDATE saas_entitlements SET status='ACTIVE',ends_at=:ends,version=version+1,
                            updated_at=now(),reason='Paiement intégral confirmé' WHERE subscription_id=:id AND status IN ('ACTIVE','SUSPENDED')"""),
                            {"ends": entitlement_end, "id": subscription["id"]})
                        if subscription["status"] != "ACTIVE":
                            conn.execute(text("""INSERT INTO saas_subscription_events(subscription_id,school_id,actor_user_id,
                                from_status,to_status,reason,correlation_id,idempotency_key) VALUES(:id,:school,:actor,:old,'ACTIVE',
                                :reason,:correlation,:key)"""), {"id": subscription["id"], "school": subscription["school_id"],
                                "actor": actor.user_id, "old": subscription["status"], "reason": body.reason.strip(),
                                "correlation": actor.correlation_id, "key": key})
                result = {**_json(row), "invoice_status": invoice_state, "invoice_paid_total": format(paid, "f"),
                          "subscription_version": subscription_version}
                _audit(conn, actor, action="SAAS_PAYMENT_RECONCILED", entity_type="SaaSPayment", entity_id=payment_id,
                       school_id=invoice["school_id"], reason=body.reason, new=result, key=key)
                return 201, result
            result = IdempotentExecutor(PostgresIdempotencyRepository(conn)).execute(
                scope_key="platform", idempotency_key=key, operation="SAAS_MANUAL_PAYMENT",
                payload={"invoice_id": str(invoice_id), **body.model_dump(mode="json")}, school_id=None,
                actor_user_id=str(actor.user_id), action=action)
        response.status_code = result.status_code
        response.headers["Idempotent-Replayed"] = "true" if result.replayed else "false"
        return result.body
    except (IdempotencyConflict, IdempotencyInProgress, IntegrityError) as exc:
        raise HTTPException(409, "Paiement déjà enregistré ou référence déjà utilisée") from exc
