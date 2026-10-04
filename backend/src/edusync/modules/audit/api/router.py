from __future__ import annotations
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy import text
from edusync.bootstrap.dependencies import get_services,require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.shared.application.context import ActorContext

router=APIRouter(tags=['Audit transversal'])
def need(a:ActorContext,c:str):
    try:a.require(c)
    except PermissionError as e:raise HTTPException(403,str(e)) from e

@router.get('/events')
def events(action:str|None=None,entity_type:str|None=None,actor_user_id:UUID|None=None,date_from:datetime|None=None,date_to:datetime|None=None,limit:int=Query(100,ge=1,le=500),cursor_at:datetime|None=None,cursor_id:UUID|None=None,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """Journal append-only paginé par keyset (occurred_at,id), stable à grande profondeur."""
    need(actor,'audit.school.read')
    if any(x is not None for x in (action,entity_type,actor_user_id,date_from,date_to)): need(actor,'audit.school.filter')
    if (cursor_at is None) != (cursor_id is None): raise HTTPException(422,'Le curseur doit contenir cursor_at et cursor_id')
    where=['school_id=:sid'];p={'sid':str(actor.school_id),'lim':limit+1}
    if action:where.append('action=:action');p['action']=action
    if entity_type:where.append('entity_type=:et');p['et']=entity_type
    if actor_user_id:where.append('actor_user_id=:uid');p['uid']=str(actor_user_id)
    if date_from:where.append('occurred_at>=:df');p['df']=date_from
    if date_to:where.append('occurred_at<=:dt');p['dt']=date_to
    if cursor_at is not None:
        where.append('(occurred_at,id) < (:cursor_at,:cursor_id)');p['cursor_at']=cursor_at;p['cursor_id']=str(cursor_id)
    sql='SELECT id,occurred_at,actor_user_id,membership_id,action,entity_type,entity_id,source,result,reason,correlation_id FROM audit_events WHERE '+' AND '.join(where)+' ORDER BY occurred_at DESC,id DESC LIMIT :lim'
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
        rows=c.execute(text(sql),p).all();has_more=len(rows)>limit;rows=rows[:limit];items=[dict(r._mapping) for r in rows]
        last=items[-1] if has_more and items else None
        return {'items':items,'limit':limit,'has_more':has_more,'next_cursor':({'occurred_at':last['occurred_at'],'id':last['id']} if last else None)}

@router.get('/entities/{entity_type}/{entity_id}')
def entity_history(entity_type:str,entity_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'audit.entity.history.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
        rows=c.execute(text('SELECT id,occurred_at,actor_user_id,action,source,result,old_json,new_json,reason,correlation_id FROM audit_events WHERE school_id=:sid AND entity_type=:et AND entity_id=:eid ORDER BY occurred_at DESC LIMIT 300'),{'sid':str(actor.school_id),'et':entity_type,'eid':str(entity_id)}).all()
        return {'items':[dict(r._mapping) for r in rows]}
