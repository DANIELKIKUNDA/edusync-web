"""WEB-0B live PostgreSQL probe.

Run after migrations:
  python scripts/g1_postgres_probe.py
It intentionally performs only disposable foundation writes with random identifiers.
"""
from __future__ import annotations
import os
from uuid import uuid4
from sqlalchemy import create_engine, text

url = os.environ.get("EDUSYNC_DATABASE_URL")
if not url:
    raise SystemExit("EDUSYNC_DATABASE_URL manquant")
engine = create_engine(url, future=True)

school_a, school_b = uuid4(), uuid4()
code_a, code_b = f"G1A-{str(school_a)[:8]}", f"G1B-{str(school_b)[:8]}"
with engine.begin() as c:
    c.execute(text("INSERT INTO schools(id,code,name) VALUES (:id,:code,'G1 Probe A')"), {"id":school_a,"code":code_a})
    c.execute(text("INSERT INTO schools(id,code,name) VALUES (:id,:code,'G1 Probe B')"), {"id":school_b,"code":code_b})

# Idempotency DB uniqueness: second insert must be ignored by ON CONFLICT.
with engine.begin() as c:
    c.execute(text("SELECT set_config('app.current_school_id', :sid, true)"), {"sid":str(school_a)})
    for _ in range(2):
        c.execute(text("""
          INSERT INTO idempotency_registry(scope_key,school_id,idempotency_key,request_hash,operation,status)
          VALUES (:scope,:sid,'probe:1',repeat('a',64),'PROBE','PROCESSING')
          ON CONFLICT (scope_key,idempotency_key) DO NOTHING
        """), {"scope":str(school_a),"sid":school_a})
    n=c.execute(text("SELECT count(*) FROM idempotency_registry WHERE school_id=:sid AND idempotency_key='probe:1'"),{"sid":school_a}).scalar_one()
    assert n == 1, n

# Optimistic locking: first writer wins; stale expected version must affect zero rows.
with engine.begin() as c:
    r1=c.execute(text("UPDATE schools SET name='A1',version=version+1 WHERE id=:id AND version=1 RETURNING version"),{"id":school_a}).first()
    assert r1 and r1[0] == 2
    r2=c.execute(text("UPDATE schools SET name='A-stale',version=version+1 WHERE id=:id AND version=1 RETURNING version"),{"id":school_a}).first()
    assert r2 is None

# Cleanup platform tables. Tenant children first.
with engine.begin() as c:
    c.execute(text("DELETE FROM idempotency_registry WHERE school_id IN (:a,:b)"),{"a":school_a,"b":school_b})
    c.execute(text("DELETE FROM schools WHERE id IN (:a,:b)"),{"a":school_a,"b":school_b})
print("G1_POSTGRES_PROBE_PASS")
