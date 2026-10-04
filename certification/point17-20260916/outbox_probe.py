"""Outbox retry and publication against isolated PostgreSQL and real WSL Redis."""
import json
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine,text
import redis
from edusync.bootstrap.settings import Settings
from edusync.modules.sync import outbox_worker as worker

root=Path(__file__).resolve().parents[2];cfg=Settings()
assert ':55432/edusync_certification' in cfg.owner_database_url
engine=create_engine(cfg.owner_database_url)
r=redis.Redis.from_url(cfg.redis_url,decode_responses=True,socket_connect_timeout=3,socket_timeout=3)
assert r.ping()
eid=uuid4();worker.QUEUE='edusync:certification:'+str(eid);results=[]
def check(name,ok):
 results.append({'check':name,'pass':bool(ok)});print(('PASS ' if ok else 'FAIL ')+name,flush=True)
class Unavailable:
 def lpush(self,*args):raise redis.ConnectionError('Injected outage in isolated probe')
try:
 with engine.begin() as c:c.execute(text("INSERT INTO outbox_events(id,event_type,aggregate_type,aggregate_id,payload,created_at) VALUES(:id,'CERTIFICATION_PROBE','Certification',:id,'{}','1970-01-01')"),{'id':eid})
 first=worker.claim_one(engine);assert first and first[0]['id']==eid
 check('Redis failure is reported',worker.publish_claim(engine,Unavailable(),*first) is False)
 with engine.begin() as c:
  row=c.execute(text('SELECT published_at,attempts,next_attempt_at>now() waiting FROM outbox_events WHERE id=:id'),{'id':eid}).one()
  check('outage keeps durable event with backoff',row.published_at is None and row.attempts==1 and row.waiting)
  c.execute(text("UPDATE outbox_events SET next_attempt_at=now()-interval '1 second' WHERE id=:id"),{'id':eid})
 restarted=create_engine(cfg.owner_database_url)
 second=worker.claim_one(restarted);assert second and second[0]['id']==eid
 check('publication to real Redis succeeds after restart',worker.publish_claim(restarted,r,*second))
 envelope=json.loads(r.rpop(worker.QUEUE))
 check('immutable event id transported',envelope['event_id']==str(eid))
 with engine.begin() as c:
  row=c.execute(text('SELECT published_at,attempts,processing_token FROM outbox_events WHERE id=:id'),{'id':eid}).one()
  check('durable acknowledgement follows Redis acceptance',row.published_at is not None and row.attempts==2 and row.processing_token is None)
finally:
 r.delete(worker.QUEUE)
 with engine.begin() as c:c.execute(text('DELETE FROM outbox_events WHERE id=:id'),{'id':eid})
 (root/'certification/point17-20260916/outbox.json').write_text(json.dumps({'results':results,'limitation':'At-least-once publisher; consumer deduplication and provider exactly-once are not certified.'},indent=2),encoding='utf-8')
assert all(x['pass'] for x in results)
