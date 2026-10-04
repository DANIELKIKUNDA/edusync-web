"""Intendance live probe: stock invariants, concurrency, replay, inventory counts integrity, isolation."""
import os
import sys
import threading
from decimal import Decimal
from uuid import uuid4

sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa: E402,F403

A, B = state["A"], state["B"]
ensure_user(A, "INTENDANT", ("INTENDANT",))
ensure_user(B, "INTENDANT", ("INTENDANT",))
i = user_client(A, "INTENDANT")
ib = user_client(B, "INTENDANT")
caps = set(must(i, "GET", "auth/me").json()["permissions"])
check("standard INTENDANT role carries stock + counts capabilities",
      {"inventory.stock.receive", "inventory.stock.issue", "inventory.counts.create", "inventory.counts.validate"} <= caps,
      str(sorted(c for c in caps if c.startswith("inventory."))[:12]))
item = str(uuid4())
sql("INSERT INTO inventory_items(id,school_id,code,label,item_kind,unit,quantity,low_threshold) VALUES(:i,:s,:c,'Craie blanche','CONSUMABLE','boîte',0,5)",
    {"i": item, "s": A["school_id"], "c": "CRAIE-" + uuid4().hex[:4]})


def move(client, t, q, key=None, direction=None, reason="Recette intendance"):
    body = {"item_id": item, "movement_type": t, "quantity": str(q), "reason": reason}
    if direction:
        body["adjustment_direction"] = direction
    return call(client, "POST", "stewardship/stock/movements", json=body, headers={"Idempotency-Key": key or str(uuid4())})


def qty():
    return Decimal(sql("SELECT quantity FROM inventory_items WHERE id=:i", {"i": item})[0]["quantity"])


check("receipt +100", move(i, "RECEIPT", 100).status_code == 201 and qty() == 100)
check("issue beyond stock refused (no negative stock)", move(i, "ISSUE", 101).status_code == 409 and qty() == 100)
check("adjustment without direction refused", move(i, "ADJUSTMENT", 1).status_code == 422)

# concurrency: 10 parallel issues of 15 on a stock of 100 -> at most 6 succeed, never negative
codes = []
ts = [threading.Thread(target=lambda: codes.append(move(user_client(A, "INTENDANT"), "ISSUE", 15).status_code)) for _ in range(10)]
[t.start() for t in ts]
[t.join() for t in ts]
mv = Decimal(sql("SELECT coalesce(sum(quantity_delta),0) s FROM inventory_item_movements WHERE item_id=:i", {"i": item})[0]["s"])
check("10 concurrent issues: stock never negative, ledger == quantity", qty() >= 0 and qty() == mv and codes.count(201) == 6, f"201x{codes.count(201)} 409x{codes.count(409)} qty={qty()} ledger={mv}")

# replay of the same request (network retry) must not issue twice
before = qty()
k = str(uuid4())
r1, r2 = move(i, "RECEIPT", 7, key=k), move(i, "RECEIPT", 7, key=k)
check("replayed movement with same Idempotency-Key applied once", qty() == before + 7, f"{r1.status_code}/{r2.status_code} qty {before} -> {qty()}")

# cross-tenant
check("B cannot move A's stock", move(ib, "ISSUE", 1).status_code == 404)
check("B stock list never shows A items", item not in call(ib, "GET", "stewardship/stock").text)

# inventory count integrity
cid = must(i, "POST", "stewardship/counts", 201, json={"notes": "Inventaire recette"}).json()["id"]
theo = qty()
must(i, "POST", f"stewardship/counts/{cid}/lines", json={"item_id": item, "counted_quantity": str(theo - 2), "reason": "2 boîtes cassées"})
move(i, "ISSUE", 5)  # real movement after counting, before validation
after_move = qty()
r = call(i, "POST", f"stewardship/counts/{cid}/validate")
final = qty()
ledger = Decimal(sql("SELECT coalesce(sum(quantity_delta),0) s FROM inventory_item_movements WHERE item_id=:i", {"i": item})[0]["s"])
check("validation does not silently erase a movement made after counting", not (r.status_code == 200 and final == theo - 2),
      f"validate=HTTP {r.status_code}; counted={theo - 2} after_issue={after_move} final={final}")
check("stock ledger (sum of movements) equals quantity after count", final == ledger, f"qty={final} ledger={ledger}")
cid2 = must(i, "POST", "stewardship/counts", 201, json={"notes": "Inventaire 2"}).json()["id"]
must(i, "POST", f"stewardship/counts/{cid2}/lines", json={"item_id": item, "counted_quantity": str(qty()), "reason": None})
check("count with no variance validates", call(i, "POST", f"stewardship/counts/{cid2}/validate").status_code == 200)
r = call(i, "POST", f"stewardship/counts/{cid2}/lines", json={"item_id": item, "counted_quantity": "0", "reason": "réécriture"})
line = sql("SELECT counted_quantity FROM inventory_count_lines WHERE count_id=:c AND item_id=:i", {"c": cid2, "i": item})[0]["counted_quantity"]
check("validated inventory is immutable (no line rewrite)", r.status_code in (409, 422) and Decimal(line) != 0, f"HTTP {r.status_code} counted now={line}")
r = call(ib, "POST", f"stewardship/counts/{cid}/lines", json={"item_id": item, "counted_quantity": "1", "reason": "x"})
check("B cannot add lines to A's count", r.status_code in (403, 404, 409), f"HTTP {r.status_code}")
dump("stewardship-live.json")
