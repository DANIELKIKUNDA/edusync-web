"""N3-C — real probe: financial decisions copied from the Desktop golden master (app/db/financial_decisions.py).

Scope ALL_FEES / FEE_CODE / FEE_CATEGORY / CHARGE, natures, PERCENT / FIXED (exemptions = 100 %), priority, cumulative,
period and effective dates, recalculation, cancellation, explanation, operator view, follow-up, planned responsibility per
charge; the cash desk collects only what remains. Fresh school, real API. Nothing secret is printed.
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
s = ok(platform().post("platform/schools", json={"code": f"N3C-{run}", "name": f"École décisions N3-C {run}"}, headers=k()))
school = {"code": f"N3C-{run}", "school_id": s["id"], "users": {}}
state.setdefault("N3C", {})[run] = school
save()
ensure_user(school, "ADMIN", ("ADMIN_SYSTEME_ECOLE",))
ensure_user(school, "CASH", ("CAISSIER",))
ensure_user(school, "GES", ("GESTIONNAIRE",))
adm, cash, ges = user_client(school, "ADMIN"), user_client(school, "CASH"), user_client(school, "GES")
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


def enroll(name):
    d = ok(cash.post("schooling/enrollments/family", json={"primary_guardian": {"full_name": f"Tuteur {name}", "is_primary": True},
           "children": [{"last_name": name, "middle_name": "Recette", "first_name": "N3C", "gender": "F", "class_id": p1["id"]}]}, headers=k()))
    return d["enrollment_ids"][0], d["student_ids"][0]


e1, st1 = enroll(f"DEC{run}")
e2, st2 = enroll(f"DED{run}")


def charges(enr):
    with owner.connect() as c:
        return [dict(r) for r in c.execute(text("""SELECT fc.id, fc.period_label, fc.due_date, fc.net_amount,
            GREATEST(fc.net_amount - finance_charge_decision_amount(fc.id), 0) AS payable FROM finance_charges fc
            WHERE fc.enrollment_id=:e ORDER BY fc.due_date"""), {"e": enr}).mappings().all()]


def decide(client=None, **body):
    base = {"enrollment_id": e1, "reason": "Décision de recette N3-C", "effective_date": f"{sy}-09-01"}
    return (client or ges).post("finance/controls/decisions", json={**base, **body}, headers=k())


ch = charges(e1)
check("Préparation : 10 mensualités à 20 000 CDF", len(ch) == 10 and all(Decimal(c["payable"]) == Decimal("20000") for c in ch), len(ch))
# ---------- validations (Desktop messages) ----------
r = decide(decision_type="REDUCTION", value_type="PERCENT", amount="10")
check("Nature hors Desktop (REDUCTION) refusée à la création", r.status_code == 409 and "invalide" in r.text, r.status_code)
check("Portée inconnue refusée", decide(decision_type="DISCOUNT", scope_type="CLASS", amount="10").status_code == 409)
check("Pourcentage > 100 refusé", decide(decision_type="DISCOUNT", value_type="PERCENT", amount="120").status_code == 409)
check("Cible obligatoire pour une portée FEE_CODE", decide(decision_type="DISCOUNT", scope_type="FEE_CODE", amount="10").status_code == 409)
check("Motif obligatoire", decide(decision_type="DISCOUNT", amount="10", reason="").status_code == 422)
r = decide(decision_type="DISCOUNT", amount="10", enrollment_id=str(uuid4()))
check("Inscription inconnue : refus métier (plus de 500)", r.status_code == 409, r.status_code)
check("Droits : le caissier ne décide pas", decide(cash, decision_type="DISCOUNT", amount="10").status_code == 403)
check("Droits : l'administrateur technique ne décide pas", decide(adm, decision_type="DISCOUNT", amount="10").status_code == 403)
# ---------- computation ----------
d25 = ok(decide(decision_type="DISCOUNT", scope_type="ALL_FEES", value_type="PERCENT", amount="25", priority=100))
ch = charges(e1)
check("Réduction 25 % sur tous les frais : 15 000 par mois", all(Decimal(c["payable"]) == Decimal("15000") for c in ch), [c["payable"] for c in ch][:3])
dfix = ok(decide(decision_type="DIRECTION_EXCEPTION", scope_type="FEE_CODE", scope_ref="scolarite", value_type="FIXED", amount="2000", priority=200))
ch = charges(e1)
check("Montant fixe sur le code de frais, après la réduction (ordre de priorité) : 13 000", all(Decimal(c["payable"]) == Decimal("13000") for c in ch), [c["payable"] for c in ch][:3])
r = decide(decision_type="DISCOUNT", value_type="FIXED", amount="1000", currency="USD", priority=300)
ch = charges(e1)
check("Montant fixe en USD : ne touche pas les frais en CDF (aucune conversion)", r.status_code == 200 and all(Decimal(c["payable"]) == Decimal("13000") for c in ch))
nov = next(c for c in ch if c["due_date"].month == 11)
ex = ok(decide(decision_type="EXEMPTION", scope_type="CHARGE", scope_ref=str(nov["id"]), value_type="FIXED", amount="1", priority=400))
check("Exonération : toujours 100 % (valeur forcée par le Desktop)", ex["value_type"] == "PERCENT" and Decimal(str(ex["value_amount"])) == Decimal("100"), (ex["value_type"], ex["value_amount"]))
ch = charges(e1)
check("Exonération du mois de novembre seulement", Decimal(next(c for c in ch if c["id"] == nov["id"])["payable"]) == 0
      and sum(1 for c in ch if Decimal(c["payable"]) == Decimal("13000")) == 9)
# non-cumulative (e2): the second non-cumulative decision is skipped, a cumulative one still applies
ok(decide(enrollment_id=e2, decision_type="DISCOUNT", value_type="PERCENT", amount="10", cumulative=False, priority=10))
ok(decide(enrollment_id=e2, decision_type="DISCOUNT", value_type="PERCENT", amount="50", cumulative=False, priority=20))
ok(decide(enrollment_id=e2, decision_type="THIRD_PARTY_COVERAGE", value_type="FIXED", amount="1000", cumulative=True, priority=30))
c2 = charges(e2)
check("Non cumulatif : la 2e décision non cumulative est ignorée, la cumulative s'applique (20 000 − 10 % − 1 000 = 17 000)",
      all(Decimal(c["payable"]) == Decimal("17000") for c in c2), [c["payable"] for c in c2][:3])
# period (e2): only charges due inside the period
per = ok(decide(enrollment_id=e2, decision_type="DISCOUNT", value_type="FIXED", amount="7000", priority=40, period_start=f"{sy}-12-01", period_end=f"{sy+1}-01-31"))
c2 = charges(e2)
inside = [c for c in c2 if date(sy, 12, 1) <= c["due_date"] <= date(sy + 1, 1, 31)]
check("Période : seules les échéances de décembre à janvier sont réduites", inside and all(Decimal(c["payable"]) == Decimal("10000") for c in inside)
      and all(Decimal(c["payable"]) == Decimal("17000") for c in c2 if c not in inside), len(inside))
# ---------- cancellation ----------
r = ges.post(f"finance/controls/decisions/{per['id']}/cancel", json={"reason": "Erreur de période"}, headers=k())
c2 = charges(e2)
check("Annulation : recalcul immédiat, montants rétablis", r.status_code == 200 and all(Decimal(c["payable"]) == Decimal("17000") for c in c2))
check("Annulation : une seconde fois refusée", ges.post(f"finance/controls/decisions/{per['id']}/cancel", json={"reason": "Encore"}, headers=k()).status_code == 409)
check("Recalcul explicite idempotent", ok(ges.post(f"finance/controls/enrollments/{e2}/recalculate", headers=k())) is not None
      and [c["payable"] for c in charges(e2)] == [c["payable"] for c in c2])
# ---------- cash desk respects the decisions ----------
if not cash.get("finance/cash/current").json().get("session"):
    ok(cash.post("finance/cash/open", json={"opening_cdf": 0, "opening_usd": 0}))
first = next(i for i in cash.get(f"finance/checkout/balance/{e1}").json()["items"] if i["eligible"])
check("Caisse : le reste à payer affiché tient compte des décisions (13 000)", Decimal(first["remaining"]) == Decimal("13000"), first["remaining"])
r = cash.post("finance/checkout/collect", json={"enrollment_id": e1, "charge_ids": [first["id"]], "amount": "20000", "currency": "CDF"}, headers=k())
check("Caisse : encaisser plus que le reste dû est refusé", r.status_code in (409, 422), r.status_code)
ok(cash.post("finance/checkout/collect", json={"enrollment_id": e1, "charge_ids": [first["id"]], "amount": "13000", "currency": "CDF"}, headers=k()))
# ---------- read models ----------
exp = ok(ges.get(f"finance/controls/charges/{first['id']}/explanation"))
check("Explication : brut, décisions dans l'ordre de priorité, net, réglé, reste", Decimal(exp["gross"]) == Decimal("20000") and [d["priority"] for d in exp["decisions"]] == [100, 200]
      and Decimal(exp["net_after_decisions"]) == Decimal("13000") and Decimal(exp["settled"]) == Decimal("13000") and Decimal(exp["remaining"]) == 0,
      {k2: exp[k2] for k2 in ("gross", "net_after_decisions", "settled", "remaining")})
view = ok(ges.get(f"finance/controls/students/{st1}/view"))
statuses = {c["id"]: c["status"] for c in view["charges"]}
check("Vue opérateur : SOLDEE, EXONEREE et A_REGLER", statuses.get(first["id"]) == "SOLDEE" and statuses.get(str(nov["id"])) == "EXONEREE" and "A_REGLER" in statuses.values(), sorted(set(statuses.values())))
fu = ok(ges.get("finance/controls/follow-up"))
check("Suivi : décisions de l'année avec leur nombre d'applications", any(d["id"] == d25["id"] and d["application_count"] == 10 for d in fu["decisions"]), len(fu["decisions"]))
# ---------- planned responsibility per charge ----------
dec = next(c for c in charges(e1) if c["due_date"].month == 12)
r = ges.post(f"finance/controls/charges/{dec['id']}/responsibility", json={"responsibility_type": "THIRD_PARTY", "planned_amount": "20000", "reason": "Bourse ONG"}, headers=k())
check("Responsabilité : jamais au-delà du restant réel (13 000)", r.status_code == 409 and "restant réel" in r.text, r.status_code)
ok(ges.post(f"finance/controls/charges/{dec['id']}/responsibility", json={"responsibility_type": "THIRD_PARTY", "planned_amount": "13000", "responsible_name": "ONG Lumière", "reason": "Bourse ONG"}, headers=k()))
ok(ges.post(f"finance/controls/charges/{dec['id']}/responsibility", json={"responsibility_type": "PAYROLL_DEDUCTION", "planned_amount": "6500", "reason": "Retenue sur salaire du parent"}, headers=k()))
with owner.connect() as c:
    rows = c.execute(text("SELECT status, count(*) FROM finance_charge_responsibilities WHERE charge_id=:c GROUP BY status"), {"c": dec["id"]}).all()
check("Responsabilité : la nouvelle remplace l'ancienne (annulée, jamais supprimée)", dict(rows) == {"PLANNED": 1, "CANCELLED": 1}, dict(rows))
check("Responsabilité : le caissier ne la fixe pas", cash.post(f"finance/controls/charges/{dec['id']}/responsibility", json={"responsibility_type": "FAMILY_CASH", "planned_amount": "100", "reason": "Essai"}, headers=k()).status_code == 403)
# ---------- audit ----------
with owner.connect() as c:
    acts = {a: n for a, n in c.execute(text("SELECT action, count(*) FROM audit_events WHERE school_id=:s AND action IN ('CREATE_FINANCIAL_DECISION','CANCEL_FINANCIAL_DECISION','SET_CHARGE_RESPONSIBILITY') GROUP BY action"), {"s": school["school_id"]})}
check("Audit : création, annulation et responsabilités tracées", set(acts) == {"CREATE_FINANCIAL_DECISION", "CANCEL_FINANCIAL_DECISION", "SET_CHARGE_RESPONSIBILITY"}, acts)

ok_n = sum(r["pass"] for r in results)
Path(__file__).with_name("decisions-live.json").write_text(json.dumps({"school": school["code"], "results": results}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print(f"== {ok_n}/{len(results)} PASS -> decisions-live.json")
