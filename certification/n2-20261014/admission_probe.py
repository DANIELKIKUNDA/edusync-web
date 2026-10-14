"""Live probe — parity lot L4: admission conditions and the registration bundle, copied from the Desktop golden master.

Desktop reference (EduSync École Offline 0.11.0-rc.1): configuration.py (upsert_enrollment_policy_item,
set_enrollment_policy_item_active, mark_enrollment_policy_reviewed), terrain.py (registration_bundle_codes,
registration_bundle_due: SCOLARITE = month required at enrollment; legacy INSCRIPTION + June until the rubric is
validated), finance_checkout.py ("Les obligations exigées à l'inscription doivent être soldées avant les autres frais").
Fresh school, real cash desk through the public API.
"""
import json
import sys
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
s = ok(platform().post("platform/schools", json={"code": f"L4-{run}", "name": f"École admission L4 {run}"}, headers=k()))
school = {"code": f"L4-{run}", "school_id": s["id"], "users": {}}
state.setdefault("L4", {})[run] = school
save()
ensure_user(school, "ADMIN", ("ADMIN_SYSTEME_ECOLE",))
ensure_user(school, "CASH", ("CAISSIER",))
adm, cash = user_client(school, "ADMIN"), user_client(school, "CASH")

y = ok(adm.post("settings/academic-years", json={"code": "2026-2027", "label": "2026-2027", "start_date": "2026-09-01", "end_date": "2027-06-30"}, headers=k()))
y = ok(adm.post(f"settings/academic-years/{y['id']}/activate", headers=k({"If-Match": str(y["version"])})))
pri = ok(adm.put("settings/sections/PRIMAIRE", json={"code": "PRIMAIRE", "label": "Primaire", "enabled": True}, headers=k()))
p1 = ok(adm.post("settings/classes", json={"academic_year_id": y["id"], "section_id": pri["id"], "reference_code": "P1", "code": "P1A", "label": "P1A"}, headers=k()))
p2 = ok(adm.post("settings/classes", json={"academic_year_id": y["id"], "section_id": pri["id"], "reference_code": "P2", "code": "P2A", "label": "P2A"}, headers=k()))
fees = {}
for code, per, amount in (("INSCRIPTION", "ONE_TIME", "15000"), ("SCOLARITE", "MONTHLY", "20000"), ("MANUELS", "ONE_TIME", "8000")):
    fees[code] = ok(adm.post("settings/fee-types", json={"code": code, "label": code.title(), "periodicity": per, "default_currency": "CDF"}, headers=k()))
    ok(adm.put("settings/tariff-rules", json={"academic_year_id": y["id"], "fee_type_id": fees[code]["id"], "scope_type": "SCHOOL", "amount": amount, "currency": "CDF"}, headers=k()))
bp = adm.get("settings/billing-policy").json()
ok(adm.put("settings/billing-policy", json={"billing_months": bp["billing_months"], "month_due_at_enrollment": "09", "expected_version": bp["version"]}, headers=k()))
ok(adm.post("settings/tariffs/apply", json={"academic_year_id": y["id"]}, headers=k()))


def enroll(name, class_id=None):
    d = ok(cash.post("schooling/enrollments/family", json={"primary_guardian": {"full_name": f"Tuteur {name}", "is_primary": True},
            "children": [{"last_name": name, "middle_name": "Recette", "first_name": "L4", "gender": "F", "class_id": class_id or p1["id"]}]}, headers=k()))
    return d["enrollment_ids"][0]


def bundle(e):
    return cash.get(f"finance/checkout/registration-bundle/{e}").json()


def charges(e):
    items = cash.get(f"finance/checkout/balance/{e}").json()["items"]
    return {i["label"]: i for i in items}


# ---------- legacy bundle until the rubric is validated ----------
e1 = enroll(f"LEG{run}")
b = bundle(e1)
check("Sans condition ni validation : lot historique Inscription + mensualité de juin (Desktop)",
      b["bundle"] == [{"fee_code": "INSCRIPTION", "month": None}, {"fee_code": "SCOLARITE", "month": "06"}] and b["ready"], b["bundle"])
r = ok(adm.post("settings/admission-conditions/review", headers=k()))
check("Rubrique validée sans condition : plus aucun lot exigé", bundle(e1)["bundle"] == [] and r.get("reviewed_at"), bundle(e1)["bundle"])


# ---------- configured conditions ----------
def cond(label, fee_code, timing="AT_ENROLLMENT", scope="SCHOOL", ref=None, required=True):
    return adm.put("settings/admission-conditions", json={"academic_year_id": y["id"], "label": label, "fee_type_id": fees[fee_code]["id"] if fee_code else None,
                                                          "required": required, "payment_timing": timing, "scope_type": scope, "scope_ref": ref}, headers=k())


c_ins = ok(cond("Frais d'inscription", "INSCRIPTION"))
c_sco = ok(cond("1re mensualité exigée", "SCOLARITE"))
ok(cond("Manuels (après l'inscription)", "MANUELS", timing="AFTER_ENROLLMENT"))
ok(cond("Uniforme P2 seulement", "MANUELS", scope="CLASS", ref=p2["id"]))
ok(cond("Dossier (facultatif)", "MANUELS", required=False))
check("Condition invalide (portée sans cible) refusée", cond("Mauvaise portée", "INSCRIPTION", scope="SECTION").status_code in (409, 422))
e2 = enroll(f"CON{run}")
b2 = bundle(e2)
check("Lot d'inscription P1 (ordre Desktop : ordre puis libellé) : mensualité de septembre (mois exigé) + inscription, rien d'autre",
      b2["bundle"] == [{"fee_code": "SCOLARITE", "month": "09"}, {"fee_code": "INSCRIPTION", "month": None}] and b2["totals"] == {"CDF": "35000.00"}, (b2["bundle"], b2["totals"]))
ch = charges(e2)
ins, sept, man = ch["Inscription"], ch["Scolarite — Septembre"], ch["Manuels"]

# ---------- cash desk: bundle first ----------
if not cash.get("finance/cash/current").json().get("session"):
    ok(cash.post("finance/cash/open", json={"opening_cdf": 0, "opening_usd": 0}))


def collect(e, ids, amount):
    return cash.post("finance/checkout/collect", json={"enrollment_id": e, "charge_ids": ids, "amount": amount, "currency": "CDF"}, headers=k())


r = collect(e2, [man["id"]], "8000")
check("Caisse : un autre frais avant le lot d'inscription est refusé", r.status_code == 409 and "obligations exigées à l'inscription" in r.text, r.status_code)
r = collect(e2, [ins["id"], sept["id"], man["id"]], "20000")
check("Caisse : lot non couvert par le montant (autres frais sélectionnés) refusé", r.status_code == 409, r.status_code)
r = collect(e2, [ins["id"], sept["id"], man["id"]], "43000")
check("Caisse : un seul encaissement qui solde le lot et un autre frais est accepté", r.status_code in (200, 201), r.status_code)
e3 = enroll(f"PART{run}")
c3 = charges(e3)
r = collect(e3, [c3["Inscription"]["id"]], "15000")
check("Caisse : payer une partie du lot seul est accepté", r.status_code in (200, 201), r.status_code)
r = collect(e3, [c3["Manuels"]["id"]], "8000")
check("Caisse : tant que septembre (lot) reste dû, les manuels sont refusés", r.status_code == 409, r.status_code)
ok(adm.post(f"settings/admission-conditions/{c_sco['id']}/active", json={"active": False}, headers=k()))
check("Condition retirée : le lot ne contient plus que l'inscription", bundle(e3)["bundle"] == [{"fee_code": "INSCRIPTION", "month": None}])
r = collect(e3, [c3["Manuels"]["id"]], "8000")
check("Caisse : lot soldé, les manuels sont acceptés", r.status_code in (200, 201), r.status_code)

# ---------- scope, permissions, isolation, audit ----------
e4 = enroll(f"P2{run}", p2["id"])
check("Classe P2 : la condition propre à P2 entre dans son lot (et pas dans celui de P1)",
      bundle(e4)["bundle"] == [{"fee_code": "INSCRIPTION", "month": None}, {"fee_code": "MANUELS", "month": None}], bundle(e4)["bundle"])
check("Sans droit : validation de la rubrique refusée (403)", cash.post("settings/admission-conditions/review", headers=k()).status_code == 403)
check("Sans droit : retrait d'une condition refusé (403)", cash.post(f"settings/admission-conditions/{c_ins['id']}/active", json={"active": False}, headers=k()).status_code == 403)
a_admin = user_client(state["A"], "ADMIN")
check("Autre école : aucune condition de L4 visible", a_admin.get("settings/admission-conditions", params={"year_id": y["id"]}).json()["items"] == [])
with owner.connect() as c:
    acts = dict(c.execute(text("""SELECT action,count(*) FROM audit_events WHERE school_id=:s AND action LIKE 'ADMISSION_%' GROUP BY action"""), {"s": school["school_id"]}).all())
check("Audit : conditions, retrait et validation tracés", acts.get("ADMISSION_CONDITION_SAVED", 0) >= 5 and acts.get("ADMISSION_CONDITION_DEACTIVATED") == 1
      and acts.get("ADMISSION_CONDITIONS_REVIEWED") == 1, acts)

passed = sum(r["pass"] for r in results)
out = Path(__file__).with_name("admission-live.json")
out.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"== {passed}/{len(results)} PASS -> {out.name}")
sys.exit(0 if passed == len(results) else 1)
