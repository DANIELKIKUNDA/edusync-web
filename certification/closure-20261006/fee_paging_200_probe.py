"""D22 replay on the volume database with the UI's real lot size (200 lines), filters and search.

Numbers are explicit: the previous report's "13 pages" was a chaining test with 1000-line API pages
(12 x 1000 + 3); the screen loads lots of 200, i.e. 61 lots (60 x 200 + 3) for 12 003 lines.
"""
import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import DB_URL, state, user_client  # noqa: E402
from edusync.bootstrap.settings import Settings  # noqa: E402
from edusync.shared.infrastructure.postgres import DatabaseRuntime  # noqa: E402
from edusync.adapters.postgres_fee_tracking import PostgresFeeTrackingRepository  # noqa: E402

assert DB_URL.endswith("/edusync_claude_perf"), "volume database required"
results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


A = state["A"]; sid, year = UUID(A["school_id"]), UUID(A["year_id"])
c = user_client(A, "ADMIN")
tdb = DatabaseRuntime.from_url(Settings().tenant_database_url, role_kind="tenant")
money = lambda v: Decimal(str(v)).quantize(Decimal("0.01"))  # noqa: E731
key = lambda r: (str(r["student_id"]), str(r["fee_type_id"]))  # noqa: E731
line = lambda x: (str(x["student_id"]), str(x["fee_type_id"]), money(x["net_expected"]), money(x["regularized"]), money(x["remaining"]))  # noqa: E731


def chain(params, lot=200):
    seen, offset, lots, times, total, totals = [], 0, 0, [], None, None
    while True:
        t0 = time.perf_counter()
        r = c.get("finance/fees/students", params={**params, "limit": lot, "offset": offset})
        times.append((time.perf_counter() - t0) * 1000)
        body = r.json(); seen += body["items"]; offset += len(body["items"]); lots += 1
        total, totals = body["total"], body.get("totals")
        if not body["items"] or offset >= total:
            break
    return seen, lots, total, totals, times


with tdb.tenant_transaction(school_id=sid) as conn:
    full = PostgresFeeTrackingRepository(conn).students(sid, year, "CDF")
seen, lots, total, totals, times = chain({"currency": "CDF"})
expected_lots = -(-len(full) // 200)
check("toute l'école en lots de 200 : nombre de lots exact", total == len(full) and lots == expected_lots, f"{len(full)} lignes -> {lots} lots de 200 (attendu {expected_lots} = {len(full)//200} x 200 + {len(full) % 200})")
check("aucune perte, aucun doublon", len(seen) == len(full) and len({key(x) for x in seen}) == len(seen), f"{len(seen)} lues, {len({key(x) for x in seen})} uniques")
check("lignes paginées = lignes non paginées, au centime", sorted(map(line, seen)) == sorted(map(line, full)))
check("totaux serveur = somme de toutes les lignes (pas seulement la page)",
      totals and money(totals["net_expected"]) == sum(money(x["net_expected"]) for x in full) and money(totals["remaining"]) == sum(money(x["remaining"]) for x in full), totals)
seen2, *_ = chain({"currency": "CDF"})
check("ordre stable : deux lectures complètes identiques", [key(x) for x in seen] == [key(x) for x in seen2])
p50 = sorted(times)[len(times) // 2]; p95 = sorted(times)[int(len(times) * 0.95)]
check("temps par lot de 200 (12 003 élèves, 1 utilisateur)", p95 < 5000, f"p50 {p50:.0f} ms · p95 {p95:.0f} ms · {len(times)} lots")

# Filters + search are preserved through the lots.
cls = full[len(full) // 2]["class_label"]
in_class = [x for x in full if x["class_label"] == cls]
with tdb.tenant_transaction(school_id=sid) as conn:
    class_id = conn.execute(__import__("sqlalchemy").text("SELECT id FROM school_classes WHERE school_id=:s AND academic_year_id=:y AND label=:l LIMIT 1"), {"s": str(sid), "y": str(year), "l": cls}).scalar_one()
s_cls, lots_cls, total_cls, _, _ = chain({"currency": "CDF", "class_id": str(class_id)})
check("filtre classe conservé sur tous les lots", total_cls == len(in_class) and all(x["class_label"] == cls for x in s_cls) and len({key(x) for x in s_cls}) == len(in_class), f"{cls}: {total_cls} lignes, {lots_cls} lots")
name = full[123]["student_name"].split()[0]
want = [x for x in full if name.lower() in x["student_name"].lower() or name.lower() in (x["matricule"] or "").lower()]
s_q, lots_q, total_q, totals_q, _ = chain({"currency": "CDF", "q": name})
check("recherche conservée sur tous les lots (nom)", total_q == len(want) and {key(x) for x in s_q} == {key(x) for x in want}, f"« {name} » : {total_q} lignes, {lots_q} lots")
check("totaux recalculés pour la recherche", totals_q and money(totals_q["remaining"]) == sum(money(x["remaining"]) for x in want))
mat = full[42]["matricule"]
s_m, *_ = chain({"currency": "CDF", "q": mat})
check("recherche par matricule", s_m and all(mat.lower() in (x["matricule"] or "").lower() for x in s_m), f"{mat}: {len(s_m)}")
odd = c.get("finance/fees/students", params={"currency": "CDF", "q": "%_\\"}).json()
check("caractères spéciaux de recherche neutralisés (%, _, \\)", odd["total"] == 0, odd["total"])
not_in_order = [x for x in full if money(x["regularized"]) == 0 and money(x["net_expected"]) > 0]
s_st, lots_st, total_st, _, _ = chain({"currency": "CDF", "status": "NOT_IN_ORDER"})
check("filtre « Non en ordre » conservé sur tous les lots", total_st == len(not_in_order) and {key(x) for x in s_st} == {key(x) for x in not_in_order}, f"{total_st} lignes, {lots_st} lots")
past = c.get("finance/fees/students", params={"currency": "CDF", "offset": len(full) + 5}).json()
check("au-delà de la fin : liste vide, total et totaux exacts", past["items"] == [] and past["total"] == len(full) and money(past["totals"]["net_expected"]) == money(totals["net_expected"]))

out = Path(__file__).with_name("fee-paging-200-live.json")
out.write_text(json.dumps({"dataset": {"school_lines": len(full), "lot": 200}, "passed": sum(x["pass"] for x in results), "total": len(results), "results": results}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print(f"{sum(x['pass'] for x in results)}/{len(results)} PASS")
sys.exit(0 if all(x["pass"] for x in results) else 1)
