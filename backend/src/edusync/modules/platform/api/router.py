from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from edusync.adapters.postgres_idempotency import PostgresIdempotencyRepository
from edusync.adapters.postgres_repositories import (
    PostgresAuditRepository,
    PostgresMembershipRepository,
    PostgresOutboxRepository,
    PostgresSchoolRepository,
    PostgresUserRepository,
)
from edusync.bootstrap.dependencies import get_services, require_platform_actor, require_recent_mfa
from edusync.bootstrap.services import AppServices
from edusync.modules.platform.application.use_cases import (
    BootstrapSchoolAdmin,
    BootstrapSchoolAdminCommand,
    ChangeSchoolStatus,
    CreateSchool,
    CreateSchoolCommand,
)
from edusync.shared.application.context import ActorContext
from edusync.shared.application.idempotency import IdempotentExecutor
from edusync.shared.domain.concurrency import (
    IdempotencyConflict,
    IdempotencyInProgress,
    OptimisticConcurrencyError,
)

router = APIRouter(tags=["Atelier Pro"])


class SchoolCreate(BaseModel):
    # N1 2026-10: identity + contacts + address, validated. No external logo URL: the logo is uploaded by the
    # school (validated PNG/JPEG on private object storage), never hot-linked from another site.
    name: str = Field(min_length=2, max_length=160)
    code: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{1,31}$")
    email: str | None = Field(default=None, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str | None = Field(default=None, max_length=24, pattern=r"^\+?[0-9 ().-]{6,24}$")
    address: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=120)
    province: str | None = Field(default=None, max_length=120)


class SuspendInput(BaseModel):
    reason: str = Field(min_length=3, max_length=500)




class SystemNotificationInput(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    body: str = Field(min_length=2, max_length=2000)
    severity: str = Field(default="INFO", pattern="^(INFO|WARNING|CRITICAL)$")
    target_scope: str = Field(pattern="^(ALL_ACTIVE_SCHOOLS|SCHOOL)$")
    target_school_id: UUID | None = None

class AdminBootstrap(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    full_name: str = Field(min_length=2, max_length=180)
    password: str = Field(min_length=10, max_length=512)


def _school_json(s):
    return {
        "id": str(s.id), "name": s.name, "code": s.code, "status": s.status.value,
        "logo_url": s.logo_url, "email": s.email, "phone": s.phone,
        "address": s.address, "city": s.city, "province": s.province,
        "created_at": s.created_at.isoformat(), "updated_at": s.updated_at.isoformat(),
        "version": s.version,
    }


def _mutation_error(exc: Exception):
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, (ValueError, OptimisticConcurrencyError, IdempotencyConflict)):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, IntegrityError):
        raise HTTPException(status_code=409, detail="Conflit d'unicité ou de référence; rechargez les données") from exc
    if isinstance(exc, IdempotencyInProgress):
        raise HTTPException(status_code=409, detail=str(exc), headers={"Retry-After": "1"}) from exc
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    raise exc


def _key(value: str | None) -> str:
    key = (value or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="En-tête Idempotency-Key obligatoire pour cette mutation")
    if len(key) > 180:
        raise HTTPException(status_code=400, detail="Idempotency-Key trop longue")
    return key


@router.get("/schools")
def list_schools(
    actor: ActorContext = Depends(require_platform_actor),
    services: AppServices = Depends(get_services),
):
    actor.require("platform.schools.read")
    with services.platform_db.platform_transaction() as conn:
        return [_school_json(s) for s in PostgresSchoolRepository(conn).list()]


@router.post("/schools", status_code=201)
def create_school(
    body: SchoolCreate,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    actor: ActorContext = Depends(require_platform_actor),
    services: AppServices = Depends(get_services),
):
    key = _key(idempotency_key)
    request_actor = replace(actor, correlation_id=uuid4(), idempotency_key=key)
    try:
        with services.platform_db.platform_transaction() as conn:
            schools = PostgresSchoolRepository(conn)
            audit = PostgresAuditRepository(conn)
            outbox = PostgresOutboxRepository(conn)
            idem = IdempotentExecutor(PostgresIdempotencyRepository(conn))

            def action():
                school = CreateSchool(schools, audit, outbox).execute(
                    request_actor, CreateSchoolCommand(**body.model_dump())
                )
                return 201, _school_json(school)

            result = idem.execute(
                scope_key="platform", idempotency_key=key, operation="PLATFORM_CREATE_SCHOOL",
                payload=body.model_dump(mode="json"), school_id=None,
                actor_user_id=str(actor.user_id), action=action,
            )
        response.status_code = result.status_code
        response.headers["Idempotent-Replayed"] = "true" if result.replayed else "false"
        return result.body
    except Exception as exc:
        _mutation_error(exc)


@router.post("/schools/{school_id}/suspend")
def suspend_school(
    school_id: UUID,
    body: SuspendInput,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    actor: ActorContext = Depends(require_platform_actor),
    services: AppServices = Depends(get_services),
):
    key = _key(idempotency_key)
    require_recent_mfa(services, actor, "platform.schools.suspend")  # step-up: code confirmed in the last minutes
    request_actor = replace(actor, correlation_id=uuid4(), idempotency_key=key)
    payload = {"school_id": str(school_id), **body.model_dump(mode="json")}
    try:
        with services.platform_db.platform_transaction() as conn:
            schools = PostgresSchoolRepository(conn)
            audit = PostgresAuditRepository(conn)
            outbox = PostgresOutboxRepository(conn)
            idem = IdempotentExecutor(PostgresIdempotencyRepository(conn))

            def action():
                school = ChangeSchoolStatus(schools, audit, outbox).suspend(request_actor, school_id, body.reason)
                # Real effect: every open session of this school ends now (API calls already refuse a suspended school).
                from sqlalchemy import text as _text
                conn.execute(_text("""UPDATE user_device_sessions SET revoked_at=coalesce(revoked_at,now()),
                    revoked_reason=coalesce(revoked_reason,'SCHOOL_SUSPENDED') WHERE school_id=:s AND revoked_at IS NULL"""), {"s": str(school_id)})
                return 200, _school_json(school)

            result = idem.execute(
                scope_key="platform", idempotency_key=key, operation="PLATFORM_SUSPEND_SCHOOL",
                payload=payload, school_id=None, actor_user_id=str(actor.user_id), action=action,
            )
        response.status_code = result.status_code
        response.headers["Idempotent-Replayed"] = "true" if result.replayed else "false"
        return result.body
    except Exception as exc:
        _mutation_error(exc)


@router.post("/schools/{school_id}/reactivate")
def reactivate_school(
    school_id: UUID,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    actor: ActorContext = Depends(require_platform_actor),
    services: AppServices = Depends(get_services),
):
    key = _key(idempotency_key)
    request_actor = replace(actor, correlation_id=uuid4(), idempotency_key=key)
    payload = {"school_id": str(school_id)}
    try:
        with services.platform_db.platform_transaction() as conn:
            schools = PostgresSchoolRepository(conn)
            audit = PostgresAuditRepository(conn)
            outbox = PostgresOutboxRepository(conn)
            idem = IdempotentExecutor(PostgresIdempotencyRepository(conn))

            def action():
                school = ChangeSchoolStatus(schools, audit, outbox).reactivate(request_actor, school_id)
                return 200, _school_json(school)

            result = idem.execute(
                scope_key="platform", idempotency_key=key, operation="PLATFORM_REACTIVATE_SCHOOL",
                payload=payload, school_id=None, actor_user_id=str(actor.user_id), action=action,
            )
        response.status_code = result.status_code
        response.headers["Idempotent-Replayed"] = "true" if result.replayed else "false"
        return result.body
    except Exception as exc:
        _mutation_error(exc)


@router.post("/schools/{school_id}/bootstrap-admin", status_code=201)
def bootstrap_admin(
    school_id: UUID,
    body: AdminBootstrap,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    actor: ActorContext = Depends(require_platform_actor),
    services: AppServices = Depends(get_services),
):
    key = _key(idempotency_key)
    require_recent_mfa(services, actor, "platform.school_admin.bootstrap")  # step-up: code confirmed in the last minutes
    request_actor = replace(actor, correlation_id=uuid4(), idempotency_key=key)
    # Never include raw password in the idempotency hash. The logical command identity uses
    # school/email/name; password is consumed only if a new user is actually created.
    payload = {"school_id": str(school_id), "email": body.email.strip().lower(), "full_name": body.full_name.strip()}
    try:
        with services.platform_db.platform_transaction() as conn:
            schools = PostgresSchoolRepository(conn)
            users = PostgresUserRepository(conn)
            memberships = PostgresMembershipRepository(conn)
            audit = PostgresAuditRepository(conn)
            outbox = PostgresOutboxRepository(conn)
            idem = IdempotentExecutor(PostgresIdempotencyRepository(conn))

            def action():
                user, membership = BootstrapSchoolAdmin(
                    schools, users, memberships, audit, outbox
                ).execute(request_actor, BootstrapSchoolAdminCommand(school_id=school_id, **body.model_dump()))
                return 201, {
                    "user_id": str(user.id), "membership_id": str(membership.id),
                    "school_id": str(school_id), "role": "ADMIN_SYSTEME_ECOLE",
                }

            result = idem.execute(
                scope_key="platform", idempotency_key=key, operation="PLATFORM_BOOTSTRAP_SCHOOL_ADMIN",
                payload=payload, school_id=None, actor_user_id=str(actor.user_id), action=action,
            )
        response.status_code = result.status_code
        response.headers["Idempotent-Replayed"] = "true" if result.replayed else "false"
        return result.body
    except Exception as exc:
        _mutation_error(exc)


@router.get("/audit-count")
def audit_count(
    actor: ActorContext = Depends(require_platform_actor),
    services: AppServices = Depends(get_services),
):
    actor.require("platform.audit.read")
    from sqlalchemy import text
    with services.platform_db.platform_transaction() as conn:
        audit = int(conn.execute(text("SELECT count(*) FROM audit_events")).scalar_one())
        outbox = int(conn.execute(text("SELECT count(*) FROM outbox_events WHERE published_at IS NULL")).scalar_one())
        return {"count": audit, "outbox_pending": outbox}

@router.get('/dashboard')
def platform_dashboard(actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require('platform.schools.read')
    from sqlalchemy import text
    with services.platform_db.platform_transaction() as c:
        schools=c.execute(text("SELECT count(*) total,count(*) FILTER(WHERE status='ACTIVE') active,count(*) FILTER(WHERE status='SUSPENDED') suspended FROM schools")).mappings().one()
        members=int(c.execute(text("SELECT count(*) FROM school_memberships WHERE active=true")).scalar_one())
        admins=int(c.execute(text("SELECT count(DISTINCT a.membership_id) FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id WHERE a.active=true AND r.code='ADMIN_SYSTEME_ECOLE'")).scalar_one())
        outbox=int(c.execute(text("SELECT count(*) FROM outbox_events WHERE published_at IS NULL")).scalar_one())
        recent=[dict(r._mapping) for r in c.execute(text("SELECT a.id,a.occurred_at,a.action,a.entity_type,a.result,s.code school_code,u.full_name actor FROM audit_events a LEFT JOIN schools s ON s.id=a.school_id LEFT JOIN users u ON u.id=a.actor_user_id ORDER BY a.occurred_at DESC,a.id DESC LIMIT 8"))]
    return {'schools':dict(schools),'active_memberships':members,'schools_with_admin':admins,'outbox_pending':outbox,'recent_activity':recent}

@router.get('/schools-page')
def platform_schools_page(q: str|None=None,status: str|None=None,limit:int=50,offset:int=0,actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require('platform.schools.read'); limit=max(1,min(limit,100)); offset=max(0,offset)
    from sqlalchemy import text
    with services.platform_db.platform_transaction() as c:
        rows=c.execute(text("""SELECT s.id,s.code,s.name,s.status,s.email,s.phone,s.created_at,s.updated_at,s.version,
          count(DISTINCT m.id) FILTER(WHERE m.active=true) active_memberships,
          count(DISTINCT a.membership_id) FILTER(WHERE a.active=true AND r.code='ADMIN_SYSTEME_ECOLE') admin_count
          FROM schools s LEFT JOIN school_memberships m ON m.school_id=s.id LEFT JOIN rbac_assignments a ON a.membership_id=m.id LEFT JOIN rbac_roles r ON r.id=a.role_id
          WHERE (CAST(:q AS text) IS NULL OR s.name ILIKE '%'||:q||'%' OR s.code ILIKE '%'||:q||'%') AND (CAST(:status AS text) IS NULL OR s.status=:status)
          GROUP BY s.id ORDER BY lower(s.name),s.code LIMIT :lim OFFSET :off"""),{'q':q.strip() if q else None,'status':status,'lim':limit+1,'off':offset}).mappings().all()
    more=len(rows)>limit; rows=rows[:limit]
    return {'items':[dict(x) for x in rows],'limit':limit,'offset':offset,'has_more':more}

@router.get('/access')
def platform_access(q:str|None=None,limit:int=50,offset:int=0,actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require('platform.schools.read'); limit=max(1,min(limit,100)); offset=max(0,offset)
    from sqlalchemy import text
    with services.platform_db.platform_transaction() as c:
        rows=c.execute(text("""SELECT u.id,u.full_name,u.email,u.active,u.is_platform_admin,u.created_at,
          count(DISTINCT m.id) FILTER(WHERE m.active=true) school_memberships,
          bool_or(pr.code='COLLABORATEUR_PLATEFORME' AND pa.active=true) collaborator_platform,
          string_agg(DISTINCT s.code,', ' ORDER BY s.code) FILTER(WHERE m.active=true) schools
          FROM users u LEFT JOIN school_memberships m ON m.user_id=u.id LEFT JOIN schools s ON s.id=m.school_id
          LEFT JOIN rbac_assignments pa ON pa.user_id=u.id AND pa.school_id IS NULL LEFT JOIN rbac_roles pr ON pr.id=pa.role_id
          WHERE (CAST(:q AS text) IS NULL OR u.full_name ILIKE '%'||:q||'%' OR u.email::text ILIKE '%'||:q||'%')
          GROUP BY u.id ORDER BY lower(u.full_name),u.id LIMIT :lim OFFSET :off"""),{'q':q.strip() if q else None,'lim':limit+1,'off':offset}).mappings().all()
    more=len(rows)>limit
    return {'items':[dict(x) for x in rows[:limit]],'limit':limit,'offset':offset,'has_more':more,'can_manage_collaborators':'platform.collaborators.manage' in actor.permissions}

@router.get('/audit')
def platform_audit(limit:int=50,cursor_at:str|None=None,cursor_id:UUID|None=None,actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require('platform.audit.read'); limit=max(1,min(limit,100))
    if (cursor_at is None)!=(cursor_id is None): raise HTTPException(422,'Curseur incomplet')
    from sqlalchemy import text
    from datetime import datetime
    ca=None
    if cursor_at:
        try: ca=datetime.fromisoformat(cursor_at.replace('Z','+00:00'))
        except ValueError as e: raise HTTPException(422,'Curseur invalide') from e
    with services.platform_db.platform_transaction() as c:
        rows=c.execute(text("""SELECT a.id,a.occurred_at,a.school_id,s.code school_code,a.actor_user_id,u.full_name actor,a.action,a.entity_type,a.entity_id,a.source,a.result,a.reason
        FROM audit_events a LEFT JOIN schools s ON s.id=a.school_id LEFT JOIN users u ON u.id=a.actor_user_id
        WHERE (CAST(:ca AS timestamptz) IS NULL OR (a.occurred_at,a.id)<(:ca,:cid)) ORDER BY a.occurred_at DESC,a.id DESC LIMIT :lim"""),{'ca':ca,'cid':cursor_id,'lim':limit+1}).mappings().all()
    more=len(rows)>limit; items=[dict(x) for x in rows[:limit]]; last=items[-1] if items else None
    return {'items':items,'has_more':more,'next_cursor':({'at':last['occurred_at'].isoformat(),'id':str(last['id'])} if more and last else None)}

@router.get('/diagnostics')
def platform_diagnostics(actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require('platform.health.read')
    from sqlalchemy import text
    with services.platform_db.platform_transaction() as c:
        db=int(c.execute(text('SELECT 1')).scalar_one()); pending=int(c.execute(text('SELECT count(*) FROM outbox_events WHERE published_at IS NULL')).scalar_one()); conflicts=int(c.execute(text("SELECT count(*) FROM sync_conflicts WHERE status IN ('CONFLICT','REJECTED')")).scalar_one())
        schools=int(c.execute(text("SELECT count(*) FROM schools WHERE status='ACTIVE'")).scalar_one())
        sessions=int(c.execute(text("SELECT count(*) FROM user_device_sessions WHERE revoked_at IS NULL")).scalar_one())
        dead=int(c.execute(text("SELECT count(*) FROM communication_deliveries WHERE status='FAILED' AND attempts>=5")).scalar_one())
    return {'database':'READY' if db==1 else 'DEGRADED','outbox_pending':pending,'sync_conflicts':conflicts,'active_schools':schools,'active_device_sessions':sessions,'dead_letter_deliveries':dead,'global_lock':False}


@router.get('/system-notifications')
def platform_system_notifications(limit:int=50, offset:int=0, actor:ActorContext=Depends(require_platform_actor), services:AppServices=Depends(get_services)):
    actor.require('platform.notifications.system.send'); limit=max(1,min(limit,100)); offset=max(0,offset)
    from sqlalchemy import text
    with services.platform_db.platform_transaction() as c:
        rows=c.execute(text("""SELECT n.id,n.title,n.body,n.severity,n.target_scope,n.target_school_id,s.code target_school_code,
          n.recipient_count,n.created_at,u.full_name created_by
          FROM platform_system_notifications n LEFT JOIN schools s ON s.id=n.target_school_id LEFT JOIN users u ON u.id=n.created_by
          ORDER BY n.created_at DESC,n.id DESC LIMIT :lim OFFSET :off"""),{'lim':limit+1,'off':offset}).mappings().all()
    more=len(rows)>limit
    return {'items':[dict(x) for x in rows[:limit]],'limit':limit,'offset':offset,'has_more':more}

@router.post('/system-notifications',status_code=201)
def send_platform_system_notification(body:SystemNotificationInput,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_platform_actor),services:AppServices=Depends(get_services)):
    actor.require('platform.notifications.system.send'); key=_key(idempotency_key)
    if body.target_scope=='SCHOOL' and body.target_school_id is None: raise HTTPException(422,'École cible obligatoire')
    if body.target_scope=='ALL_ACTIVE_SCHOOLS' and body.target_school_id is not None: raise HTTPException(422,'Une diffusion globale ne doit pas contenir une école cible')
    if body.target_scope=='ALL_ACTIVE_SCHOOLS': require_recent_mfa(services,actor)  # step-up: message to every school
    request_actor=replace(actor,correlation_id=uuid4(),idempotency_key=key)
    payload=body.model_dump(mode='json')
    try:
      from sqlalchemy import text
      from edusync.modules.audit.domain.audit import AuditRecord
      with services.platform_db.platform_transaction() as c:
        idem=IdempotentExecutor(PostgresIdempotencyRepository(c)); audit=PostgresAuditRepository(c)
        def action():
          campaign_id=uuid4()
          if body.target_scope=='SCHOOL':
            school=c.execute(text("SELECT id,status FROM schools WHERE id=:sid"),{'sid':body.target_school_id}).mappings().first()
            if school is None: raise LookupError('École introuvable')
            if school['status']!='ACTIVE': raise ValueError("La notification système ne peut cibler qu'une école active")
          recipients=c.execute(text("""SELECT DISTINCT m.school_id,m.user_id FROM school_memberships m JOIN schools s ON s.id=m.school_id JOIN users u ON u.id=m.user_id
             WHERE m.active=true AND u.active=true AND s.status='ACTIVE'
             AND (:scope='ALL_ACTIVE_SCHOOLS' OR m.school_id=:sid)"""),{'scope':body.target_scope,'sid':body.target_school_id}).mappings().all()
          c.execute(text("""INSERT INTO platform_system_notifications(id,title,body,severity,target_scope,target_school_id,created_by,recipient_count)
             VALUES(:id,:title,:body,:sev,:scope,:sid,:uid,:count)"""),{'id':campaign_id,'title':body.title.strip(),'body':body.body.strip(),'sev':body.severity,'scope':body.target_scope,'sid':body.target_school_id,'uid':actor.user_id,'count':len(recipients)})
          for r in recipients:
            c.execute(text("""INSERT INTO notifications(school_id,user_id,category,title,body) VALUES(:sid,:uid,:cat,:title,:body)"""),{'sid':r['school_id'],'uid':r['user_id'],'cat':f'SYSTEM_{body.severity}','title':body.title.strip(),'body':body.body.strip()})
          audit.append(AuditRecord(action='PLATFORM_SYSTEM_NOTIFICATION_SENT',entity_type='PlatformSystemNotification',entity_id=campaign_id,actor_user_id=actor.user_id,school_id=body.target_school_id,source=actor.source,new_data={'severity':body.severity,'target_scope':body.target_scope,'target_school_id':str(body.target_school_id) if body.target_school_id else None,'recipient_count':len(recipients),'title':body.title.strip()},correlation_id=request_actor.correlation_id,idempotency_key=key))
          return 201,{'id':str(campaign_id),'recipient_count':len(recipients),'target_scope':body.target_scope,'severity':body.severity}
        result=idem.execute(scope_key='platform',idempotency_key=key,operation='PLATFORM_SYSTEM_NOTIFICATION_SEND',payload=payload,school_id=None,actor_user_id=str(actor.user_id),action=action)
      response.status_code=result.status_code; response.headers['Idempotent-Replayed']='true' if result.replayed else 'false'; return result.body
    except Exception as exc: _mutation_error(exc)


class AccessMutationInput(BaseModel):
    reason: str = Field(min_length=5, max_length=500)

class RoleAssignmentInput(BaseModel):
    role_code: str = Field(min_length=2, max_length=96)
    reason: str = Field(min_length=5, max_length=500)

@router.get('/schools/{school_id}/detail')
def platform_school_detail(school_id:UUID, actor:ActorContext=Depends(require_platform_actor), services:AppServices=Depends(get_services)):
    actor.require('platform.schools.read')
    from sqlalchemy import text
    with services.platform_db.platform_transaction() as c:
        school=c.execute(text("SELECT id,code,name,status,email,phone,created_at,updated_at,version FROM schools WHERE id=:sid"),{'sid':school_id}).mappings().first()
        if not school: raise HTTPException(404,'École introuvable')
        counts=c.execute(text("""SELECT count(DISTINCT m.id) FILTER(WHERE m.active) memberships,
          count(DISTINCT a.membership_id) FILTER(WHERE a.active AND r.code='ADMIN_SYSTEME_ECOLE') admins
          FROM school_memberships m LEFT JOIN rbac_assignments a ON a.membership_id=m.id LEFT JOIN rbac_roles r ON r.id=a.role_id WHERE m.school_id=:sid"""),{'sid':school_id}).mappings().one()
        users=c.execute(text("""SELECT m.id membership_id,u.id user_id,u.full_name,u.email,u.active user_active,m.active membership_active,
          coalesce(string_agg(DISTINCT r.code,', ' ORDER BY r.code) FILTER(WHERE a.active),'') roles,
          coalesce(jsonb_agg(DISTINCT jsonb_build_object('assignment_id',a.id,'role_code',r.code,'role_label',r.label)) FILTER(WHERE a.active),'[]'::jsonb) role_assignments
          FROM school_memberships m JOIN users u ON u.id=m.user_id LEFT JOIN rbac_assignments a ON a.membership_id=m.id LEFT JOIN rbac_roles r ON r.id=a.role_id
          WHERE m.school_id=:sid GROUP BY m.id,u.id ORDER BY lower(u.full_name)"""),{'sid':school_id}).mappings().all()
    # Platform permission and school existence were checked above. Read only
    # readiness counts through the school-scoped pool; keep settings FORCE RLS.
    with services.tenant_db.tenant_transaction(school_id=school_id,user_id=actor.user_id) as c:
        years=int(c.execute(text("SELECT count(*) FROM academic_years WHERE school_id=:sid"),{'sid':school_id}).scalar_one())
        classes=int(c.execute(text("SELECT count(*) FROM school_classes WHERE school_id=:sid AND enabled=true"),{'sid':school_id}).scalar_one())
        fee_types=int(c.execute(text("SELECT count(*) FROM fee_types WHERE school_id=:sid AND enabled=true"),{'sid':school_id}).scalar_one())
    readiness={'school_identity':True,'initial_admin':counts['admins']>0,'academic_year':years>0,'classes':classes>0,'fee_catalog':fee_types>0}
    return {'school':dict(school),'readiness':readiness,'ready_count':sum(readiness.values()),'total_gates':len(readiness),'memberships':int(counts['memberships'] or 0),'users':[dict(x) for x in users]}

@router.get('/rbac/roles')
def platform_rbac_roles(actor:ActorContext=Depends(require_platform_actor), services:AppServices=Depends(get_services)):
    actor.require('platform.schools.read')
    from sqlalchemy import text
    with services.platform_db.platform_transaction() as c:
        rows=c.execute(text("""SELECT r.id,r.code,r.label,r.description,r.status,count(rc.capability_code) capability_count
          FROM rbac_roles r LEFT JOIN rbac_role_capabilities rc ON rc.role_id=r.id
          WHERE r.level='SCHOOL' AND r.kind='SCHOOL_STANDARD' AND r.status='ACTIVE'
          GROUP BY r.id ORDER BY r.label""")).mappings().all()
    return [dict(x) for x in rows]

@router.post('/memberships/{membership_id}/deactivate')
def platform_deactivate_membership(membership_id:UUID,body:AccessMutationInput,actor:ActorContext=Depends(require_platform_actor),services:AppServices=Depends(get_services)):
    actor.require('platform.access.manage')
    from sqlalchemy import text
    from edusync.modules.audit.domain.audit import AuditRecord
    with services.platform_db.platform_transaction() as c:
        row=c.execute(text("SELECT id,school_id,user_id,active FROM school_memberships WHERE id=:id FOR UPDATE"),{'id':membership_id}).mappings().first()
        if not row: raise HTTPException(404,'Appartenance introuvable')
        if row['active']:
            c.execute(text("UPDATE school_memberships SET active=false,version=version+1 WHERE id=:id"),{'id':membership_id})
            c.execute(text("UPDATE rbac_assignments SET active=false,version=version+1,updated_at=now() WHERE membership_id=:id AND active=true"),{'id':membership_id})
            c.execute(text("UPDATE user_device_sessions SET revoked_at=coalesce(revoked_at,now()) WHERE user_id=:uid AND school_id=:sid AND revoked_at IS NULL"),{'uid':row['user_id'],'sid':row['school_id']})
            PostgresAuditRepository(c).append(AuditRecord(action='PLATFORM_MEMBERSHIP_DEACTIVATED',entity_type='SchoolMembership',entity_id=membership_id,actor_user_id=actor.user_id,school_id=row['school_id'],source=actor.source,reason=body.reason,new_data={'user_id':str(row['user_id'])}))
    return {'membership_id':str(membership_id),'active':False}

@router.post('/memberships/{membership_id}/activate')
def platform_activate_membership(membership_id:UUID,body:AccessMutationInput,actor:ActorContext=Depends(require_platform_actor),services:AppServices=Depends(get_services)):
    actor.require('platform.access.manage')
    from sqlalchemy import text
    from edusync.modules.audit.domain.audit import AuditRecord
    with services.platform_db.platform_transaction() as c:
        row=c.execute(text("SELECT m.id,m.school_id,m.user_id,m.active,s.status school_status,u.active user_active FROM school_memberships m JOIN schools s ON s.id=m.school_id JOIN users u ON u.id=m.user_id WHERE m.id=:id FOR UPDATE"),{'id':membership_id}).mappings().first()
        if not row: raise HTTPException(404,'Appartenance introuvable')
        if row['school_status']!='ACTIVE' or not row['user_active']: raise HTTPException(409,"L’école et le compte utilisateur doivent être actifs")
        if not row['active']:
            c.execute(text("UPDATE school_memberships SET active=true,version=version+1 WHERE id=:id"),{'id':membership_id})
            PostgresAuditRepository(c).append(AuditRecord(action='PLATFORM_MEMBERSHIP_ACTIVATED',entity_type='SchoolMembership',entity_id=membership_id,actor_user_id=actor.user_id,school_id=row['school_id'],source=actor.source,reason=body.reason,new_data={'user_id':str(row['user_id'])}))
    return {'membership_id':str(membership_id),'active':True}

@router.post('/memberships/{membership_id}/roles')
def platform_assign_standard_role(membership_id:UUID,body:RoleAssignmentInput,actor:ActorContext=Depends(require_platform_actor),services:AppServices=Depends(get_services)):
    actor.require('platform.access.manage')
    from sqlalchemy import text
    from edusync.modules.audit.domain.audit import AuditRecord
    with services.platform_db.platform_transaction() as c:
        m=c.execute(text("SELECT id,school_id,user_id,active FROM school_memberships WHERE id=:id FOR UPDATE"),{'id':membership_id}).mappings().first()
        if not m or not m['active']: raise HTTPException(409,'Appartenance active obligatoire')
        role=c.execute(text("SELECT id,code FROM rbac_roles WHERE code=:code AND level='SCHOOL' AND kind='SCHOOL_STANDARD' AND status='ACTIVE'"),{'code':body.role_code}).mappings().first()
        if not role: raise HTTPException(404,'Rôle standard actif introuvable')
        existing=c.execute(text("SELECT id,active FROM rbac_assignments WHERE membership_id=:mid AND role_id=:rid ORDER BY created_at DESC LIMIT 1 FOR UPDATE"),{'mid':membership_id,'rid':role['id']}).mappings().first()
        if existing:
            assignment_id=existing['id']
            c.execute(text("UPDATE rbac_assignments SET active=true,reason=:reason,valid_until=NULL,version=version+1,updated_at=now() WHERE id=:id"),{'reason':body.reason,'id':existing['id']})
        else:
            assignment_id=c.execute(text("INSERT INTO rbac_assignments(user_id,role_id,school_id,membership_id,active,granted_by_user_id,reason) VALUES(:uid,:rid,:sid,:mid,true,:by,:reason) RETURNING id"),{'uid':m['user_id'],'rid':role['id'],'sid':m['school_id'],'mid':membership_id,'by':actor.user_id,'reason':body.reason}).scalar_one()
        # This endpoint assigns a school-wide standard role. Preserve any existing
        # explicit narrower scopes; repair only assignments with no scope at all.
        c.execute(text("""INSERT INTO rbac_assignment_scopes(assignment_id,scope_type,scope_value)
          SELECT :id,'SCHOOL',NULL WHERE NOT EXISTS
          (SELECT 1 FROM rbac_assignment_scopes WHERE assignment_id=:id)"""),{'id':assignment_id})
        PostgresAuditRepository(c).append(AuditRecord(action='PLATFORM_STANDARD_ROLE_ASSIGNED',entity_type='SchoolMembership',entity_id=membership_id,actor_user_id=actor.user_id,school_id=m['school_id'],source=actor.source,reason=body.reason,new_data={'role_code':body.role_code,'user_id':str(m['user_id'])}))
    return {'membership_id':str(membership_id),'role_code':body.role_code,'active':True}


@router.post('/memberships/{membership_id}/roles/{role_code}/revoke')
def platform_revoke_standard_role(membership_id:UUID, role_code:str, body:AccessMutationInput, actor:ActorContext=Depends(require_platform_actor), services:AppServices=Depends(get_services)):
    actor.require('platform.access.manage')
    from sqlalchemy import text
    from edusync.modules.audit.domain.audit import AuditRecord
    with services.platform_db.platform_transaction() as c:
        m=c.execute(text("SELECT id,school_id,user_id,active FROM school_memberships WHERE id=:id FOR UPDATE"),{'id':membership_id}).mappings().first()
        if not m: raise HTTPException(404,'Appartenance introuvable')
        a=c.execute(text("""SELECT a.id,a.active FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id
          WHERE a.membership_id=:mid AND r.code=:code AND r.level='SCHOOL' AND r.kind='SCHOOL_STANDARD' ORDER BY a.created_at DESC LIMIT 1 FOR UPDATE"""),{'mid':membership_id,'code':role_code}).mappings().first()
        if not a or not a['active']: raise HTTPException(404,'Attribution de rôle active introuvable')
        c.execute(text("UPDATE rbac_assignments SET active=false,version=version+1,updated_at=now(),reason=:reason WHERE id=:id"),{'id':a['id'],'reason':body.reason})
        PostgresAuditRepository(c).append(AuditRecord(action='PLATFORM_STANDARD_ROLE_REVOKED',entity_type='SchoolMembership',entity_id=membership_id,actor_user_id=actor.user_id,school_id=m['school_id'],source=actor.source,reason=body.reason,new_data={'role_code':role_code,'user_id':str(m['user_id'])}))
    return {'membership_id':str(membership_id),'role_code':role_code,'active':False}

class PlatformCollaboratorMutation(BaseModel):
    reason: str = Field(min_length=5, max_length=500)

@router.post('/collaborators/{user_id}/grant')
def platform_grant_collaborator(user_id:UUID, body:PlatformCollaboratorMutation, actor:ActorContext=Depends(require_platform_actor), services:AppServices=Depends(get_services)):
    from edusync.modules.audit.domain.audit import AuditRecord
    actor.require('platform.collaborators.manage'); require_recent_mfa(services, actor)
    from sqlalchemy import text
    with services.platform_db.platform_transaction() as c:
        user=c.execute(text("SELECT id,active FROM users WHERE id=:uid FOR UPDATE"),{'uid':user_id}).mappings().first()
        if not user or not user['active']: raise HTTPException(404,'Compte actif introuvable')
        role=c.execute(text("SELECT id FROM rbac_roles WHERE code='COLLABORATEUR_PLATEFORME' AND kind='PLATFORM_STANDARD' AND status='ACTIVE'")).scalar_one_or_none()
        if role is None: raise HTTPException(409,'Rôle Collaborateur plateforme indisponible')
        existing=c.execute(text("SELECT id,active FROM rbac_assignments WHERE user_id=:uid AND role_id=:rid AND school_id IS NULL ORDER BY created_at DESC LIMIT 1 FOR UPDATE"),{'uid':user_id,'rid':role}).mappings().first()
        if existing and existing['active']: return {'status':'already_granted'}
        if existing:
            aid=existing['id']; c.execute(text("UPDATE rbac_assignments SET active=true,valid_from=now(),valid_until=NULL,granted_by_user_id=:by,reason=:reason,version=version+1,updated_at=now() WHERE id=:id"),{'id':aid,'by':actor.user_id,'reason':body.reason})
        else:
            aid=c.execute(text("INSERT INTO rbac_assignments(user_id,role_id,granted_by_user_id,reason) VALUES(:uid,:rid,:by,:reason) RETURNING id"),{'uid':user_id,'rid':role,'by':actor.user_id,'reason':body.reason}).scalar_one()
            c.execute(text("INSERT INTO rbac_assignment_scopes(assignment_id,scope_type,scope_value) VALUES(:id,'PLATFORM',NULL)"),{'id':aid})
        c.execute(text("UPDATE users SET is_platform_admin=true,version=version+1 WHERE id=:uid"),{'uid':user_id})
        PostgresAuditRepository(c).append(AuditRecord(action='PLATFORM_COLLABORATOR_GRANTED',entity_type='User',entity_id=user_id,actor_user_id=actor.user_id,school_id=None,source=actor.source,reason=body.reason,new_data={'role_code':'COLLABORATEUR_PLATEFORME'}))
    return {'status':'granted','role_code':'COLLABORATEUR_PLATEFORME'}

@router.post('/collaborators/{user_id}/revoke')
def platform_revoke_collaborator(user_id:UUID, body:PlatformCollaboratorMutation, actor:ActorContext=Depends(require_platform_actor), services:AppServices=Depends(get_services)):
    from edusync.modules.audit.domain.audit import AuditRecord
    actor.require('platform.collaborators.manage')
    from sqlalchemy import text
    with services.platform_db.platform_transaction() as c:
        row=c.execute(text("SELECT a.id FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id WHERE a.user_id=:uid AND a.school_id IS NULL AND a.active=true AND r.code='COLLABORATEUR_PLATEFORME' FOR UPDATE"),{'uid':user_id}).mappings().first()
        if not row: raise HTTPException(404,'Collaboration active introuvable')
        c.execute(text("UPDATE rbac_assignments SET active=false,reason=:reason,version=version+1,updated_at=now() WHERE id=:id"),{'id':row['id'],'reason':body.reason})
        has_other=c.execute(text("SELECT 1 FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id WHERE a.user_id=:uid AND a.school_id IS NULL AND a.active=true AND r.level='PLATFORM' AND r.status='ACTIVE' LIMIT 1"),{'uid':user_id}).first()
        if not has_other: c.execute(text("UPDATE users SET is_platform_admin=false,version=version+1 WHERE id=:uid"),{'uid':user_id})
        c.execute(text("UPDATE user_device_sessions SET revoked_at=coalesce(revoked_at,now()),revoked_reason=coalesce(revoked_reason,'PLATFORM_ROLE_REVOKED') WHERE user_id=:uid AND school_id IS NULL AND revoked_at IS NULL"),{'uid':user_id})
        PostgresAuditRepository(c).append(AuditRecord(action='PLATFORM_COLLABORATOR_REVOKED',entity_type='User',entity_id=user_id,actor_user_id=actor.user_id,school_id=None,source=actor.source,reason=body.reason,new_data={'role_code':'COLLABORATEUR_PLATEFORME'}))
    return {'status':'revoked'}
