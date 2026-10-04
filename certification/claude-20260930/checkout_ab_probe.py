"""A/B proof for checkout defects D2-D4: same PostgreSQL, same tenant role/RLS, old vs fixed adapter.

Usage: checkout_ab_probe.py <path-to-adapter.py> <label>
Runs directly through the application's tenant runtime (edusync_tenant + app.school_id), not the owner.
"""
import importlib.util
import sys
import threading
from decimal import Decimal
from uuid import UUID, uuid4

sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *  # noqa: E402,F403
from edusync.bootstrap.settings import Settings  # noqa: E402
from edusync.shared.infrastructure.postgres import DatabaseRuntime  # noqa: E402

spec = importlib.util.spec_from_file_location("adapter_under_test", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
Repo = mod.PostgresFinanceCheckoutRepository
label = sys.argv[2]
db = DatabaseRuntime.from_url(Settings().tenant_database_url, role_kind="tenant")

A = state["A"]
sid = UUID(A["school_id"])
cashier = A["users"]["CAISSIER1"]
uid, mid = UUID(cashier["user_id"]), UUID(cashier["membership_id"])
eid = A["family"]["enrollment_ids"][1]  # owes CDF and USD

# fresh mixed-currency charges for this run
cdf_id, usd_id = str(uuid4()), str(uuid4())
sql("""INSERT INTO finance_charges(id,school_id,enrollment_id,label,currency,net_amount,periodicity) VALUES
       (:c,:s,:e,'AB CDF','CDF',1000,'ONE_OFF'),(:u,:s,:e,'AB USD','USD',10,'ONE_OFF')""",
    {"c": cdf_id, "u": usd_id, "s": str(sid), "e": eid})
eid0 = A["family"]["enrollment_ids"][0]  # CDF-only enrollment, isolates D3/D4 from D2
one_id = str(uuid4())
sql("INSERT INTO finance_charges(id,school_id,enrollment_id,label,currency,net_amount,periodicity) VALUES (:c,:s,:e,'AB ONE','CDF',1000,'ONE_OFF')",
    {"c": one_id, "s": str(sid), "e": eid0})


def run(fn):
    try:
        with db.tenant_transaction(school_id=sid, user_id=uid) as conn:
            return ("OK", fn(Repo(conn)))
    except Exception as e:  # noqa: BLE001
        return (type(e).__name__, str(e).splitlines()[0][:120])


# D2: CDF payment on an enrollment that also owes USD
d2 = run(lambda r: r.collect(sid, uid, mid, UUID(eid), [UUID(cdf_id)], Decimal("100"), "CDF", str(uuid4())))
check(f"[{label}] D2 CDF payment when enrollment also owes USD", d2[0] == "OK", str(d2))

# D4: same key reused with a different amount
k = str(uuid4())
first = run(lambda r: r.collect(sid, uid, mid, UUID(eid0), [UUID(one_id)], Decimal("1"), "CDF", k))
second = run(lambda r: r.collect(sid, uid, mid, UUID(eid0), [UUID(one_id)], Decimal("2"), "CDF", k))
check(f"[{label}] D4 key reuse with different amount rejected", second[0] == "ValueError", f"first={first[0]} second={second}")

# D3: same key, concurrent
k2 = str(uuid4())
outs = []
barrier = threading.Barrier(3)


def worker():
    barrier.wait()
    outs.append(run(lambda r: r.collect(sid, uid, mid, UUID(eid0), [UUID(one_id)], Decimal("1"), "CDF", k2)))


ts = [threading.Thread(target=worker) for _ in range(3)]
[t.start() for t in ts]
[t.join() for t in ts]
n = sql("SELECT count(*) n FROM finance_payments WHERE idempotency_key=:k", {"k": k2})[0]["n"]
check(f"[{label}] D3 concurrent same key: no IntegrityError, one payment", all(o[0] == "OK" for o in outs) and n == 1, f"{[o[0] for o in outs]} payments={n}")
dump(f"checkout-ab-{label}.json")
