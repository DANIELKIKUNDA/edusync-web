from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy import text
from edusync.bootstrap.dependencies import require_school_actor,get_services
from edusync.bootstrap.services import AppServices
from edusync.shared.application.context import ActorContext
from edusync.modules.communications.domain.models import sms_segments
router=APIRouter(tags=['communications'])
def need(a,p):
 try:a.require(p)
 except PermissionError as e:raise HTTPException(403,str(e)) from e
class Draft(BaseModel):
 kind:str='COMMUNIQUE';audience_type:str;audience_ref:UUID|None=None;subject:str|None=None;body:str=Field(min_length=1,max_length=4000);channel:str='IN_APP';idempotency_key:str=Field(min_length=8,max_length=180)
@router.get('/readiness')
def readiness(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'communications.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  r=c.execute(text('SELECT * FROM communication_settings WHERE school_id=:sid'),{'sid':str(actor.school_id)}).mappings().first()
  if not r:return {'enabled':False,'in_app_enabled':True,'sms_enabled':False,'provider_configured':False,'sender_configured':False,'external_ready':False}
  d=dict(r);d['provider_configured']=bool(d.get('provider_code'));d['sender_configured']=bool(d.get('sender_id'));d['external_ready']=bool(d['enabled'] and d['sms_enabled'] and d['provider_configured'] and d['sender_configured']);return d
@router.get('/history')
def history(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'communications.history.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  rows=c.execute(text('''SELECT m.id,m.kind,m.subject,m.body,m.audience_type,m.created_at,d.channel,d.destination,d.status,d.attempts,d.estimated_segments,d.sent_at,d.delivered_at FROM communication_messages m LEFT JOIN communication_deliveries d ON d.message_id=m.id WHERE m.school_id=:sid ORDER BY m.created_at DESC LIMIT 200'''),{'sid':str(actor.school_id)}).mappings().all();return [dict(x) for x in rows]
@router.post('/send')
def send(b:Draft,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'communications.compose'); channel=b.channel.upper()
 cap={'INDIVIDUAL':'communications.send.individual','CLASS':'communications.send.class','SECTION':'communications.send.section','SCHOOL':'communications.send.all_parents'}.get(b.audience_type.upper())
 if cap:need(actor,cap)
 if channel=='SMS': need(actor,'communications.sms.send' if b.audience_type.upper()=='INDIVIDUAL' else 'communications.sms.bulk_send')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  cfg=c.execute(text('SELECT * FROM communication_settings WHERE school_id=:sid'),{'sid':str(actor.school_id)}).mappings().first()
  if channel!='IN_APP' and (not cfg or not cfg['enabled'] or not cfg.get(channel.lower()+'_enabled',False)): raise HTTPException(409,'Canal externe non activé pour cette école')
  if channel=='SMS' and (not cfg.get('provider_code') or not cfg.get('sender_id')): raise HTTPException(409,'Fournisseur SMS ou expéditeur non configuré')
  row=c.execute(text('''INSERT INTO communication_messages(school_id,kind,audience_type,audience_ref,subject,body,created_by,idempotency_key) VALUES(:sid,:kind,:aud,:ref,:sub,:body,:uid,:key) ON CONFLICT(school_id,idempotency_key) DO UPDATE SET idempotency_key=EXCLUDED.idempotency_key RETURNING id'''),{'sid':str(actor.school_id),'kind':b.kind,'aud':b.audience_type.upper(),'ref':str(b.audience_ref) if b.audience_ref else None,'sub':b.subject,'body':b.body,'uid':str(actor.user_id),'key':b.idempotency_key}).first();mid=row[0]
  # Recipient expansion is deliberately server-side and scope-aware; unresolved destinations stay pending, never falsely SENT.
  c.execute(text('''INSERT INTO outbox_events(school_id,event_type,aggregate_type,aggregate_id,payload) VALUES(:sid,'COMMUNICATION_REQUESTED','communication_message',:mid,jsonb_build_object('message_id',:mid,'channel',:ch))'''),{'sid':str(actor.school_id),'mid':str(mid),'ch':channel})
  return {'id':str(mid),'status':'QUEUED','channel':channel,'estimated_segments':sms_segments(b.body) if channel=='SMS' else None}


# --- Templates and delivery retry (local closure 2026-10) -----------------------------------------
from edusync.modules.communications.domain.models import TEMPLATE_VARIABLES,render_template,validate_template


class TemplateBody(BaseModel):
 code:str=Field(min_length=2,max_length=96,pattern=r'^[A-Z0-9_]+$');label:str=Field(min_length=2,max_length=180);channel:str=Field(default='SMS',pattern='^(SMS|IN_APP)$');body:str=Field(min_length=1,max_length=1000)


@router.get('/templates')
def list_templates(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'communications.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  rows=c.execute(text('SELECT id,code,label,channel,body,enabled,version,updated_at FROM communication_templates WHERE school_id=:sid ORDER BY label'),{'sid':str(actor.school_id)}).mappings().all()
 return {'items':[dict(r) for r in rows],'variables':sorted(TEMPLATE_VARIABLES)}


@router.post('/templates',status_code=201)
def save_template(b:TemplateBody,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'communications.templates.manage')
 try:validate_template(b.body)
 except ValueError as e:raise HTTPException(422,str(e)) from e
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  row=c.execute(text('''INSERT INTO communication_templates(school_id,code,label,channel,body) VALUES(:sid,:code,:label,:ch,:body)
   ON CONFLICT(school_id,code,channel) DO UPDATE SET label=EXCLUDED.label,body=EXCLUDED.body,updated_at=now(),version=communication_templates.version+1 RETURNING id,version'''),
   {'sid':str(actor.school_id),'code':b.code,'label':b.label,'ch':b.channel,'body':b.body}).mappings().one()
  c.execute(text('''INSERT INTO audit_events(school_id,actor_user_id,membership_id,action,entity_type,entity_id,source,new_json) VALUES(:sid,:uid,:mid,'COMMUNICATION_TEMPLATE_SAVED','CommunicationTemplate',:id,'WEB',jsonb_build_object('code',CAST(:code AS text),'version',CAST(:v AS int)))'''),
   {'sid':str(actor.school_id),'uid':str(actor.user_id),'mid':str(actor.membership_id),'id':str(row['id']),'code':b.code,'v':row['version']})
 return {'id':str(row['id']),'version':row['version']}


class PreviewBody(BaseModel):
 body:str=Field(min_length=1,max_length=1000);values:dict[str,str]=Field(default_factory=dict)


@router.post('/templates/preview')
def preview_template(b:PreviewBody,actor:ActorContext=Depends(require_school_actor)):
 need(actor,'communications.compose')
 try:text_=render_template(b.body,b.values)
 except ValueError as e:raise HTTPException(422,str(e)) from e
 return {'text':text_,'estimated_segments':sms_segments(text_)}


@router.post('/deliveries/{delivery_id}/retry')
def retry_delivery(delivery_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """Manual retry of a terminal failure. Idempotent: a delivery already queued/sent/delivered is left unchanged."""
 need(actor,'communications.delivery.retry')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  row=c.execute(text("""UPDATE communication_deliveries SET status='QUEUED',attempts=0,next_attempt_at=NULL,last_error_code=NULL,failed_at=NULL
   WHERE id=:id AND school_id=:sid AND status='FAILED' RETURNING id"""),{'id':str(delivery_id),'sid':str(actor.school_id)}).first()
  current=c.execute(text('SELECT status FROM communication_deliveries WHERE id=:id AND school_id=:sid'),{'id':str(delivery_id),'sid':str(actor.school_id)}).scalar_one_or_none()
  if current is None:raise HTTPException(404,'Envoi introuvable')
  if row:c.execute(text('''INSERT INTO audit_events(school_id,actor_user_id,membership_id,action,entity_type,entity_id,source) VALUES(:sid,:uid,:mid,'COMMUNICATION_DELIVERY_RETRIED','CommunicationDelivery',:id,'WEB')'''),
   {'sid':str(actor.school_id),'uid':str(actor.user_id),'mid':str(actor.membership_id),'id':str(delivery_id)})
 return {'status':current,'requeued':bool(row)}
