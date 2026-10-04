"""D11: the cash desk must not collect what is already settled outside cash or exempted."""
import os, sys
from decimal import Decimal
from uuid import uuid4
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa

A = state["A"]
c1 = user_client(A, "CAISSIER1")
eid = A["family"]["enrollment_ids"][2]
ch = str(uuid4())
sql("INSERT INTO finance_charges(id,school_id,enrollment_id,label,currency,net_amount,periodicity) VALUES(:c,:s,:e,'D11 Frais régularisé','CDF',30000,'ONE_OFF')",
    {"c": ch, "s": A["school_id"], "e": eid})
# fully settled outside cash (historical regularization, as the finance-history import does)
sql("INSERT INTO finance_charge_regularizations(school_id,charge_id,amount,reason,reference,actor_user_id) VALUES(:s,:c,30000,'Reprise historique recette','D11',:u)",
    {"s": A["school_id"], "c": ch, "u": A["users"]["ADMIN"]["user_id"]})
row = next((x for x in must(c1, "GET", f"finance/checkout/balance/{eid}").json()["items"] if x["id"] == ch), None)
check("balance: regularized charge no longer shown as due", row is None or Decimal(row["remaining"]) == 0, str(row and row["remaining"]))
r = call(c1, "POST", "finance/checkout/collect", json={"enrollment_id": eid, "charge_ids": [ch], "amount": "30000", "currency": "CDF"})
check("cash desk refuses to collect a charge settled outside cash", r.status_code == 409, f"HTTP {r.status_code} {r.text[:120]}")
total = sql("""SELECT (SELECT coalesce(sum(amount),0) FROM finance_payment_allocations WHERE charge_id=:c)
               + (SELECT coalesce(sum(amount),0) FROM finance_charge_regularizations WHERE charge_id=:c) t""", {"c": ch})[0]["t"]
check("money received (cash + outside cash) never exceeds the obligation", Decimal(total) <= 30000, f"total={total}")

# exemption decision through the API, then the cashier tries to collect the exempted part
grant_test_role(A, "ADMIN", "CL_DECISIONS", ("finance.decisions.create", "finance.decisions.read"))
adm = user_client(A, "ADMIN")
ch2 = str(uuid4())
sql("INSERT INTO finance_charges(id,school_id,enrollment_id,label,currency,net_amount,periodicity) VALUES(:c,:s,:e,'D11 Frais exonéré','CDF',40000,'ONE_OFF')",
    {"c": ch2, "s": A["school_id"], "e": eid})
r = call(adm, "POST", "finance/controls/decisions", json={"enrollment_id": eid, "charge_id": ch2, "decision_type": "EXEMPTION", "currency": "CDF", "amount": 15000, "reason": "Exonération partielle recette", "effective_date": "2026-10-01"})
check("partial exemption recorded via API", r.status_code in (200, 201), f"HTTP {r.status_code} {r.text[:160]}")
row = next((x for x in must(c1, "GET", f"finance/checkout/balance/{eid}").json()["items"] if x["id"] == ch2), None)
check("balance shows obligation net of exemption (25 000)", row is not None and Decimal(row["remaining"]) == 25000, str(row and row["remaining"]))
r = call(c1, "POST", "finance/checkout/collect", json={"enrollment_id": eid, "charge_ids": [ch2], "amount": "40000", "currency": "CDF"})
check("cash desk refuses to collect the exempted part", r.status_code == 409, f"HTTP {r.status_code}")
r = call(c1, "POST", "finance/checkout/collect", json={"enrollment_id": eid, "charge_ids": [ch2], "amount": "25000", "currency": "CDF"})
check("cash desk collects exactly what is owed after exemption", r.status_code == 200, f"HTTP {r.status_code} {r.text[:120]}")

# database guard: a writer bypassing the application (tenant role, RLS on) cannot over-regularize
from uuid import UUID
from sqlalchemy import text as _t
from edusync.bootstrap.settings import Settings
from edusync.shared.infrastructure.postgres import DatabaseRuntime
tdb = DatabaseRuntime.from_url(Settings().tenant_database_url, role_kind="tenant")
try:
    with tdb.tenant_transaction(school_id=UUID(A["school_id"])) as c:
        c.execute(_t("INSERT INTO finance_charge_regularizations(school_id,charge_id,amount,reason,reference,actor_user_id) VALUES(:s,:c,1,'Contournement','RAW',:u)"),
                  {"s": A["school_id"], "c": ch2, "u": A["users"]["ADMIN"]["user_id"]})
    out = "ACCEPTED"
except Exception as e:  # noqa: BLE001
    out = type(e).__name__ + ": " + str(e).splitlines()[0][:110]
check("DB trigger rejects a raw over-regularization (tenant role)", out != "ACCEPTED", out)
dump("d11-live.json")
