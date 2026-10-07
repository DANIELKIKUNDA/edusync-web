"""Crash-safe transactional-outbox publisher.

PostgreSQL is the source of truth. Redis transports a wake-up/event envelope only.
An event is marked published *after* Redis accepts it. A crash between Redis LPUSH and
PostgreSQL acknowledgement can duplicate an envelope, therefore every consumer MUST
deduplicate by immutable outbox event id. Redis failure leaves the row due in PostgreSQL.
"""
from __future__ import annotations
import json, logging, time
from uuid import uuid4
from sqlalchemy import create_engine, text
import redis
from edusync.bootstrap.settings import Settings, worker_url

QUEUE='edusync:outbox'
MAX_ATTEMPTS=12
LEASE_SECONDS=60
# No consumer of this list exists in the codebase yet: envelopes are a transport hint, PostgreSQL keeps
# the truth. The list is capped so unconsumed envelopes can never exhaust Redis memory (noeviction).
MAX_QUEUE_LENGTH=100_000
log=logging.getLogger('edusync.outbox_worker')

def _backoff(attempt:int)->int:
    return min(3600, max(2, 2 ** min(attempt, 11)))

def claim_one(engine):
    token=str(uuid4())
    with engine.begin() as c:
        row=c.execute(text("""
          SELECT id,school_id,event_type,aggregate_type,aggregate_id,payload,correlation_id,causation_id,created_at,attempts
          FROM outbox_events
          WHERE published_at IS NULL AND dead_lettered_at IS NULL
            AND (next_attempt_at IS NULL OR next_attempt_at<=now())
            AND (locked_until IS NULL OR locked_until<now())
          ORDER BY created_at,id
          FOR UPDATE SKIP LOCKED LIMIT 1
        """)).mappings().first()
        if not row:return None
        c.execute(text("""UPDATE outbox_events SET processing_token=:t,locked_until=now()+(:lease||' seconds')::interval
                          WHERE id=:id"""),{'t':token,'lease':LEASE_SECONDS,'id':row['id']})
        return dict(row),token

def publish_claim(engine,r,row,token):
    envelope={k:(str(v) if k not in {'payload'} and v is not None else v) for k,v in row.items()}
    envelope['event_id']=str(row['id'])
    try:
        # Redis acceptance precedes DB acknowledgement. Consumers deduplicate event_id.
        pipe=r.pipeline(transaction=True)
        pipe.lpush(QUEUE,json.dumps(envelope,default=str,separators=(',',':')))
        pipe.ltrim(QUEUE,0,MAX_QUEUE_LENGTH-1)
        pipe.execute()
    except Exception as exc:
        log.warning('outbox publish failed event=%s error=%s',row['id'],type(exc).__name__)
        attempts=int(row['attempts'])+1; delay=_backoff(attempts)
        with engine.begin() as c:
            c.execute(text("""UPDATE outbox_events SET attempts=:a,next_attempt_at=now()+(:d||' seconds')::interval,
              locked_until=NULL,processing_token=NULL,last_error_code='REDIS_UNAVAILABLE',
              dead_lettered_at=CASE WHEN :a>=:max THEN now() ELSE dead_lettered_at END
              WHERE id=:id AND processing_token=:t"""),{'a':attempts,'d':delay,'max':MAX_ATTEMPTS,'id':row['id'],'t':token})
        return False
    with engine.begin() as c:
        c.execute(text("""UPDATE outbox_events SET published_at=now(),attempts=attempts+1,locked_until=NULL,
          processing_token=NULL,next_attempt_at=NULL,last_error_code=NULL
          WHERE id=:id AND processing_token=:t AND published_at IS NULL"""),{'id':row['id'],'t':token})
    return True

def run_once(cfg,r,engine):
    claimed=claim_one(engine)
    if not claimed:return False
    return publish_claim(engine,r,*claimed)

def run():
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s')
    cfg=Settings();engine=create_engine(worker_url(cfg),pool_pre_ping=True,pool_recycle=1800)
    r=redis.Redis.from_url(cfg.redis_url,decode_responses=True,socket_connect_timeout=3,socket_timeout=3)
    while True:
        try:
            if not run_once(cfg,r,engine):time.sleep(0.5)
        except Exception:
            log.exception('outbox worker iteration failed')
            time.sleep(2)
if __name__=='__main__':run()
