from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from edusync.adapters.postgres_effectifs import PostgresEffectifsRepository
from edusync.adapters.postgres_idempotency import PostgresIdempotencyRepository
from edusync.adapters.postgres_repositories import PostgresAuditRepository, PostgresOutboxRepository
from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.modules.audit.domain.audit import AuditRecord
from edusync.modules.effectifs.application.documents import deposits_xlsx, headcounts_pdf, headcounts_xlsx
from edusync.modules.effectifs.domain.models import HeadcountScope, total_headcount
from edusync.modules.sync.domain.outbox import OutboxMessage
from edusync.shared.application.context import ActorContext
from edusync.shared.application.idempotency import IdempotentExecutor

router=APIRouter(tags=["Effectifs & dépôts"])


def _need(actor:ActorContext,cap:str):
    try:actor.require(cap)
    except PermissionError as exc:raise HTTPException(status_code=403,detail=str(exc)) from exc

def _scopes(actor:ActorContext,cap:str):
    scopes=actor.scopes_for(cap)
    return scopes if scopes else (() if cap in actor.permissions else ())

def _key(v:str|None):
    k=(v or "").strip()
    if not k:raise HTTPException(status_code=400,detail="Idempotency-Key obligatoire")
    if len(k)>180:raise HTTPException(status_code=400,detail="Idempotency-Key trop longue")
    return k

def _json(v:Any)->Any:
    if isinstance(v,(UUID,date,datetime,Decimal)):return str(v)
    if isinstance(v,dict):return {str(k):_json(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [_json(x) for x in v]
    if hasattr(v,"value"):return str(v.value)
    return v

def _year(repo:PostgresEffectifsRepository,school_id:UUID,year_id:UUID|None):
    y=repo.year(school_id,year_id)
    if not y:raise HTTPException(status_code=409,detail="Aucune année scolaire disponible pour cette consultation")
    return y

def _scope_label(scope:HeadcountScope)->str:
    return {HeadcountScope.ALL:"Toute l'école",HeadcountScope.MATERNELLE:"Maternelle",HeadcountScope.PRIMAIRE:"Primaire",HeadcountScope.SECONDAIRE:"Secondaire"}[scope]

def _group_meta(group_by:str):
    return {
      "class":("headcounts.by_class.read","EFFECTIFS PAR CLASSE","Par classe"),
      "section":("headcounts.by_section.read","EFFECTIFS PAR SECTION","Par section"),
      "option":("headcounts.by_option.read","EFFECTIFS PAR FILIÈRE / OPTION","Par filière-option"),
    }[group_by]


@router.get("/overview")
def overview(year_id:UUID|None=None,scope:HeadcountScope=HeadcountScope.ALL,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,"headcounts.read");scopes=_scopes(actor,"headcounts.read")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresEffectifsRepository(conn);y=_year(repo,actor.school_id,year_id)
        return {**_json(repo.overview(actor.school_id,y["id"],scopes=scopes,scope=scope.value)),"academic_year":_json(y),"scope":scope.value}

@router.get("/counts")
def counts(group_by:Literal["class","section","option"]="class",year_id:UUID|None=None,scope:HeadcountScope=HeadcountScope.ALL,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    cap,_,_=_group_meta(group_by);_need(actor,cap);scopes=_scopes(actor,cap)
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresEffectifsRepository(conn);y=_year(repo,actor.school_id,year_id);rows=repo.counts(actor.school_id,y["id"],scopes=scopes,scope=scope.value,group_by=group_by);total=total_headcount(rows)
        return {"items":_json(rows),"total":_json(total),"academic_year":_json(y),"scope":scope.value,"group_by":group_by}

@router.get("/classes")
def classes(year_id:UUID|None=None,scope:HeadcountScope=HeadcountScope.ALL,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,"headcounts.read");scopes=_scopes(actor,"headcounts.read")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresEffectifsRepository(conn);y=_year(repo,actor.school_id,year_id);return _json(repo.classes(actor.school_id,y["id"],scopes=scopes,scope=scope.value))

@router.get("/movements")
def movements(year_id:UUID|None=None,scope:HeadcountScope=HeadcountScope.ALL,class_id:UUID|None=None,event_type:Literal["ABANDON","TRANSFER","SUSPEND","REINTEGRATE","CLASS_CHANGE"]|None=None,q:str|None=None,limit:int=Query(50,ge=1,le=250),offset:int=Query(0,ge=0),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,"headcounts.movements.read");scopes=_scopes(actor,"headcounts.movements.read")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresEffectifsRepository(conn);y=_year(repo,actor.school_id,year_id);return _json(repo.movements(actor.school_id,y["id"],scopes=scopes,scope=scope.value,class_id=class_id,event_type=event_type,q=q,limit=limit,offset=offset))

@router.get("/contribution-types")
def contribution_types(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,"contributions.read")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return _json(PostgresEffectifsRepository(conn).contribution_types(actor.school_id))

@router.get("/deposits")
def deposit_register(year_id:UUID|None=None,scope:HeadcountScope=HeadcountScope.ALL,class_id:UUID|None=None,contribution_type_id:UUID|None=None,q:str|None=None,limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,"contributions.register.read");scopes=_scopes(actor,"contributions.register.read")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresEffectifsRepository(conn);y=_year(repo,actor.school_id,year_id);return _json(repo.deposits(actor.school_id,y["id"],scopes=scopes,scope=scope.value,class_id=class_id,contribution_type_id=contribution_type_id,q=q,limit=limit,offset=offset))

class DepositBody(BaseModel):
    enrollment_id:UUID
    contribution_type_id:UUID
    quantity:Decimal=Field(gt=0,max_digits=14,decimal_places=3)
    deposited_on:date=Field(default_factory=date.today)
    notes:str|None=Field(default=None,max_length=700)
    client_operation_id:UUID|None=None
    scope:HeadcountScope=HeadcountScope.ALL

@router.post("/deposits",status_code=201)
def record_deposit(body:DepositBody,idempotency_key:str|None=Header(default=None,alias="Idempotency-Key"),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,"contributions.record");scopes=_scopes(actor,"contributions.record");key=_key(idempotency_key);request_actor=replace(actor,correlation_id=uuid4(),idempotency_key=key)
    payload=body.model_dump(mode="json")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        def action():
            repo=PostgresEffectifsRepository(conn);enrollment=repo.enrollment_in_scope(actor.school_id,body.enrollment_id,scopes=scopes,scope=body.scope.value)
            if not enrollment:raise LookupError("Inscription introuvable dans votre périmètre")
            if enrollment["academic_year_status"]!="ACTIVE":raise ValueError("Les dépôts matériels sont enregistrables uniquement dans l'année ACTIVE")
            created=repo.record_deposit(actor.school_id,student_id=enrollment["student_id"],enrollment_id=body.enrollment_id,academic_year_id=enrollment["academic_year_id"],contribution_type_id=body.contribution_type_id,quantity=body.quantity,deposited_on=body.deposited_on,notes=body.notes,recorded_by=actor.user_id,client_operation_id=body.client_operation_id)
            PostgresAuditRepository(conn).append(AuditRecord(action="contribution.recorded",entity_type="material_contribution",entity_id=created["id"],actor_user_id=actor.user_id,membership_id=actor.membership_id,school_id=actor.school_id,source=actor.source,new_data=_json(created),reason=body.notes,correlation_id=request_actor.correlation_id,idempotency_key=key))
            PostgresOutboxRepository(conn).add(OutboxMessage(event_type="contribution.recorded",aggregate_type="material_contribution",aggregate_id=created["id"],school_id=actor.school_id,payload=_json(created),correlation_id=request_actor.correlation_id,deduplication_key=f"{key}:contribution.recorded"))
            return 201,_json(created)
        try:
            result=IdempotentExecutor(PostgresIdempotencyRepository(conn)).execute(scope_key=str(actor.school_id),idempotency_key=key,operation="effectifs.deposit.record",payload=payload,school_id=str(actor.school_id),actor_user_id=str(actor.user_id),action=action)
            return result.body
        except LookupError as exc:raise HTTPException(status_code=404,detail=str(exc)) from exc
        except (ValueError,PermissionError) as exc:raise HTTPException(status_code=409 if isinstance(exc,ValueError) else 403,detail=str(exc)) from exc


def _export_counts(group_by:str,scope:HeadcountScope,year_id:UUID|None,actor:ActorContext,services:AppServices,*,xlsx:bool,print_mode:bool=False):
    cap="headcounts.print" if print_mode else ("headcounts.export_xlsx" if xlsx else "headcounts.export_pdf")
    group_cap,title,sheet=_group_meta(group_by)
    _need(actor,cap);_need(actor,group_cap)
    # Data scope is anchored to the read capability; an export permission can never widen it.
    scopes=_scopes(actor,group_cap)
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresEffectifsRepository(conn);y=_year(repo,actor.school_id,year_id);rows=repo.counts(actor.school_id,y["id"],scopes=scopes,scope=scope.value,group_by=group_by);school=repo.school_identity(actor.school_id)
        data=headcounts_xlsx(school=school,rows=rows,title=title,scope_label=_scope_label(scope),year_label=y["label"],sheet_name=sheet) if xlsx else headcounts_pdf(school=school,rows=rows,title=title,scope_label=_scope_label(scope),year_label=y["label"])
        archive_generated(conn,actor,data=data,fmt="XLSX" if xlsx else "PDF",required_capability=group_cap,document_code=f"headcounts.{group_by}",title=title,file_name=f"effectifs_{group_by}.{'xlsx' if xlsx else 'pdf'}",academic_year_id=y["id"],filters={"scope":scope.value})
    media="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if xlsx else "application/pdf";ext="xlsx" if xlsx else "pdf";disp="attachment" if xlsx else "inline"
    return StreamingResponse(BytesIO(data),media_type=media,headers={"Content-Disposition":f'{disp}; filename="effectifs_{group_by}.{ext}"'})

from edusync.modules.documents.application.object_store import archive_generated
@router.get("/exports/counts.pdf")
def export_counts_pdf(group_by:Literal["class","section","option"]="class",year_id:UUID|None=None,scope:HeadcountScope=HeadcountScope.ALL,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):return _export_counts(group_by,scope,year_id,actor,services,xlsx=False)
@router.get("/exports/counts.xlsx")
def export_counts_xlsx(group_by:Literal["class","section","option"]="class",year_id:UUID|None=None,scope:HeadcountScope=HeadcountScope.ALL,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):return _export_counts(group_by,scope,year_id,actor,services,xlsx=True)
@router.get("/print/counts.pdf")
def print_counts_pdf(group_by:Literal["class","section","option"]="class",year_id:UUID|None=None,scope:HeadcountScope=HeadcountScope.ALL,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):return _export_counts(group_by,scope,year_id,actor,services,xlsx=False,print_mode=True)

@router.get("/exports/deposits.xlsx")
def export_deposits(year_id:UUID|None=None,scope:HeadcountScope=HeadcountScope.ALL,class_id:UUID|None=None,contribution_type_id:UUID|None=None,q:str|None=None,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,"contributions.register.export_xlsx");_need(actor,"contributions.register.read");scopes=_scopes(actor,"contributions.register.read")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresEffectifsRepository(conn);y=_year(repo,actor.school_id,year_id);rows=repo.deposits(actor.school_id,y["id"],scopes=scopes,scope=scope.value,class_id=class_id,contribution_type_id=contribution_type_id,q=q,limit=5000,offset=0)["items"]
        data=deposits_xlsx(school=repo.school_identity(actor.school_id),rows=rows,scope_label=_scope_label(scope),year_label=y["label"])
        archive_generated(conn,actor,data=data,fmt="XLSX",required_capability="contributions.register.read",document_code="contributions.register",title="Registre des dépôts matériels",file_name="registre_depots_materiels.xlsx",academic_year_id=y["id"],filters={"scope":scope.value})
    return StreamingResponse(BytesIO(data),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":'attachment; filename="registre_depots_materiels.xlsx"'})


# ---------------------------------------------------------------- N3-H / G-EFF-1 — Desktop contribution_register
from edusync.adapters.postgres_schooling_parity import PostgresSchoolingParityRepository as _Parity
@router.get("/contribution-register")
def contribution_register(year_id:UUID|None=None,class_id:UUID|None=None,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """Required / delivered / remaining per pupil and item (a contribution in kind is never turned into a payment)."""
    _need(actor,"contributions.register.read")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        import json as _j
        return _j.loads(_j.dumps(_Parity(conn).contribution_register(actor.school_id,year_id=year_id,class_id=class_id),default=str))
