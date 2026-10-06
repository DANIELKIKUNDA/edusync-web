"""Durable communications worker. PostgreSQL remains source of truth; Redis is only a wake-up hint.
Provider failure never rolls back a business transaction. Due rows are recoverable from PostgreSQL
after Redis loss or process crash; claims use SKIP LOCKED + expiring leases.
"""
from __future__ import annotations
import json,logging,time
from uuid import uuid4
from sqlalchemy import create_engine,text
import redis
from edusync.bootstrap.settings import Settings
from edusync.modules.communications.providers import provider_for

QUEUE='edusync:communications';MAX_ATTEMPTS=5;LEASE_SECONDS=90;REPORT_BATCH=50
log=logging.getLogger('edusync.communications_worker')

def provider(cfg,code):
 return provider_for(cfg,code)

def reconcile_delivery_reports(cfg,engine,limit:int=REPORT_BATCH)->int:
 """SENT -> DELIVERED/FAILED only from a provider delivery report; nothing is assumed delivered.
 Provider calls happen outside any row lock; the update is conditional on the row still being SENT."""
 with engine.begin() as c:
  rows=c.execute(text("""SELECT d.id,d.provider_message_id,coalesce(d.provider_code,s.provider_code) provider_code FROM communication_deliveries d
   LEFT JOIN communication_settings s ON s.school_id=d.school_id
   WHERE d.status='SENT' AND d.provider_message_id IS NOT NULL ORDER BY d.sent_at NULLS FIRST,d.id LIMIT :n"""),{'n':limit}).mappings().all()
 changed=0
 for row in rows:
  p=provider(cfg,row['provider_code'])
  if p is None:continue
  try:report=p.delivery_report(row['provider_message_id'])
  except Exception:log.exception('delivery report failed');continue
  if report.status not in {'DELIVERED','FAILED'}:continue
  with engine.begin() as c:
   if report.status=='DELIVERED':
    n=c.execute(text("UPDATE communication_deliveries SET status='DELIVERED',delivered_at=now() WHERE id=:id AND status='SENT'"),{'id':row['id']}).rowcount
   else:
    n=c.execute(text("UPDATE communication_deliveries SET status='FAILED',failed_at=now(),last_error_code=:e WHERE id=:id AND status='SENT'"),{'id':row['id'],'e':report.error_code or 'UNDELIVERED'}).rowcount
  changed+=n
 return changed

def _claim(engine,delivery_id=None):
 token=str(uuid4())
 with engine.begin() as c:
  params={'token':token,'lease':LEASE_SECONDS,'max_attempts':MAX_ATTEMPTS}; extra=''
  if delivery_id:extra=' AND d.id=:did';params['did']=delivery_id
  row=c.execute(text(f"""SELECT d.id,d.school_id,d.destination,d.attempts,d.channel,m.body,
   s.provider_code,s.sender_id,s.enabled,s.sms_enabled FROM communication_deliveries d
   JOIN communication_messages m ON m.id=d.message_id LEFT JOIN communication_settings s ON s.school_id=d.school_id
   WHERE d.status IN ('PENDING','QUEUED','FAILED') AND d.attempts<:max_attempts AND (d.next_attempt_at IS NULL OR d.next_attempt_at<=now())
   AND (d.locked_until IS NULL OR d.locked_until<now()) {extra}
   ORDER BY d.created_at,d.id FOR UPDATE OF d SKIP LOCKED LIMIT 1"""),params).mappings().first()
  if not row:return None
  c.execute(text("UPDATE communication_deliveries SET processing_token=:token,locked_until=now()+(:lease||' seconds')::interval,status='QUEUED',queued_at=COALESCE(queued_at,now()) WHERE id=:id"),{'token':token,'lease':LEASE_SECONDS,'id':row['id']})
  return dict(row),token

def _error_code(result):
 if result is None:return 'PROVIDER_NOT_CONFIGURED'
 return result.error_code or ('NO_PROVIDER_PROOF' if result.accepted else 'PROVIDER_ERROR')

def _finish(engine,row,token,result):
 attempts=int(row['attempts'])+1
 with engine.begin() as c:
  # SENT only with provider proof (a message id); an 'accepted' without id is retried as a failure.
  if result and result.accepted and result.provider_message_id:
   c.execute(text("""UPDATE communication_deliveries SET status='SENT',attempts=:a,sent_at=now(),provider_message_id=:pm,
    last_error_code=NULL,last_error_detail=NULL,next_attempt_at=NULL,locked_until=NULL,processing_token=NULL
    WHERE id=:id AND processing_token=:t"""),{'a':attempts,'pm':result.provider_message_id,'id':row['id'],'t':token})
   c.execute(text("UPDATE communication_deliveries SET provider_code=coalesce(provider_code,:pc) WHERE id=:id"),{'pc':row.get('provider_code'),'id':row['id']})
  elif attempts<MAX_ATTEMPTS:
   delay=min(3600,30*(2**(attempts-1)))
   c.execute(text("""UPDATE communication_deliveries SET status='QUEUED',attempts=:a,next_attempt_at=now()+(:d||' seconds')::interval,
    last_error_code=:e,locked_until=NULL,processing_token=NULL WHERE id=:id AND processing_token=:t"""),
    {'a':attempts,'d':delay,'e':_error_code(result),'id':row['id'],'t':token})
  else:
   c.execute(text("""UPDATE communication_deliveries SET status='FAILED',attempts=:a,failed_at=now(),last_error_code=:e,
    locked_until=NULL,processing_token=NULL WHERE id=:id AND processing_token=:t"""),
    {'a':attempts,'e':_error_code(result),'id':row['id'],'t':token})

def run_once(cfg,r,engine):
 # Redis is a hint, never the durable scheduler. If the hint is lost, DB due-row polling recovers it.
 delivery_id=None
 try:
  job=r.brpop('edusync:communications',timeout=1)
  if job:
   try:delivery_id=json.loads(job[1]).get('delivery_id')
   except Exception:delivery_id=None
 except redis.RedisError:pass
 claimed=_claim(engine,delivery_id) or (_claim(engine) if delivery_id else None)
 if not claimed:return False
 row,token=claimed
 if not row.get('enabled') or row['channel']!='SMS' or not row.get('sms_enabled'):
  class Disabled:accepted=False;error_code='CHANNEL_DISABLED'
  _finish(engine,row,token,Disabled());return True
 p=provider(cfg,row.get('provider_code') or cfg.sms_provider)
 # External I/O happens outside the PostgreSQL transaction/row lock.
 result=p.send_sms(destination=row['destination'],body=row['body'],sender_id=row.get('sender_id')) if p else None
 _finish(engine,row,token,result);return True

def run():
 logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s')
 cfg=Settings();r=redis.Redis.from_url(cfg.redis_url,decode_responses=True,socket_connect_timeout=3,socket_timeout=3);engine=create_engine(cfg.owner_database_url,pool_pre_ping=True,pool_recycle=1800)
 last_reports=0.0
 while True:
  try:
   if time.monotonic()-last_reports>=30:
    reconcile_delivery_reports(cfg,engine);last_reports=time.monotonic()
   if not run_once(cfg,r,engine):time.sleep(.5)
  except Exception:
   log.exception('communications worker iteration failed')
   time.sleep(2)
if __name__=='__main__':run()
