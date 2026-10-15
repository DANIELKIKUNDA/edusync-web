"""N3-F — real probe: staff children finance copied from the Desktop golden master (app/db/staff_finance.py).
Payroll deduction = non-cash settlement (no payment, no receipt, no cash operation), cancellable with a reason.
Fresh school, real API. Staff creation and child link use a test-only role (no standard role holds them); the
deduction itself is done by the standard GESTIONNAIRE (owner decision 2026-10-15). Nothing secret is printed.
"""
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import ensure_user, grant_test_role, owner, platform, save, state, user_client  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


def k(extra=None):
    return {"Idempotency-Key": str(uuid4()), **(extra or {})}


def ok(r, codes=(200, 201)):
    assert r.status_code in codes, (r.request.method, str(r.request.url)[-70:], r.status_code, r.text[:300])
    return r.json()


run = uuid4().hex[:5].upper()
s = ok(platform().post("platform/schools", json={"code": f"N3F-{run}", "name": f"École personnel N3-F {run}"}, headers=k()))
school = {"code": f"N3F-{run}", "school_id": s["id"], "users": {}}
state.setdefault("N3F", {})[run] = school
save()
ensure_user(school, "ADMIN", ("ADMIN_SYSTEME_ECOLE",))
ensure_user(school, "CASH", ("CAISSIER",))
ensure_user(school, "GES", ("GESTIONNAIRE",))
ensure_user(school, "RH", ())
grant_test_role(school, "RH", "RECETTE_RH", ("personnel.create", "personnel.read", "personnel.staff_children.link", "personnel.staff_children.read"))
adm, cash, ges, rh = (user_client(school, x) for x in ("ADMIN", "CASH", "GES", "RH"))
today = date.today()
sy = today.year if today.month >= 9 else today.year - 1
y = ok(adm.post("settings/academic-years", json={"code": f"{sy}-{sy+1}", "label": f"{sy}-{sy+1}", "start_date": f"{sy}-09-01", "end_date": f"{sy+1}-06-30"}, headers=k()))
y = ok(adm.post(f"settings/academic-years/{y['id']}/activate", headers=k({"If-Match": str(y["version"])})))
pri = ok(adm.put("settings/sections/PRIMAIRE", json={"code": "PRIMAIRE", "label": "Primaire", "enabled": True}, headers=k()))
p1 = ok(adm.post("settings/classes", json={"academic_year_id": y["id"], "section_id": pri["id"], "reference_code": "P1", "code": "P1A", "label": "P1A"}, headers=k()))
sco = ok(adm.post("settings/fee-types", json={"code": "SCOLARITE", "label": "Frais scolaires", "periodicity": "MONTHLY", "default_currency": "CDF"}, headers=k()))
ok(adm.put("settings/tariff-rules", json={"academic_year_id": y["id"], "fee_type_id": sco["id"], "scope_type": "SCHOOL", "amount": "20000", "currency": "CDF"}, headers=k()))
ok(adm.post("settings/admission-conditions/review", headers=k()))
ok(adm.post("settings/tariffs/apply", json={"academic_year_id": y["id"]}, headers=k()))
d = ok(cash.post("schooling/enrollments/family", json={"primary_guardian": {"full_name": f"Agent {run}", "is_primary": True},
       "children": [{"last_name": f"PAI{run}", "middle_name": "Recette", "first_name": "N3F", "gender": "F", "class_id": p1["id"]}]}, headers=k()))
enr, student = d["enrollment_ids"][0], d["student_ids"][0]
staff = ok(rh.post("personnel", json={"employee_no": f"AG-{run}", "last_name": f"AGENT{run}", "first_name": "Recette"}, headers=k()))
link = ok(rh.post(f"personnel/{staff['id']}/children", json={"student_id": student}, headers=k()))


def deduct(client=None, **body):
    return (client or ges).post(f"personnel/{staff['id']}/children/{student}/payroll-deductions", json=body, headers=k())


open_ = ok(ges.get(f"personnel/{staff['id']}/children/{student}/open-charges"))["items"]
check("Frais ouverts de l'enfant de l'agent (G-PER-1)", len(open_) == 10 and all(Decimal(o["balance"]) == Decimal("20000") for o in open_), len(open_))
r = deduct(allocations=[{"charge_id": open_[0]["charge_id"], "amount": "20000"}])
check("Retenue refusée tant que le mode « retenue à la source » n'est pas actif (message Desktop)", r.status_code == 409 and "retenue à la source" in r.text, r.status_code)
ok(ges.put(f"personnel/children/{link['id']}/finance-mode", json={"responsibility_mode": "PAYROLL", "effective_from": f"{sy}-09-01"}, headers=k()))
check("Droits : le caissier ne confirme pas de retenue", deduct(cash, allocations=[{"charge_id": open_[0]["charge_id"], "amount": "20000"}]).status_code == 403)
check("Droits : l'administrateur technique ne confirme pas de retenue", deduct(adm, allocations=[{"charge_id": open_[0]["charge_id"], "amount": "20000"}]).status_code == 403)
check("Montant supérieur au reste dû refusé", deduct(allocations=[{"charge_id": open_[0]["charge_id"], "amount": "25000"}]).status_code == 409)
with owner.connect() as c:
    before = c.execute(text("SELECT (SELECT count(*) FROM finance_payments WHERE school_id=:s), (SELECT count(*) FROM finance_receipt_sequences WHERE school_id=:s)"), {"s": school["school_id"]}).one()
r = deduct(allocations=[{"charge_id": open_[0]["charge_id"], "amount": "20000"}, {"charge_id": open_[1]["charge_id"], "amount": "5000"}], reference="PAIE-OCT", period_label="Octobre")
out = r.json() if r.status_code == 200 else {}
check("Retenue confirmée : 2 lignes, total 25 000 CDF", r.status_code == 200 and len(out.get("settlement_ids", [])) == 2 and out.get("currency_totals", {}).get("CDF") == "25000.00", out)
with owner.connect() as c:
    after = c.execute(text("SELECT (SELECT count(*) FROM finance_payments WHERE school_id=:s), (SELECT count(*) FROM finance_receipt_sequences WHERE school_id=:s)"), {"s": school["school_id"]}).one()
check("Aucun paiement, aucun reçu créés (séparation comptable Desktop)", tuple(before) == tuple(after), (tuple(before), tuple(after)))
bal = {i["id"]: Decimal(i["remaining"]) for i in cash.get(f"finance/checkout/balance/{enr}").json()["items"]}
check("La caisse voit les frais réglés hors caisse (septembre soldé, octobre 15 000)", open_[0]["charge_id"] not in bal and bal.get(open_[1]["charge_id"]) == Decimal("15000"), bal.get(open_[1]["charge_id"]))
if not cash.get("finance/cash/current").json().get("session"):
    ok(cash.post("finance/cash/open", json={"opening_cdf": 0, "opening_usd": 0}))
day = ges.get("finance/cash/day").json()
check("Journée de caisse : aucune entrée liée à la retenue", all(op["source"] != "PAIEMENT_ELEVE" for op in day.get("operations", [])), len(day.get("operations", [])))
fin = ok(ges.get(f"personnel/{staff['id']}/children/finance"))["items"]
t = fin[0]["totals"]["CDF"] if fin else {}
check("Vue agent : mode retenue, attendu, réglé, retenu, reste", fin and fin[0]["finance_mode"] == "PAYROLL_DEDUCTION" and t.get("payroll_deducted") == "25000.00"
      and t.get("balance") == "175000.00" and fin[0]["in_order"] is False, t)
r = ges.post(f"personnel/payroll-deductions/{out['settlement_ids'][1]}/cancel", json={"reason": "Retenue non effectuée par la paie"}, headers=k())
bal = {i["id"]: Decimal(i["remaining"]) for i in cash.get(f"finance/checkout/balance/{enr}").json()["items"]}
check("Annulation motivée : le frais redevient dû", r.status_code == 200 and bal.get(open_[1]["charge_id"]) == Decimal("20000"), bal.get(open_[1]["charge_id"]))
check("Annulation : une seconde fois refusée", ges.post(f"personnel/payroll-deductions/{out['settlement_ids'][1]}/cancel", json={"reason": "Encore une fois"}, headers=k()).status_code == 409)
check("Annulation : motif obligatoire", ges.post(f"personnel/payroll-deductions/{out['settlement_ids'][0]}/cancel", json={"reason": "ab"}, headers=k()).status_code == 422)
r = deduct(reference="PAIE-NOV")
check("Sans lignes : tous les frais ouverts sont réglés (Desktop)", r.status_code == 200 and r.json()["currency_totals"].get("CDF") == "180000.00", r.text[:120])
fin = ok(ges.get(f"personnel/{staff['id']}/children/finance"))["items"]
check("Enfant en ordre après retenue totale", fin and fin[0]["in_order"] is True, fin[0]["totals"] if fin else None)
with owner.connect() as c:
    acts = {a: n for a, n in c.execute(text("SELECT action, count(*) FROM audit_events WHERE school_id=:s AND action IN ('CONFIRM_STAFF_PAYROLL_DEDUCTION','CANCEL_STAFF_NONCASH_SETTLEMENT') GROUP BY action"), {"s": school["school_id"]})}
    priv = {t2: c.execute(text("SELECT has_table_privilege('edusync_tenant', :t, 'UPDATE') OR has_table_privilege('edusync_tenant', :t, 'DELETE')"), {"t": t2}).scalar_one()
            for t2 in ("finance_noncash_settlements", "finance_noncash_cancellations")}
check("Audit : confirmations et annulation tracées", acts.get("CONFIRM_STAFF_PAYROLL_DEDUCTION") == 2 and acts.get("CANCEL_STAFF_NONCASH_SETTLEMENT") == 1, acts)
check("Retenues et annulations : aucun UPDATE / DELETE possible", not any(priv.values()), priv)
ok_n = sum(r["pass"] for r in results)
Path(__file__).with_name("payroll-live.json").write_text(json.dumps({"school": school["code"], "results": results}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print(f"== {ok_n}/{len(results)} PASS -> payroll-live.json")
