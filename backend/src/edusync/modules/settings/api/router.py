from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text

from edusync.adapters.postgres_idempotency import PostgresIdempotencyRepository
from edusync.adapters.postgres_repositories import PostgresAuditRepository, PostgresOutboxRepository, PostgresSchoolRepository
from edusync.adapters.postgres_fee_schedules import PostgresFeeScheduleRepository
from edusync.adapters.postgres_anticipation import PostgresAnticipationRepository
from edusync.adapters.postgres_annual_policy_admin import PostgresAnnualPolicyAdminRepository
from edusync.adapters.postgres_annual_policy_activation import activate_annual_policy
from edusync.modules.finance_fee_tracking.domain.annual_policy_validation import french_policy_error, validate_policy_rules
from edusync.adapters.postgres_annual_exigibility_preview import preview_enrollment_monthly_schedules
from edusync.adapters.postgres_settings import PostgresSettingsRepository
from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.modules.audit.domain.audit import AuditRecord
from edusync.modules.settings.domain.models import AcademicYear
from edusync.modules.sync.domain.outbox import OutboxMessage
from edusync.shared.application.context import ActorContext
from edusync.shared.application.idempotency import IdempotentExecutor
from edusync.shared.domain.concurrency import IdempotencyConflict, IdempotencyInProgress, OptimisticConcurrencyError

router = APIRouter(tags=["Paramètres"])


def _need(actor: ActorContext, capability: str) -> None:
    try:
        actor.require(capability)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _key(value: str | None) -> str:
    key=(value or "").strip()
    if not key: raise HTTPException(status_code=400,detail="Idempotency-Key obligatoire")
    if len(key)>180: raise HTTPException(status_code=400,detail="Idempotency-Key trop longue")
    return key


def _expected(if_match: str | None) -> int:
    raw=(if_match or "").strip().replace('W/','').strip('"')
    if not raw: raise HTTPException(status_code=428,detail="If-Match avec la version courante est obligatoire")
    try:
        n=int(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400,detail="If-Match invalide") from exc
    if n<1: raise HTTPException(status_code=400,detail="Version invalide")
    return n


def _error(exc: Exception):
    if isinstance(exc, LookupError): raise HTTPException(status_code=404,detail=str(exc)) from exc
    if isinstance(exc,IntegrityError):
        # never the raw SQL text: a uniqueness / reference violation explained in the user's terms
        raw=str(getattr(exc,'orig',exc)).lower()
        msg=('Cet élément existe déjà : un autre porte le même code ou le même nom.' if 'unique' in raw or 'duplicate' in raw
             else 'Enregistrement refusé : un élément lié est introuvable ou encore utilisé.')
        raise HTTPException(status_code=409,detail=msg) from exc
    if isinstance(exc,(ValueError,OptimisticConcurrencyError,IdempotencyConflict)):
        raise HTTPException(status_code=409,detail=str(exc)) from exc
    if isinstance(exc,IdempotencyInProgress):
        raise HTTPException(status_code=409,detail=str(exc),headers={"Retry-After":"1"}) from exc
    raise exc


def _audit_and_outbox(conn, actor: ActorContext, *, action:str, entity_type:str, entity_id:UUID|None,
                      old:dict|None,new:dict|None, reason:str|None=None):
    PostgresAuditRepository(conn).append(AuditRecord(
        action=action,entity_type=entity_type,entity_id=entity_id,actor_user_id=actor.user_id,
        membership_id=actor.membership_id,school_id=actor.school_id,source=actor.source,
        old_data=old,new_data=new,reason=reason,correlation_id=actor.correlation_id,idempotency_key=actor.idempotency_key,
    ))
    if entity_id is not None:
        PostgresOutboxRepository(conn).add(OutboxMessage(
            event_type=action,aggregate_type=entity_type,aggregate_id=entity_id,school_id=actor.school_id,
            payload=new or {},correlation_id=actor.correlation_id,
            deduplication_key=f"{actor.idempotency_key or actor.correlation_id}:{action}:{entity_id}",
        ))


def _mutate(*, services:AppServices, actor:ActorContext, key:str, operation:str, payload:dict[str,Any], action):
    request_actor=replace(actor,correlation_id=uuid4(),idempotency_key=key)
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        idem=IdempotentExecutor(PostgresIdempotencyRepository(conn))
        result=idem.execute(scope_key=str(actor.school_id),idempotency_key=key,operation=operation,payload=payload,
                            school_id=str(actor.school_id),actor_user_id=str(actor.user_id),
                            action=lambda: action(conn,request_actor))
    return result


class IdentityPatch(BaseModel):
    name:str=Field(min_length=2,max_length=160)
    email:str|None=Field(default=None,max_length=320)
    phone:str|None=Field(default=None,max_length=64)
    logo_url:str|None=Field(default=None,max_length=2048)
    address:str|None=Field(default=None,max_length=500)
    city:str|None=Field(default=None,max_length=120)
    province:str|None=Field(default=None,max_length=120)
    # Desktop identity « devise / mention » (settings parity pass 3): printed under the school name on documents.
    motto:str|None=Field(default=None,max_length=160)


@router.get('/overview')
def overview(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.school_identity.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresSettingsRepository(conn); snap,bootstrap=repo.readiness(actor.school_id)
        school=PostgresSchoolRepository(conn).get(actor.school_id)
        return {
            'school':{'id':str(school.id),'code':school.code,'name':school.name,'email':school.email,'phone':school.phone,'logo_url':school.logo_url,'address':school.address,'city':school.city,'province':school.province,'version':school.version,
                      'motto':conn.execute(text('SELECT motto FROM schools WHERE id=:sid'),{'sid':str(actor.school_id)}).scalar_one_or_none()},
            'readiness':{'percent':snap.percent,'global_blocking':False,'items':[{'code':x.code,'label':x.label,'state':x.state,'detail':x.detail,'blocking_only_for':list(x.blocking_only_for)} for x in snap.items]},
            'bootstrap':bootstrap,
        }


@router.get('/reference-catalog')
def reference_catalog(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.structure.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        return PostgresSettingsRepository(conn).reference_catalog()


@router.patch('/identity')
def update_identity(body:IdentityPatch,response:Response,if_match:str|None=Header(default=None,alias='If-Match'),
                    idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),
                    services:AppServices=Depends(get_services)):
    _need(actor,'settings.school_identity.update'); expected=_expected(if_match); key=_key(idempotency_key)
    payload={**body.model_dump(mode='json'),'expected_version':expected}
    try:
        def action(conn,request_actor):
            schools=PostgresSchoolRepository(conn); school=schools.get(actor.school_id)
            if school is None: raise LookupError('École introuvable')
            if school.version!=expected: raise OptimisticConcurrencyError('Identité école modifiée par une autre session')
            old={'name':school.name,'email':school.email,'phone':school.phone,'logo_url':school.logo_url,'address':school.address,'city':school.city,'province':school.province,'version':school.version}
            school.name=body.name.strip();school.email=body.email;school.phone=body.phone;school.logo_url=body.logo_url;school.address=body.address;school.city=body.city;school.province=body.province
            old['motto']=conn.execute(text('SELECT motto FROM schools WHERE id=:sid'),{'sid':str(school.id)}).scalar_one_or_none()
            schools.save_identity(school)
            # Column-level grant of migration 0088. A client that does not send the motto (older screen, setup assistant)
            # keeps it; an explicit empty value clears it.
            motto=((body.motto or '').strip() or None) if 'motto' in body.model_fields_set else old['motto']
            conn.execute(text('UPDATE schools SET motto=:m WHERE id=:sid'),{'m':motto,'sid':str(school.id)})
            new={'name':school.name,'email':school.email,'phone':school.phone,'logo_url':school.logo_url,'address':school.address,'city':school.city,'province':school.province,'version':school.version,'motto':motto}
            _audit_and_outbox(conn,request_actor,action='SCHOOL_IDENTITY_UPDATED',entity_type='School',entity_id=school.id,old=old,new=new)
            return 200,new
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_UPDATE_IDENTITY',payload=payload,action=action)
        response.headers['ETag']=f'"{result.body["version"]}"';response.headers['Idempotent-Replayed']='true' if result.replayed else 'false';return result.body
    except Exception as exc:_error(exc)


class AcademicYearCreate(BaseModel):
    code:str=Field(min_length=4,max_length=32)
    label:str=Field(min_length=4,max_length=96)
    start_date:date
    end_date:date
    # Enrollment period (2026-10-24): informative, editable, never blocking (late enrollments and transfers exist).
    enrollment_start:date|None=None
    enrollment_end:date|None=None

@router.get('/academic-years/selector')
def year_selector(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """Minimal, non-sensitive year list for the shell's year selector, readable by every school member.
    Full year administration stays behind settings.academic_year.read / management capabilities."""
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresSettingsRepository(conn);windows=repo.enrollment_windows(actor.school_id)
        # The enrollment period (2026-10-24) is shown to whoever enrolls: informative, never blocking.
        return [{**{k:v for k,v in year_json(y).items() if k in ('id','code','label','status','start_date','end_date')},
                 **windows.get(str(y.id),{'enrollment_start':None,'enrollment_end':None})} for y in repo.list_academic_years(actor.school_id)]

@router.get('/academic-years')
def list_years(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.academic_year.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresSettingsRepository(conn);windows=repo.enrollment_windows(actor.school_id)
        return [{**year_json(y),**windows.get(str(y.id),{'enrollment_start':None,'enrollment_end':None})} for y in repo.list_academic_years(actor.school_id)]

def year_json(y:AcademicYear):
    return {'id':str(y.id),'code':y.code,'label':y.label,'start_date':y.start_date.isoformat(),'end_date':y.end_date.isoformat(),'status':y.status.value,'version':y.version}

@router.post('/academic-years',status_code=201)
def create_year(body:AcademicYearCreate,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),
                actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.academic_year.create');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            data=body.model_dump();window=(data.pop('enrollment_start'),data.pop('enrollment_end'))
            repo=PostgresSettingsRepository(conn);y=AcademicYear(school_id=actor.school_id,**data);repo.add_academic_year(y)
            repo.set_enrollment_window(actor.school_id,y.id,*window)
            out={**year_json(y),'enrollment_start':window[0].isoformat() if window[0] else None,'enrollment_end':window[1].isoformat() if window[1] else None};_audit_and_outbox(conn,request_actor,action='ACADEMIC_YEAR_CREATED',entity_type='AcademicYear',entity_id=y.id,old=None,new=out)
            return 201,out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_CREATE_ACADEMIC_YEAR',payload=body.model_dump(mode='json'),action=action)
        response.status_code=result.status_code;response.headers['ETag']=f'"{result.body["version"]}"';return result.body
    except Exception as exc:_error(exc)

class AcademicYearUpdate(BaseModel):
    code:str=Field(min_length=4,max_length=32)
    label:str=Field(min_length=4,max_length=96)
    start_date:date
    end_date:date

@router.put('/academic-years/{year_id}')
def update_year(year_id:UUID,body:AcademicYearUpdate,response:Response,if_match:str|None=Header(default=None,alias='If-Match'),idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.academic_year.update');expected=_expected(if_match);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            repo=PostgresSettingsRepository(conn);y=repo.get_academic_year(actor.school_id,year_id)
            if y is None: raise LookupError('Année scolaire introuvable')
            if y.status.value!='PREPARED': raise ValueError('Seule une année PREPARED peut être modifiée directement')
            before=year_json(y);candidate=AcademicYear(id=y.id,school_id=y.school_id,status=y.status,version=y.version,created_at=y.created_at,updated_at=y.updated_at,**body.model_dump())
            repo.save_academic_year(candidate,expected_version=expected);out=year_json(candidate)
            _audit_and_outbox(conn,request_actor,action='ACADEMIC_YEAR_UPDATED',entity_type='AcademicYear',entity_id=year_id,old=before,new=out);return 200,out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_UPDATE_ACADEMIC_YEAR',payload={**body.model_dump(mode='json'),'year_id':str(year_id),'expected':expected},action=action)
        response.headers['ETag']=f'"{result.body["version"]}"';return result.body
    except Exception as exc:_error(exc)

class CopyYearConfiguration(BaseModel):
    source_year_id:UUID

@router.post('/academic-years/{target_year_id}/copy-configuration')
def copy_year_configuration(target_year_id:UUID,body:CopyYearConfiguration,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.academic_year.copy_previous');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            repo=PostgresSettingsRepository(conn);result=repo.copy_academic_year_configuration(actor.school_id,source_year_id=body.source_year_id,target_year_id=target_year_id)
            _audit_and_outbox(conn,request_actor,action='ACADEMIC_YEAR_CONFIGURATION_COPIED',entity_type='AcademicYear',entity_id=target_year_id,old=None,new={'source_year_id':str(body.source_year_id),**result});return 200,result
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_COPY_ACADEMIC_YEAR_CONFIGURATION',payload={'source_year_id':str(body.source_year_id),'target_year_id':str(target_year_id)},action=action);return result.body
    except Exception as exc:_error(exc)

@router.post('/academic-years/{year_id}/activate')
def activate_year(year_id:UUID,response:Response,if_match:str|None=Header(default=None,alias='If-Match'),
                  idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.academic_year.activate');expected=_expected(if_match);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            repo=PostgresSettingsRepository(conn);old=repo.get_academic_year(actor.school_id,year_id)
            if old is None: raise LookupError('Année scolaire introuvable')
            before=year_json(old);y=repo.activate_academic_year(actor.school_id,year_id,expected_version=expected);out=year_json(y)
            _audit_and_outbox(conn,request_actor,action='ACADEMIC_YEAR_ACTIVATED',entity_type='AcademicYear',entity_id=y.id,old=before,new=out)
            return 200,out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_ACTIVATE_ACADEMIC_YEAR',payload={'year_id':str(year_id),'expected':expected},action=action)
        response.headers['ETag']=f'"{result.body["version"]}"';return result.body
    except Exception as exc:_error(exc)


def _transition_year(*, year_id:UUID, transition:str, capability:str, event:str, response:Response, if_match:str|None, idempotency_key:str|None, actor:ActorContext, services:AppServices):
    _need(actor,capability);expected=_expected(if_match);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            repo=PostgresSettingsRepository(conn);old=repo.get_academic_year(actor.school_id,year_id)
            if old is None: raise LookupError('Année scolaire introuvable')
            before=year_json(old);y=repo.transition_academic_year(actor.school_id,year_id,expected_version=expected,action=transition);out=year_json(y)
            _audit_and_outbox(conn,request_actor,action=event,entity_type='AcademicYear',entity_id=y.id,old=before,new=out)
            return 200,out
        result=_mutate(services=services,actor=actor,key=key,operation=f'SETTINGS_{transition}_ACADEMIC_YEAR',payload={'year_id':str(year_id),'expected':expected},action=action)
        response.headers['ETag']=f'"{result.body["version"]}"';return result.body
    except Exception as exc:_error(exc)

@router.post('/academic-years/{year_id}/close')
def close_year(year_id:UUID,response:Response,if_match:str|None=Header(default=None,alias='If-Match'),idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    return _transition_year(year_id=year_id,transition='CLOSE',capability='settings.academic_year.close',event='ACADEMIC_YEAR_CLOSED',response=response,if_match=if_match,idempotency_key=idempotency_key,actor=actor,services=services)

@router.post('/academic-years/{year_id}/archive')
def archive_year(year_id:UUID,response:Response,if_match:str|None=Header(default=None,alias='If-Match'),idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    return _transition_year(year_id=year_id,transition='ARCHIVE',capability='settings.academic_year.archive',event='ACADEMIC_YEAR_ARCHIVED',response=response,if_match=if_match,idempotency_key=idempotency_key,actor=actor,services=services)

@router.post('/academic-years/{year_id}/reopen')
def reopen_year(year_id:UUID,response:Response,if_match:str|None=Header(default=None,alias='If-Match'),idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    return _transition_year(year_id=year_id,transition='REOPEN',capability='settings.academic_year.reopen',event='ACADEMIC_YEAR_REOPENED',response=response,if_match=if_match,idempotency_key=idempotency_key,actor=actor,services=services)


class SectionPut(BaseModel):
    code:str=Field(min_length=2,max_length=32)
    label:str=Field(min_length=2,max_length=96)
    enabled:bool=True
    expected_version:int|None=Field(default=None,ge=1)

@router.get('/sections')
def sections(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.structure.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return PostgresSettingsRepository(conn).list_sections(actor.school_id)

@router.put('/sections/{code}')
def put_section(code:str,body:SectionPut,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.sections.manage');key=_key(idempotency_key)
    if code.strip().upper()!=body.code.strip().upper():raise HTTPException(status_code=400,detail='Le code URL et le code du corps diffèrent')
    try:
        def action(conn,request_actor):
            repo=PostgresSettingsRepository(conn);out=repo.upsert_section(actor.school_id,code=body.code,label=body.label,enabled=body.enabled,expected_version=body.expected_version)
            _audit_and_outbox(conn,request_actor,action='SCHOOL_SECTION_UPSERTED',entity_type='SchoolSection',entity_id=out['id'],old=None,new={k:str(v) if isinstance(v,UUID) else v for k,v in out.items()})
            return 200,{k:str(v) if isinstance(v,UUID) else v for k,v in out.items()}
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_UPSERT_SECTION',payload=body.model_dump(mode='json'),action=action);return result.body
    except Exception as exc:_error(exc)


class OptionPut(BaseModel):
    section_id:UUID
    code:str=Field(min_length=1,max_length=48)
    label:str=Field(min_length=1,max_length=120)
    tariff_group_code:Literal['GENERAL','TECHNICAL','OTHER']|None=None
    enabled:bool=True
    expected_version:int|None=Field(default=None,ge=1)

@router.get('/options/selector')
def options_selector(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """Enabled options (labels, section) for operational filters (student directory), readable by every school member —
    same doctrine as /classes/selector. Option administration stays behind settings.structure.read."""
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        return _jsonable([o for o in PostgresSettingsRepository(conn).list_options(actor.school_id) if o.get('enabled',True)])

@router.get('/options')
def options(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.structure.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        return _jsonable(PostgresSettingsRepository(conn).list_options(actor.school_id))

@router.put('/options/{code}')
def put_option(code:str,body:OptionPut,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.options.manage');key=_key(idempotency_key)
    if code.strip().upper()!=body.code.strip().upper(): raise HTTPException(status_code=400,detail='Le code URL et le code du corps diffèrent')
    try:
        def action(conn,request_actor):
            repo=PostgresSettingsRepository(conn);data=body.model_dump()
            old=conn.execute(text("SELECT section_id,code,label,tariff_group_code,enabled,version FROM school_options WHERE school_id=:s AND code=:c"),
                             {"s":actor.school_id,"c":body.code.strip().upper()}).first()
            old=None if old is None else _jsonable(dict(old._mapping))
            if old is None:
                # Owner decision 2026-10-24 (desktop parity): study options exist only in the Secondaire (Humanités).
                sec=conn.execute(text("SELECT code FROM school_sections WHERE school_id=:s AND id=:id"),{"s":actor.school_id,"id":body.section_id}).scalar()
                if sec is None: raise LookupError('Section introuvable')
                if str(sec).upper()!='SECONDAIRE': raise ValueError('Les options n’existent qu’en Secondaire (Humanités) : la Maternelle et le Primaire n’en ont pas.')
            # Desktop set_option_tariff_group: the Humanities tariff group is its own action and capability; an update that
            # does not send it keeps the current group.
            if 'tariff_group_code' not in body.model_fields_set: data['tariff_group_code']=(old or {}).get('tariff_group_code')
            elif data['tariff_group_code']!=(old or {}).get('tariff_group_code'): _need(actor,'settings.option_tariff_group.manage')
            out=repo.upsert_option(actor.school_id,**data)
            payload=_jsonable(out);_audit_and_outbox(conn,request_actor,action='SCHOOL_OPTION_UPSERTED',entity_type='SchoolOption',entity_id=UUID(str(out['id'])),old=old,new=payload);return 200,payload
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_UPSERT_OPTION',payload=body.model_dump(mode='json'),action=action);return result.body
    except Exception as exc:_error(exc)


HUMANITIES_REFERENCES={'H1','H2','H3','H4'}


class ClassCreate(BaseModel):
    academic_year_id:UUID
    section_id:UUID
    option_id:UUID|None=None
    reference_code:str|None=Field(default=None,max_length=48)
    code:str=Field(min_length=1,max_length=64)
    label:str=Field(min_length=1,max_length=140)

@router.get('/classes/selector')
def classes_selector(year_id:UUID|None=None,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """Minimal class list for operational screens (enrollment, cash desk filters), readable by every school member.
    Class structure administration stays behind settings.structure.read / management capabilities."""
    # Class labels/sections are not sensitive: same shape as the administration list, so screens render identically.
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        return _jsonable(PostgresSettingsRepository(conn).list_classes(actor.school_id,year_id))

@router.get('/classes')
def classes(year_id:UUID|None=None,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.structure.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        return _jsonable(PostgresSettingsRepository(conn).list_classes(actor.school_id,year_id))

@router.post('/classes',status_code=201)
def create_class(body:ClassCreate,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.classes.create');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            if body.option_id is not None and (body.reference_code or '').upper() not in HUMANITIES_REFERENCES:
                raise ValueError('Une option ne s’applique qu’aux classes des Humanités (1re à 4e Humanités).')
            out=PostgresSettingsRepository(conn).create_class(actor.school_id,**body.model_dump());out=_jsonable(out)
            _audit_and_outbox(conn,request_actor,action='SCHOOL_CLASS_CREATED',entity_type='SchoolClass',entity_id=UUID(out['id']),old=None,new=out);return 201,out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_CREATE_CLASS',payload=body.model_dump(mode='json'),action=action);response.status_code=result.status_code;return result.body
    except Exception as exc:_error(exc)


class ClassUpdate(BaseModel):
    code:str=Field(min_length=1,max_length=64)
    label:str=Field(min_length=1,max_length=140)
    # Legacy field: the class state is no longer changed by a rename (Desktop parity, owner decision 2026-10-14).
    enabled:bool|None=None

class ClassStatusChange(BaseModel):
    status:Literal['ACTIVE','INACTIVE','ARCHIVED']

def _class_snapshot(conn,school_id:UUID,class_id:UUID)->dict[str,Any]|None:
    row=conn.execute(text("SELECT code,label,status,enabled,version FROM school_classes WHERE school_id=:s AND id=:id"),{"s":school_id,"id":class_id}).first()
    return None if row is None else _jsonable(dict(row._mapping))

@router.put('/classes/{class_id}')
def update_class(class_id:UUID,body:ClassUpdate,response:Response,if_match:str|None=Header(default=None,alias='If-Match'),idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """Rename a class (settings.classes.rename). Renaming never opens, pauses or archives a class."""
    _need(actor,'settings.classes.rename');expected=_expected(if_match);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            old=_class_snapshot(conn,actor.school_id,class_id)
            if old is not None and body.enabled is not None and body.enabled!=bool(old['enabled']):
                raise ValueError("Le statut d'une classe se change par l'action Activer / Mettre en pause / Archiver, pas par un renommage")
            repo=PostgresSettingsRepository(conn);out=_jsonable(repo.update_class(actor.school_id,class_id,code=body.code,label=body.label,expected_version=expected))
            _audit_and_outbox(conn,request_actor,action='SCHOOL_CLASS_UPDATED',entity_type='SchoolClass',entity_id=class_id,old=old,new=out);return 200,out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_UPDATE_CLASS',payload={**body.model_dump(mode='json'),'class_id':str(class_id),'expected':expected},action=action);return result.body
    except Exception as exc:_error(exc)

@router.post('/classes/{class_id}/status')
def change_class_status(class_id:UUID,body:ClassStatusChange,response:Response,if_match:str|None=Header(default=None,alias='If-Match'),idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """Desktop set_class_status: one capability (settings.classes.activate) for activate / pause / reactivate / archive."""
    _need(actor,'settings.classes.activate');expected=_expected(if_match);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            old=_class_snapshot(conn,actor.school_id,class_id)
            repo=PostgresSettingsRepository(conn);out=_jsonable(repo.set_class_status(actor.school_id,class_id,status=body.status,expected_version=expected))
            _audit_and_outbox(conn,request_actor,action='SCHOOL_CLASS_STATUS_CHANGED',entity_type='SchoolClass',entity_id=class_id,old=old,new=out);return 200,out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_CLASS_STATUS',payload={**body.model_dump(mode='json'),'class_id':str(class_id),'expected':expected},action=action);return result.body
    except Exception as exc:_error(exc)

class FeeTypeCreate(BaseModel):
    code:str=Field(min_length=2,max_length=48)
    label:str=Field(min_length=2,max_length=140)
    periodicity:Literal['ONE_TIME','MONTHLY','PERIODIC','OPTIONAL']
    default_currency:Literal['CDF','USD']='CDF'
    regulatory:bool=False

@router.get('/fee-types')
def fee_types(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.fee_types.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return _jsonable(PostgresSettingsRepository(conn).list_fee_types(actor.school_id))

@router.post('/fee-types',status_code=201)
def create_fee_type(body:FeeTypeCreate,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.fee_types.manage');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out=_jsonable(PostgresSettingsRepository(conn).create_fee_type(actor.school_id,**body.model_dump()))
            _audit_and_outbox(conn,request_actor,action='FEE_TYPE_CREATED',entity_type='FeeType',entity_id=UUID(out['id']),old=None,new=out);return 201,out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_CREATE_FEE_TYPE',payload=body.model_dump(mode='json'),action=action);response.status_code=result.status_code;return result.body
    except Exception as exc:_error(exc)


class FeeTypeUpdate(BaseModel):
    label:str=Field(min_length=2,max_length=140)
    periodicity:Literal['ONE_TIME','MONTHLY','PERIODIC','OPTIONAL']
    default_currency:Literal['CDF','USD']='CDF'
    regulatory:bool=False
    enabled:bool=True

@router.put('/fee-types/{fee_type_id}')
def update_fee_type(fee_type_id:UUID,body:FeeTypeUpdate,response:Response,if_match:str|None=Header(default=None,alias='If-Match'),idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.fee_types.manage' if body.enabled else 'settings.fee_types.activate');expected=_expected(if_match);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out=_jsonable(PostgresSettingsRepository(conn).update_fee_type(actor.school_id,fee_type_id,expected_version=expected,**body.model_dump()))
            _audit_and_outbox(conn,request_actor,action='FEE_TYPE_UPDATED',entity_type='FeeType',entity_id=fee_type_id,old=None,new=out);return 200,out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_UPDATE_FEE_TYPE',payload={**body.model_dump(mode='json'),'fee_type_id':str(fee_type_id),'expected':expected},action=action);return result.body
    except Exception as exc:_error(exc)

class TariffCreate(BaseModel):
    academic_year_id:UUID
    fee_type_id:UUID
    currency:Literal['CDF','USD']
    amount:Decimal=Field(gt=0,max_digits=18,decimal_places=2)
    class_id:UUID|None=None
    section_id:UUID|None=None
    option_id:UUID|None=None
    billing_months:list[str]=Field(default_factory=list,max_length=12)

@router.get('/tariffs')
def tariffs(year_id:UUID|None=None,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.tariffs.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return _jsonable(PostgresSettingsRepository(conn).list_tariffs(actor.school_id,year_id))

@router.post('/tariffs',status_code=201)
def create_tariff(body:TariffCreate,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.tariffs.manage');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out=_jsonable(PostgresSettingsRepository(conn).create_tariff(actor.school_id,**body.model_dump()))
            _audit_and_outbox(conn,request_actor,action='TARIFF_CREATED',entity_type='Tariff',entity_id=UUID(out['id']),old=None,new=out);return 201,out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_CREATE_TARIFF',payload=body.model_dump(mode='json'),action=action);response.status_code=result.status_code;return result.body
    except Exception as exc:_error(exc)


class TariffUpdate(BaseModel):
    currency:Literal['CDF','USD']
    amount:Decimal=Field(gt=0,max_digits=18,decimal_places=2)
    billing_months:list[str]=Field(default_factory=list,max_length=12)
    enabled:bool=True

@router.put('/tariffs/{tariff_id}')
def update_tariff(tariff_id:UUID,body:TariffUpdate,response:Response,if_match:str|None=Header(default=None,alias='If-Match'),idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.tariffs.manage');expected=_expected(if_match);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out=_jsonable(PostgresSettingsRepository(conn).update_tariff(actor.school_id,tariff_id,expected_version=expected,**body.model_dump()))
            _audit_and_outbox(conn,request_actor,action='TARIFF_UPDATED',entity_type='Tariff',entity_id=tariff_id,old=None,new=out);return 200,out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_UPDATE_TARIFF',payload={**body.model_dump(mode='json'),'tariff_id':str(tariff_id),'expected':expected},action=action);return result.body
    except Exception as exc:_error(exc)

class TariffRulePut(BaseModel):
    academic_year_id:UUID
    fee_type_id:UUID
    scope_type:Literal['SCHOOL','SECTION','ACADEMIC_CLASS','OPTION_GROUP','CLASS']
    scope_ref:str|None=Field(default=None,max_length=64)
    amount:Decimal|None=Field(default=None,ge=0,max_digits=18,decimal_places=2)
    currency:Literal['CDF','USD']='CDF'
    status:Literal['ACTIVE','PENDING_OFFICIAL','INACTIVE']='ACTIVE'
    effective_from:date|None=None
    source_reference:str|None=Field(default=None,max_length=240)

@router.put('/tariff-rules')
def put_tariff_rule(body:TariffRulePut,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """Desktop upsert_tariff_rule / save_tariff_group_rule: one rule per fee, target and effective date (same key = update)."""
    _need(actor,'settings.tariffs.manage')
    if body.scope_type=='OPTION_GROUP': _need(actor,'settings.tariff_groups.manage')
    key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out,old=PostgresSettingsRepository(conn).upsert_tariff_rule(actor.school_id,**body.model_dump())
            out=_jsonable(out)
            _audit_and_outbox(conn,request_actor,action='TARIFF_RULE_UPSERTED',entity_type='Tariff',entity_id=UUID(out['id']),old=_jsonable(old) if old else None,new=out)
            return (200 if old else 201),out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_PUT_TARIFF_RULE',payload=body.model_dump(mode='json'),action=action);response.status_code=result.status_code;return result.body
    except Exception as exc:_error(exc)

@router.get('/tariffs/resolve')
def resolve_tariff(class_id:UUID,fee_type_id:UUID,as_of:date|None=None,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """The rule that applies to a class at a date (Desktop resolve_tariff_for_class), or null."""
    _need(actor,'settings.tariffs.read')
    try:
        with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
            return _jsonable(PostgresSettingsRepository(conn).resolve_tariff(actor.school_id,class_id=class_id,fee_type_id=fee_type_id,as_of=as_of))
    except Exception as exc:_error(exc)

class ApplyTariffs(BaseModel):
    academic_year_id:UUID

@router.post('/tariffs/apply')
def apply_tariffs(body:ApplyTariffs,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """Desktop « Appliquer les barèmes aux classes ouvertes » (apply_tariff_rules_to_classes): schedule lines per class and
    due charges for every validated enrollment; never rewrites a line that already received money."""
    _need(actor,'settings.tariffs.apply');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out=PostgresFeeScheduleRepository(conn).apply_tariffs(actor.school_id,body.academic_year_id)
            _audit_and_outbox(conn,request_actor,action='TARIFFS_APPLIED',entity_type='AcademicYear',entity_id=body.academic_year_id,old=None,new=out);return 200,out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_APPLY_TARIFFS',payload=body.model_dump(mode='json'),action=action);return result.body
    except Exception as exc:_error(exc)

@router.get('/fee-schedules')
def fee_schedules(year_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.tariffs.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        return _jsonable(PostgresFeeScheduleRepository(conn).list_schedules(actor.school_id,year_id))

class ExigibilityDraftCreate(BaseModel):
    academic_year_id:UUID
    effective_from:date
    source_policy_id:UUID|None=None

class ExigibilityBand(BaseModel):
    first_day:int=Field(ge=1,le=31)
    last_day:int|None=Field(default=None,ge=1,le=31)
    percent:Decimal=Field(ge=0,le=100,max_digits=5,decimal_places=2)

class ExigibilityRulePut(BaseModel):
    fee_type_id:UUID
    prior_mode:Literal['NOT_APPLICABLE','FULL','CUSTOM']
    prior_percent:Decimal|None=Field(default=None,ge=0,le=100,max_digits=5,decimal_places=2)
    bands:list[ExigibilityBand]=Field(min_length=1,max_length=31)

@router.get('/annual-exigibility')
def annual_exigibility_list(year_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.tariffs.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        return _jsonable(PostgresAnnualPolicyAdminRepository(conn).list(actor.school_id,year_id))

@router.get('/annual-exigibility/{policy_id}')
def annual_exigibility_detail(policy_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.tariffs.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        return _jsonable(PostgresAnnualPolicyAdminRepository(conn).detail(actor.school_id,policy_id))

@router.post('/annual-exigibility',status_code=201)
def annual_exigibility_create(body:ExigibilityDraftCreate,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.tariffs.manage')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        return _jsonable(PostgresAnnualPolicyAdminRepository(conn).create_draft(
            actor.school_id,body.academic_year_id,body.effective_from,actor.user_id,body.source_policy_id))

@router.put('/annual-exigibility/{policy_id}/rules')
def annual_exigibility_rule(policy_id:UUID,body:ExigibilityRulePut,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.tariffs.manage')
    bands=body.model_dump(mode='python')['bands']
    # Checked BEFORE saving (2026-11-02): an incoherent rule is refused at once, in French, instead of at activation.
    try:validate_policy_rules([{'fee_type_id':body.fee_type_id,'prior_mode':body.prior_mode,'prior_percent':body.prior_percent,'bands':bands}])
    except ValueError as exc:raise french_policy_error(exc) from exc
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        return _jsonable(PostgresAnnualPolicyAdminRepository(conn).put_rule(
            actor.school_id,policy_id,body.fee_type_id,body.prior_mode,body.prior_percent,bands))

@router.post('/annual-exigibility/{policy_id}/activate')
def annual_exigibility_activate(policy_id:UUID,year_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.tariffs.apply')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        try:return activate_annual_policy(conn,school_id=actor.school_id,academic_year_id=year_id,policy_id=policy_id,actor_id=actor.user_id)
        except ValueError as exc:raise french_policy_error(exc) from exc

@router.get('/annual-exigibility-preview/class')
def annual_exigibility_preview(year_id:UUID,class_id:UUID,financial_entry_date:date,
        actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.tariffs.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        return _jsonable(preview_enrollment_monthly_schedules(conn,school_id=actor.school_id,
            academic_year_id=year_id,class_id=class_id,financial_entry_date=financial_entry_date))

class BenefitPolicyPut(BaseModel):
    academic_year_id:UUID
    enabled:bool=False
    min_children:int=Field(default=0,ge=0,le=50)
    max_beneficiaries:int=Field(default=0,ge=0,le=50)
    discount_percent:Decimal=Field(default=Decimal('0'),ge=0,le=100,max_digits=5,decimal_places=2)
    free_beneficiaries:int=Field(default=0,ge=0,le=50)
    applies_to_fee_code:str|None=Field(default='SCOLARITE',max_length=48)
    # Several fees (2026-10-24): when given, the list wins over the single code; an empty list means every fee.
    applies_to_fee_codes:list[str]|None=Field(default=None,max_length=30)
    # Large family « par tranche » (2026-11-06): the free beneficiaries are granted per group of min_children children.
    per_group:bool=False
    notes:str|None=Field(default=None,max_length=600)
    expected_version:int|None=Field(default=None,ge=1)

@router.get('/benefit-policies')
def benefit_policies(year_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.benefits.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        return _jsonable(PostgresSettingsRepository(conn).list_benefit_policies(actor.school_id,year_id))

@router.put('/benefit-policies/{benefit_type}')
def put_benefit_policy(benefit_type:Literal['LARGE_FAMILY','STAFF_CHILD','SOCIAL_CASE','BURSARY','CUSTOM'],body:BenefitPolicyPut,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """Desktop save_benefit_policy: one policy per school year and benefit type; the beneficiary stays a manual choice."""
    _need(actor,'settings.benefits.manage');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out,old=PostgresSettingsRepository(conn).save_benefit_policy(actor.school_id,benefit_type=benefit_type,**body.model_dump())
            out=_jsonable(out);_audit_and_outbox(conn,request_actor,action='BENEFIT_POLICY_SAVED',entity_type='BenefitPolicy',entity_id=UUID(str(out['id'])),old=_jsonable(old) if old else None,new=out);return 200,out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_PUT_BENEFIT_POLICY',payload={**body.model_dump(mode='json'),'benefit_type':benefit_type},action=action);return result.body
    except Exception as exc:_error(exc)

class AdmissionConditionPut(BaseModel):
    academic_year_id:UUID
    condition_id:UUID|None=None
    label:str=Field(min_length=2,max_length=160)
    fee_type_id:UUID|None=None
    required:bool=True
    payment_timing:Literal['AT_ENROLLMENT','AFTER_ENROLLMENT','OPTIONAL']='AT_ENROLLMENT'
    can_pay_later:bool=False
    bundle_code:str|None=Field(default=None,max_length=48)
    scope_type:Literal['SCHOOL','SECTION','ACADEMIC_CLASS','CLASS']='SCHOOL'
    scope_ref:str|None=Field(default=None,max_length=64)
    scope_refs:list[str]|None=Field(default=None,max_length=300)
    sort_order:int=Field(default=100,ge=0,le=10000)
    expected_version:int|None=Field(default=None,ge=1)

class ActiveFlag(BaseModel):
    active:bool

@router.get('/admission-conditions')
def admission_conditions(year_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.enrollment_policy.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresSettingsRepository(conn)
        return _jsonable({"items":repo.list_admission_conditions(actor.school_id,year_id),"review":repo.admission_review(actor.school_id)})

@router.put('/admission-conditions')
def put_admission_condition(body:AdmissionConditionPut,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """Desktop upsert_enrollment_policy_item: an admission obligation of the school year."""
    _need(actor,'settings.enrollment_policy.manage');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out,old=PostgresSettingsRepository(conn).upsert_admission_condition(actor.school_id,**body.model_dump())
            out=_jsonable(out);_audit_and_outbox(conn,request_actor,action='ADMISSION_CONDITION_SAVED',entity_type='AdmissionCondition',entity_id=UUID(str(out['id'])),old=_jsonable(old) if old else None,new=out)
            return (200 if old else 201),out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_PUT_ADMISSION_CONDITION',payload=body.model_dump(mode='json'),action=action);response.status_code=result.status_code;return result.body
    except Exception as exc:_error(exc)

@router.post('/admission-conditions/{condition_id}/active')
def set_admission_condition_active(condition_id:UUID,body:ActiveFlag,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """Desktop set_enrollment_policy_item_active (settings.enrollment_policy.activate)."""
    _need(actor,'settings.enrollment_policy.activate');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out,old=PostgresSettingsRepository(conn).set_admission_condition_active(actor.school_id,condition_id,active=body.active)
            out=_jsonable(out);_audit_and_outbox(conn,request_actor,action='ADMISSION_CONDITION_ACTIVATED' if body.active else 'ADMISSION_CONDITION_DEACTIVATED',entity_type='AdmissionCondition',entity_id=condition_id,old=_jsonable(old),new=out);return 200,out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_ADMISSION_CONDITION_ACTIVE',payload={**body.model_dump(mode='json'),'condition_id':str(condition_id)},action=action);return result.body
    except Exception as exc:_error(exc)

@router.post('/admission-conditions/review')
def review_admission_conditions(response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """Desktop mark_enrollment_policy_reviewed: the school validated the rubric, even if it requires no fee at enrollment."""
    _need(actor,'settings.enrollment_policy.review');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out=_jsonable(PostgresSettingsRepository(conn).mark_admission_reviewed(actor.school_id,actor.user_id))
            _audit_and_outbox(conn,request_actor,action='ADMISSION_CONDITIONS_REVIEWED',entity_type='School',entity_id=actor.school_id,old=None,new=out);return 200,out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_ADMISSION_REVIEW',payload={},action=action);return result.body
    except Exception as exc:_error(exc)

class PaymentPolicyPut(BaseModel):
    partial_payments_enabled:bool=True
    partial_min_amount:Decimal=Field(default=Decimal('0'),ge=0,max_digits=18,decimal_places=2)
    partial_reporting_mode:Literal['INCLUDE','SEPARATE','EXCLUDE_UNTIL_SETTLED']='SEPARATE'
    advance_payments_enabled:bool=True
    future_charge_payments_enabled:bool=True
    accepted_modes:list[Literal['CASH','MOBILE_MONEY','BANQUE','AUTRE']]=Field(min_length=1,max_length=4)
    expected_version:int|None=Field(default=None,ge=1)

@router.get('/payment-policy')
def payment_policy(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.payment_policy.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        return _jsonable(PostgresSettingsRepository(conn).get_payment_policy(actor.school_id))

@router.put('/payment-policy')
def put_payment_policy(body:PaymentPolicyPut,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """Desktop save_payment_policy: partial payments and minimum deposit, advance and future months, accepted modes."""
    _need(actor,'settings.payment_policy.manage');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out,old=PostgresSettingsRepository(conn).put_payment_policy(actor.school_id,**body.model_dump())
            out=_jsonable(out);_audit_and_outbox(conn,request_actor,action='PAYMENT_POLICY_SAVED',entity_type='SchoolPaymentPolicy',entity_id=actor.school_id,old=_jsonable(old),new=out);return 200,out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_PUT_PAYMENT_POLICY',payload=body.model_dump(mode='json'),action=action);return result.body
    except Exception as exc:_error(exc)

class AnticipationPlanPut(BaseModel):
    academic_year_id:UUID
    plan_id:UUID|None=None
    name:str=Field(min_length=2,max_length=160)
    fee_type_id:UUID
    target_months:list[str]=Field(min_length=1,max_length=12)
    contribution_months:list[str]=Field(min_length=1,max_length=12)
    participation_mode:Literal['OPTIONAL','MANDATORY']='OPTIONAL'
    scope_type:Literal['SCHOOL','SECTION','OPTION_GROUP','ACADEMIC_CLASS','CLASS']='SCHOOL'
    scope_ref:str|None=Field(default=None,max_length=64)
    # Several targets of the same kind (2026-10-24); when given, the list wins over the single scope_ref.
    scope_refs:list[str]|None=Field(default=None,max_length=200)
    effective_from:date|None=None
    active:bool=True

@router.get('/anticipation-plans')
def anticipation_plans(year_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'finance.anticipation_plans.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        return _jsonable(PostgresAnticipationRepository(conn).list_plans(actor.school_id,year_id))

@router.put('/anticipation-plans')
def put_anticipation_plan(body:AnticipationPlanPut,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """Desktop save_anticipation_plan: a plan with memberships keeps its structure (new version instead)."""
    _need(actor,'finance.anticipation_plans.manage');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out,old=PostgresAnticipationRepository(conn).save_plan(actor.school_id,**body.model_dump())
            out=_jsonable(out);_audit_and_outbox(conn,request_actor,action='ANTICIPATION_PLAN_SAVED',entity_type='AnticipationPlan',entity_id=UUID(str(out['id'])),old=_jsonable(old) if old else None,new=out)
            return (200 if old else 201),out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_PUT_ANTICIPATION_PLAN',payload=body.model_dump(mode='json'),action=action);response.status_code=result.status_code;return result.body
    except Exception as exc:_error(exc)

@router.post('/anticipation-plans/{plan_id}/active')
def set_anticipation_plan_active(plan_id:UUID,body:ActiveFlag,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'finance.anticipation_plans.manage');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out,old=PostgresAnticipationRepository(conn).set_plan_active(actor.school_id,plan_id,active=body.active)
            out=_jsonable(out);_audit_and_outbox(conn,request_actor,action='ANTICIPATION_PLAN_ACTIVATED' if body.active else 'ANTICIPATION_PLAN_DEACTIVATED',entity_type='AnticipationPlan',entity_id=plan_id,old=_jsonable(old),new=out);return 200,out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_ANTICIPATION_PLAN_ACTIVE',payload={**body.model_dump(mode='json'),'plan_id':str(plan_id)},action=action);return result.body
    except Exception as exc:_error(exc)

class BillingPolicyPut(BaseModel):
    billing_months:list[str]=Field(min_length=1,max_length=12)
    month_due_at_enrollment:str|None=Field(default=None,max_length=2)
    expected_version:int|None=Field(default=None,ge=1)

@router.get('/billing-policy')
def billing_policy(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.tariffs.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        return _jsonable(PostgresSettingsRepository(conn).get_billing_policy(actor.school_id))

@router.put('/billing-policy')
def put_billing_policy(body:BillingPolicyPut,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """Desktop save_monthly_billing_policy: billed months and the month possibly required at enrollment."""
    _need(actor,'settings.billing_months.manage');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out,old=PostgresSettingsRepository(conn).put_billing_policy(actor.school_id,**body.model_dump())
            out=_jsonable(out);_audit_and_outbox(conn,request_actor,action='BILLING_MONTHS_UPDATED',entity_type='SchoolBillingPolicy',entity_id=actor.school_id,old=_jsonable(old),new=out);return 200,out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_PUT_BILLING_POLICY',payload=body.model_dump(mode='json'),action=action);return result.body
    except Exception as exc:_error(exc)

class PolicyPut(BaseModel):
    payload:dict[str,Any]
    status:Literal['DRAFT','ACTIVE','ARCHIVED']='ACTIVE'
    effective_from:date|None=None
    effective_until:date|None=None
    expected_version:int|None=Field(default=None,ge=1)

POLICY_CAPS={
 'PAYMENT':('settings.payment_policy.read','settings.payment_policy.manage'),
 'ENROLLMENT':('settings.enrollment_policy.read','settings.enrollment_policy.manage'),
 'BENEFITS':('settings.benefits.read','settings.benefits.manage'),
 'DOCUMENTS':('settings.documents.read','settings.documents.manage'),
 'BACKUP':('settings.backups.read','settings.backups.manage'),
 'COMMUNICATIONS':('notifications.internal.read','notifications.internal.configure'),
}

@router.get('/policies/{kind}')
def get_policy(kind:str,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    kind=kind.upper();caps=POLICY_CAPS.get(kind)
    if caps is None:raise HTTPException(status_code=404,detail='Politique inconnue')
    _need(actor,caps[0])
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        out=PostgresSettingsRepository(conn).get_policy(actor.school_id,kind);return _jsonable(out) if out else None

@router.put('/policies/{kind}')
def put_policy(kind:str,body:PolicyPut,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    kind=kind.upper();caps=POLICY_CAPS.get(kind)
    if caps is None:raise HTTPException(status_code=404,detail='Politique inconnue')
    _need(actor,caps[1]);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            repo=PostgresSettingsRepository(conn);old=repo.get_policy(actor.school_id,kind);out=repo.put_policy(actor.school_id,kind=kind,**body.model_dump());out=_jsonable(out)
            _audit_and_outbox(conn,request_actor,action=f'{kind}_POLICY_UPDATED',entity_type='SchoolPolicy',entity_id=UUID(out['id']),old=_jsonable(old) if old else None,new=out);return 200,out
        result=_mutate(services=services,actor=actor,key=key,operation=f'SETTINGS_PUT_POLICY_{kind}',payload=body.model_dump(mode='json'),action=action);return result.body
    except Exception as exc:_error(exc)


class ContributionCreate(BaseModel):
    code:str=Field(min_length=2,max_length=48);label:str=Field(min_length=2,max_length=140);unit:str=Field(default='unité',max_length=48)
    required_quantity:Decimal=Field(default=Decimal('0'),ge=0,max_digits=18,decimal_places=3)   # N3-H / G-EFF-1 (Desktop required_quantity)

@router.get('/contributions')
def contributions(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.contributions.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return _jsonable(PostgresSettingsRepository(conn).list_contributions(actor.school_id))

@router.post('/contributions',status_code=201)
def create_contribution(body:ContributionCreate,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.contributions.manage');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out=_jsonable(PostgresSettingsRepository(conn).create_contribution(actor.school_id,**body.model_dump()));_audit_and_outbox(conn,request_actor,action='CONTRIBUTION_TYPE_CREATED',entity_type='ContributionType',entity_id=UUID(out['id']),old=None,new=out);return 201,out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_CREATE_CONTRIBUTION',payload=body.model_dump(mode='json'),action=action);response.status_code=result.status_code;return result.body
    except Exception as exc:_error(exc)


class ContributionUpdate(BaseModel):
    label:str=Field(min_length=2,max_length=140)
    unit:str=Field(default='unité',max_length=48)
    enabled:bool=True
    required_quantity:Decimal|None=Field(default=None,ge=0,max_digits=18,decimal_places=3)

@router.put('/contributions/{contribution_id}')
def update_contribution(contribution_id:UUID,body:ContributionUpdate,response:Response,if_match:str|None=Header(default=None,alias='If-Match'),idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.contributions.manage' if body.enabled else 'settings.contributions.activate');expected=_expected(if_match);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out=_jsonable(PostgresSettingsRepository(conn).update_contribution(actor.school_id,contribution_id,expected_version=expected,**body.model_dump()))
            _audit_and_outbox(conn,request_actor,action='CONTRIBUTION_TYPE_UPDATED',entity_type='ContributionType',entity_id=contribution_id,old=None,new=out);return 200,out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_UPDATE_CONTRIBUTION',payload={**body.model_dump(mode='json'),'contribution_id':str(contribution_id),'expected':expected},action=action);return result.body
    except Exception as exc:_error(exc)

class ProductCreate(BaseModel):
    code:str=Field(min_length=2,max_length=48);label:str=Field(min_length=2,max_length=160);currency:Literal['CDF','USD'];unit_price:Decimal=Field(gt=0);stock_tracking:bool=False
    # Stock management (2026-10-24): opening quantity (traced RECEIPT « Stock initial ») and low-stock alert threshold.
    opening_quantity:Decimal=Field(default=Decimal('0'),ge=0,max_digits=18,decimal_places=3)
    low_threshold:Decimal=Field(default=Decimal('0'),ge=0,max_digits=18,decimal_places=3)

@router.get('/products')
def products(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.products.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return _jsonable(PostgresSettingsRepository(conn).list_products(actor.school_id))

@router.post('/products',status_code=201)
def create_product(body:ProductCreate,response:Response,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.products.manage');key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out=_jsonable(PostgresSettingsRepository(conn).create_product(actor.school_id,user_id=actor.user_id,**body.model_dump()));_audit_and_outbox(conn,request_actor,action='SCHOOL_PRODUCT_CREATED',entity_type='SchoolProduct',entity_id=UUID(out['id']),old=None,new=out);return 201,out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_CREATE_PRODUCT',payload=body.model_dump(mode='json'),action=action);response.status_code=result.status_code;return result.body
    except Exception as exc:_error(exc)


class ProductUpdate(BaseModel):
    label:str=Field(min_length=2,max_length=160)
    currency:Literal['CDF','USD']
    unit_price:Decimal=Field(gt=0)
    stock_tracking:bool=False
    enabled:bool=True
    low_threshold:Decimal|None=Field(default=None,ge=0,max_digits=18,decimal_places=3)

@router.put('/products/{product_id}')
def update_product(product_id:UUID,body:ProductUpdate,response:Response,if_match:str|None=Header(default=None,alias='If-Match'),idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,'settings.products.manage' if body.enabled else 'settings.products.activate');expected=_expected(if_match);key=_key(idempotency_key)
    try:
        def action(conn,request_actor):
            out=_jsonable(PostgresSettingsRepository(conn).update_product(actor.school_id,product_id,expected_version=expected,**body.model_dump()))
            _audit_and_outbox(conn,request_actor,action='SCHOOL_PRODUCT_UPDATED',entity_type='SchoolProduct',entity_id=product_id,old=None,new=out);return 200,out
        result=_mutate(services=services,actor=actor,key=key,operation='SETTINGS_UPDATE_PRODUCT',payload={**body.model_dump(mode='json'),'product_id':str(product_id),'expected':expected},action=action);return result.body
    except Exception as exc:_error(exc)

def _jsonable(value):
    if value is None:return None
    if isinstance(value,list):return [_jsonable(x) for x in value]
    if isinstance(value,dict):
        return {k:_jsonable(v) for k,v in value.items()}
    if isinstance(value,UUID):return str(value)
    if isinstance(value,(date,)):return value.isoformat()
    if isinstance(value,Decimal):return str(value)
    try:
        import datetime
        if isinstance(value,datetime.datetime):return value.isoformat()
    except Exception:pass
    return value


# --- Settings parity pass 3 (2026-10-24): numbering, school data export / test, diagnostic ---------------------------
# Desktop golden master: « numérotation automatique », _backup_now, _test_backup, _export_diagnostic.
from edusync.modules.settings.application import school_maintenance as _maint


def _audit_direct(conn, actor: ActorContext, action: str, new: dict) -> None:
    """Read-only operations (export, test, diagnostic) are evidence too: audit only, no outbox event."""
    PostgresAuditRepository(conn).append(AuditRecord(action=action, entity_type='School', entity_id=actor.school_id, actor_user_id=actor.user_id,
        membership_id=actor.membership_id, school_id=actor.school_id, source=actor.source, old_data=None, new_data=new,
        reason=None, correlation_id=actor.correlation_id, idempotency_key=None))


def _platform_backup(services: AppServices) -> dict:
    from edusync.modules.platform_health.api.router import backup_component
    b = backup_component(services)
    return {'state': b.get('state'), 'detail': b.get('detail'), 'finished_at': (b.get('backup') or {}).get('finished_at'),
            'restore_verified': bool((b.get('backup') or {}).get('restore_verified')), 'offsite': bool((b.get('backup') or {}).get('offsite'))}


@router.get('/numbering')
def numbering(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, 'settings.school_identity.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        return _maint.numbering(conn, actor.school_id)


@router.get('/backups/status')
def backups_status(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, 'settings.backups.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        last = conn.execute(text("""SELECT occurred_at AS created_at, new_json FROM audit_events WHERE school_id=:sid AND action IN ('SCHOOL_DATA_EXPORTED','SCHOOL_DATA_EXPORT_TESTED')
            ORDER BY occurred_at DESC LIMIT 1"""), {'sid': str(actor.school_id)}).mappings().first()
    return _jsonable({'platform': _platform_backup(services), 'last_school_copy': dict(last) if last else None,
                      'restore': 'La restauration d’une école est réalisée par l’équipe de la plateforme EduSync, sur demande de la direction.'})


@router.post('/backups/export')
def backups_export(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, 'settings.backups.create')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        data, manifest = _maint.export_school_data(conn, actor.school_id, generated_by=str(actor.user_id))
        check = _maint.verify_export(data)
        if not check['ok']:
            raise HTTPException(status_code=500, detail='La copie générée n’a pas passé le contrôle d’intégrité : ' + '; '.join(check['problems']))
        _audit_direct(conn, actor, 'SCHOOL_DATA_EXPORTED', {'tables': check['tables'], 'total_rows': check['total_rows'], 'sha256': check['sha256'], 'size_bytes': check['size_bytes']})
    name = f"sauvegarde_{manifest['school']['code'] or 'ecole'}_{manifest['generated_at'][:10]}.zip"
    return Response(data, media_type='application/zip', headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
                    'Content-Disposition': f'attachment; filename="{name}"', 'X-Export-Sha256': check['sha256']})


@router.post('/backups/test')
def backups_test(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, 'settings.backups.test')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        data, _manifest = _maint.export_school_data(conn, actor.school_id, generated_by=str(actor.user_id))
        check = _maint.verify_export(data)
        _audit_direct(conn, actor, 'SCHOOL_DATA_EXPORT_TESTED', {k: check[k] for k in ('ok', 'tables', 'total_rows', 'sha256', 'size_bytes')})
    return check


def _diagnostic(conn, actor: ActorContext, services: AppServices) -> dict:
    snap, _bootstrap = PostgresSettingsRepository(conn).readiness(actor.school_id)
    readiness = {'percent': snap.percent, 'items': [{'code': x.code, 'label': x.label, 'state': x.state} for x in snap.items]}
    return _maint.diagnostic(conn, actor.school_id, readiness=readiness, backup=_platform_backup(services))


@router.get('/diagnostics')
def diagnostics(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, 'settings.diagnostics.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        return _jsonable(_diagnostic(conn, actor, services))


@router.get('/diagnostics/report.txt')
def diagnostics_report(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, 'settings.diagnostics.export')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        d = _diagnostic(conn, actor, services)
        _audit_direct(conn, actor, 'SCHOOL_DIAGNOSTIC_EXPORTED', {'app_version': d['app_version'], 'schema_version': d['schema_version']})
    return Response(_maint.diagnostic_text(d).encode('utf-8'), media_type='text/plain; charset=utf-8',
                    headers={'Cache-Control': 'private, no-store', 'Content-Disposition': f'attachment; filename="diagnostic_{d["generated_at"][:10]}.txt"'})


class DocumentSettingsPut(BaseModel):
    signatory_name:str|None=Field(default=None,max_length=120)
    signatory_title:str|None=Field(default=None,max_length=120)
    show_school_logo:bool=True


@router.get('/document-settings')
def document_settings(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """Desktop _build_documents: signatory printed on documents and « show the school logo » (receipt numbering, format
    and copies stay in the Documents module, next to the cash desk)."""
    _need(actor, 'settings.documents.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        r = conn.execute(text("SELECT signatory_name,signatory_title,show_school_logo,version FROM school_print_settings WHERE school_id=:sid"), {'sid': str(actor.school_id)}).mappings().first()
    return dict(r) if r else {'signatory_name': None, 'signatory_title': None, 'show_school_logo': True, 'version': 0}


@router.put('/document-settings')
def put_document_settings(body: DocumentSettingsPut, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, 'settings.documents.manage')
    values = {'sid': str(actor.school_id), 'n': (body.signatory_name or '').strip() or None, 't': (body.signatory_title or '').strip() or None,
              'l': body.show_school_logo, 'u': str(actor.user_id)}
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        old = conn.execute(text("SELECT signatory_name,signatory_title,show_school_logo FROM school_print_settings WHERE school_id=:sid"), {'sid': str(actor.school_id)}).mappings().first()
        row = conn.execute(text("""INSERT INTO school_print_settings(school_id,signatory_name,signatory_title,show_school_logo,updated_by) VALUES(:sid,:n,:t,:l,:u)
            ON CONFLICT(school_id) DO UPDATE SET signatory_name=EXCLUDED.signatory_name,signatory_title=EXCLUDED.signatory_title,show_school_logo=EXCLUDED.show_school_logo,
            updated_by=EXCLUDED.updated_by,updated_at=now(),version=school_print_settings.version+1
            RETURNING signatory_name,signatory_title,show_school_logo,version"""), values).mappings().one()
        PostgresAuditRepository(conn).append(AuditRecord(action='DOCUMENT_SETTINGS_UPDATED', entity_type='SchoolPrintSettings', entity_id=actor.school_id,
            actor_user_id=actor.user_id, membership_id=actor.membership_id, school_id=actor.school_id, source=actor.source,
            old_data=dict(old) if old else None, new_data=dict(row), reason=None, correlation_id=actor.correlation_id, idempotency_key=None))
    return dict(row)



# --- Administrator finishing pass (2026-10-24): enrollment period, product stock -------------------------------------
class EnrollmentWindowPut(BaseModel):
    enrollment_start:date|None=None
    enrollment_end:date|None=None


@router.put('/academic-years/{year_id}/enrollment-window')
def put_enrollment_window(year_id:UUID,body:EnrollmentWindowPut,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """Enrollment period of a prepared or active year. Informative only: an enrollment outside the period stays possible
    (late enrollment, transfer) and is simply flagged to the secretary."""
    _need(actor,'settings.academic_year.update')
    try:
        with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
            repo=PostgresSettingsRepository(conn);y=repo.get_academic_year(actor.school_id,year_id)
            if y is None: raise LookupError('Année scolaire introuvable')
            if y.status.value not in ('PREPARED','ACTIVE'): raise ValueError(f"L'année {y.label} est en lecture seule")
            old=repo.enrollment_windows(actor.school_id).get(str(year_id))
            out=repo.set_enrollment_window(actor.school_id,year_id,body.enrollment_start,body.enrollment_end)
            PostgresAuditRepository(conn).append(AuditRecord(action='ENROLLMENT_WINDOW_UPDATED',entity_type='AcademicYear',entity_id=year_id,actor_user_id=actor.user_id,
                membership_id=actor.membership_id,school_id=actor.school_id,source=actor.source,old_data=old,new_data=out,reason=None,
                correlation_id=actor.correlation_id,idempotency_key=None))
            return out
    except Exception as exc:_error(exc)


class ProductStockMove(BaseModel):
    movement_type:Literal['RECEIPT','ADJUSTMENT']
    quantity:Decimal=Field(gt=0,max_digits=18,decimal_places=3)
    adjustment_direction:Literal['INCREASE','DECREASE']|None=None
    reason:str=Field(min_length=3,max_length=240)
    reference:str|None=Field(default=None,max_length=96)


@router.post('/products/{product_id}/stock',status_code=201)
def product_stock_move(product_id:UUID,body:ProductStockMove,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """Stock of a school article: receipt (delivery) or counted correction, always traced. Same capabilities as the
    Intendance stock (inventory.stock.receive / inventory.stock.adjust); a sale is recorded by the cash desk only.
    Owner request 2026-11-06: a school without intendant must still be able to count its articles, so the administrator
    who manages the catalogue (settings.products.manage) may record them too — always traced and audited the same way."""
    stock_capability='inventory.stock.receive' if body.movement_type=='RECEIPT' else 'inventory.stock.adjust'
    if 'settings.products.manage' not in actor.permissions:_need(actor,stock_capability)
    if body.movement_type=='ADJUSTMENT' and body.adjustment_direction is None:
        raise HTTPException(status_code=422,detail='Précisez le sens de la correction de stock')
    delta=body.quantity if body.movement_type=='RECEIPT' or body.adjustment_direction=='INCREASE' else -body.quantity
    try:
        with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
            out=PostgresSettingsRepository(conn).move_product_stock(actor.school_id,product_id,movement_type=body.movement_type,delta=delta,
                reason=body.reason.strip(),reference=(body.reference or '').strip() or None,user_id=actor.user_id)
            PostgresAuditRepository(conn).append(AuditRecord(action='SCHOOL_PRODUCT_STOCK_MOVED',entity_type='SchoolProduct',entity_id=product_id,actor_user_id=actor.user_id,
                membership_id=actor.membership_id,school_id=actor.school_id,source=actor.source,old_data=None,
                new_data={'movement_type':body.movement_type,'delta':str(delta),'quantity':out['quantity'],'reason':body.reason.strip()},reason=body.reason.strip(),
                correlation_id=actor.correlation_id,idempotency_key=None))
            return _jsonable(out)
    except Exception as exc:_error(exc)

