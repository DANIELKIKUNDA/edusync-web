from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from io import BytesIO
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from edusync.adapters.postgres_idempotency import PostgresIdempotencyRepository
from edusync.adapters.postgres_repositories import PostgresAuditRepository, PostgresOutboxRepository, PostgresSchoolRepository
from edusync.adapters.postgres_schooling import PostgresSchoolingRepository
from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.modules.audit.domain.audit import AuditRecord
from edusync.modules.documents.application.object_store import archive_generated
from edusync.modules.schooling.application.documents import family_directory_pdf, family_directory_xlsx, student_directory_pdf, student_directory_xlsx, student_profile_pdf
from edusync.modules.schooling.application.use_cases import SchoolingService
from edusync.modules.schooling.domain.models import Guardian, GuardianRole
from edusync.modules.sync.domain.outbox import OutboxMessage
from edusync.shared.application.context import ActorContext
from edusync.shared.application.idempotency import IdempotentExecutor
from edusync.shared.domain.concurrency import IdempotencyConflict, IdempotencyInProgress, OptimisticConcurrencyError

router=APIRouter(tags=['Élèves, familles & inscriptions'])


def _need(actor:ActorContext, capability:str)->None:
    try: actor.require(capability)
    except PermissionError as exc: raise HTTPException(status_code=403,detail=str(exc)) from exc

def _scopes(actor:ActorContext, capability:str)->tuple[tuple[str,str|None],...]:
    scopes=actor.scopes_for(capability)
    return scopes if scopes else (() if capability in actor.permissions else ())

def _key(value:str|None)->str:
    key=(value or '').strip()
    if not key: raise HTTPException(status_code=400,detail='Idempotency-Key obligatoire')
    if len(key)>180: raise HTTPException(status_code=400,detail='Idempotency-Key trop longue')
    return key

def _expected(value:str|None)->int:
    raw=(value or '').strip().replace('W/','').strip('"')
    if not raw: raise HTTPException(status_code=428,detail='If-Match obligatoire')
    try:n=int(raw)
    except ValueError as exc: raise HTTPException(status_code=400,detail='If-Match invalide') from exc
    if n<1:raise HTTPException(status_code=400,detail='Version invalide')
    return n

def _jsonable(v:Any)->Any:
    if isinstance(v,(UUID,date,datetime)):return str(v)
    if isinstance(v,dict):return {str(k):_jsonable(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [_jsonable(x) for x in v]
    if hasattr(v,'value'):return str(v.value)
    return v

def _error(exc:Exception):
    if isinstance(exc,PermissionError):raise HTTPException(status_code=403,detail=str(exc)) from exc
    if isinstance(exc,LookupError):raise HTTPException(status_code=404,detail=str(exc)) from exc
    if isinstance(exc,(ValueError,OptimisticConcurrencyError,IdempotencyConflict,IntegrityError)):
        raise HTTPException(status_code=409,detail=str(exc)) from exc
    if isinstance(exc,IdempotencyInProgress):raise HTTPException(status_code=409,detail=str(exc),headers={'Retry-After':'1'}) from exc
    raise exc

def _audit_outbox(conn,actor:ActorContext,*,action:str,entity_type:str,entity_id:UUID,new:dict|None,old:dict|None=None,reason:str|None=None):
    PostgresAuditRepository(conn).append(AuditRecord(action=action,entity_type=entity_type,entity_id=entity_id,actor_user_id=actor.user_id,membership_id=actor.membership_id,school_id=actor.school_id,source=actor.source,old_data=old,new_data=new,reason=reason,correlation_id=actor.correlation_id,idempotency_key=actor.idempotency_key))
    PostgresOutboxRepository(conn).add(OutboxMessage(event_type=action,aggregate_type=entity_type,aggregate_id=entity_id,school_id=actor.school_id,payload=new or {},correlation_id=actor.correlation_id,deduplication_key=f'{actor.idempotency_key or actor.correlation_id}:{action}:{entity_id}'))

def _mutate(*,services:AppServices,actor:ActorContext,key:str,operation:str,payload:dict[str,Any],action):
    request_actor=replace(actor,correlation_id=uuid4(),idempotency_key=key)
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        return IdempotentExecutor(PostgresIdempotencyRepository(conn)).execute(scope_key=str(actor.school_id),idempotency_key=key,operation=operation,payload=payload,school_id=str(actor.school_id),actor_user_id=str(actor.user_id),action=lambda:action(conn,request_actor))

class GuardianInput(BaseModel):
    full_name:str=Field(min_length=2,max_length=180)
    role:GuardianRole=GuardianRole.TUTEUR
    phone:str|None=Field(default=None,max_length=48)
    email:str|None=Field(default=None,max_length=200)
    address:str|None=None
    occupation:str|None=Field(default=None,max_length=160)
    notes:str|None=None
    is_primary:bool=False

class ChildInput(BaseModel):
    student_id:UUID|None=None
    last_name:str|None=Field(default=None,max_length=120)
    middle_name:str|None=Field(default=None,max_length=120)
    first_name:str|None=Field(default=None,max_length=120)
    class_id:UUID
    gender:Literal['M','F']
    birth_date:date|None=None
    birth_place:str|None=Field(default=None,max_length=160)
    nationality:str|None=Field(default=None,max_length=96)
    address:str|None=None
    previous_school:str|None=Field(default=None,max_length=180)
    origin:Literal['NEW','REENROLLMENT','TRANSFER_IN']='NEW'
    origin_school:str|None=Field(default=None,max_length=180)
    notes:str|None=None
    enrollment_notes:str|None=None
    large_family_beneficiary:bool=False
    staff_member_id:UUID|None=None
    staff_beneficiary:bool=False

class FamilyEnrollmentBody(BaseModel):
    family_id:UUID|None=None
    household_query:str|None=None
    household_confidence:Literal['CERTAIN','POSSIBLE','NONE']='NONE'
    primary_guardian:GuardianInput|None=None
    additional_guardians:list[GuardianInput]=Field(default_factory=list,max_length=6)
    children:list[ChildInput]=Field(min_length=1,max_length=20)
    admission_notes:str|None=None

class StudentPatch(BaseModel):
    last_name:str|None=Field(default=None,max_length=120)
    middle_name:str|None=Field(default=None,max_length=120)
    first_name:str|None=Field(default=None,max_length=120)
    gender:Literal['M','F']|None=None
    birth_date:date|None=None
    birth_place:str|None=Field(default=None,max_length=160)
    nationality:str|None=Field(default=None,max_length=96)
    address:str|None=None
    previous_school:str|None=Field(default=None,max_length=180)
    photo_url:str|None=None
    notes:str|None=None

class LifecycleBody(BaseModel):
    effective_date:date=Field(default_factory=date.today)
    reason:str=Field(min_length=3,max_length=700)
    destination:str|None=Field(default=None,max_length=180)

class ClassChangeBody(BaseModel):
    class_id:UUID
    effective_date:date=Field(default_factory=date.today)
    reason:str=Field(min_length=3,max_length=700)

class FamilyPatch(BaseModel):
    display_name:str|None=Field(default=None,max_length=180)
    phone:str|None=Field(default=None,max_length=48)
    email:str|None=Field(default=None,max_length=200)
    address:str|None=None
    contact_status:Literal['COMPLETE','TO_COMPLETE']|None=None
    notes:str|None=None

@router.get('/summary')
def summary(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'students.read');scopes=_scopes(actor,'students.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return _jsonable(PostgresSchoolingRepository(conn).summary(actor.school_id,scopes=scopes))

@router.get('/students')
def students(q:str|None=None,class_id:UUID|None=None,section_id:UUID|None=None,academic_year_id:UUID|None=None,gender:Literal['M','F']|None=None,status:str|None=None,all_years:bool=False,limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'students.read');scopes=_scopes(actor,'students.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        rows=PostgresSchoolingRepository(conn).list_students(actor.school_id,scopes=scopes,q=q,class_id=class_id,section_id=section_id,academic_year_id=academic_year_id,gender=gender,status=status,all_years=all_years,limit=min(limit+1,500),offset=offset); has_more=len(rows)>limit; return {'items':_jsonable(rows[:limit]),'limit':limit,'offset':offset,'has_more':has_more}

@router.get('/students/{student_id}')
def student_profile(student_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'students.read');scopes=_scopes(actor,'students.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        item=PostgresSchoolingRepository(conn).get_student(actor.school_id,student_id,scopes=scopes)
        if not item:raise HTTPException(status_code=404,detail='Élève introuvable dans votre périmètre')
        return _jsonable(item)

@router.get('/families')
def families(q:str|None=None,contact_status:str|None=None,large_family_only:bool=False,academic_year_id:UUID|None=None,enrolled_only:bool=False,limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'families.read');scopes=_scopes(actor,'families.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        rows=PostgresSchoolingRepository(conn).list_families(actor.school_id,scopes=scopes,q=q,contact_status=contact_status,large_family_only=large_family_only,academic_year_id=academic_year_id,enrolled_only=enrolled_only,limit=min(limit+1,500),offset=offset); has_more=len(rows)>limit; return {'items':_jsonable(rows[:limit]),'limit':limit,'offset':offset,'has_more':has_more}

@router.get('/families/resolve/candidates')
def resolve_households(q:str=Query(min_length=1,max_length=180),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'families.resolve');scopes=_scopes(actor,'families.resolve')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return _jsonable(PostgresSchoolingRepository(conn).resolve_households(actor.school_id,q,scopes=scopes))

@router.get('/families/{family_id}')
def family_profile(family_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'families.read');scopes=_scopes(actor,'families.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        item=PostgresSchoolingRepository(conn).get_family(actor.school_id,family_id,scopes=scopes)
        if not item:raise HTTPException(status_code=404,detail='Foyer introuvable')
        return _jsonable(item)

@router.post('/enrollments/family',status_code=201)
def enroll_family(body:FamilyEnrollmentBody,response:Response,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    cap='enrollments.reenroll' if any(c.student_id for c in body.children) else 'enrollments.create';_need(actor,cap);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            repo=PostgresSchoolingRepository(conn);svc=SchoolingService(repo,school_id=actor.school_id,actor_user_id=actor.user_id,permitted_scopes=_scopes(actor,cap))
            payload=svc.enroll_family_batch(family_id=body.family_id,household_query=body.household_query,household_confidence=body.household_confidence,primary_guardian=body.primary_guardian.model_dump(mode='python') if body.primary_guardian else None,additional_guardians=[x.model_dump(mode='python') for x in body.additional_guardians],children=[x.model_dump(mode='python') for x in body.children],admission_notes=body.admission_notes)
            fid=UUID(payload['family_id']);_audit_outbox(conn,request_actor,action='FAMILY_ENROLLMENT_COMPLETED',entity_type='Family',entity_id=fid,new=payload);return 201,payload
        result=_mutate(services=services,actor=actor,key=key,operation='SCHOOLING_FAMILY_ENROLLMENT',payload=body.model_dump(mode='json'),action=action);response.status_code=result.status_code;return result.body
    except Exception as exc:_error(exc)

@router.patch('/students/{student_id}')
def patch_student(student_id:UUID,body:StudentPatch,if_match:str|None=Header(None,alias='If-Match'),idempotency_key:str|None=Header(None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    capability='students.identity.update' if any(getattr(body,x) is not None for x in ('last_name','middle_name','first_name')) else 'students.profile.complete'
    _need(actor,capability);scopes=_scopes(actor,capability);expected=_expected(if_match);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            repo=PostgresSchoolingRepository(conn);old=repo.get_student(actor.school_id,student_id,scopes=scopes)
            if not old: raise LookupError('Élève introuvable dans votre périmètre')
            out=repo.update_student(actor.school_id,student_id,expected_version=expected,patch=body.model_dump(exclude_none=True));payload=_jsonable(out);_audit_outbox(conn,request_actor,action='STUDENT_PROFILE_UPDATED',entity_type='Student',entity_id=student_id,old=_jsonable(old),new=payload);return 200,payload
        return _mutate(services=services,actor=actor,key=key,operation='SCHOOLING_UPDATE_STUDENT',payload={**body.model_dump(mode='json'),'id':str(student_id),'expected':expected},action=action).body
    except Exception as exc:_error(exc)

@router.post('/students/{student_id}/abandon')
def abandon(student_id:UUID,body:LifecycleBody,if_match:str|None=Header(None,alias='If-Match'),idempotency_key:str|None=Header(None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    return _lifecycle('students.lifecycle.abandon','ABANDON',student_id,body,if_match,idempotency_key,actor,services)

@router.post('/students/{student_id}/transfer')
def transfer(student_id:UUID,body:LifecycleBody,if_match:str|None=Header(None,alias='If-Match'),idempotency_key:str|None=Header(None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    return _lifecycle('students.lifecycle.transfer','TRANSFER',student_id,body,if_match,idempotency_key,actor,services)

@router.post('/students/{student_id}/reintegrate')
def reintegrate(student_id:UUID,body:LifecycleBody,if_match:str|None=Header(None,alias='If-Match'),idempotency_key:str|None=Header(None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    return _lifecycle('students.lifecycle.reintegrate','REINTEGRATE',student_id,body,if_match,idempotency_key,actor,services)

def _lifecycle(capability,event,student_id,body,if_match,idempotency_key,actor,services):
    _need(actor,capability);scopes=_scopes(actor,capability);expected=_expected(if_match);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            repo=PostgresSchoolingRepository(conn);old=repo.get_student(actor.school_id,student_id,scopes=scopes)
            if not old: raise LookupError('Élève introuvable dans votre périmètre')
            out=repo.change_status(actor.school_id,student_id,expected_version=expected,event_type=event,effective_date=body.effective_date,reason=body.reason,actor_user_id=actor.user_id,destination=body.destination);payload=_jsonable(out);_audit_outbox(conn,request_actor,action=f'STUDENT_{event}',entity_type='Student',entity_id=student_id,old=_jsonable(old),new=payload,reason=body.reason);return 200,payload
        return _mutate(services=services,actor=actor,key=key,operation=f'SCHOOLING_{event}',payload={**body.model_dump(mode='json'),'id':str(student_id),'expected':expected},action=action).body
    except Exception as exc:_error(exc)

@router.patch('/families/{family_id}')
def patch_family(family_id:UUID,body:FamilyPatch,if_match:str|None=Header(None,alias='If-Match'),idempotency_key:str|None=Header(None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'families.update');scopes=_scopes(actor,'families.update');expected=_expected(if_match);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            repo=PostgresSchoolingRepository(conn);old=repo.get_family(actor.school_id,family_id,scopes=scopes);patch=body.model_dump(exclude_none=True)
            if not old: raise LookupError('Foyer introuvable dans votre périmètre')
            if 'display_name' in patch:patch['display_name_origin']='MANUAL_OVERRIDE'
            out=repo.update_family(actor.school_id,family_id,expected_version=expected,patch=patch);payload=_jsonable(out);_audit_outbox(conn,request_actor,action='FAMILY_UPDATED',entity_type='Family',entity_id=family_id,old=_jsonable(old),new=payload);return 200,payload
        return _mutate(services=services,actor=actor,key=key,operation='SCHOOLING_UPDATE_FAMILY',payload={**body.model_dump(mode='json'),'id':str(family_id),'expected':expected},action=action).body
    except Exception as exc:_error(exc)

@router.post('/families/{family_id}/guardians',status_code=201)
def add_guardian(family_id:UUID,body:GuardianInput,response:Response,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'families.responsibles.add');scopes=_scopes(actor,'families.responsibles.add');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            repo=PostgresSchoolingRepository(conn)
            if not repo.get_family(actor.school_id,family_id,scopes=scopes):raise LookupError('Foyer introuvable dans votre périmètre')
            g=Guardian(school_id=actor.school_id,full_name=body.full_name,phone=body.phone,email=body.email,address=body.address,occupation=body.occupation,notes=body.notes);repo.create_guardian(g);link=repo.link_guardian(actor.school_id,family_id=family_id,guardian_id=g.id,role=body.role.value,is_primary=body.is_primary);payload=_jsonable(link);_audit_outbox(conn,request_actor,action='FAMILY_GUARDIAN_ADDED',entity_type='Family',entity_id=family_id,new={'guardian_id':str(g.id),**payload});return 201,{'guardian_id':str(g.id),**payload}
        result=_mutate(services=services,actor=actor,key=key,operation='SCHOOLING_ADD_GUARDIAN',payload={**body.model_dump(mode='json'),'family_id':str(family_id)},action=action);response.status_code=result.status_code;return result.body
    except Exception as exc:_error(exc)

@router.post('/students/{student_id}/class-change')
def class_change(student_id:UUID,body:ClassChangeBody,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    capability='students.class.change';_need(actor,capability);scopes=_scopes(actor,capability);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            repo=PostgresSchoolingRepository(conn);old=repo.get_student(actor.school_id,student_id,scopes=scopes)
            if not old: raise LookupError('Élève introuvable dans votre périmètre')
            target=repo.class_info(actor.school_id,body.class_id)
            if not target: raise LookupError('Classe cible introuvable')
            if not any(t=='SCHOOL' or (t=='SECTION' and str(v or '').upper()==str(target.get('section_code') or '').upper()) or (t=='CLASS' and str(v or '').upper()==str(target.get('code') or '').upper()) for t,v in scopes):
                raise PermissionError('Classe cible hors de votre périmètre')
            out=repo.change_class(actor.school_id,student_id,target_class_id=body.class_id,effective_date=body.effective_date,reason=body.reason,actor_user_id=actor.user_id);payload=_jsonable(out);_audit_outbox(conn,request_actor,action='STUDENT_CLASS_CHANGED',entity_type='Student',entity_id=student_id,old={'class_id':str((old.get('enrollments') or [{}])[0].get('class_id') or '')},new=payload,reason=body.reason);return 200,payload
        return _mutate(services=services,actor=actor,key=key,operation='SCHOOLING_CLASS_CHANGE',payload={**body.model_dump(mode='json'),'id':str(student_id)},action=action).body
    except PermissionError as exc: raise HTTPException(status_code=403,detail=str(exc)) from exc
    except Exception as exc:_error(exc)

@router.delete('/families/{family_id}/guardians/{guardian_id}')
def remove_guardian(family_id:UUID,guardian_id:UUID,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    capability='families.responsibles.remove';_need(actor,capability);scopes=_scopes(actor,capability);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            repo=PostgresSchoolingRepository(conn)
            if not repo.get_family(actor.school_id,family_id,scopes=scopes): raise LookupError('Foyer introuvable dans votre périmètre')
            out=repo.end_guardian_link(actor.school_id,family_id=family_id,guardian_id=guardian_id);payload=_jsonable(out);_audit_outbox(conn,request_actor,action='FAMILY_GUARDIAN_ENDED',entity_type='Family',entity_id=family_id,new=payload);return 200,payload
        return _mutate(services=services,actor=actor,key=key,operation='SCHOOLING_END_GUARDIAN',payload={'family_id':str(family_id),'guardian_id':str(guardian_id)},action=action).body
    except Exception as exc:_error(exc)

def _school_identity(conn,school_id:UUID)->dict[str,Any]:
    school=PostgresSchoolRepository(conn).get(school_id)
    if not school:return {'name':'École'}
    logo_key=conn.execute(text("SELECT logo_object_key FROM school_branding WHERE school_id=:sid"),{'sid':str(school_id)}).scalar_one_or_none()
    return {'id':str(school_id),'name':school.name,'logo_object_key':logo_key,'email':school.email,'phone':school.phone,'address':school.address,'city':school.city,'province':school.province}

def _school_name(conn,school_id:UUID)->str:
    return _school_identity(conn,school_id).get('name') or 'École'

def _export_filters(repo:PostgresSchoolingRepository,*,q:str|None,academic_year_id:UUID|None,section_id:UUID|None,class_id:UUID|None,status:str|None,gender:str|None,all_years:bool)->list[str]:
    if all_years: year_label='Tout l’historique'
    elif academic_year_id:
        y=repo.connection.execute(text('SELECT label FROM academic_years WHERE school_id=:sid AND id=:id'),{'sid':repo.connection.execute(text('SELECT current_setting(\'app.current_school_id\', true)')).scalar_one_or_none(),'id':academic_year_id}).first()
        year_label=str(y[0]) if y else 'Année sélectionnée'
    else:
        year=repo.active_year(UUID(str(repo.connection.execute(text("SELECT current_setting('app.current_school_id', true)")).scalar_one()))) if repo.connection.execute(text("SELECT current_setting('app.current_school_id', true)")).scalar_one_or_none() else None
        year_label=str((year or {}).get('label') or 'Année active')
    out=[f'Année : {year_label}']
    if section_id: out.append('Section : sélectionnée')
    else: out.append('Section : Toutes')
    if class_id: out.append('Classe : sélectionnée')
    else: out.append('Classe : Toutes')
    out.append(f'Statut : {status or "Tous"}')
    out.append(f'Sexe : {gender or "M/F"}')
    if q: out.append(f'Recherche : {q}')
    return out

@router.get('/exports/students.pdf')
def export_students_pdf(q:str|None=None,academic_year_id:UUID|None=None,section_id:UUID|None=None,class_id:UUID|None=None,status:str|None=None,gender:Literal['M','F']|None=None,all_years:bool=False,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'students.directory.print_pdf');scopes=_scopes(actor,'students.directory.print_pdf')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresSchoolingRepository(conn);rows=repo.list_students(actor.school_id,scopes=scopes,q=q,class_id=class_id,section_id=section_id,academic_year_id=academic_year_id,gender=gender,status=status,all_years=all_years,limit=1000,offset=0)
        filters=[]
        if all_years: filters.append('Périmètre : tout l’historique')
        else:
            year=repo.active_year(actor.school_id) if academic_year_id is None else conn.execute(text('SELECT label FROM academic_years WHERE school_id=:sid AND id=:id'),{'sid':actor.school_id,'id':academic_year_id}).mappings().first()
            filters.append(f"Année : {(year or {}).get('label','Année sélectionnée')}")
        filters += [f"Section : {'sélectionnée' if section_id else 'Toutes'}",f"Classe : {'sélectionnée' if class_id else 'Toutes'}",f"Statut : {status or 'Tous'}",f"Sexe : {gender or 'M/F'}"]
        if q:filters.append(f'Recherche : {q}')
        data=student_directory_pdf(school=_school_identity(conn,actor.school_id),rows=rows,filters=filters)
        archive_generated(conn,actor,data=data,fmt='PDF',required_capability='students.directory.print_pdf',document_code='students.directory',title='Annuaire des élèves',file_name='annuaire_eleves.pdf',academic_year_id=academic_year_id if 'students.directory'!='students.profile' else None)
    return StreamingResponse(BytesIO(data),media_type='application/pdf',headers={'Content-Disposition':'inline; filename="annuaire_eleves.pdf"'})

@router.get('/exports/students.xlsx')
def export_students_xlsx(q:str|None=None,academic_year_id:UUID|None=None,section_id:UUID|None=None,class_id:UUID|None=None,status:str|None=None,gender:Literal['M','F']|None=None,all_years:bool=False,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'students.directory.export_xlsx');scopes=_scopes(actor,'students.directory.export_xlsx')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresSchoolingRepository(conn);rows=repo.list_students(actor.school_id,scopes=scopes,q=q,class_id=class_id,section_id=section_id,academic_year_id=academic_year_id,gender=gender,status=status,all_years=all_years,limit=1000,offset=0)
        filters=[]
        if all_years:filters.append('Périmètre : tout l’historique')
        else:
            year=repo.active_year(actor.school_id) if academic_year_id is None else conn.execute(text('SELECT label FROM academic_years WHERE school_id=:sid AND id=:id'),{'sid':actor.school_id,'id':academic_year_id}).mappings().first()
            filters.append(f"Année : {(year or {}).get('label','Année sélectionnée')}")
        filters += [f"Section : {'sélectionnée' if section_id else 'Toutes'}",f"Classe : {'sélectionnée' if class_id else 'Toutes'}",f"Statut : {status or 'Tous'}",f"Sexe : {gender or 'M/F'}"]
        if q:filters.append(f'Recherche : {q}')
        data=student_directory_xlsx(school=_school_identity(conn,actor.school_id),rows=rows,filters=filters)
        archive_generated(conn,actor,data=data,fmt='XLSX',required_capability='students.directory.export_xlsx',document_code='students.directory',title='Annuaire des élèves',file_name='annuaire_eleves.xlsx',academic_year_id=academic_year_id if 'students.directory'!='students.profile' else None)
    return StreamingResponse(BytesIO(data),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="annuaire_eleves.xlsx"'})

@router.get('/exports/families.pdf')
def export_families_pdf(q:str|None=None,academic_year_id:UUID|None=None,enrolled_only:bool=True,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'families.directory.print_pdf');scopes=_scopes(actor,'families.directory.print_pdf')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresSchoolingRepository(conn);rows=repo.list_families(actor.school_id,scopes=scopes,q=q,academic_year_id=academic_year_id,enrolled_only=enrolled_only,limit=1000,offset=0)
        year=repo.active_year(actor.school_id) if academic_year_id is None else conn.execute(text('SELECT label FROM academic_years WHERE school_id=:sid AND id=:id'),{'sid':actor.school_id,'id':academic_year_id}).mappings().first()
        filters=[f"Année : {(year or {}).get('label','Année sélectionnée')}",'Inscrits dans l’année consultée' if enrolled_only else 'Répertoire global']
        if q:filters.append(f'Recherche : {q}')
        data=family_directory_pdf(school=_school_identity(conn,actor.school_id),rows=rows,filters=filters)
        archive_generated(conn,actor,data=data,fmt='PDF',required_capability='families.directory.print_pdf',document_code='families.directory',title='Répertoire des familles',file_name='repertoire_familles.pdf',academic_year_id=academic_year_id if 'families.directory'!='students.profile' else None)
    return StreamingResponse(BytesIO(data),media_type='application/pdf',headers={'Content-Disposition':'inline; filename="repertoire_familles.pdf"'})

@router.get('/exports/families.xlsx')
def export_families_xlsx(q:str|None=None,academic_year_id:UUID|None=None,enrolled_only:bool=True,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'families.directory.export_xlsx');scopes=_scopes(actor,'families.directory.export_xlsx')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresSchoolingRepository(conn);rows=repo.list_families(actor.school_id,scopes=scopes,q=q,academic_year_id=academic_year_id,enrolled_only=enrolled_only,limit=1000,offset=0)
        year=repo.active_year(actor.school_id) if academic_year_id is None else conn.execute(text('SELECT label FROM academic_years WHERE school_id=:sid AND id=:id'),{'sid':actor.school_id,'id':academic_year_id}).mappings().first()
        filters=[f"Année : {(year or {}).get('label','Année sélectionnée')}",'Inscrits dans l’année consultée' if enrolled_only else 'Répertoire global']
        if q:filters.append(f'Recherche : {q}')
        data=family_directory_xlsx(school=_school_identity(conn,actor.school_id),rows=rows,filters=filters)
        archive_generated(conn,actor,data=data,fmt='XLSX',required_capability='families.directory.export_xlsx',document_code='families.directory',title='Répertoire des familles',file_name='repertoire_familles.xlsx',academic_year_id=academic_year_id if 'families.directory'!='students.profile' else None)
    return StreamingResponse(BytesIO(data),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="repertoire_familles.xlsx"'})

@router.get('/students/{student_id}/profile.pdf')
def export_student_profile(student_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'students.profile.print_pdf');scopes=_scopes(actor,'students.profile.print_pdf')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        student=PostgresSchoolingRepository(conn).get_student(actor.school_id,student_id,scopes=scopes)
        if not student:raise HTTPException(status_code=404,detail='Élève introuvable')
        data=student_profile_pdf(school=_school_identity(conn,actor.school_id),student=student)
        archive_generated(conn,actor,data=data,fmt='PDF',required_capability='students.profile.print_pdf',document_code='students.profile',title='Fiche élève',file_name=f'fiche_eleve_{student_id}.pdf',academic_year_id=academic_year_id if 'students.profile'!='students.profile' else None)
    return StreamingResponse(BytesIO(data),media_type='application/pdf',headers={'Content-Disposition':'inline; filename="fiche_eleve.pdf"'})
