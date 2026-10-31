"""Month required at enrollment — real HTTP + real PostgreSQL (2026-10-31, PR #29 merged with the owner's agreement).

Owner decision 31/10: the tuition month required at enrollment (school without its own rubric: the historical bundle
INSCRIPTION + June) may be collected while September is still unpaid; ONLY that month escapes the order — October still
waits for September, and the bundle still comes before any other fee.

    python tools/local/isolated_db.py env <db> -- ../.venv/Scripts/python.exe ../tools/ci/enrollment_month_postgres_integration.py

Reuses tools/ci/three_roles_postgres_integration.py (CI=true, localhost only). Exits 1 on any FAIL.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_roles_postgres_integration as H  # noqa: E402
from three_roles_postgres_integration import actor_for, as_, check, key, one, school, sql  # noqa: E402


def fixture(A: dict) -> dict:
    """Fee types, schedules and charges of one pupil: INSCRIPTION, then school fees September, October … June."""
    sid, y, cls = A["id"], A["year"], A["classes"]["SECONDAIRE"]
    enr = one("SELECT id FROM enrollments WHERE student_id=:s", s=A["pupils"]["SECONDAIRE"])[0]
    sql("UPDATE enrollments SET status='VALIDATED' WHERE id=:e", e=enr)
    ins_t, sco_t = uuid.uuid4(), uuid.uuid4()
    sql("INSERT INTO fee_types(id,school_id,code,label,periodicity,default_currency,regulatory,enabled) VALUES(:i,:s,'INSCRIPTION','Inscription','ONE_TIME','CDF',false,true)", i=ins_t, s=sid)
    sql("INSERT INTO fee_types(id,school_id,code,label,periodicity,default_currency,regulatory,enabled) VALUES(:i,:s,'SCOLARITE','Frais scolaires','MONTHLY','CDF',false,true)", i=sco_t, s=sid)
    out = {"enrollment": enr}
    plan = [("ins", ins_t, "*", "Inscription", None, "ONE_OFF", None, "2026-09-01", 15000),
            ("sep", sco_t, "09", "Septembre", 1, "MONTHLY", "MONTHLY:SCOLARITE", "2026-09-30", 20000),
            ("oct", sco_t, "10", "Octobre", 2, "MONTHLY", "MONTHLY:SCOLARITE", "2026-10-31", 20000),
            ("jun", sco_t, "06", "Juin", 10, "MONTHLY", "MONTHLY:SCOLARITE", "2027-06-30", 20000)]
    for name, ft, code, label, order, per, seq, due, amount in plan:
        sch, ch = uuid.uuid4(), uuid.uuid4()
        sql("""INSERT INTO fee_schedules(id,school_id,academic_year_id,class_id,fee_type_id,period_code,period_label,period_order,due_date,amount,currency)
               VALUES(:i,:s,:y,:c,:f,:p,:l,:o,:d,:a,'CDF')""", i=sch, s=sid, y=y, c=cls, f=ft, p=code, l=label, o=order, d=due, a=amount)
        sql("""INSERT INTO finance_charges(id,school_id,enrollment_id,label,currency,net_amount,periodicity,period_label,period_order,due_date,sequence_group,sequence_order,fee_type_id,schedule_id)
               VALUES(:i,:s,:e,:l,'CDF',:a,:per,:l,:o,:d,:seq,:o,:f,:sch)""", i=ch, s=sid, e=enr, l=label, a=amount, per=per, o=order, d=due, seq=seq, f=ft, sch=sch)
        out[name] = str(ch)
    return out


def run(A: dict) -> None:
    print("\n== Mois exigé à l'inscription (décision du 31/10, PR #29)")
    f = fixture(A)
    as_(actor_for("CAISSIER", A["id"]))
    c = H.CLIENT
    o = c.post("/api/v1/finance/cash/open", json={"opening_cdf": "0", "opening_usd": "0"}, headers=key())
    check("caisse ouverte", o.status_code in (200, 201), o.text[:150])
    pay = lambda ids, amount: c.post("/api/v1/finance/checkout/collect", json={"enrollment_id": str(f["enrollment"]), "charge_ids": ids, "amount": str(amount), "currency": "CDF"}, headers=key())
    paid = lambda name: float(one("SELECT paid_amount FROM finance_charges WHERE id=:i", i=f[name])[0])
    bal = c.get(f"/api/v1/finance/checkout/balance/{f['enrollment']}")
    june = next((x for x in bal.json().get("items", []) if x["id"] == f["jun"]), {}) if bal.status_code == 200 else {}
    check("juin, mois exigé à l'inscription, est proposé au guichet même avec septembre impayé", june.get("eligible") is True and not june.get("requires"), str(june)[:200])
    r = pay([f["sep"]], 20000)
    check("septembre seul avant le lot d'inscription → refusé (le lot passe d'abord), rien encaissé", r.status_code == 409 and paid("sep") == 0, f"{r.status_code} {r.text[:120]}")
    r = pay([f["ins"], f["jun"]], 35000)
    check("lot d'inscription (inscription + juin) encaissé alors que septembre est impayé", r.status_code in (200, 201) and paid("ins") == 15000 and paid("jun") == 20000, f"{r.status_code} {r.text[:150]}")
    r = pay([f["oct"]], 20000)
    check("octobre avant septembre → toujours refusé (seul le mois exigé échappe à l'ordre), rien encaissé", r.status_code == 409 and paid("oct") == 0, f"{r.status_code} {r.text[:120]}")
    r = pay([f["sep"]], 20000)
    check("septembre ensuite → encaissé", r.status_code in (200, 201) and paid("sep") == 20000, f"{r.status_code} {r.text[:120]}")
    r = pay([f["oct"]], 20000)
    check("octobre après septembre → encaissé", r.status_code in (200, 201) and paid("oct") == 20000, f"{r.status_code} {r.text[:120]}")
    n = tuple(one("SELECT count(*), count(DISTINCT receipt_number) FROM finance_payments WHERE enrollment_id=:e", e=f["enrollment"]))
    check("aucun doublon : 3 encaissements acceptés = 3 paiements, 3 reçus distincts", n == (3, 3), n)


def main() -> int:
    A = school("A")
    run(A)
    H.CLIENT.__exit__(None, None, None)
    fails = [r for r in H.RESULTS if r[0] == "FAIL"]
    print(f"\n{len(H.RESULTS) - len(fails)}/{len(H.RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
