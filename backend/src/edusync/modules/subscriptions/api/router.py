from __future__ import annotations

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


@router.get("/catalog")
def catalog(actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    _need(actor, "platform.billing.read")
    with services.platform_db.platform_transaction() as conn:
        modules = conn.execute(text("SELECT code,label,description,status,dependencies,version FROM saas_modules ORDER BY status,code")).mappings()
        plans = conn.execute(text("""SELECT p.id,p.code,p.name,p.description,p.status,p.public_offer,p.version,
          count(v.id) AS version_count FROM saas_plans p LEFT JOIN saas_plan_versions v ON v.plan_id=p.id
          GROUP BY p.id ORDER BY lower(p.name),p.code""")).mappings()
        return {"modules": [_json(r) for r in modules], "plans": [_json(r) for r in plans]}


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
          SELECT :school,:subscription,module_code,'PLAN','ACTIVE',:ends,limits,:reason FROM saas_plan_modules WHERE plan_version_id=:plan"""),
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
