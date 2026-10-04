"""Real PostgreSQL worker claims; Redis only on a unique test queue. No SMS."""
import json
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine,text
import redis
from edusync.bootstrap.settings import Settings
from edusync.modules.communications import worker as comm
from edusync.modules.communications.providers import DeliveryResult

root=Path(__file__).resolve().parents[2]
cfg=Settings();assert ':55432/edusync_certification' in cfg.owner_database_url
f=json.loads((root/'.local/http-fixtures.json').read_text(encoding='utf-8'))['A']
engine=create_engine(cfg.owner_database_url)
mid,did=uuid4(),uuid4();results=[]
def check(name,ok):
 results.append({'check':name,'pass':bool(ok)});print(('PASS ' if ok else 'FAIL ')+name,flush=True)
try:
 with engine.begin() as c:
  c.execute(text("INSERT INTO communication_messages(id,school_id,kind,audience_type,body) VALUES(:id,:s,'CERTIFICATION','TEST','Test local sans envoi')"),{'id':mid,'s':f['school_id']})
  c.execute(text("INSERT INTO communication_deliveries(id,school_id,message_id,channel,destination) VALUES(:id,:s,:m,'SMS','TEST-NO-SEND')"),{'id':did,'s':f['school_id'],'m':mid})
 first=comm._claim(engine,did);check('claim obtained',first is not None)
 check('active lease prevents second claim',comm._claim(engine,did) is None)
 with engine.begin() as c:c.execute(text("UPDATE communication_deliveries SET locked_until=now()-interval '1 second' WHERE id=:id"),{'id':did})
 # A separate engine represents a restarted process and uses the durable lease.
 restarted=create_engine(cfg.owner_database_url)
 second=comm._claim(restarted,did);check('expired lease recovered after restart',second is not None and second[1]!=first[1])
 comm._finish(engine,*first,DeliveryResult(True,'stale-test'))
 with engine.begin() as c:check('stale worker cannot acknowledge new lease',c.execute(text('SELECT status FROM communication_deliveries WHERE id=:id'),{'id':did}).scalar_one()=='QUEUED')
 comm._finish(restarted,*second,DeliveryResult(False,error_code='CERTIFICATION_FAILURE'))
 check('retry waits for backoff',comm._claim(engine,did) is None)
 for attempt in range(2,6):
  with engine.begin() as c:c.execute(text("UPDATE communication_deliveries SET next_attempt_at=now()-interval '1 second' WHERE id=:id"),{'id':did})
  claimed=comm._claim(engine,did);assert claimed is not None
  comm._finish(engine,*claimed,DeliveryResult(False,error_code='CERTIFICATION_FAILURE'))
 with engine.begin() as c:
  row=c.execute(text('SELECT status,attempts FROM communication_deliveries WHERE id=:id'),{'id':did}).one()
 check('fifth failure is terminal',row.status=='FAILED' and row.attempts==5)
 check('terminal failure is not reclaimed',comm._claim(engine,did) is None)
finally:
 with engine.begin() as c:
  c.execute(text('DELETE FROM communication_deliveries WHERE id=:id'),{'id':did})
  c.execute(text('DELETE FROM communication_messages WHERE id=:id'),{'id':mid})
 (root/'certification/point17-20260916/workers.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
assert all(x['pass'] for x in results)
