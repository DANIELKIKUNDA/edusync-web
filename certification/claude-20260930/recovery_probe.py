"""Recovery read models: availability + numbers reconciled against the ledger (real PostgreSQL)."""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa: E402,F403

A, B = state["A"], state["B"]
grant_test_role(A, "ADMIN", "CL_RECOVERY", ("finance.recovery.monthly.read", "finance.views.vf01.export_pdf", "finance.views.vf01.export_xlsx"))
adm = user_client(A, "ADMIN")

truth = sql("""SELECT coalesce(sum(fc.effective_net_amount),0) expected, coalesce(sum(fc.paid_amount),0) cash,
                 coalesce(sum((SELECT coalesce(sum(r.amount),0) FROM finance_charge_regularizations r WHERE r.charge_id=fc.id)),0) outside
               FROM finance_charge_effective fc JOIN enrollments e ON e.id=fc.enrollment_id
               WHERE fc.school_id=:s AND fc.currency='CDF' AND fc.status='ACTIVE' AND e.academic_year_id=:y""",
            {"s": A["school_id"], "y": A["year_id"]})[0]
for kind, params in [("section", {"section_id": A["section_id"]}), ("school", {}), ("class", {"class_id": A["class_id"]})]:
    r = call(adm, "GET", f"finance/recovery/summary/{kind}", params={"currency": "CDF", **params})
    check(f"recovery summary/{kind} available", r.status_code == 200, f"HTTP {r.status_code} {r.text[:120]}")
    if r.status_code == 200 and kind in ("section", "school"):
        t = r.json().get("total") or {}
        ok = Decimal(str(t.get("expected", -1))) == Decimal(truth["expected"]) and Decimal(str(t.get("cash_collected", -1))) == Decimal(truth["cash"]) \
            and Decimal(str(t.get("outside_cash", -1))) == Decimal(truth["outside"])
        check(f"summary/{kind} totals reconcile with ledger (expected net of exemptions, cash, outside cash)", ok,
              f"api expected={t.get('expected')} cash={t.get('cash_collected')} outside={t.get('outside_cash')} | db {dict(truth)}")
    for fmt in ("pdf", "xlsx"):
        r = call(adm, "GET", f"finance/recovery/summary/{kind}.{fmt}", params={"currency": "CDF", **params})
        check(f"recovery summary/{kind}.{fmt} export", r.status_code == 200 and len(r.content) > 500, f"HTTP {r.status_code}")
for path, params in [("finance/recovery/monthly", {}), ("finance/recovery/class-register", {"class_id": A["class_id"]})]:
    for suffix in ("", ".pdf", ".xlsx"):
        r = call(adm, "GET", path + suffix, params={"currency": "CDF", **params})
        check(f"{path.split('/')[-1]}{suffix or ' (json)'} available", r.status_code == 200, f"HTTP {r.status_code} {r.text[:100] if r.status_code != 200 else ''}")
r = call(adm, "GET", "finance/recovery/class-register", params={"currency": "CDF", "class_id": A["class_id"]})
if r.status_code == 200:
    body = r.text
    check("class register reflects exemptions (net, not gross tariff)", "25000" in body or "25000.0" in body, "exempted D11 charge expected at 25 000")
b = user_client(B, "ADMIN")
grant_test_role(B, "ADMIN", "CL_RECOVERY", ("finance.recovery.monthly.read",))
b = user_client(B, "ADMIN")
r = call(b, "GET", "finance/recovery/summary/school", params={"currency": "CDF"})
check("school B summary never includes school A money", r.status_code == 200 and Decimal(str((r.json().get("total") or {}).get("cash_collected", 0))) == Decimal(
    sql("SELECT coalesce(sum(paid_amount),0) s FROM finance_charges fc JOIN enrollments e ON e.id=fc.enrollment_id WHERE fc.school_id=:s AND fc.currency='CDF' AND e.academic_year_id=:y",
        {"s": B["school_id"], "y": B["year_id"]})[0]["s"]), r.text[:160])
dump("recovery-live.json")
