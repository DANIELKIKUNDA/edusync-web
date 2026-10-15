"""Live probe — parity lot L5: cash-desk rules copied from the Desktop golden master.

Desktop reference (EduSync École Offline 0.11.0-rc.1): configuration.py::save_payment_policy; finance_checkout.py: partial
payments refused when disabled, minimum deposit, future-month payments, accepted payment modes; schema payment_policy.
Fresh school, real cash desk through the public API.
"""
import json
import sys
from datetime import date
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
s = ok(platform().post("platform/schools", json={"code": f"L5-{run}", "name": f"École encaissement L5 {run}"}, headers=k()))
school = {"code": f"L5-{run}", "school_id": s["id"], "users": {}}
state.setdefault("L5", {})[run] = school
save()
ensure_user(school, "ADMIN", ("ADMIN_SYSTEME_ECOLE",))
ensure_user(school, "CASH", ("CAISSIER",))
adm, cash = user_client(school, "ADMIN"), user_client(school, "CASH")
today = date.today()
start_year = today.year if today.month >= 9 else today.year - 1
y = ok(adm.post("settings/academic-years", json={"code": f"{start_year}-{start_year+1}", "label": f"{start_year}-{start_year+1}",
                                                 "start_date": f"{start_year}-09-01", "end_date": f"{start_year+1}-06-30"}, headers=k()))
y = ok(adm.post(f"settings/academic-years/{y['id']}/activate", headers=k({"If-Match": str(y["version"])})))
pri = ok(adm.put("settings/sections/PRIMAIRE", json={"code": "PRIMAIRE", "label": "Primaire", "enabled": True}, headers=k()))
p1 = ok(adm.post("settings/classes", json={"academic_year_id": y["id"], "section_id": pri["id"], "reference_code": "P1", "code": "P1A", "label": "P1A"}, headers=k()))
sco = ok(adm.post("settings/fee-types", json={"code": "SCOLARITE", "label": "Frais scolaires", "periodicity": "MONTHLY", "default_currency": "CDF"}, headers=k()))
ok(adm.put("settings/tariff-rules", json={"academic_year_id": y["id"], "fee_type_id": sco["id"], "scope_type": "SCHOOL", "amount": "20000", "currency": "CDF"}, headers=k()))
ok(adm.post("settings/admission-conditions/review", headers=k()))  # no registration bundle in this scenario
ok(adm.post("settings/tariffs/apply", json={"academic_year_id": y["id"]}, headers=k()))
enr = ok(cash.post("schooling/enrollments/family", json={"primary_guardian": {"full_name": f"Tuteur {run}", "is_primary": True},
         "children": [{"last_name": f"PAY{run}", "middle_name": "Recette", "first_name": "L5", "gender": "M", "class_id": p1["id"]}]}, headers=k()))["enrollment_ids"][0]
if not cash.get("finance/cash/current").json().get("session"):
    ok(cash.post("finance/cash/open", json={"opening_cdf": 0, "opening_usd": 0}))


def first_due():
    items = cash.get(f"finance/checkout/balance/{enr}").json()["items"]
    return next(i for i in items if i["eligible"])


def collect(amount, mode="CASH", reference=None, ids=None, advance=False):
    c = first_due()
    return cash.post("finance/checkout/collect", json={"enrollment_id": enr, "charge_ids": ids or [c["id"]], "amount": amount, "currency": "CDF",
                                                     "mode": mode, "reference": reference, "use_anticipation": advance}, headers=k())


def policy(**v):
    cur = adm.get("settings/payment-policy").json()
    body = {k2: cur[k2] for k2 in ("partial_payments_enabled", "partial_min_amount", "partial_reporting_mode", "advance_payments_enabled",
                                    "future_charge_payments_enabled", "accepted_modes")}
    body.update(v)
    return adm.put("settings/payment-policy", json={**body, "expected_version": cur["version"]}, headers=k())


d = adm.get("settings/payment-policy").json()
check("Règles par défaut (Desktop) : acomptes, anticipé, mois futurs autorisés ; 4 modes",
      d["partial_payments_enabled"] and d["advance_payments_enabled"] and d["future_charge_payments_enabled"] and d["accepted_modes"] == ["CASH", "MOBILE_MONEY", "BANQUE", "AUTRE"], d)
check("Acompte permis par défaut", collect("5000").status_code in (200, 201))
ok(policy(partial_payments_enabled=False))
r = collect("5000")
check("Acomptes désactivés : paiement partiel refusé", r.status_code == 409 and "paiements partiels ne sont pas autorisés" in r.text, r.status_code)
check("Acomptes désactivés : solde exact accepté", collect(first_due()["remaining"]).status_code in (200, 201))
ok(policy(partial_payments_enabled=True, partial_min_amount="10000"))
r = collect("5000")
check("Acompte minimum 10 000 : 5 000 refusé", r.status_code == 409 and "acompte minimum" in r.text, r.status_code)
check("Acompte minimum 10 000 : 12 000 accepté", collect("12000").status_code in (200, 201))
def due_of(charge):
    with owner.connect() as c:
        return c.execute(text("SELECT due_date FROM finance_charges WHERE id=:i"), {"i": charge["id"]}).scalar_one()


ok(policy(future_charge_payments_enabled=False, partial_min_amount="0"))
# settle the months already due, so that the next eligible month is in the future
while due_of(first_due()) <= today:
    ok(cash.post("finance/checkout/collect", json={"enrollment_id": enr, "charge_ids": [first_due()["id"]], "amount": first_due()["remaining"], "currency": "CDF"}, headers=k()))
r = collect(first_due()["remaining"])
check("Mois futurs désactivés : paiement d'une mensualité à venir refusé", r.status_code == 409 and "mois futur" in r.text, (r.status_code, due_of(first_due())))
ok(policy(future_charge_payments_enabled=True, accepted_modes=["CASH", "BANQUE"]))
opts = cash.get("finance/checkout/payment-options").json()
check("Caisse : modes acceptés exposés (espèces, banque)", opts["accepted_modes"] == ["CASH", "BANQUE"], opts)
r = collect("5000", mode="MOBILE_MONEY", reference="MM-1")
check("Mode non accepté (Mobile Money) refusé", r.status_code == 409 and "mode de paiement n'est pas autorisé" in r.text, r.status_code)
r = collect("5000", mode="BANQUE", reference=f"VIR-{run}")
check("Mode accepté (banque) avec référence : enregistré", r.status_code in (200, 201), r.status_code)
with owner.connect() as c:
    pm = c.execute(text("SELECT payment_mode,payment_reference FROM finance_payments WHERE school_id=:s ORDER BY created_at DESC LIMIT 1"), {"s": school["school_id"]}).one()
check("Paiement : mode et référence conservés", (pm.payment_mode, pm.payment_reference) == ("BANQUE", f"VIR-{run}"), tuple(pm))
check("Mode inconnu refusé", collect("5000", mode="CHEQUE").status_code == 409)
ok(policy(advance_payments_enabled=False))
r = collect("5000", advance=True)
# Lot L6: the former surplus-as-provision path is retired from the cash desk whatever the switch; at the Desktop the switch
# gates the « fonds anticipé » (operations.py, not ported yet) and plans are collected through collect-plan.
check("Ancien chemin d'avance refusé : un plan s'encaisse selon le plan anticipé", r.status_code == 409 and "plan de paiement anticipé" in r.text, r.status_code)
check("Aucun mode autorisé : réglage refusé", policy(accepted_modes=[]).status_code == 422)
cur = adm.get("settings/payment-policy").json()
r = adm.put("settings/payment-policy", json={**{k2: cur[k2] for k2 in ("partial_payments_enabled", "partial_min_amount", "partial_reporting_mode", "advance_payments_enabled",
            "future_charge_payments_enabled", "accepted_modes")}, "expected_version": cur["version"] - 1}, headers=k())
check("Version périmée : réglage refusé (409)", r.status_code == 409, r.status_code)
check("Sans droit : le caissier ne modifie pas les règles (403)", cash.put("settings/payment-policy", json={"accepted_modes": ["CASH"]}, headers=k()).status_code == 403)
a_admin = user_client(state["A"], "ADMIN")
check("Autre école : règles par défaut, pas celles de L5", a_admin.get("settings/payment-policy").json()["accepted_modes"] != ["CASH", "BANQUE"])
with owner.connect() as c:
    audit = c.execute(text("SELECT count(*) FROM audit_events WHERE action='PAYMENT_POLICY_SAVED' AND school_id=:s"), {"s": school["school_id"]}).scalar_one()
check("Audit : chaque réglage tracé", audit == 5, audit)

passed = sum(r["pass"] for r in results)
out = Path(__file__).with_name("payment-policy-live.json")
out.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"== {passed}/{len(results)} PASS -> {out.name}")
sys.exit(0 if passed == len(results) else 1)
