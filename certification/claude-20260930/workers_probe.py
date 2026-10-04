"""Live worker certification: real PostgreSQL + real Redis, the shipped worker functions run in-process.

Covers: outbox publication, Redis outage + retry, crash during lease + recovery, stale-token ack,
concurrent workers (exactly-once acknowledgement), dead-letter, bounded Redis queue,
communications worker success / retry / terminal failure / provider outage outside the DB transaction.
"""
import json
import os
import sys
import threading
from collections import Counter
from uuid import uuid4

import redis

sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa: E402,F403
from edusync.bootstrap.settings import Settings  # noqa: E402
from edusync.modules.sync import outbox_worker as ow  # noqa: E402
from edusync.modules.communications import worker as cw  # noqa: E402
from edusync.modules.communications.providers import DeliveryResult  # noqa: E402

cfg = Settings()
r = redis.Redis.from_url(cfg.redis_url, decode_responses=True, socket_timeout=3, socket_connect_timeout=3)
dead = redis.Redis(host="127.0.0.1", port=1, socket_timeout=0.3, socket_connect_timeout=0.3, decode_responses=True)
A = state["A"]


def outbox_rows(where="published_at IS NULL AND dead_lettered_at IS NULL"):
    return sql(f"SELECT id FROM outbox_events WHERE {where} ORDER BY created_at,id")


def envelopes():
    return Counter(json.loads(x)["event_id"] for x in r.lrange(ow.QUEUE, 0, -1))


r.delete(ow.QUEUE)
pending = outbox_rows()
check("business mutations produced outbox events (transactional outbox)", len(pending) > 0, f"pending={len(pending)}")

# 1. Redis outage: nothing lost, retry scheduled, no publication recorded
first = pending[0]["id"]
ok = ow.run_once(cfg, dead, owner)
row = sql("SELECT published_at,attempts,next_attempt_at>now() later,last_error_code,locked_until FROM outbox_events WHERE id=:i", {"i": first})[0]
check("Redis down: event stays due in PostgreSQL with backoff", ok is False and row["published_at"] is None and row["attempts"] == 1 and row["later"] and row["last_error_code"] == "REDIS_UNAVAILABLE" and row["locked_until"] is None, str(dict(row)))

# 2. crash after claim (worker killed before publish): lease blocks others, then expires and is recovered
sql("UPDATE outbox_events SET next_attempt_at=NULL WHERE id=:i", {"i": first})
claimed = ow.claim_one(owner)
crashed_id, crashed_token = claimed[0]["id"], claimed[1]
other = ow.claim_one(owner)
check("leased event not handed to a second worker", other is None or other[0]["id"] != crashed_id)
if other:  # release the second claim cleanly
    ow.publish_claim(owner, r, *other)
sql("UPDATE outbox_events SET locked_until=now()-interval '1 second' WHERE id=:i", {"i": crashed_id})  # lease expiry
recovered = ow.claim_one(owner)
check("expired lease is reclaimed by another worker", recovered is not None and recovered[0]["id"] == crashed_id)
ow.publish_claim(owner, r, *recovered)
late = ow.publish_claim(owner, r, claimed[0], crashed_token)  # the crashed worker wakes up late
pub = sql("SELECT published_at IS NOT NULL p, processing_token FROM outbox_events WHERE id=:i", {"i": crashed_id})[0]
check("late ack from the crashed worker does not corrupt the row", pub["p"] and pub["processing_token"] is None)
check("duplicate envelope carries the same immutable event_id (consumer dedupe key)", envelopes()[str(crashed_id)] == 2, str(envelopes()[str(crashed_id)]))

# 3. concurrent workers drain everything, each event acknowledged exactly once
for i in range(60):
    sql("INSERT INTO outbox_events(school_id,event_type,aggregate_type,aggregate_id,payload,deduplication_key) VALUES(:s,'CERT_EVENT','cert',:a,'{}'::jsonb,:d)",
        {"s": A["school_id"], "a": str(uuid4()), "d": "cert-" + uuid4().hex})
r.delete(ow.QUEUE)


def drain():
    while ow.run_once(cfg, r, owner):
        pass


ts = [threading.Thread(target=drain) for _ in range(4)]
[t.start() for t in ts]
[t.join() for t in ts]
left = outbox_rows()
env = envelopes()
check("4 concurrent workers drained the outbox", not left, f"left={len(left)}")
check("no event published twice by concurrent workers", env and max(env.values()) == 1, f"max per event={max(env.values()) if env else 0} total={sum(env.values())}")

# 4. dead-letter after MAX_ATTEMPTS
eid = sql("INSERT INTO outbox_events(school_id,event_type,aggregate_type,aggregate_id,payload,attempts,deduplication_key) VALUES(:s,'CERT_DLQ','cert',:a,'{}'::jsonb,:n,:d) RETURNING id",
          {"s": A["school_id"], "a": str(uuid4()), "n": ow.MAX_ATTEMPTS - 1, "d": "cert-" + uuid4().hex})[0]["id"]
ow.run_once(cfg, dead, owner)
d = sql("SELECT dead_lettered_at IS NOT NULL dl FROM outbox_events WHERE id=:i", {"i": eid})[0]["dl"]
check("event dead-lettered after max attempts, never retried forever", d is True)

# 5. bounded transport queue (no consumer exists for edusync:outbox in this codebase)
r.delete(ow.QUEUE)
cap = getattr(ow, "MAX_QUEUE_LENGTH", None)
if cap:
    for i in range(30):
        sql("INSERT INTO outbox_events(school_id,event_type,aggregate_type,aggregate_id,payload,deduplication_key) VALUES(:s,'CERT_CAP','cert',:a,'{}'::jsonb,:d)",
            {"s": A["school_id"], "a": str(uuid4()), "d": "cert-" + uuid4().hex})
    old_cap = ow.MAX_QUEUE_LENGTH
    ow.MAX_QUEUE_LENGTH = 10
    drain()
    ow.MAX_QUEUE_LENGTH = old_cap
check("Redis transport queue is bounded (unconsumed envelopes cannot exhaust Redis)", bool(cap) and r.llen(ow.QUEUE) <= 10, f"cap={cap} llen={r.llen(ow.QUEUE)}")

# 6. communications worker (deliveries seeded: recipient expansion does not exist, see report)
sql("""INSERT INTO communication_settings(school_id,enabled,sms_enabled,provider_code,sender_id) VALUES(:s,true,true,'mock','EDUSYNC')
       ON CONFLICT(school_id) DO UPDATE SET enabled=true,sms_enabled=true,provider_code='mock',sender_id='EDUSYNC'""", {"s": A["school_id"]})
mid = sql("INSERT INTO communication_messages(school_id,kind,audience_type,subject,body,created_by,idempotency_key) VALUES(:s,'ANNOUNCEMENT','INDIVIDUAL','Recette','Message recette',:u,:k) RETURNING id",
          {"s": A["school_id"], "u": A["users"]["ADMIN"]["user_id"], "k": "cert-" + uuid4().hex})[0]["id"]


def delivery(dest):
    return sql("INSERT INTO communication_deliveries(school_id,message_id,channel,destination,status) VALUES(:s,:m,'SMS',:d,'PENDING') RETURNING id",
               {"s": A["school_id"], "m": mid, "d": dest})[0]["id"]


ok_id = delivery("+243810000001")
while cw.run_once(cfg, r, owner):
    pass
st = sql("SELECT status,attempts,provider_message_id FROM communication_deliveries WHERE id=:i", {"i": ok_id})[0]
check("SMS delivery SENT only with a provider message id", st["status"] == "SENT" and st["provider_message_id"], str(dict(st)))


class Down:
    def send_sms(self, **_):
        return DeliveryResult(False, error_code="PROVIDER_TIMEOUT")


orig = cw.provider
cw.provider = lambda c, code: Down()
bad = delivery("+243810000002")
cw.run_once(cfg, r, owner)
st = sql("SELECT status,attempts,last_error_code,next_attempt_at>now() later FROM communication_deliveries WHERE id=:i", {"i": bad})[0]
check("provider outage: delivery re-queued with backoff, not SENT", st["status"] == "QUEUED" and st["attempts"] == 1 and st["later"] and st["last_error_code"] == "PROVIDER_TIMEOUT", str(dict(st)))
for _ in range(cw.MAX_ATTEMPTS):
    sql("UPDATE communication_deliveries SET next_attempt_at=NULL WHERE id=:i", {"i": bad})
    cw.run_once(cfg, r, owner)
st = sql("SELECT status,attempts FROM communication_deliveries WHERE id=:i", {"i": bad})[0]
check("terminal FAILED after max attempts, no infinite retry", st["status"] == "FAILED" and st["attempts"] == cw.MAX_ATTEMPTS, str(dict(st)))
cw.provider = orig

# provider I/O happens outside the DB transaction: a slow provider must not hold row locks
gate = threading.Event()


class Slow:
    def send_sms(self, **_):
        gate.wait(10)
        return DeliveryResult(True, "slow-1")


cw.provider = lambda c, code: Slow()
slow = delivery("+243810000003")
t = threading.Thread(target=lambda: cw.run_once(cfg, r, owner))
t.start()
import time
deadline = time.time() + 20  # wait until the worker has committed its lease and is inside the provider call
while time.time() < deadline and not sql("SELECT locked_until>now() l FROM communication_deliveries WHERE id=:i", {"i": slow})[0]["l"]:
    time.sleep(0.1)
time.sleep(0.5)
blocked = sql("SELECT count(*) n FROM pg_locks l JOIN pg_class c ON c.oid=l.relation WHERE c.relname='communication_deliveries' AND l.mode='RowExclusiveLock' AND l.granted")[0]["n"]
locked_row = sql("SELECT locked_until>now() leased FROM communication_deliveries WHERE id=:i", {"i": slow})[0]["leased"]
gate.set()
t.join()
cw.provider = orig
check("slow provider: row leased but no DB transaction/lock held during provider I/O", locked_row and blocked == 0, f"leased={locked_row} row_locks={blocked}")
dump("workers-live.json")
