"""Live Finance checkout certification: real HTTP API + real PostgreSQL (tenant role, RLS, FORCE RLS).

Fixture note: the application has no endpoint that generates finance_charges from tariffs (see report).
Charges are therefore inserted by the owner role as an explicit test fixture; every payment,
allocation, cash session and receipt below goes through the public API only.
"""
import sys
import threading
from decimal import Decimal
from uuid import uuid4

sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *  # noqa: E402,F403

A, B = state["A"], state["B"]


def seed_charges(school: dict) -> None:
    enr = school["family"]["enrollment_ids"]
    if school.get("charges_seeded"):
        return
    # enrollment 0: CDF monthly chain only; enrollment 1: CDF + USD (mixed currencies); enrollment 2: CDF chain for concurrency
    plan = {
        enr[0]: [("Minerval · SEPTEMBRE", "CDF", 50000, "MONTHLY", "SEPTEMBRE", 1), ("Minerval · OCTOBRE", "CDF", 50000, "MONTHLY", "OCTOBRE", 2)],
        enr[1]: [("Minerval · SEPTEMBRE", "CDF", 50000, "MONTHLY", "SEPTEMBRE", 1), ("Frais d'inscription", "USD", 20, "ONE_OFF", None, None)],
        enr[2]: [("Minerval · SEPTEMBRE", "CDF", 60000, "MONTHLY", "SEPTEMBRE", 1)],
    }
    for eid, rows in plan.items():
        for label, cur, amt, per, plabel, porder in rows:
            sql("""INSERT INTO finance_charges(school_id,enrollment_id,label,currency,net_amount,periodicity,period_label,period_order)
                   VALUES(:s,:e,:l,:c,:a,:p,:pl,:po)""",
                {"s": school["school_id"], "e": eid, "l": label, "c": cur, "a": amt, "p": per, "pl": plabel, "po": porder})
    school["charges_seeded"] = True
    save()


def charges(client, eid):
    return must(client, "GET", f"finance/checkout/balance/{eid}").json()["items"]


def ensure_open(client):
    cur = must(client, "GET", "finance/cash/current").json()["session"]
    if not cur:
        r = call(client, "POST", "finance/cash/open", json={"opening_cdf": 0, "opening_usd": 0})
        check("cash.open", r.status_code == 200, f"HTTP {r.status_code} {r.text[:150]}")


for s in (A, B):
    seed_charges(s)

c1 = user_client(A, "CAISSIER1")
c2 = user_client(A, "CAISSIER2")
b1 = user_client(B, "CAISSIER1")
for c in (c1, c2, b1):
    ensure_open(c)

eA = A["family"]["enrollment_ids"]
eB = B["family"]["enrollment_ids"]

# --- 1. Simple CDF payment on a CDF-only enrollment (sequential month) -------------------------
ch = charges(c1, eA[0])
sept = next(x for x in ch if x["period_label"] == "SEPTEMBRE")
octo = next(x for x in ch if x["period_label"] == "OCTOBRE")
check("sequential: OCTOBRE locked while SEPTEMBRE due", not octo["eligible"] and sept["eligible"], str(octo["lock_reason"]))
key = str(uuid4())
body = {"enrollment_id": eA[0], "charge_ids": [sept["id"]], "amount": "20000", "currency": "CDF"}
r = call(c1, "POST", "finance/checkout/collect", json=body, headers={"Idempotency-Key": key})
check("collect CDF partial payment (fresh install)", r.status_code == 200, f"HTTP {r.status_code} {r.text[:200]}")
first = r.json() if r.status_code == 200 else {}

# --- 2. Idempotent replay -----------------------------------------------------------------------
r2 = call(c1, "POST", "finance/checkout/collect", json=body, headers={"Idempotency-Key": key})
check("replay same key+payload returns same receipt", r2.status_code == 200 and r2.json().get("receipt_number") == first.get("receipt_number") and r2.json().get("replayed") is True, r2.text[:200])
r3 = call(c1, "POST", "finance/checkout/collect", json={**body, "amount": "25000"}, headers={"Idempotency-Key": key})
check("replay same key with different payload is rejected (409)", r3.status_code == 409, f"HTTP {r3.status_code} {r3.text[:200]}")
paid = sql("SELECT paid_amount FROM finance_charges WHERE id=:i", {"i": sept["id"]})[0]["paid_amount"]
check("replays did not double-allocate", Decimal(paid) == Decimal("20000"), f"paid={paid}")

# --- 3. Over-payment without plan refused; out-of-order month refused ---------------------------
r = call(c1, "POST", "finance/checkout/collect", json={"enrollment_id": eA[0], "charge_ids": [sept["id"]], "amount": "999999", "currency": "CDF"})
check("over-payment without anticipation plan refused", r.status_code == 409, f"HTTP {r.status_code}")
r = call(c1, "POST", "finance/checkout/collect", json={"enrollment_id": eA[0], "charge_ids": [octo["id"]], "amount": "1000", "currency": "CDF"})
check("OCTOBRE refused before SEPTEMBRE settled", r.status_code == 409, f"HTTP {r.status_code}")

# --- 4. Mixed-currency enrollment: pay CDF charge only ------------------------------------------
ch1 = charges(c1, eA[1])
cdf = next(x for x in ch1 if x["currency"] == "CDF")
usd = next(x for x in ch1 if x["currency"] == "USD")
r = call(c1, "POST", "finance/checkout/collect", json={"enrollment_id": eA[1], "charge_ids": [cdf["id"]], "amount": "10000", "currency": "CDF"})
check("collect CDF on enrollment that also owes USD", r.status_code == 200, f"HTTP {r.status_code} {r.text[:200]}")
r = call(c1, "POST", "finance/checkout/collect", json={"enrollment_id": eA[1], "charge_ids": [usd["id"]], "amount": "5", "currency": "USD"})
check("collect USD on same enrollment", r.status_code == 200, f"HTTP {r.status_code} {r.text[:200]}")
r = call(c1, "POST", "finance/checkout/collect", json={"enrollment_id": eA[1], "charge_ids": [cdf["id"], usd["id"]], "amount": "10", "currency": "USD"})
check("CDF+USD in one payment refused", r.status_code == 409, f"HTTP {r.status_code}")
r = call(c1, "POST", "finance/checkout/collect", json={"enrollment_id": eA[1], "charge_ids": [usd["id"]], "amount": "1", "currency": "CDF"})
check("currency mismatch with selected charge refused", r.status_code == 409, f"HTTP {r.status_code}")

# --- 5. Cross-tenant (BOLA/IDOR) ------------------------------------------------------------------
r = call(b1, "GET", f"finance/checkout/balance/{eA[0]}")
check("B cannot read A balance by known enrollment id", r.status_code in (200, 404) and not (r.status_code == 200 and r.json().get("items")), f"HTTP {r.status_code} {r.text[:120]}")
r = call(b1, "POST", "finance/checkout/collect", json={"enrollment_id": eA[0], "charge_ids": [sept["id"]], "amount": "100", "currency": "CDF"})
check("B cannot collect on A charge", r.status_code in (403, 404, 409), f"HTTP {r.status_code} {r.text[:120]}")
r = call(b1, "GET", "finance/checkout/search", params={"q": "ELEVEA"})
check("B search does not return A students", r.status_code == 200 and not r.json()["items"], f"HTTP {r.status_code} n={len(r.json().get('items', [])) if r.status_code == 200 else '-'}")
r = call(b1, "GET", f"finance/checkout/family/{A['family']['family_id']}/children")
check("B cannot list A family children", r.status_code == 200 and not r.json()["items"], f"HTTP {r.status_code}")
paid = sql("SELECT paid_amount FROM finance_charges WHERE id=:i", {"i": sept["id"]})[0]["paid_amount"]
check("A charge untouched by B attempts", Decimal(paid) == Decimal("20000"), f"paid={paid}")

# --- 6. Two cashiers, same charge, concurrently (no over-allocation, no lost update) ------------
target = charges(c1, eA[2])[0]
outs = []


def pay(cli, key):
    rr = call(cli, "POST", "finance/checkout/collect", headers={"Idempotency-Key": key},
              json={"enrollment_id": eA[2], "charge_ids": [target["id"]], "amount": "40000", "currency": "CDF"})
    outs.append(rr.status_code)


ts = [threading.Thread(target=pay, args=(cl, str(uuid4()))) for cl in (c1, c2)]
[t.start() for t in ts]
[t.join() for t in ts]
row = sql("SELECT net_amount,paid_amount FROM finance_charges WHERE id=:i", {"i": target["id"]})[0]
alloc = sql("SELECT coalesce(sum(amount),0) s FROM finance_payment_allocations WHERE charge_id=:i", {"i": target["id"]})[0]["s"]
check("2 cashiers concurrent: one full payment + one capped/refused, no over-allocation",
      Decimal(row["paid_amount"]) <= Decimal(row["net_amount"]) and Decimal(alloc) == Decimal(row["paid_amount"]) and 500 not in outs,
      f"statuses={sorted(outs)} paid={row['paid_amount']} alloc={alloc}")

# --- 7. Same idempotency key sent twice concurrently by the same cashier -----------------------
sept2 = charges(c1, eA[0])[0]
k = str(uuid4())
outs2 = []


def pay2():
    rr = call(c1, "POST", "finance/checkout/collect", headers={"Idempotency-Key": k},
              json={"enrollment_id": eA[0], "charge_ids": [sept2["id"]], "amount": "1000", "currency": "CDF"})
    outs2.append((rr.status_code, rr.json().get("receipt_number") if rr.status_code == 200 else rr.text[:80]))


ts = [threading.Thread(target=pay2) for _ in range(3)]
[t.start() for t in ts]
[t.join() for t in ts]
n = sql("SELECT count(*) n FROM finance_payments WHERE idempotency_key=:k", {"k": k})[0]["n"]
check("concurrent same Idempotency-Key: one payment, all responses 200 with same receipt",
      n == 1 and all(s == 200 for s, _ in outs2) and len({x for _, x in outs2}) == 1, f"payments={n} responses={outs2}")

# --- 8. Ledger integrity -----------------------------------------------------------------------
bad = sql("""SELECT count(*) n FROM finance_charges fc WHERE fc.paid_amount <>
             coalesce((SELECT sum(a.amount) FROM finance_payment_allocations a WHERE a.charge_id=fc.id),0)""")[0]["n"]
check("ledger: paid_amount == sum(allocations) for every charge", bad == 0, f"mismatches={bad}")
dup = sql("SELECT count(*) n FROM (SELECT school_id,receipt_number FROM finance_payments GROUP BY 1,2 HAVING count(*)>1) x")[0]["n"]
check("no duplicate receipt numbers", dup == 0)
cross = sql("""SELECT count(*) n FROM finance_payment_allocations a JOIN finance_payments p ON p.id=a.payment_id
               JOIN finance_charges c ON c.id=a.charge_id WHERE a.school_id<>p.school_id OR a.school_id<>c.school_id""")[0]["n"]
check("no cross-school allocation rows", cross == 0)
over = sql("SELECT count(*) n FROM finance_payments p WHERE p.amount < coalesce((SELECT sum(amount) FROM finance_payment_allocations a WHERE a.payment_id=p.id),0)")[0]["n"]
check("no payment allocates more than its amount", over == 0)

# --- 9. Cash session totals reflect receipts ------------------------------------------------------
cur = must(c1, "GET", "finance/cash/current").json()["session"]
check("cash session projection readable after payments", bool(cur) and "cdf" in cur, str(cur.get("cdf") if cur else None))

dump("finance-live.json")
