"""Live probe — parity lot L3: benefit policies copied from the Desktop golden master.

Desktop reference (EduSync École Offline 0.11.0-rc.1): configuration.py::save_benefit_policy; schooling.py: _policy_for,
_discount_from_policy, beneficiary limits and no-cumulation at enrollment; database.py::generate_charges_for_enrollment
(discount on the charge of the benefit's fee code); domain/benefits.py::apply_discount. Fresh school.
"""
import json
import sys
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
s = ok(platform().post("platform/schools", json={"code": f"L3-{run}", "name": f"École avantages L3 {run}"}, headers=k()))
school = {"code": f"L3-{run}", "school_id": s["id"], "users": {}}
state.setdefault("L3", {})[run] = school
save()
ensure_user(school, "ADMIN", ("ADMIN_SYSTEME_ECOLE",))
adm = user_client(school, "ADMIN")
ensure_user(school, "OPS", ())
grant_test_role(school, "OPS", "RECETTE_INSCRIPTIONS", ("enrollments.create", "students.read", "settings.structure.read", "personnel.create", "personnel.read"))
ops = user_client(school, "OPS")

y = ok(adm.post("settings/academic-years", json={"code": "2026-2027", "label": "2026-2027", "start_date": "2026-09-01", "end_date": "2027-06-30"}, headers=k()))
y = ok(adm.post(f"settings/academic-years/{y['id']}/activate", headers=k({"If-Match": str(y["version"])})))
pri = ok(adm.put("settings/sections/PRIMAIRE", json={"code": "PRIMAIRE", "label": "Primaire", "enabled": True}, headers=k()))
cls = ok(adm.post("settings/classes", json={"academic_year_id": y["id"], "section_id": pri["id"], "reference_code": "P3", "code": "P3A", "label": "P3A"}, headers=k()))
sco = ok(adm.post("settings/fee-types", json={"code": "SCOLARITE", "label": "Frais scolaires", "periodicity": "MONTHLY", "default_currency": "CDF"}, headers=k()))
ins = ok(adm.post("settings/fee-types", json={"code": "INSCRIPTION", "label": "Inscription", "periodicity": "ONE_TIME", "default_currency": "CDF"}, headers=k()))
for f, amount in ((sco, "20000"), (ins, "15000")):
    ok(adm.put("settings/tariff-rules", json={"academic_year_id": y["id"], "fee_type_id": f["id"], "scope_type": "SCHOOL", "amount": amount, "currency": "CDF"}, headers=k()))
ok(adm.post("settings/tariffs/apply", json={"academic_year_id": y["id"]}, headers=k()))
staff = ok(ops.post("personnel", json={"employee_no": f"AG{run}", "last_name": "AGENT", "first_name": "Recette", "category": "ENSEIGNANT"}, headers=k()))


def child(name, **extra):
    return {"last_name": name, "middle_name": "Recette", "first_name": "L3", "gender": "F", "class_id": cls["id"], **extra}


def enroll(children, family_id=None):
    body = {"children": children}
    body["family_id" if family_id else "primary_guardian"] = family_id or {"full_name": f"Tuteur {run}", "is_primary": True}
    return ops.post("schooling/enrollments/family", json=body, headers=k())


def policy(kind, **values):
    return adm.put(f"settings/benefit-policies/{kind}", json={"academic_year_id": y["id"], **values}, headers=k())


# ---------- policy disabled: no beneficiary ----------
r = enroll([child(f"SEUL{run}", large_family_beneficiary=True)])
check("Politique non activée : bénéficiaire Famille nombreuse refusé", r.status_code == 409 and "n'est pas activée" in r.text, r.status_code)
pv = ops.get("schooling/enrollment-benefits").json()
check("Aperçu à l'inscription : aucune politique active", pv["large_family"] is None and pv["staff_child"] is None, pv)

# ---------- large family: threshold, limit, discount ----------
r = policy("LARGE_FAMILY", enabled=True, min_children=3, free_beneficiaries=1, discount_percent="0", applies_to_fee_code="SCOLARITE")
check("Politique Famille nombreuse enregistrée (seuil 3, 1 gratuit, frais scolaires)", r.status_code == 200 and r.json()["min_children"] == 3, r.status_code)
pv = ops.get("schooling/enrollment-benefits").json()
check("Aperçu : famille nombreuse dès 3 enfants, 1 bénéficiaire, 100 %", pv["large_family"] == {"min_children": 3, "beneficiary_limit": 1, "discount_percent": "100", "fee_code": "SCOLARITE"}, pv["large_family"])
r = enroll([child(f"A{run}", large_family_beneficiary=True), child(f"B{run}")])
check("Seuil non atteint (2 enfants < 3) : refusé, rien n'est enregistré", r.status_code == 409 and "seuil" in r.text, r.status_code)
r = enroll([child(f"A{run}", large_family_beneficiary=True), child(f"B{run}", large_family_beneficiary=True), child(f"C{run}")])
check("Deux bénéficiaires alors qu'1 seul est permis : refusé", r.status_code == 409 and "ne peut avoir que 1" in r.text, r.status_code)
r = enroll([child(f"A{run}", large_family_beneficiary=True), child(f"B{run}"), child(f"C{run}")])
d = ok(r)
fam = d["family_id"]
benef_enr, other_enr = d["enrollment_ids"][0], d["enrollment_ids"][1]
with owner.connect() as c:
    def charges(e):
        return c.execute(text("""SELECT f.code,fc.gross_amount,fc.discount_percent,fc.discount_amount,fc.net_amount FROM finance_charges fc
                                  JOIN fee_types f ON f.id=fc.fee_type_id WHERE fc.enrollment_id=:e"""), {"e": e}).all()
    bc, oc = charges(benef_enr), charges(other_enr)
    stored = c.execute(text("SELECT kind,configured_percent,applies_to_fee_code FROM student_benefits WHERE student_id=:s"), {"s": d["student_ids"][0]}).all()
sco_b = [x for x in bc if x.code == "SCOLARITE"]
check("Bénéficiaire : rate figé sur l'élève (100 %, frais scolaires)", [(x.kind, str(x.configured_percent), x.applies_to_fee_code) for x in stored] == [("LARGE_FAMILY", "100.00", "SCOLARITE")], stored)
check("Bénéficiaire : 10 mensualités brutes 20 000, réduction 100 %, net 0",
      len(sco_b) == 10 and all(str(x.gross_amount) == "20000.00" and str(x.discount_percent) == "100.00" and str(x.net_amount) == "0.00" for x in sco_b), sco_b[:2])
check("Bénéficiaire : l'inscription (autre frais) reste due en entier", any(x.code == "INSCRIPTION" and str(x.net_amount) == "15000.00" for x in bc))
check("Frère non bénéficiaire : aucun rabais", all(str(x.discount_percent) == "0.00" for x in oc) and len(oc) == 11, len(oc))
r = enroll([child(f"D{run}", large_family_beneficiary=True)], family_id=fam)
check("Même foyer, 2e bénéficiaire la même année : refusé (plafond)", r.status_code == 409 and "ne peut avoir que 1" in r.text, r.status_code)

# ---------- staff child: limit per agent, discount, no cumulation ----------
policy("STAFF_CHILD", enabled=True, max_beneficiaries=1, discount_percent="50", free_beneficiaries=0, applies_to_fee_code="SCOLARITE")
pv = ops.get("schooling/enrollment-benefits").json()
check("Aperçu : enfants du personnel 50 %, agent proposé", pv["staff_child"]["discount_percent"] == "50.00" and any(m["id"] == staff["id"] for m in pv["staff"]), pv["staff_child"])
r = enroll([child(f"E{run}", staff_member_id=staff["id"], staff_beneficiary=True, large_family_beneficiary=True)])
check("Cumul famille nombreuse + personnel sur le même élève : refusé", r.status_code == 409 and "cumuler" in r.text, r.status_code)
r = enroll([child(f"F{run}", staff_member_id=staff["id"], staff_beneficiary=True)])
e_staff = ok(r)["enrollment_ids"][0]
with owner.connect() as c:
    sc = c.execute(text("""SELECT fc.discount_percent,fc.net_amount FROM finance_charges fc JOIN fee_types f ON f.id=fc.fee_type_id
                            WHERE fc.enrollment_id=:e AND f.code='SCOLARITE'"""), {"e": e_staff}).all()
check("Enfant du personnel : mensualités à 50 % (net 10 000)", sc and all(str(x.discount_percent) == "50.00" and str(x.net_amount) == "10000.00" for x in sc), sc[:2])
r = enroll([child(f"G{run}", staff_member_id=staff["id"], staff_beneficiary=True)])
check("Plafond par agent (1) : un 2e enfant bénéficiaire refusé", r.status_code == 409 and "Cet agent ne peut avoir que 1" in r.text, r.status_code)
r = enroll([child(f"H{run}", staff_beneficiary=True)])
check("Bénéficiaire du personnel sans agent : refusé", r.status_code == 409, r.status_code)

# ---------- rate frozen at selection; permissions; isolation; closed year ----------
policy("STAFF_CHILD", enabled=True, max_beneficiaries=1, discount_percent="70", expected_version=None)
ok(adm.post("settings/tariffs/apply", json={"academic_year_id": y["id"]}, headers=k()))
with owner.connect() as c:
    again = c.execute(text("""SELECT DISTINCT fc.discount_percent FROM finance_charges fc JOIN fee_types f ON f.id=fc.fee_type_id
                               WHERE fc.enrollment_id=:e AND f.code='SCOLARITE'"""), {"e": e_staff}).all()
check("Changement de politique : le taux de l'élève déjà choisi reste figé (50 %)", [str(x[0]) for x in again] == ["50.00"], again)
check("Pourcentage hors 0–100 refusé", policy("LARGE_FAMILY", enabled=True, discount_percent="120").status_code == 422)
check("Sans droit « avantages » : réglage refusé (403)", ops.put(f"settings/benefit-policies/LARGE_FAMILY", json={"academic_year_id": y["id"], "enabled": False}, headers=k()).status_code == 403)
a_admin = user_client(state["A"], "ADMIN")
check("Autre école : aucune politique de L3 visible", a_admin.get("settings/benefit-policies", params={"year_id": y["id"]}).json() == [])
with owner.connect() as c:
    audit = c.execute(text("SELECT count(*) FROM audit_events WHERE action='BENEFIT_POLICY_SAVED' AND school_id=:s"), {"s": school["school_id"]}).scalar_one()
check("Audit : chaque réglage de politique est tracé", audit == 3, audit)

passed = sum(r["pass"] for r in results)
out = Path(__file__).with_name("benefits-live.json")
out.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"== {passed}/{len(results)} PASS -> {out.name}")
sys.exit(0 if passed == len(results) else 1)
