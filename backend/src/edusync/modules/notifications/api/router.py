from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy import text
from edusync.bootstrap.dependencies import get_services,require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.shared.application.context import ActorContext

router=APIRouter(tags=['Notifications internes'])
def need(a,c):
    try:a.require(c)
    except PermissionError as e:raise HTTPException(403,str(e)) from e

@router.get('')
def list_notifications(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'notifications.internal.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
        rows=c.execute(text('SELECT id,category,title,body,created_at,read_at FROM notifications WHERE school_id=:sid AND user_id=:uid ORDER BY created_at DESC LIMIT 100'),{'sid':str(actor.school_id),'uid':str(actor.user_id)}).all()
        return {'items':[dict(r._mapping) for r in rows]}

@router.post('/{notification_id}/dismiss')
def dismiss(notification_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'notifications.internal.dismiss')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
        row=c.execute(text('UPDATE notifications SET read_at=coalesce(read_at,now()) WHERE id=:id AND school_id=:sid AND user_id=:uid RETURNING id,read_at'),{'id':str(notification_id),'sid':str(actor.school_id),'uid':str(actor.user_id)}).first()
        if row is None:raise HTTPException(404,'Notification introuvable')
        return dict(row._mapping)

class CreateNotification(BaseModel):
    user_id:UUID;title:str=Field(min_length=2,max_length=180);body:str=Field(min_length=2,max_length=2000);category:str=Field('GENERAL',min_length=2,max_length=64)
@router.post('',status_code=201)
def create_notification(b:CreateNotification,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'notifications.internal.create')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
        member=c.execute(text('SELECT 1 FROM school_memberships WHERE school_id=:sid AND user_id=:uid AND active=true'),{'sid':str(actor.school_id),'uid':str(b.user_id)}).first()
        if member is None:raise HTTPException(409,"Le destinataire n'est pas un membre actif de cette école")
        row=c.execute(text('INSERT INTO notifications(school_id,user_id,category,title,body) VALUES(:sid,:uid,:cat,:title,:body) RETURNING id,created_at'),{'sid':str(actor.school_id),'uid':str(b.user_id),'cat':b.category,'title':b.title,'body':b.body}).first()
        return dict(row._mapping)
