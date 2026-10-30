from __future__ import annotations
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy import text
from edusync.bootstrap.dependencies import get_services,require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.shared.application.context import ActorContext

router=APIRouter(tags=['Audit transversal'])


def _actor_names(services:AppServices,school_id,items:list[dict])->list[dict]:
    """WHO acted (journal screen, 2026-10-28). The tenant role reads only its own users row (RLS users_tenant_self), so names
    come from the platform connection — strictly for members of THIS school and only the ids on the page."""
    ids=sorted({str(i['actor_user_id']) for i in items if i.get('actor_user_id')})
    names={}
    if ids:
        with services.platform_db.platform_transaction() as pc:
            names={str(r[0]):r[1] for r in pc.execute(text("""SELECT DISTINCT u.id,u.full_name FROM users u JOIN school_memberships m ON m.user_id=u.id
                WHERE m.school_id=:sid AND u.id = ANY(CAST(:ids AS uuid[]))"""),{'sid':str(school_id),'ids':ids}).all()}
    return [{**i,'actor_name':names.get(str(i.get('actor_user_id')))} for i in items]
def need(a:ActorContext,c:str):
    try:a.require(c)
    except PermissionError as e:raise HTTPException(403,str(e)) from e

@router.get('/events')
def events(action:str|None=None,entity_type:str|None=None,entity_types:list[str]|None=Query(None,max_length=40),actor_user_id:UUID|None=None,date_from:datetime|None=None,date_to:datetime|None=None,limit:int=Query(100,ge=1,le=500),cursor_at:datetime|None=None,cursor_id:UUID|None=None,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    """Journal append-only paginé par keyset (occurred_at,id), stable à grande profondeur."""
    need(actor,'audit.school.read')
    if any(x is not None for x in (action,entity_type,entity_types,actor_user_id,date_from,date_to)): need(actor,'audit.school.filter')
    if (cursor_at is None) != (cursor_id is None): raise HTTPException(422,'Le curseur doit contenir cursor_at et cursor_id')
    where=['e.school_id=:sid'];p={'sid':str(actor.school_id),'lim':limit+1}
    if action:where.append('e.action=:action');p['action']=action
    if entity_type:where.append('e.entity_type=:et');p['et']=entity_type
    # a domain of the journal screen (finances, schooling…) is several entity types at once
    if entity_types:where.append('e.entity_type = ANY(:ets)');p['ets']=list(entity_types)
    if actor_user_id:where.append('e.actor_user_id=:uid');p['uid']=str(actor_user_id)
    if date_from:where.append('e.occurred_at>=:df');p['df']=date_from
    if date_to:where.append('e.occurred_at<=:dt');p['dt']=date_to
    if cursor_at is not None:
        where.append('(e.occurred_at,e.id) < (:cursor_at,:cursor_id)');p['cursor_at']=cursor_at;p['cursor_id']=str(cursor_id)
    # actor_name (2026-10-28): the school journal screen shows WHO acted, not a bare identifier.
    sql='SELECT e.id,e.occurred_at,e.actor_user_id,e.membership_id,e.action,e.entity_type,e.entity_id,e.source,e.result,e.reason,e.correlation_id FROM audit_events e WHERE '+' AND '.join(where)+' ORDER BY e.occurred_at DESC,e.id DESC LIMIT :lim'
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
        rows=c.execute(text(sql),p).all();has_more=len(rows)>limit;rows=rows[:limit];items=[dict(r._mapping) for r in rows]
    items=_actor_names(services,actor.school_id,items)
    last=items[-1] if has_more and items else None
    return {'items':items,'limit':limit,'has_more':has_more,'next_cursor':({'occurred_at':last['occurred_at'],'id':last['id']} if last else None)}

@router.get('/entities/{entity_type}/{entity_id}')
def entity_history(entity_type:str,entity_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'audit.entity.history.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
        rows=c.execute(text('SELECT e.id,e.occurred_at,e.actor_user_id,e.action,e.source,e.result,e.old_json,e.new_json,e.reason,e.correlation_id FROM audit_events e WHERE e.school_id=:sid AND e.entity_type=:et AND e.entity_id=:eid ORDER BY e.occurred_at DESC LIMIT 300'),{'sid':str(actor.school_id),'et':entity_type,'eid':str(entity_id)}).all()
    return {'items':_actor_names(services,actor.school_id,[dict(r._mapping) for r in rows])}
