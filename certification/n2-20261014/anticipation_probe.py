"""Live probe — parity lot L6: payment plans (« plans de paiement anticipé ») copied from the Desktop golden master.

Desktop reference (EduSync École Offline 0.11.0-rc.1): app/db/anticipation.py (save_anticipation_plan,
set_anticipation_membership, _split_equal, anticipation_payment_preview, record_monthly_payment_with_anticipation),
app/db/financial_decisions.py::apply_lifecycle_to_future_charges. Doctrine: Plan anticipé ≠ Fonds anticipé.
Owner-required parity cases: optional plan, mandatory plan, several target months, month already paid, rounding,
CDF/USD without implicit conversion, tariff change after membership, abandon / transfer / exemption, change of year,
no allocation to a month the plan does not name. Fresh school, real cash desk.
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
    assert r.status_code in codes, (r.request.method, str(r.request.url)[-80:], r.status_code, r.text[:300])
    return r.json()


run = uuid4().hex[:5].upper()
s = ok(platform().post("platform/schools", json={"code": f"L6-{run}", "name": f"École plans L6 {run}"}, headers=k()))
school = {"code": f"L6-{run}", "school_id": s["id"], "users": {}}
state.setdefault("L6", {})[run] = school
save()
ensure_user(school, "ADMIN", ("ADMIN_SYSTEME_ECOLE",))
ensure_user(school, "CASH", ("CAISSIER",))
ensure_user(school, "PLANS", ())
# finance.anticipation_plans.manage is held by no standard role (owner decision pending): test-only role.
grant_test_role(school, "PLANS", "RECETTE_PLANS", ("finance.anticipation_plans.manage", "finance.anticipation_plans.read", "settings.tariffs.read",
                                                  "settings.academic_year.read", "settings.fee_types.read", "settings.structure.read"))  # what a plan manager needs to fill the form
ensure_user(school, "DECIDE", ())
grant_test_role(school, "DECIDE", "RECETTE_DECISIONS", ("finance.decisions.create", "students.lifecycle.abandon", "students.lifecycle.transfer",
                                                        "students.lifecycle.reintegrate", "students.read"))
adm, cash, plans, dec = user_client(school, "ADMIN"), user_client(school, "CASH"), user_client(school, "PLANS"), user_client(school, "DECIDE")

today = date.today()
sy = today.year if today.month >= 9 else today.year - 1
y = ok(adm.post("settings/academic-years", json={"code": f"{sy}-{sy+1}", "label": f"{sy}-{sy+1}", "start_date": f"{sy}-09-01", "end_date": f"{sy+1}-06-30"}, headers=k()))
y = ok(adm.post(f"settings/academic-years/{y['id']}/activate", headers=k({"If-Match": str(y["version"])})))
y2 = ok(adm.post("settings/academic-years", json={"code": f"{sy+1}-{sy+2}", "label": f"{sy+1}-{sy+2}", "start_date": f"{sy+1}-09-01", "end_date": f"{sy+2}-06-30"}, headers=k()))
pri = ok(adm.put("settings/sections/PRIMAIRE", json={"code": "PRIMAIRE", "label": "Primaire", "enabled": True}, headers=k()))
p1 = ok(adm.post("settings/classes", json={"academic_year_id": y["id"], "section_id": pri["id"], "reference_code": "P1", "code": "P1A", "label": "P1A"}, headers=k()))
sco = ok(adm.post("settings/fee-types", json={"code": "SCOLARITE", "label": "Frais scolaires", "periodicity": "MONTHLY", "default_currency": "CDF"}, headers=k()))
ins = ok(adm.post("settings/fee-types", json={"code": "INSCRIPTION", "label": "Inscription", "periodicity": "ONE_TIME", "default_currency": "CDF"}, headers=k()))
ok(adm.put("settings/tariff-rules", json={"academic_year_id": y["id"], "fee_type_id": sco["id"], "scope_type": "SCHOOL", "amount": "40000", "currency": "CDF"}, headers=k()))
ok(adm.put("settings/tariff-rules", json={"academic_year_id": y["id"], "fee_type_id": sco["id"], "scope_type": "SCHOOL", "amount": "55000", "currency": "CDF",
                                          "effective_from": f"{sy+1}-05-01"}, headers=k()))   # May and June cost more (Desktop example)
ok(adm.put("settings/tariff-rules", json={"academic_year_id": y["id"], "fee_type_id": ins["id"], "scope_type": "SCHOOL", "amount": "15000", "currency": "USD"}, headers=k()))
ok(adm.post("settings/admission-conditions/review", headers=k()))
ok(adm.post("settings/tariffs/apply", json={"academic_year_id": y["id"]}, headers=k()))
if not cash.get("finance/cash/current").json().get("session"):
    ok(cash.post("finance/cash/open", json={"opening_cdf": 0, "opening_usd": 0}))


def enroll(name):
    d = ok(cash.post("schooling/enrollments/family", json={"primary_guardian": {"full_name": f"Tuteur {name}", "is_primary": True},
            "children": [{"last_name": name, "middle_name": "Recette", "first_name": "L6", "gender": "M", "class_id": p1["id"]}]}, headers=k()))
    return d["enrollment_ids"][0], d["student_ids"][0]


def plan(name, targets, contributions, mode="OPTIONAL", year=None, **extra):
    return plans.put("settings/anticipation-plans", json={"academic_year_id": (year or y)["id"], "name": name, "fee_type_id": sco["id"],
                                                         "target_months": targets, "contribution_months": contributions, "participation_mode": mode,
                                                         "effective_from": f"{sy}-09-01" if (year or y) is y else f"{sy+1}-09-01", **extra}, headers=k())


def member(e, pid, status="ENROLLED"):
    return cash.post(f"finance/checkout/anticipation-plans/{pid}/membership", json={"enrollment_id": e, "status": status}, headers=k())


def pay_plan(e, pid, month, amount, currency="CDF"):
    return cash.post("finance/checkout/collect-plan", json={"enrollment_id": e, "plan_id": pid, "contribution_month": month, "amount": amount, "currency": currency}, headers=k())


def charges(e):
    with owner.connect() as c:
        return {r.month: r for r in c.execute(text("""SELECT s.period_code AS month,fc.id,fc.net_amount,fc.paid_amount,fc.status FROM finance_charges fc
            JOIN fee_schedules s ON s.id=fc.schedule_id WHERE fc.enrollment_id=:e AND s.fee_type_id=:f"""), {"e": e, "f": sco["id"]}).all()}


# ---------- plan rules ----------
check("Plan : un mois cible ne peut pas être aussi un mois de contribution", plan("Mauvais", ["05"], ["05", "01"]).status_code == 409)
check("Plan : frais non mensuel refusé", plans.put("settings/anticipation-plans", json={"academic_year_id": y["id"], "name": "Plan inscription", "fee_type_id": ins["id"],
      "target_months": ["05"], "contribution_months": ["01"]}, headers=k()).status_code == 409)
check("Sans droit « gérer les plans » (caissier) : création refusée (403)", cash.put("settings/anticipation-plans", json={"academic_year_id": y["id"], "name": "Plan administrateur",
      "fee_type_id": sco["id"], "target_months": ["05"], "contribution_months": ["01"]}, headers=k()).status_code == 403)
opt = ok(plan("Mai-Juin étalés (facultatif)", ["05", "06"], ["01", "02", "03"]))
man = ok(plan("Juin anticipé (obligatoire)", ["06"], ["02", "03", "04"], mode="MANDATORY"))

# ---------- 1. optional plan ----------
e1, s1 = enroll(f"OPT{run}")
r = pay_plan(e1, opt["id"], "01", "40000")
check("Plan facultatif : sans adhésion, encaissement selon le plan refusé", r.status_code == 409 and "n'adhère pas" in r.text, r.status_code)
m1 = ok(member(e1, opt["id"]))
with owner.connect() as c:
    inst = [tuple(x) for x in c.execute(text("SELECT contribution_month,planned_amount FROM anticipation_installments WHERE membership_id=:m ORDER BY sort_order"), {"m": m1["id"]}).all()]
# ---------- 5. rounding: 110 000 over 3 months ----------
check("Adhésion : cible figée = mai + juin restants (110 000)", Decimal(str(m1["snapshot_target_amount"])) == Decimal("110000.00"), m1["snapshot_target_amount"])
check("Arrondis (Desktop) : 110 000 / 3 = 36 666,67 + 36 666,67 + 36 666,66", [(mo, str(a)) for mo, a in inst] == [("01", "36666.67"), ("02", "36666.67"), ("03", "36666.66")], inst)
pv = cash.get(f"finance/checkout/anticipation-plans/{opt['id']}/preview", params={"enrollment_id": e1, "month": "01"}).json()
check("Aperçu janvier : mois courant 40 000 + part du plan 36 666,67", pv["current_due"] == "40000.00" and pv["suggested_extra"] == "36666.67" and pv["suggested_total"] == "76666.67", pv.get("suggested_total"))
# ---------- 3. several target months: current month first, then the plan's targets in order ----------
r = ok(pay_plan(e1, opt["id"], "01", "76666.67"))
ch = charges(e1)
check("Paiement de janvier : janvier soldé puis mai alimenté (mois cibles dans l'ordre du plan)",
      str(ch["01"].paid_amount) == "40000.00" and str(ch["05"].paid_amount) == "36666.67" and str(ch["06"].paid_amount) == "0.00", (ch["01"].paid_amount, ch["05"].paid_amount, ch["06"].paid_amount))
with owner.connect() as c:
    links = [tuple(x) for x in c.execute(text("SELECT target_month,amount FROM anticipation_payment_links WHERE payment_id=:p"), {"p": r["id"]}).all()]
check("Traçabilité : allocation vers mai liée à l'adhésion", links == [("05", Decimal("36666.67"))], links)
# ---------- 10. never a month the plan does not name ----------
r = pay_plan(e1, opt["id"], "02", "200000")
check("Montant au-delà du mois courant et des mois cibles : refusé, aucun autre mois alimenté", r.status_code == 409 and "aucun autre mois" in r.text, r.status_code)
r = pay_plan(e1, opt["id"], "04", "10000")
check("Mois hors période de contribution : refusé", r.status_code == 409 and "période de contribution" in r.text, r.status_code)
ch = charges(e1)
check("Après les refus : février, mars, avril intacts (aucune allocation non prévue)", all(str(ch[m].paid_amount) == "0.00" for m in ("02", "03", "04")))
# ---------- 6. CDF/USD without implicit conversion ----------
r = pay_plan(e1, opt["id"], "02", "50", currency="USD")
check("Devise : paiement USD sur un plan CDF refusé (aucune conversion)", r.status_code == 409 and "conversion" in r.text, r.status_code)

# ---------- 2. mandatory plan: automatic membership ----------
e2, _ = enroll(f"MAN{run}")
r = ok(pay_plan(e2, man["id"], "02", "58333.34"))
st = cash.get(f"finance/checkout/anticipation-plans/{e2}").json()["items"]
mm = next(p for p in st if p["id"] == man["id"])
check("Plan obligatoire : adhésion automatique au premier paiement", mm["membership"] and mm["membership"]["status"] == "ENROLLED", mm["membership"])
ch2 = charges(e2)
check("Plan obligatoire : février soldé, 18 333,34 vers juin", str(ch2["02"].paid_amount) == "40000.00" and str(ch2["06"].paid_amount) == "18333.34", (ch2["02"].paid_amount, ch2["06"].paid_amount))

# ---------- 4. month already paid before joining ----------
e3, _ = enroll(f"PAYE{run}")
may3 = charges(e3)["05"]
ok(cash.post("finance/checkout/collect", json={"enrollment_id": e3, "charge_ids": [str(charges(e3)["09"].id)], "amount": "40000", "currency": "CDF"}, headers=k()))
with owner.begin() as c:   # test-only: May already partially settled before the membership (e.g. an earlier receipt)
    c.execute(text("UPDATE finance_charges SET paid_amount=25000 WHERE id=:i"), {"i": may3.id})
m3 = ok(member(e3, opt["id"]))
check("Mois déjà payé : la cible ne reprend que le reste (30 000 + 55 000 = 85 000)", Decimal(str(m3["snapshot_target_amount"])) == Decimal("85000.00"), m3["snapshot_target_amount"])

# ---------- 7. tariff change after membership: the membership snapshot stays, the live remaining follows ----------
e4, _ = enroll(f"TARIF{run}")
m4 = ok(member(e4, opt["id"]))
ok(adm.put("settings/tariff-rules", json={"academic_year_id": y["id"], "fee_type_id": sco["id"], "scope_type": "SCHOOL", "amount": "60000", "currency": "CDF",
                                          "effective_from": f"{sy+1}-05-01"}, headers=k()))
r = adm.post("settings/tariffs/apply", json={"academic_year_id": y["id"]}, headers=k())
check("Changement de tarif : refusé tant que mai a déjà reçu de l'argent (élève 1)", r.status_code == 409 and "déjà un paiement" in r.text, r.status_code)
ok(adm.put("settings/tariff-rules", json={"academic_year_id": y["id"], "fee_type_id": sco["id"], "scope_type": "SCHOOL", "amount": "55000", "currency": "CDF",
                                          "effective_from": f"{sy+1}-05-01"}, headers=k()))
pv4 = cash.get(f"finance/checkout/anticipation-plans/{opt['id']}/preview", params={"enrollment_id": e4, "month": "01"}).json()
check("Adhésion : échéancier figé, part proposée jamais supérieure au reste réel des mois cibles",
      Decimal(pv4["suggested_extra"]) <= Decimal(pv4["remaining_target"]) and Decimal(str(m4["snapshot_target_amount"])) == Decimal("110000.00"), (pv4["suggested_extra"], pv4["remaining_target"]))

# ---------- 8. exemption / abandon / transfer ----------
e5, s5 = enroll(f"EXO{run}")
ok(member(e5, opt["id"]))
ok(dec.post("finance/controls/decisions", json={"enrollment_id": e5, "charge_id": str(charges(e5)["05"].id), "decision_type": "EXEMPTION", "currency": "CDF",
                                       "amount": "55000", "reason": "Exonération de mai (recette L6)", "effective_date": today.isoformat()}, headers=k()))
ok(pay_plan(e5, opt["id"], "01", "76666.67"))
ch5 = charges(e5)
check("Exonération : mai exonéré n'est pas alimenté, la part va sur juin", str(ch5["05"].paid_amount) == "0.00" and str(ch5["06"].paid_amount) == "36666.67",
      (ch5["05"].paid_amount, ch5["06"].paid_amount))
e6, s6 = enroll(f"ABAN{run}")
ok(member(e6, opt["id"]))
stu6 = dec.get(f"schooling/students/{s6}").json()
ok(dec.post(f"schooling/students/{s6}/abandon", json={"effective_date": f"{sy+1}-01-15", "reason": "Abandon (recette L6)"},
            headers=k({"If-Match": str(stu6.get("version", 1))})))
ch6 = charges(e6)
check("Abandon : les mois futurs non payés sont neutralisés (Desktop), l'historique reste", ch6["05"].status == "CANCELLED" and ch6["06"].status == "CANCELLED"
      and ch6["09"].status == "ACTIVE", {m: ch6[m].status for m in ("09", "01", "02", "05", "06")})
r = pay_plan(e6, opt["id"], "02", "40000")
check("Abandon : le plan ne peut plus alimenter les mois neutralisés", r.status_code == 409 or charges(e6)["05"].paid_amount == 0, r.status_code)
stu6 = dec.get(f"schooling/students/{s6}").json()
ok(dec.post(f"schooling/students/{s6}/reintegrate", json={"effective_date": f"{sy+1}-02-01", "reason": "Retour (recette L6)"}, headers=k({"If-Match": str(stu6.get("version", 1))})))
check("Réintégration : les mois neutralisés redeviennent dus", charges(e6)["05"].status == "ACTIVE" and charges(e6)["06"].status == "ACTIVE")
e7, s7 = enroll(f"TRANS{run}")
stu7 = dec.get(f"schooling/students/{s7}").json()
ok(dec.post(f"schooling/students/{s7}/transfer", json={"effective_date": f"{sy+1}-03-01", "reason": "Transfert (recette L6)", "destination": "École voisine"},
            headers=k({"If-Match": str(stu7.get("version", 1))})))
ch7 = charges(e7)
check("Transfert : mois à partir de mars neutralisés, février reste dû", ch7["03"].status == "CANCELLED" and ch7["02"].status == "ACTIVE", {m: ch7[m].status for m in ("02", "03", "06")})

# ---------- 9. change of year ----------
nxt = ok(plan("Plan de l'année suivante", ["05"], ["01"], year=y2))
r = member(e1, nxt["id"])
check("Changement d'année : un plan d'une autre année n'est pas proposé ni utilisable", r.status_code == 409 and "année scolaire active" in r.text, r.status_code)
check("Changement d'année : les plans proposés sont ceux de l'année de l'élève", all(p["id"] != nxt["id"] for p in cash.get(f"finance/checkout/anticipation-plans/{e1}").json()["items"]))

# ---------- structure locked once members exist; old Web path retired; isolation; audit ----------
r = plans.put("settings/anticipation-plans", json={"academic_year_id": y["id"], "plan_id": opt["id"], "name": opt["name"], "fee_type_id": sco["id"],
                                                  "target_months": ["06"], "contribution_months": ["01", "02", "03"]}, headers=k())
check("Plan avec adhésions : changement de structure refusé (nouvelle version)", r.status_code == 409 and "nouvelle version" in r.text, r.status_code)
r = cash.post("finance/checkout/collect", json={"enrollment_id": e2, "charge_ids": [str(charges(e2)["03"].id)], "amount": "60000", "currency": "CDF", "use_anticipation": True}, headers=k())
check("Ancien mécanisme Web (surplus en provision) retiré de la caisse", r.status_code == 409 and "plan de paiement anticipé" in r.text, r.status_code)
a_cash = user_client(state["A"], "CAISSIER1")
check("Autre école : plan de L6 introuvable", a_cash.get(f"finance/checkout/anticipation-plans/{opt['id']}/preview", params={"enrollment_id": e1, "month": "01"}).status_code in (404, 409))
with owner.connect() as c:
    acts = dict(c.execute(text("SELECT action,count(*) FROM audit_events WHERE school_id=:s AND action LIKE 'ANTICIPATION_%' GROUP BY action"), {"s": school["school_id"]}).all())
    provisions = c.execute(text("SELECT count(*) FROM finance_advance_allocations WHERE school_id=:s"), {"s": school["school_id"]}).scalar_one()
check("Audit : plans, adhésions et paiements selon plan tracés", acts.get("ANTICIPATION_PLAN_SAVED", 0) >= 3 and acts.get("ANTICIPATION_MEMBERSHIP_SET", 0) >= 4
      and acts.get("ANTICIPATION_PAYMENT_RECORDED", 0) >= 3, acts)
check("Plan anticipé ≠ fonds anticipé : aucune provision créée par les plans", provisions == 0, provisions)
# N3-A / G-PLAN-1 (owner decision 2026-10-15): the school system administrator creates plans by default; the cashier does not.
adm_plan = adm.put("settings/anticipation-plans", json={"academic_year_id": y["id"], "name": "Plan créé par l'administrateur", "fee_type_id": sco["id"],
                   "target_months": ["04"], "contribution_months": ["01"], "effective_from": f"{sy}-09-01"}, headers=k())
check("Droits : l'administrateur de l'école crée un plan (ADMIN_SYSTEME_ECOLE)", adm_plan.status_code == 201, adm_plan.status_code)
cash_plan = cash.put("settings/anticipation-plans", json={"academic_year_id": y["id"], "name": "Plan du caissier", "fee_type_id": sco["id"],
                     "target_months": ["04"], "contribution_months": ["01"], "effective_from": f"{sy}-09-01"}, headers=k())
check("Droits : le caissier ne crée pas de plan", cash_plan.status_code == 403, cash_plan.status_code)

passed = sum(r["pass"] for r in results)
out = Path(__file__).with_name("anticipation-live.json")
out.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"== {passed}/{len(results)} PASS -> {out.name}")
sys.exit(0 if passed == len(results) else 1)
