"""N3-E — real probe: cash-desk rules copied from the Desktop golden master (app/db/finance_checkout.py
_validate_allocations, recommended_checkout, suggest_checkout_allocations; app/db/terrain.py fee_bundle_due).
Fresh school, real API, real cash desk. Nothing secret is printed.
"""
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import ensure_user, owner, platform, save, state, user_client  # noqa: E402

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
s = ok(platform().post("platform/schools", json={"code": f"N3E-{run}", "name": f"École caisse N3-E {run}"}, headers=k()))
school = {"code": f"N3E-{run}", "school_id": s["id"], "users": {}}
state.setdefault("N3E", {})[run] = school
save()
ensure_user(school, "ADMIN", ("ADMIN_SYSTEME_ECOLE",))
ensure_user(school, "CASH", ("CAISSIER",))
adm, cash = user_client(school, "ADMIN"), user_client(school, "CASH")
today = date.today()
sy = today.year if today.month >= 9 else today.year - 1
y = ok(adm.post("settings/academic-years", json={"code": f"{sy}-{sy+1}", "label": f"{sy}-{sy+1}", "start_date": f"{sy}-09-01", "end_date": f"{sy+1}-06-30"}, headers=k()))
y = ok(adm.post(f"settings/academic-years/{y['id']}/activate", headers=k({"If-Match": str(y["version"])})))
pri = ok(adm.put("settings/sections/PRIMAIRE", json={"code": "PRIMAIRE", "label": "Primaire", "enabled": True}, headers=k()))
p1 = ok(adm.post("settings/classes", json={"academic_year_id": y["id"], "section_id": pri["id"], "reference_code": "P1", "code": "P1A", "label": "P1A"}, headers=k()))
fees = {}
for code, label, per, amount in (("SCOLARITE", "Frais scolaires", "MONTHLY", "20000"), ("TRANSPORT", "Transport", "MONTHLY", "5000"),
                                  ("FRAIS_ETAT", "Frais de l'État", "PERIODIC", "9000"), ("JOURNAL_CLASSE", "Journal de classe", "ONE_TIME", "3000"),
                                  ("ECUSSON", "Écusson", "ONE_TIME", "2000")):
    fees[code] = ok(adm.post("settings/fee-types", json={"code": code, "label": label, "periodicity": per, "default_currency": "CDF"}, headers=k()))
    ok(adm.put("settings/tariff-rules", json={"academic_year_id": y["id"], "fee_type_id": fees[code]["id"], "scope_type": "SCHOOL", "amount": amount, "currency": "CDF"}, headers=k()))
ok(adm.post("settings/admission-conditions/review", headers=k()))
ok(adm.post("settings/tariffs/apply", json={"academic_year_id": y["id"]}, headers=k()))
enr = ok(cash.post("schooling/enrollments/family", json={"primary_guardian": {"full_name": f"Tuteur {run}", "is_primary": True},
         "children": [{"last_name": f"SEQ{run}", "middle_name": "Recette", "first_name": "N3E", "gender": "F", "class_id": p1["id"]}]}, headers=k()))["enrollment_ids"][0]
ok(cash.post("finance/cash/open", json={"opening_cdf": 0, "opening_usd": 0}))

with owner.connect() as c:
    rows = [dict(r) for r in c.execute(text("""SELECT fc.id, fc.period_label, fc.due_date, fc.sequence_group, fc.net_amount, upper(ft.code) AS code FROM finance_charges fc
        JOIN fee_types ft ON ft.id=fc.fee_type_id WHERE fc.enrollment_id=:e ORDER BY fc.due_date, ft.code"""), {"e": enr}).mappings().all()]
by = lambda code: [r for r in rows if r["code"] == code]
sco, tra, etat = by("SCOLARITE"), by("TRANSPORT"), by("FRAIS_ETAT")
check("Chaîne séquentielle : scolarité mensuelle chaînée (MONTHLY:SCOLARITE)", sco and all(r["sequence_group"] == "MONTHLY:SCOLARITE" for r in sco), {r["sequence_group"] for r in sco})
check("Autre frais mensuel (transport) : non séquentiel (Desktop)", tra and all(r["sequence_group"] == "NONE" for r in tra), {r["sequence_group"] for r in tra})
check("Tranches : chaîne par frais (TERM)", etat and all(r["sequence_group"] == f"TERM:{'FRAIS_ETAT'}" for r in etat) and len(etat) == 3, len(etat))


def collect(ids, amount):
    return cash.post("finance/checkout/collect", json={"enrollment_id": enr, "charge_ids": [str(i) for i in ids], "amount": str(amount), "currency": "CDF"}, headers=k())


# recommended (no admission bundle configured): the oldest charge due today
rec = ok(cash.get(f"finance/checkout/recommended/{enr}"))
check("Action conseillée : la plus ancienne échéance exigible (jamais une future)", rec["ready"] and rec["kind"] == "ECHEANCE" and len(rec["allocations"]) == 1
      and next(r for r in rows if str(r["id"]) == rec["allocations"][0]["charge_id"])["due_date"] <= today, rec.get("label"))
r = collect([tra[2]["id"]], 5000)
check("Transport de novembre payable avant septembre et octobre (frais non séquentiel)", r.status_code in (200, 201), r.text[:120])
r = collect([sco[1]["id"]], 20000)
check("Scolarité : octobre seul refusé tant que septembre est ouvert (message Desktop)", r.status_code == 409 and "ne peut pas être encaissée avant" in r.text, r.text[:160])
r = collect([sco[0]["id"], sco[1]["id"]], 40000)
pay = r.json() if r.status_code in (200, 201) else {}
check("Scolarité : septembre + octobre sur un seul reçu (périodes consécutives)", r.status_code in (200, 201) and len(pay.get("allocations", [])) == 2, (r.status_code, r.text[:160]))
r = collect([sco[2]["id"], sco[3]["id"], sco[4]["id"]], 30000)
with owner.connect() as c:
    paid = {str(x[0]): Decimal(x[1]) for x in c.execute(text("SELECT id, paid_amount FROM finance_charges WHERE id = ANY(CAST(:ids AS uuid[]))"),
                                                       {"ids": [str(sco[2]["id"]), str(sco[3]["id"]), str(sco[4]["id"])]})}
check("Montant partiel sur 3 mois : le plus ancien soldé, le suivant partiel, le dernier intact (ordre de la chaîne)",
      r.status_code in (200, 201) and paid[str(sco[2]["id"])] == Decimal("20000") and paid[str(sco[3]["id"])] == Decimal("10000") and paid[str(sco[4]["id"])] == 0, paid)
r = collect([etat[1]["id"]], 3000)
check("Tranches : la 2e tranche avant la 1re refusée", r.status_code == 409 and "tranche" in r.text.lower(), r.text[:160])
bal = cash.get(f"finance/checkout/balance/{enr}").json()["items"]
dec = next(i for i in bal if i["id"] == str(sco[5]["id"]))
check("Caisse : chaque période indique les périodes antérieures à sélectionner avec elle", dec["requires"] == [str(sco[3]["id"]), str(sco[4]["id"])], dec["requires"])
# suggest (Desktop suggest_checkout_allocations)
sug = ok(cash.get(f"finance/checkout/suggest/{enr}", params={"amount": "11000", "currency": "CDF"}))
check("Répartition automatique : plus anciennes exigibles d'abord, jamais au-delà du dû", sum(Decimal(a["amount"]) for a in sug["allocations"]) == Decimal("11000"), sug["allocations"][:3])
r = cash.get(f"finance/checkout/suggest/{enr}", params={"amount": "99999999", "currency": "CDF"})
check("Répartition : montant supérieur aux frais exigibles refusé (message Desktop)", r.status_code == 409 and "dépasse" in r.text, r.status_code)
# fee bundle (Desktop journal + écusson)
b = ok(cash.get(f"finance/checkout/fee-bundle/{enr}"))
check("Lot journal + écusson : prêt, 5 000 CDF, deux postes", b["ready"] and b["totals"].get("CDF") == "5000.00" and len(b["items"]) == 2, b["totals"])
r = collect([i["id"] for i in b["items"]], b["totals"]["CDF"])
b2 = ok(cash.get(f"finance/checkout/fee-bundle/{enr}"))
check("Lot payé en un encaissement, sans déborder sur d'autres dettes", r.status_code in (200, 201) and not b2["items"] and len(r.json().get("allocations", [])) == 2, b2["totals"])
check("Lot inconnu : non prêt", not ok(cash.get(f"finance/checkout/fee-bundle/{enr}", params={"codes": "INEXISTANT"}))["ready"])

# a pupil without any payment, for the cash-desk UI check
ok(cash.post("schooling/enrollments/family", json={"primary_guardian": {"full_name": f"Tuteur UI {run}", "is_primary": True},
   "children": [{"last_name": f"SER{run}", "middle_name": "Recette", "first_name": "UI", "gender": "M", "class_id": p1["id"]}]}, headers=k()))
ok_n = sum(r["pass"] for r in results)
Path(__file__).with_name("checkout-rules-live.json").write_text(json.dumps({"school": school["code"], "results": results}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print(f"== {ok_n}/{len(results)} PASS -> checkout-rules-live.json")
