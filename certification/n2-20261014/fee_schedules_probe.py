"""Live probe — parity lot L2: fee schedules and due charges copied from the Desktop golden master.

Desktop reference (EduSync École Offline 0.11.0-rc.1): configuration.py::apply_tariff_rules_to_classes,
database.py::create_fee_schedule / generate_charges_for_enrollment, operations.py (class change fail-closed once charges
exist). Runs on a fresh school created through the platform API.
"""
import json
import sys
from datetime import date
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
mgr = platform()
s = ok(mgr.post("platform/schools", json={"code": f"L2-{run}", "name": f"École échéances L2 {run}"}, headers=k()))
school = {"code": f"L2-{run}", "school_id": s["id"], "users": {}}
state.setdefault("L2", {})[run] = school
save()
ensure_user(school, "ADMIN", ("ADMIN_SYSTEME_ECOLE",))
adm = user_client(school, "ADMIN")
ensure_user(school, "OPS", ())
grant_test_role(school, "OPS", "RECETTE_INSCRIPTIONS", ("enrollments.create", "students.read", "students.class.change", "settings.structure.read"))
ops = user_client(school, "OPS")

y = ok(adm.post("settings/academic-years", json={"code": "2026-2027", "label": "2026-2027", "start_date": "2026-09-01", "end_date": "2027-06-30"}, headers=k()))
y = ok(adm.post(f"settings/academic-years/{y['id']}/activate", headers=k({"If-Match": str(y["version"])})))
pri = ok(adm.put("settings/sections/PRIMAIRE", json={"code": "PRIMAIRE", "label": "Primaire", "enabled": True}, headers=k()))


def new_class(code, ref):
    return ok(adm.post("settings/classes", json={"academic_year_id": y["id"], "section_id": pri["id"], "reference_code": ref, "code": code, "label": code}, headers=k()))


p1, p2 = new_class("P1A", "P1"), new_class("P2A", "P2")


def fee(code, periodicity):
    return ok(adm.post("settings/fee-types", json={"code": code, "label": code.title(), "periodicity": periodicity, "default_currency": "CDF"}, headers=k()))


sco, ins, eta, opt = fee("SCOLARITE", "MONTHLY"), fee("INSCRIPTION", "ONE_TIME"), fee("ETAT", "PERIODIC"), fee("UNIFORME", "OPTIONAL")


def rule(f, scope, ref, amount, status="ACTIVE", eff=None):
    return ok(adm.put("settings/tariff-rules", json={"academic_year_id": y["id"], "fee_type_id": f["id"], "scope_type": scope, "scope_ref": ref,
                                                    "amount": amount, "currency": "CDF", "status": status, "effective_from": eff}, headers=k()))


rule(sco, "SCHOOL", None, "20000")
rule(sco, "SCHOOL", None, "25000", eff="2027-02-01")       # dated increase from February
rule(ins, "SCHOOL", None, "15000")
rule(eta, "SECTION", pri["id"], "9000")
rule(opt, "SCHOOL", None, "30000")                          # optional fee: never generated automatically
rule(ins, "CLASS", p2["id"], None, status="PENDING_OFFICIAL")  # most precise rule pending: P2 gets no admission line


def enroll(class_id, name):
    r = ops.post("schooling/enrollments/family", json={"primary_guardian": {"full_name": f"Tuteur {name}", "is_primary": True},
                                                      "children": [{"last_name": name, "middle_name": "Recette", "first_name": "L2", "gender": "M", "class_id": class_id}]}, headers=k())
    return ok(r)


e_before = enroll(p1["id"], f"AVANT{run}")
check("Inscription avant application : aucun frais (pas encore d'échéance)", e_before.get("charges_created") == 0, e_before.get("charges_created"))

res = ok(adm.post("settings/tariffs/apply", json={"academic_year_id": y["id"]}, headers=k()))
check("Application : 10 mensualités + 3 tranches + 1 frais unique pour P1 ; P2 sans inscription (en attente)",
      res["monthly"] == 20 and res["tranches"] == 6 and res["single"] == 1 and res["pending_skipped"] == 1, res)
check("Application : frais dus créés pour l'élève déjà inscrit (14)", res["charges_created"] == 14, res["charges_created"])
sched = adm.get("settings/fee-schedules", params={"year_id": y["id"]}).json()
p1s = [x for x in sched if x["class_id"] == p1["id"]]
months = sorted((x["period_order"], x["period_label"], x["amount"]) for x in p1s if x["fee_label"] == "Scolarite")
check("Mensualités dans l'ordre de l'année, septembre → juin", [m[1] for m in months] == ["Septembre", "Octobre", "Novembre", "Décembre", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin"], [m[1] for m in months])
check("Règle datée de février : septembre–janvier à 20 000, février–juin à 25 000",
      [m[2] for m in months] == ["20000.00"] * 5 + ["25000.00"] * 5, [m[2] for m in months])
tr = sorted((x["period_order"], x["period_label"], x["due_date"]) for x in p1s if x["fee_label"] == "Etat")
check("Tranches : septembre, janvier, avril", [t[2] for t in tr] == ["2026-09-01", "2027-01-01", "2027-04-01"], tr)
check("Frais facultatif : aucune échéance générée", not any(x["fee_label"] == "Uniforme" for x in sched))
check("Classe P2 : la règle d'inscription en attente n'est pas remplacée par la règle de l'école",
      not any(x["fee_label"] == "Inscription" for x in sched if x["class_id"] == p2["id"]))

e_after = enroll(p1["id"], f"APRES{run}")
check("Inscription après application : les 14 frais dus sont créés automatiquement", e_after.get("charges_created") == 14, e_after.get("charges_created"))
enr_after = e_after["enrollment_ids"][0]
with owner.connect() as c:
    rows = c.execute(text("""SELECT label,net_amount,gross_amount,discount_percent,periodicity,sequence_group,sequence_order,due_date
                              FROM finance_charges WHERE enrollment_id=:e ORDER BY sequence_group NULLS FIRST,sequence_order"""), {"e": enr_after}).all()
groups = {r.sequence_group for r in rows}
check("Frais dus : groupes séquentiels par frais (mensuel et tranches), brut = net sans avantage",
      groups == {None, "MONTHLY:SCOLARITE", "TERM:ETAT"} and all(r.gross_amount == r.net_amount and r.discount_percent == 0 for r in rows), groups)

res2 = ok(adm.post("settings/tariffs/apply", json={"academic_year_id": y["id"]}, headers=k()))
check("Réapplication : rien n'est dupliqué (0 créé, mises à jour seulement)", res2["charges_created"] == 0 and res2["charges_updated"] == 28, res2)

# ---------- money already received: protected ----------
with owner.begin() as c:
    sept = c.execute(text("""SELECT fc.id FROM finance_charges fc JOIN fee_schedules s ON s.id=fc.schedule_id
                              WHERE fc.enrollment_id=:e AND s.period_code='09'"""), {"e": enr_after}).scalar_one()
    c.execute(text("UPDATE finance_charges SET paid_amount=5000 WHERE id=:id"), {"id": sept})  # test-only: simulate a cash receipt
rule(sco, "SCHOOL", None, "21000")  # same key (school, 1 Sept): amount change
r = adm.post("settings/tariffs/apply", json={"academic_year_id": y["id"]}, headers=k())
check("Échéance déjà payée : modification du montant refusée (créer une règle datée)", r.status_code == 409 and "déjà un paiement" in r.text, r.status_code)
with owner.connect() as c:
    still = c.execute(text("SELECT net_amount FROM finance_charges WHERE id=:id"), {"id": sept}).scalar_one()
check("Échec : transaction annulée, le frais payé garde son montant", str(still) == "20000.00", still)
rule(sco, "SCHOOL", None, "20000")  # restore

# ---------- class change fail-closed once charges exist ----------
stu = e_after["student_ids"][0]
r = ops.post(f"schooling/students/{stu}/class-change", json={"class_id": p2["id"], "effective_date": date.today().isoformat(), "reason": "Recette L2"}, headers=k())
check("Changement de classe bloqué quand des frais dus existent (Desktop)", r.status_code == 409 and "politique de transfert financier" in r.text, r.status_code)

# ---------- isolation / permissions / closed year ----------
a_admin = user_client(state["A"], "ADMIN")
check("Autre école : application sur l'année de L2 refusée", a_admin.post("settings/tariffs/apply", json={"academic_year_id": y["id"]}, headers=k()).status_code in (404, 409))
check("Sans droit « appliquer les barèmes » : refus (403)", ops.post("settings/tariffs/apply", json={"academic_year_id": y["id"]}, headers=k()).status_code == 403)
yy = next(x for x in adm.get("settings/academic-years").json() if x["id"] == y["id"])
ok(adm.post(f"settings/academic-years/{y['id']}/close", headers=k({"If-Match": str(yy["version"])})))
check("Année clôturée : application refusée", adm.post("settings/tariffs/apply", json={"academic_year_id": y["id"]}, headers=k()).status_code == 409)
with owner.connect() as c:
    audit = c.execute(text("SELECT count(*) FROM audit_events WHERE action='TARIFFS_APPLIED' AND school_id=:s"), {"s": school["school_id"]}).scalar_one()
check("Audit : chaque application réussie est tracée", audit == 2, audit)

passed = sum(r["pass"] for r in results)
out = Path(__file__).with_name("fee-schedules-live.json")
out.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"== {passed}/{len(results)} PASS -> {out.name}")
sys.exit(0 if passed == len(results) else 1)
