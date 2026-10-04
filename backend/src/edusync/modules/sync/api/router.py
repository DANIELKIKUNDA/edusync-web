from __future__ import annotations
from datetime import datetime
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from uuid import UUID,uuid4
from sqlalchemy import text
from edusync.bootstrap.dependencies import get_services,require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.shared.application.context import ActorContext
from edusync.modules.sync.domain.contracts import FINANCE_OFFLINE_POLICY
from edusync.adapters.postgres_repositories import PostgresAuditRepository
from edusync.modules.audit.domain.audit import AuditRecord
router=APIRouter(tags=['Synchronisation'])
def need(a,c):
    try:a.require(c)
    except PermissionError as e:raise HTTPException(403,str(e)) from e
@router.get('/status')
def status(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'sync.status.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
        pending=c.execute(text('SELECT count(*) FROM outbox_events WHERE school_id=:sid AND published_at IS NULL'),{'sid':str(actor.school_id)}).scalar_one()
        devices=c.execute(text('SELECT count(*) FROM devices WHERE school_id=:sid AND revoked_at IS NULL'),{'sid':str(actor.school_id)}).scalar_one()
        return {'pending_outbox':int(pending),'active_devices':int(devices),'finance_offline_protocol':FINANCE_OFFLINE_POLICY['current_implemented_protocol'],'finance_offline_enabled_by_default':FINANCE_OFFLINE_POLICY['default_enabled']}

class DeviceInput(BaseModel): label:str=Field(min_length=2,max_length=160);platform:str=Field(default='WEB',max_length=40)
@router.get('/devices')
def devices(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'sync.status.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:return {'items':[dict(r._mapping) for r in c.execute(text("SELECT id,label,platform,last_seen_at,created_at,revoked_at FROM devices WHERE school_id=:sid ORDER BY created_at DESC"),{'sid':actor.school_id})]}
@router.post('/devices',status_code=201)
def register_device(b:DeviceInput,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'sync.device.register');did=uuid4()
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:c.execute(text("INSERT INTO devices(id,school_id,user_id,label,platform,last_seen_at) VALUES(:id,:sid,:uid,:l,:p,now())"),{'id':did,'sid':actor.school_id,'uid':actor.user_id,'l':b.label,'p':b.platform})
    return {'id':str(did),'status':'ACTIVE'}
@router.post('/devices/{device_id}/revoke',status_code=204)
def revoke_device(device_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'sync.device.revoke')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:c.execute(text("UPDATE devices SET revoked_at=coalesce(revoked_at,now()) WHERE id=:id AND school_id=:sid"),{'id':device_id,'sid':actor.school_id})
@router.get('/conflicts')
def conflicts(limit:int=Query(100,ge=1,le=300),cursor_at:datetime|None=None,cursor_id:UUID|None=None,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'sync.conflicts.read')
    if (cursor_at is None) != (cursor_id is None): raise HTTPException(422,'Le curseur doit être complet')
    params={'sid':actor.school_id,'lim':limit+1}
    sql="SELECT id,device_id,operation_type,aggregate_type,aggregate_id,status,received_at,processed_at FROM sync_inbox WHERE school_id=:sid AND status IN ('CONFLICT','REJECTED') ORDER BY received_at DESC,id DESC LIMIT :lim"
    if cursor_at is not None:
      sql="SELECT id,device_id,operation_type,aggregate_type,aggregate_id,status,received_at,processed_at FROM sync_inbox WHERE school_id=:sid AND status IN ('CONFLICT','REJECTED') AND (received_at,id) < (:ca,:cid) ORDER BY received_at DESC,id DESC LIMIT :lim";params.update(ca=cursor_at,cid=cursor_id)
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
      rows=c.execute(text(sql),params).all();more=len(rows)>limit;rows=rows[:limit];items=[dict(r._mapping) for r in rows];last=items[-1] if more and items else None
      return {'items':items,'limit':limit,'has_more':more,'next_cursor':({'received_at':last['received_at'],'id':last['id']} if last else None)}

@router.get('/outbox/pending')
def pending_outbox(limit:int=Query(100,ge=1,le=300),cursor_at:datetime|None=None,cursor_id:UUID|None=None,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'sync.status.read')
    if (cursor_at is None) != (cursor_id is None): raise HTTPException(422,'Le curseur doit être complet')
    params={'sid':actor.school_id,'lim':limit+1}
    sql='SELECT id,event_type,aggregate_type,aggregate_id,created_at,attempts FROM outbox_events WHERE school_id=:sid AND published_at IS NULL ORDER BY created_at DESC,id DESC LIMIT :lim'
    if cursor_at is not None:
      sql='SELECT id,event_type,aggregate_type,aggregate_id,created_at,attempts FROM outbox_events WHERE school_id=:sid AND published_at IS NULL AND (created_at,id) < (:ca,:cid) ORDER BY created_at DESC,id DESC LIMIT :lim';params.update(ca=cursor_at,cid=cursor_id)
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
      rows=c.execute(text(sql),params).all();more=len(rows)>limit;rows=rows[:limit];items=[dict(r._mapping) for r in rows];last=items[-1] if more and items else None
      return {'items':items,'limit':limit,'has_more':more,'next_cursor':({'created_at':last['created_at'],'id':last['id']} if last else None)}


class ConflictResolutionInput(BaseModel):
    decision:str=Field(pattern="^(RESOLVED|DISMISSED)$")
    note:str=Field(min_length=5,max_length=1000)

@router.get('/review-conflicts')
def review_conflicts(limit:int=Query(100,ge=1,le=300),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'sync.conflicts.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
        rows=c.execute(text("SELECT id,device_id,aggregate_type,aggregate_id,expected_version,actual_version,policy,status,created_at FROM sync_conflicts WHERE school_id=:sid AND status='OPEN' ORDER BY created_at DESC,id DESC LIMIT :lim"),{'sid':actor.school_id,'lim':limit}).all()
        return {'items':[dict(r._mapping) for r in rows]}

@router.post('/review-conflicts/{conflict_id}/resolve')
def resolve_conflict(conflict_id:UUID,b:ConflictResolutionInput,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'sync.conflicts.resolve')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
        row=c.execute(text("SELECT id,status,aggregate_type,aggregate_id FROM sync_conflicts WHERE id=:id AND school_id=:sid FOR UPDATE"),{'id':conflict_id,'sid':actor.school_id}).first()
        if not row: raise HTTPException(404,'Conflit introuvable')
        if row.status!='OPEN': raise HTTPException(409,'Ce conflit a déjà été arbitré')
        c.execute(text("UPDATE sync_conflicts SET status=:st,resolved_at=now(),resolved_by=:uid,resolution_note=:note WHERE id=:id AND school_id=:sid AND status='OPEN'"),{'st':b.decision,'uid':actor.user_id,'note':b.note,'id':conflict_id,'sid':actor.school_id})
        PostgresAuditRepository(c).append(AuditRecord(action='sync.conflict.resolved',entity_type='sync_conflict',entity_id=conflict_id,actor_user_id=actor.user_id,membership_id=actor.membership_id,school_id=actor.school_id,source=actor.source,new_data={'status':b.decision,'aggregate_type':row.aggregate_type,'aggregate_id':str(row.aggregate_id)},reason=b.note,correlation_id=actor.correlation_id))
        return {'id':str(conflict_id),'status':b.decision}
