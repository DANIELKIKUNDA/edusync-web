from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from decimal import Decimal
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from io import BytesIO
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from edusync.adapters.postgres_idempotency import PostgresIdempotencyRepository
from edusync.adapters.postgres_personnel import PostgresPersonnelRepository
from edusync.adapters.postgres_repositories import PostgresAuditRepository, PostgresOutboxRepository, PostgresSchoolRepository
from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.modules.audit.domain.audit import AuditRecord
from edusync.modules.personnel.application.documents import build_staff_profile_pdf, build_staff_register_pdf, build_staff_register_xlsx
from edusync.modules.personnel.domain.models import AssignmentScope, StaffAssignment, StaffCategory, StaffFunction, StaffMember, StaffStatus
from edusync.modules.sync.domain.outbox import OutboxMessage
from edusync.shared.application.context import ActorContext
from edusync.shared.application.idempotency import IdempotentExecutor
from edusync.shared.domain.concurrency import IdempotencyConflict, IdempotencyInProgress, OptimisticConcurrencyError

router=APIRouter(tags=["Personnel"])


def _need(actor:ActorContext, capability:str)->None:
    try: actor.require(capability)
    except PermissionError as exc: raise HTTPException(status_code=403,detail=str(exc)) from exc

def _key(value:str|None)->str:
    key=(value or "").strip()
    if not key: raise HTTPException(status_code=400,detail="Idempotency-Key obligatoire")
    if len(key)>180: raise HTTPException(status_code=400,detail="Idempotency-Key trop longue")
    return key

def _expected(value:str|None)->int:
    raw=(value or "").strip().replace('W/','').strip('"')
    if not raw: raise HTTPException(status_code=428,detail="If-Match avec la version courante est obligatoire")
    try: n=int(raw)
    except ValueError as exc: raise HTTPException(status_code=400,detail="If-Match invalide") from exc
    if n<1: raise HTTPException(status_code=400,detail="Version invalide")
    return n

def _jsonable(v:Any)->Any:
    if isinstance(v,(UUID,date,datetime)): return str(v)
    if isinstance(v,dict): return {str(k):_jsonable(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)): return [_jsonable(x) for x in v]
    if hasattr(v,'value'): return str(v.value)
    if hasattr(v,'__dict__'): return _jsonable(vars(v))
    return v

def _error(exc:Exception):
    if isinstance(exc,LookupError): raise HTTPException(status_code=404,detail=str(exc)) from exc
    if isinstance(exc,(ValueError,OptimisticConcurrencyError,IdempotencyConflict,IntegrityError)):
        raise HTTPException(status_code=409,detail=str(exc)) from exc
    if isinstance(exc,IdempotencyInProgress): raise HTTPException(status_code=409,detail=str(exc),headers={"Retry-After":"1"}) from exc
    raise exc

def _audit_outbox(conn,actor:ActorContext,*,action:str,entity_type:str,entity_id:UUID,old:dict|None,new:dict|None,reason:str|None=None):
    PostgresAuditRepository(conn).append(AuditRecord(action=action,entity_type=entity_type,entity_id=entity_id,actor_user_id=actor.user_id,membership_id=actor.membership_id,school_id=actor.school_id,source=actor.source,old_data=old,new_data=new,reason=reason,correlation_id=actor.correlation_id,idempotency_key=actor.idempotency_key))
    PostgresOutboxRepository(conn).add(OutboxMessage(event_type=action,aggregate_type=entity_type,aggregate_id=entity_id,school_id=actor.school_id,payload=new or {},correlation_id=actor.correlation_id,deduplication_key=f"{actor.idempotency_key or actor.correlation_id}:{action}:{entity_id}"))

def _mutate(*,services:AppServices,actor:ActorContext,key:str,operation:str,payload:dict[str,Any],action):
    request_actor=replace(actor,correlation_id=uuid4(),idempotency_key=key)
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        idem=IdempotentExecutor(PostgresIdempotencyRepository(conn))
        return idem.execute(scope_key=str(actor.school_id),idempotency_key=key,operation=operation,payload=payload,school_id=str(actor.school_id),actor_user_id=str(actor.user_id),action=lambda:action(conn,request_actor))

def _scopes(actor:ActorContext,capability:str)->tuple[tuple[str,str|None],...]:
    scopes=actor.scopes_for(capability)
    if not scopes and capability in actor.permissions:
        # Fail closed on resource lists if a capability somehow exists without an assignment scope.
        return ()
    return scopes


class StaffCreate(BaseModel):
    employee_no:str=Field(min_length=1,max_length=48)
    last_name:str=Field(min_length=1,max_length=120)
    first_name:str|None=Field(default=None,max_length=120)
    middle_name:str|None=Field(default=None,max_length=120)
    gender:Literal['M','F','X']|None=None
    birth_date:date|None=None
    phone:str|None=Field(default=None,max_length=48)
    email:str|None=Field(default=None,max_length=200)
    address:str|None=None
    category:StaffCategory=StaffCategory.AUTRE
    qualification:str|None=Field(default=None,max_length=160)
    specialty:str|None=Field(default=None,max_length=160)
    hire_date:date|None=None
    photo_url:str|None=None
    notes:str|None=None

class StaffUpdate(StaffCreate): pass

class StaffStatusPatch(BaseModel):
    status:Literal['ACTIVE','SUSPENDED','INACTIVE']
    effective_date:date=Field(default_factory=date.today)
    reason:str=Field(min_length=3,max_length=500)

class ExitBody(BaseModel):
    effective_date:date=Field(default_factory=date.today)
    reason:str=Field(min_length=3,max_length=500)

class FunctionCreate(BaseModel):
    code:str=Field(min_length=1,max_length=64)
    label:str=Field(min_length=2,max_length=160)
    category:Literal['ENSEIGNEMENT','DIRECTION_PEDAGOGIQUE','ADMINISTRATION','FINANCE','INTENDANCE','SUPPORT','OUVRIER','AUTRE']='AUTRE'
    sort_order:int=Field(default=100,ge=0,le=9999)

class FunctionUpdate(BaseModel):
    label:str=Field(min_length=2,max_length=160)
    category:Literal['ENSEIGNEMENT','DIRECTION_PEDAGOGIQUE','ADMINISTRATION','FINANCE','INTENDANCE','SUPPORT','OUVRIER','AUTRE']='AUTRE'
    enabled:bool=True
    sort_order:int=Field(default=100,ge=0,le=9999)

class AssignmentCreate(BaseModel):
    staff_id:UUID
    function_id:UUID
    scope_type:AssignmentScope=AssignmentScope.SCHOOL
    scope_value:str|None=Field(default=None,max_length=96)
    section_id:UUID|None=None
    class_id:UUID|None=None
    is_primary:bool=False
    is_titular:bool=False
    titular_class_id:UUID|None=None
    start_date:date=Field(default_factory=date.today)

class AssignmentEnd(BaseModel):
    effective_date:date=Field(default_factory=date.today)
    reason:str=Field(min_length=3,max_length=500)

class AccessLinkBody(BaseModel): membership_id:UUID; reason:str|None=Field(default=None,max_length=500)
class UnlinkBody(BaseModel): reason:str=Field(min_length=3,max_length=500)
class StaffStudentLinkBody(BaseModel): student_id:UUID; relationship:str=Field(default='PARENT',min_length=2,max_length=32)
class StaffStudentFinanceModeBody(BaseModel):
    responsibility_mode:Literal['FAMILY','PAYROLL','SCHOOL','THIRD_PARTY']
    effective_from:date=Field(default_factory=date.today)
    effective_until:date|None=None
    notes:str|None=None


@router.get('/summary')
def summary(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.summary.read');scopes=_scopes(actor,'personnel.summary.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        return _jsonable(PostgresPersonnelRepository(conn).summary(actor.school_id,scopes=scopes))

@router.get('')
def directory(q:str|None=None,status:str|None=None,category:str|None=None,limit:int=Query(default=100,ge=1,le=500),offset:int=Query(default=0,ge=0),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.read');scopes=_scopes(actor,'personnel.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresPersonnelRepository(conn);items=repo.list_staff(actor.school_id,query=q,status=status,category=category,scopes=scopes,limit=limit,offset=offset);total=repo.count_staff(actor.school_id,query=q,status=status,category=category,scopes=scopes)
        return {"items":_jsonable(items),"total":total,"limit":limit,"offset":offset}

@router.get('/scope-options')
def scope_options(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    if not ({'personnel.assignments.add','personnel.assignments.read'} & set(actor.permissions)):
        raise HTTPException(status_code=403,detail='Permission affectations requise')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        sections=[_jsonable(dict(r._mapping)) for r in conn.execute(text("SELECT id,code,label FROM school_sections WHERE school_id=:sid AND enabled=true ORDER BY label"),{'sid':actor.school_id}).all()]
        classes=[_jsonable(dict(r._mapping)) for r in conn.execute(text("SELECT c.id,c.code,c.label,c.section_id,s.code section_code,s.label section_label FROM school_classes c JOIN school_sections s ON s.id=c.section_id JOIN academic_years y ON y.id=c.academic_year_id WHERE c.school_id=:sid AND c.enabled=true AND y.status='ACTIVE' ORDER BY s.label,c.label"),{'sid':actor.school_id}).all()]
        return {'sections':sections,'classes':classes}

@router.get('/history/events')
def global_history(limit:int=Query(default=100,ge=1,le=500),offset:int=Query(default=0,ge=0),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.history.read');scopes=_scopes(actor,'personnel.history.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresPersonnelRepository(conn); items=repo.list_status_history(actor.school_id,scopes=scopes,limit=limit,offset=offset); return {'items':_jsonable(items),'limit':limit,'offset':offset,'has_more':len(items)==limit}

@router.get('/{staff_id}')
def profile(staff_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.read');scopes=_scopes(actor,'personnel.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        item=PostgresPersonnelRepository(conn).get_staff(actor.school_id,staff_id,scopes=scopes)
        if item is None: raise HTTPException(status_code=404,detail='Agent introuvable dans votre périmètre')
        # Access-account identity is a separate sensitive capability.
        if 'personnel.access_link.read' not in actor.permissions: item['access_links']=[]
        return _jsonable(item)

@router.post('',status_code=201)
def create_staff(body:StaffCreate,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.create');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            member=StaffMember(school_id=actor.school_id,**body.model_dump());out=PostgresPersonnelRepository(conn).create_staff(member);payload=_jsonable(out);_audit_outbox(conn,request_actor,action='STAFF_CREATED',entity_type='StaffMember',entity_id=member.id,old=None,new=payload);return 201,payload
        result=_mutate(services=services,actor=actor,key=key,operation='PERSONNEL_CREATE_STAFF',payload=body.model_dump(mode='json'),action=action);response.status_code=result.status_code;return result.body
    except Exception as exc:_error(exc)

@router.put('/{staff_id}')
def update_staff(staff_id:UUID,body:StaffUpdate,if_match:str|None=Header(default=None,alias='If-Match'),idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.update');expected=_expected(if_match);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            repo=PostgresPersonnelRepository(conn);old=repo.get_staff(actor.school_id,staff_id);out=repo.update_staff(actor.school_id,staff_id,expected_version=expected,fields=body.model_dump());payload=_jsonable(out);_audit_outbox(conn,request_actor,action='STAFF_UPDATED',entity_type='StaffMember',entity_id=staff_id,old=_jsonable(old),new=payload);return 200,payload
        return _mutate(services=services,actor=actor,key=key,operation='PERSONNEL_UPDATE_STAFF',payload={**body.model_dump(mode='json'),'id':str(staff_id),'expected':expected},action=action).body
    except Exception as exc:_error(exc)

@router.patch('/{staff_id}/status')
def patch_status(staff_id:UUID,body:StaffStatusPatch,if_match:str|None=Header(default=None,alias='If-Match'),idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.activate');expected=_expected(if_match);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            repo=PostgresPersonnelRepository(conn);old=repo.get_staff(actor.school_id,staff_id);current=old
            if current is None: raise LookupError('Agent introuvable')
            if current['status']=='LEFT': raise ValueError('Utilisez la réactivation explicite pour un ancien agent')
            row=conn.execute(text("UPDATE staff_members SET status=:status WHERE school_id=:sid AND id=:id AND version=:expected RETURNING *"),{'status':body.status,'sid':actor.school_id,'id':staff_id,'expected':expected}).first()
            if row is None: raise OptimisticConcurrencyError('Agent modifié par un autre utilisateur')
            conn.execute(text("INSERT INTO staff_status_history(school_id,staff_id,from_status,to_status,effective_date,reason,actor_user_id) VALUES (:sid,:staff,:old,:new,:d,:reason,:actor)"),{'sid':actor.school_id,'staff':staff_id,'old':current['status'],'new':body.status,'d':body.effective_date,'reason':body.reason,'actor':actor.user_id})
            payload=_jsonable(dict(row._mapping));_audit_outbox(conn,request_actor,action='STAFF_STATUS_CHANGED',entity_type='StaffMember',entity_id=staff_id,old=_jsonable(old),new=payload,reason=body.reason);return 200,payload
        return _mutate(services=services,actor=actor,key=key,operation='PERSONNEL_CHANGE_STATUS',payload={**body.model_dump(mode='json'),'id':str(staff_id),'expected':expected},action=action).body
    except Exception as exc:_error(exc)

@router.post('/{staff_id}/exit')
def exit_staff(staff_id:UUID,body:ExitBody,if_match:str|None=Header(default=None,alias='If-Match'),idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.exit');expected=_expected(if_match);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            repo=PostgresPersonnelRepository(conn);old=repo.get_staff(actor.school_id,staff_id);out=repo.exit_staff(actor.school_id,staff_id,expected_version=expected,effective_date=body.effective_date,reason=body.reason,actor_user_id=actor.user_id);payload=_jsonable(out);_audit_outbox(conn,request_actor,action='STAFF_EXITED',entity_type='StaffMember',entity_id=staff_id,old=_jsonable(old),new=payload,reason=body.reason);return 200,payload
        return _mutate(services=services,actor=actor,key=key,operation='PERSONNEL_EXIT_STAFF',payload={**body.model_dump(mode='json'),'id':str(staff_id),'expected':expected},action=action).body
    except Exception as exc:_error(exc)

@router.post('/{staff_id}/reactivate')
def reactivate_staff(staff_id:UUID,body:ExitBody,if_match:str|None=Header(default=None,alias='If-Match'),idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.reactivate');expected=_expected(if_match);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            repo=PostgresPersonnelRepository(conn);old=repo.get_staff(actor.school_id,staff_id);out=repo.reactivate_staff(actor.school_id,staff_id,expected_version=expected,effective_date=body.effective_date,reason=body.reason,actor_user_id=actor.user_id);payload=_jsonable(out);_audit_outbox(conn,request_actor,action='STAFF_REACTIVATED',entity_type='StaffMember',entity_id=staff_id,old=_jsonable(old),new=payload,reason=body.reason);return 200,payload
        return _mutate(services=services,actor=actor,key=key,operation='PERSONNEL_REACTIVATE_STAFF',payload={**body.model_dump(mode='json'),'id':str(staff_id),'expected':expected},action=action).body
    except Exception as exc:_error(exc)

@router.get('/catalog/functions')
def functions(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.functions.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return _jsonable(PostgresPersonnelRepository(conn).list_functions(actor.school_id))

@router.post('/catalog/functions',status_code=201)
def create_function(body:FunctionCreate,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.functions.manage');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            fn=StaffFunction(school_id=actor.school_id,**body.model_dump());out=PostgresPersonnelRepository(conn).create_function(fn);payload=_jsonable(out);_audit_outbox(conn,request_actor,action='STAFF_FUNCTION_CREATED',entity_type='StaffFunction',entity_id=fn.id,old=None,new=payload);return 201,payload
        result=_mutate(services=services,actor=actor,key=key,operation='PERSONNEL_CREATE_FUNCTION',payload=body.model_dump(mode='json'),action=action);response.status_code=result.status_code;return result.body
    except Exception as exc:_error(exc)

@router.put('/catalog/functions/{function_id}')
def update_function(function_id:UUID,body:FunctionUpdate,if_match:str|None=Header(default=None,alias='If-Match'),idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.functions.manage');expected=_expected(if_match);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out=PostgresPersonnelRepository(conn).update_function(actor.school_id,function_id,expected_version=expected,**body.model_dump());payload=_jsonable(out);_audit_outbox(conn,request_actor,action='STAFF_FUNCTION_UPDATED',entity_type='StaffFunction',entity_id=function_id,old=None,new=payload);return 200,payload
        return _mutate(services=services,actor=actor,key=key,operation='PERSONNEL_UPDATE_FUNCTION',payload={**body.model_dump(mode='json'),'id':str(function_id),'expected':expected},action=action).body
    except Exception as exc:_error(exc)

@router.get('/{staff_id}/assignments')
def assignments(staff_id:UUID,include_history:bool=False,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.assignments.read');scopes=_scopes(actor,'personnel.assignments.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return _jsonable(PostgresPersonnelRepository(conn).list_assignments(actor.school_id,staff_id,scopes=scopes,include_history=include_history))

@router.post('/assignments',status_code=201)
def add_assignment(body:AssignmentCreate,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.assignments.add');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            assignment=StaffAssignment(school_id=actor.school_id,**body.model_dump());out=PostgresPersonnelRepository(conn).add_assignment(assignment);payload=_jsonable(out);_audit_outbox(conn,request_actor,action='STAFF_ASSIGNMENT_ADDED',entity_type='StaffAssignment',entity_id=assignment.id,old=None,new=payload);return 201,payload
        result=_mutate(services=services,actor=actor,key=key,operation='PERSONNEL_ADD_ASSIGNMENT',payload=body.model_dump(mode='json'),action=action);response.status_code=result.status_code;return result.body
    except Exception as exc:_error(exc)

@router.post('/assignments/{assignment_id}/end')
def end_assignment(assignment_id:UUID,body:AssignmentEnd,if_match:str|None=Header(default=None,alias='If-Match'),idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.assignments.end');expected=_expected(if_match);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out=PostgresPersonnelRepository(conn).end_assignment(actor.school_id,assignment_id,expected_version=expected,effective_date=body.effective_date,reason=body.reason);payload=_jsonable(out);_audit_outbox(conn,request_actor,action='STAFF_ASSIGNMENT_ENDED',entity_type='StaffAssignment',entity_id=assignment_id,old=None,new=payload,reason=body.reason);return 200,payload
        return _mutate(services=services,actor=actor,key=key,operation='PERSONNEL_END_ASSIGNMENT',payload={**body.model_dump(mode='json'),'id':str(assignment_id),'expected':expected},action=action).body
    except Exception as exc:_error(exc)

@router.get('/{staff_id}/children')
def children(staff_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.staff_children.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return _jsonable(PostgresPersonnelRepository(conn).staff_children(actor.school_id,staff_id))

@router.post('/{staff_id}/children')
def link_child(staff_id:UUID,body:StaffStudentLinkBody,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.staff_children.link');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out=PostgresPersonnelRepository(conn).link_student(actor.school_id,staff_id,body.student_id,relationship=body.relationship);payload=_jsonable(out);_audit_outbox(conn,request_actor,action='STAFF_CHILD_LINKED',entity_type='StaffStudentLink',entity_id=UUID(str(out['id'])),old=None,new=payload);return 200,payload
        return _mutate(services=services,actor=actor,key=key,operation='PERSONNEL_LINK_CHILD',payload={**body.model_dump(mode='json'),'staff_id':str(staff_id)},action=action).body
    except Exception as exc:_error(exc)

@router.put('/children/{link_id}/finance-mode')
def child_finance_mode(link_id:UUID,body:StaffStudentFinanceModeBody,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.staff_children.finance_mode');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out=PostgresPersonnelRepository(conn).set_student_finance_mode(actor.school_id,link_id,mode=body.responsibility_mode,effective_from=body.effective_from,effective_until=body.effective_until,notes=body.notes);payload=_jsonable(out);_audit_outbox(conn,request_actor,action='STAFF_CHILD_FINANCE_MODE_CHANGED',entity_type='StaffStudentFinancePreference',entity_id=UUID(str(out['id'])),old=None,new=payload);return 200,payload
        return _mutate(services=services,actor=actor,key=key,operation='PERSONNEL_CHILD_FINANCE_MODE',payload={**body.model_dump(mode='json'),'link_id':str(link_id)},action=action).body
    except Exception as exc:_error(exc)

@router.get('/{staff_id}/access-links')
def access_links(staff_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.access_link.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return _jsonable(PostgresPersonnelRepository(conn).access_links(actor.school_id,staff_id))

@router.post('/{staff_id}/access-links')
def link_access(staff_id:UUID,body:AccessLinkBody,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.access_link.manage');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out=PostgresPersonnelRepository(conn).link_access(actor.school_id,staff_id,body.membership_id,reason=body.reason);payload=_jsonable(out);_audit_outbox(conn,request_actor,action='STAFF_ACCESS_LINKED',entity_type='StaffAccessLink',entity_id=UUID(str(out['id'])),old=None,new=payload,reason=body.reason);return 200,payload
        return _mutate(services=services,actor=actor,key=key,operation='PERSONNEL_LINK_ACCESS',payload={**body.model_dump(mode='json'),'staff_id':str(staff_id)},action=action).body
    except Exception as exc:_error(exc)

@router.post('/{staff_id}/access-links/{membership_id}/unlink')
def unlink_access(staff_id:UUID,membership_id:UUID,body:UnlinkBody,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.access_link.manage');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out=PostgresPersonnelRepository(conn).unlink_access(actor.school_id,staff_id,membership_id,reason=body.reason);payload=_jsonable(out);_audit_outbox(conn,request_actor,action='STAFF_ACCESS_UNLINKED',entity_type='StaffAccessLink',entity_id=UUID(str(out['id'])),old=None,new=payload,reason=body.reason);return 200,payload
        return _mutate(services=services,actor=actor,key=key,operation='PERSONNEL_UNLINK_ACCESS',payload={**body.model_dump(mode='json'),'staff_id':str(staff_id),'membership_id':str(membership_id)},action=action).body
    except Exception as exc:_error(exc)

from edusync.modules.documents.application.object_store import archive_generated
@router.get('/exports/register.pdf')
def register_pdf(q:str|None=None,status:str|None=None,category:str|None=None,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.directory.export');scopes=_scopes(actor,'personnel.directory.export')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresPersonnelRepository(conn);rows=repo.list_staff(actor.school_id,query=q,status=status,category=category,scopes=scopes,limit=1000);school=PostgresSchoolRepository(conn).get(actor.school_id);data=build_staff_register_pdf(rows,school_name=school.name if school else 'École')
        archive_generated(conn,actor,data=data,fmt='PDF',required_capability='personnel.directory.export',document_code='personnel.register',title='Registre du personnel',file_name='registre_personnel.pdf')
    return StreamingResponse(BytesIO(data),media_type='application/pdf',headers={'Content-Disposition':'inline; filename="registre_personnel.pdf"'})

@router.get('/exports/register.xlsx')
def register_xlsx(q:str|None=None,status:str|None=None,category:str|None=None,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.directory.export');scopes=_scopes(actor,'personnel.directory.export')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresPersonnelRepository(conn);rows=repo.list_staff(actor.school_id,query=q,status=status,category=category,scopes=scopes,limit=1000);school=PostgresSchoolRepository(conn).get(actor.school_id);data=build_staff_register_xlsx(rows,school_name=school.name if school else 'École')
        archive_generated(conn,actor,data=data,fmt='XLSX',required_capability='personnel.directory.export',document_code='personnel.register',title='Registre du personnel',file_name='registre_personnel.xlsx')
    return StreamingResponse(BytesIO(data),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="registre_personnel.xlsx"'})

@router.get('/{staff_id}/profile.pdf')
def profile_pdf(staff_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'personnel.profile.print_pdf');scopes=_scopes(actor,'personnel.profile.print_pdf')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresPersonnelRepository(conn);item=repo.get_staff(actor.school_id,staff_id,scopes=scopes)
        if item is None: raise HTTPException(status_code=404,detail='Agent introuvable dans votre périmètre')
        school=PostgresSchoolRepository(conn).get(actor.school_id);data=build_staff_profile_pdf(item,school_name=school.name if school else 'École')
        archive_generated(conn,actor,data=data,fmt='PDF',required_capability='personnel.profile.print_pdf',document_code=f'personnel.profile.{staff_id}',title='Fiche agent',file_name=f'fiche_agent_{staff_id}.pdf')
    return StreamingResponse(BytesIO(data),media_type='application/pdf',headers={'Content-Disposition':f'inline; filename="agent_{staff_id}.pdf"'})


# ---------------------------------------------------------------- N3-F — staff children finance (Desktop staff_finance.py)
from edusync.adapters.postgres_staff_finance import PostgresStaffFinanceRepository

@router.get("/{staff_id}/children/finance")
def staff_children_finance(staff_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """Desktop list_staff_children: mode, expected, settled, payroll deducted, balance, in order (per currency)."""
    _need(actor,'personnel.staff_children.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        return {'items':_jsonable(PostgresStaffFinanceRepository(conn).children(actor.school_id,staff_id))}

@router.get("/{staff_id}/children/{student_id}/open-charges")
def staff_child_open_charges(staff_id:UUID,student_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """G-PER-1 — Desktop staff_child_open_charges."""
    _need(actor,'personnel.staff_children.read')
    try:
        with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
            return {'items':_jsonable(PostgresStaffFinanceRepository(conn).open_charges(actor.school_id,staff_id,student_id))}
    except Exception as exc:_error(exc)

class PayrollLine(BaseModel):
    charge_id:UUID;amount:Decimal=Field(gt=0,max_digits=18,decimal_places=2)
class PayrollDeductionBody(BaseModel):
    allocations:list[PayrollLine]|None=None;reference:str|None=Field(default=None,max_length=120);period_label:str|None=Field(default=None,max_length=80)

@router.post("/{staff_id}/children/{student_id}/payroll-deductions")
def confirm_payroll_deduction(staff_id:UUID,student_id:UUID,body:PayrollDeductionBody,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """G-PER-2 — Desktop confirm_staff_payroll_deduction: non-cash settlement, no payment, no receipt, no cash operation."""
    _need(actor,'personnel.payroll_deduction.confirm');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out=PostgresStaffFinanceRepository(conn).confirm(actor.school_id,user_id=actor.user_id,staff_id=staff_id,student_id=student_id,
                allocations=[{'charge_id':str(a.charge_id),'amount':a.amount} for a in body.allocations] if body.allocations else None,reference=body.reference,period_label=body.period_label)
            _audit_outbox(conn,request_actor,action='CONFIRM_STAFF_PAYROLL_DEDUCTION',entity_type='Staff',entity_id=staff_id,old=None,new={'student_id':str(student_id),**_jsonable(out),'reference':body.reference})
            return 200,out
        result=_mutate(services=services,actor=actor,key=key,operation='PERSONNEL_PAYROLL_DEDUCTION',payload={**body.model_dump(mode='json'),'staff_id':str(staff_id),'student_id':str(student_id)},action=action);return result.body
    except Exception as exc:_error(exc)

class NoncashCancelBody(BaseModel):reason:str=Field(min_length=3,max_length=500)
@router.post("/payroll-deductions/{settlement_id}/cancel")
def cancel_payroll_deduction(settlement_id:UUID,body:NoncashCancelBody,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """Desktop cancel_staff_noncash_settlement: reason required; the charge becomes owed again."""
    _need(actor,'personnel.payroll_deduction.cancel');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out=PostgresStaffFinanceRepository(conn).cancel(actor.school_id,settlement_id,user_id=actor.user_id,reason=body.reason)
            _audit_outbox(conn,request_actor,action='CANCEL_STAFF_NONCASH_SETTLEMENT',entity_type='StaffNoncashSettlement',entity_id=settlement_id,old={'status':'CONFIRMED'},new=out,reason=body.reason)
            return 200,out
        result=_mutate(services=services,actor=actor,key=key,operation='PERSONNEL_PAYROLL_DEDUCTION_CANCEL',payload={**body.model_dump(mode='json'),'settlement_id':str(settlement_id)},action=action);return result.body
    except Exception as exc:_error(exc)
