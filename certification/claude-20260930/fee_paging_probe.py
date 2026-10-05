"""D22 live proof (volume database): the fee-tracking detail is paged server side, pages chain without gap
or duplicate, totals match the unpaged repository result, and a page stays fast at school scale."""
import os
import sys
import time
from decimal import Decimal
from uuid import UUID

sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa: E402,F403
from edusync.bootstrap.settings import Settings  # noqa: E402
from edusync.shared.infrastructure.postgres import DatabaseRuntime  # noqa: E402
from edusync.adapters.postgres_fee_tracking import PostgresFeeTrackingRepository  # noqa: E402

assert DB_URL.endswith("/edusync_claude_perf")
A = state["A"]
sid, year = UUID(A["school_id"]), UUID(A["year_id"])
c = user_client(A, "ADMIN")
tdb = DatabaseRuntime.from_url(Settings().tenant_database_url, role_kind="tenant")
with tdb.tenant_transaction(school_id=sid) as conn:
    full = PostgresFeeTrackingRepository(conn).students(sid, year, "CDF")
key = lambda r: (r["student_id"], r["fee_type_id"])  # noqa: E731

t0 = time.perf_counter(); r = call(c, "GET", "finance/fees/students", params={"currency": "CDF"}); first_ms = round((time.perf_counter() - t0) * 1000)
body = r.json()
check("default page is bounded to 200 lines", r.status_code == 200 and len(body["items"]) == 200, f"{len(body.get('items', []))} lines in {first_ms} ms")
check("total equals the unpaged repository count", body["total"] == len(full), f"total={body['total']} full={len(full)}")
check("first page answers fast at school scale", first_ms < 5000, f"{first_ms} ms (before: whole school, 4 MB)")
check("limit above 1000 is refused", call(c, "GET", "finance/fees/students", params={"limit": 5000}).status_code == 422)
check("negative offset is refused", call(c, "GET", "finance/fees/students", params={"offset": -1}).status_code == 422)

seen, offset = [], 0
while True:
    page = call(c, "GET", "finance/fees/students", params={"currency": "CDF", "limit": 1000, "offset": offset}).json()
    seen += page["items"]; offset += len(page["items"])
    if not page["items"] or offset >= page["total"]:
        break
check("pages chain without gap or duplicate", len(seen) == len(full) and len({key(x) for x in seen}) == len(seen), f"{len(seen)} lines over {offset // 1000 + 1} pages")
money = lambda v: str(Decimal(str(v)).quantize(Decimal("0.01")))  # noqa: E731
line = lambda x: (str(x["student_id"]), str(x["fee_type_id"]), money(x["net_expected"]), money(x["regularized"]), money(x["remaining"]))  # noqa: E731
check("paged lines equal the unpaged lines, to the cent", sorted(map(line, seen)) == sorted(map(line, full)))
past = call(c, "GET", "finance/fees/students", params={"offset": len(full) + 10}).json()
check("offset past the end returns empty items with the true total", past["items"] == [] and past["total"] == len(full))
dump("fee-paging-checks.json")
