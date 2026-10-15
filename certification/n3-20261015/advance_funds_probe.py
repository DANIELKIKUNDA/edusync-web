"""N3-D — real probe: « fonds anticipés » copied from the Desktop golden master (app/db/operations.py:290-470),
strictly separate from the payment plans (doctrine L6), plus the decision credit (financial_decisions.py, G-DEC-6).
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
s = ok(platform().post("platform/schools", json={"code": f"N3D-{run}", "name": f"École fonds N3-D {run}"}, headers=k()))
school = {"code": f"N3D-{run}", "school_id": s["id"], "users": {}}
state.setdefault("N3D", {})[run] = school
save()
ensure_user(school, "ADMIN", ("ADMIN_SYSTEME_ECOLE",))
ensure_user(school, "CASH", ("CAISSIER",))
ensure_user(school, "CASH_B", ("CAISSIER",))
ensure_user(school, "GES", ("GESTIONNAIRE",))
adm, cash, cb, ges = (user_client(school, x) for x in ("ADMIN", "CASH", "CASH_B", "GES"))
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
           "children": [{"last_name": name, "middle_name": "Recette", "first_name": "N3D", "gender": "M", "class_id": p1["id"]}]}, headers=k()))
    return d["enrollment_ids"][0]


e1, e2 = enroll(f"FON{run}"), enroll(f"FOP{run}")
ok(cash.post("finance/cash/open", json={"opening_cdf": 0, "opening_usd": 0}))


def policy(**v):
    cur = adm.get("settings/payment-policy").json()
    body = {k2: cur[k2] for k2 in ("partial_payments_enabled", "partial_min_amount", "partial_reporting_mode", "advance_payments_enabled", "future_charge_payments_enabled", "accepted_modes")}
    body.update(v); body["expected_version"] = cur.get("version")
    return adm.put("settings/payment-policy", json=body, headers=k())


def receive(amount, enr=e1, currency="CDF", mode="CASH", client=None, key=None):
    return (client or cash).post("finance/checkout/advance-funds", json={"enrollment_id": enr, "amount": amount, "currency": currency, "mode": mode}, headers={"Idempotency-Key": key or str(uuid4())})


def balance(enr):
    return {i["period_label"]: Decimal(i["remaining"]) for i in cash.get(f"finance/checkout/balance/{enr}").json()["items"]}


def funds(enr):
    return cash.get("finance/checkout/advance-funds", params={"enrollment_id": enr}).json()["items"]


# ---------- receive (Desktop rules) ----------
ok(policy(advance_payments_enabled=False))
r = receive("30000")
check("Fonds désactivés par l'école : réception refusée", r.status_code == 409 and "désactivés" in r.text, r.status_code)
ok(policy(advance_payments_enabled=True, accepted_modes=["CASH"]))
check("Mode non accepté par l'école : refusé", receive("30000", mode="BANQUE").status_code == 409)
check("Montant nul refusé", receive("0").status_code == 422)
check("Devise inconnue refusée", receive("10", currency="EUR").status_code == 422)
check("Sans caisse ouverte : refusé", receive("1000", client=cb).status_code == 409)
check("Le gestionnaire ne reçoit pas de fonds (caisse)", receive("1000", client=ges).status_code == 403)
key = str(uuid4())
r = receive("30000", key=key)
f1 = r.json() if r.status_code == 201 else {}
check("Réception : fonds disponible, reçu propre dans la séquence unique", r.status_code == 201 and f1.get("status") == "ACTIF" and Decimal(f1["available_amount"]) == Decimal("30000")
      and str(f1.get("receipt_number", "")).count("-") == 2, (r.status_code, f1.get("receipt_number")))
r2 = receive("30000", key=key)
check("Réception rejouée (même clé) : aucun doublon", r2.status_code == 201 and r2.json().get("id") == f1.get("id"))
sess = cash.get("finance/cash/current").json()["session"]
check("Caisse : le fonds est une entrée de la session du caissier", Decimal(sess["cdf"]["receipts"]) == Decimal("30000"), sess["cdf"]["receipts"])
check("Les frais ne bougent pas à la réception (montant conservé, non imputé)", all(v == Decimal("20000") for v in balance(e1).values()))
pdf = cash.get(f"finance/checkout/advance-funds/{f1['id']}/receipt.pdf")
check("Reçu de fonds anticipé PDF", pdf.status_code == 200 and pdf.content[:4] == b"%PDF", pdf.status_code)

# ---------- allocate ----------
r = cash.post(f"finance/checkout/advance-funds/{f1['id']}/allocate", json={"amount": "5000"}, headers=k())
check("Imputation partielle : 5 000 sur la plus ancienne échéance", r.status_code == 200 and Decimal(r.json()["available_amount"]) == Decimal("25000"), r.text[:120])
check("Imputation au-delà du disponible refusée", cash.post(f"finance/checkout/advance-funds/{f1['id']}/allocate", json={"amount": "26000"}, headers=k()).status_code == 409)
r = cash.post(f"finance/checkout/advance-funds/{f1['id']}/allocate", json={}, headers=k())
b = balance(e1)
check("Imputation totale : plus anciennes d'abord, jamais au-delà du dû ; fonds épuisé", r.status_code == 200 and r.json()["status"] == "EPUISE"
      and sorted(b.values())[:1] == [Decimal("10000")] and len([v for v in b.values() if v < Decimal("20000")]) == 1, (r.status_code, sorted(b.values())[:3]))
check("Fonds épuisé : nouvelle imputation refusée", cash.post(f"finance/checkout/advance-funds/{f1['id']}/allocate", json={}, headers=k()).status_code == 409)
check("Fonds imputé : remboursement global refusé (Desktop)", ges.post(f"finance/checkout/advance-funds/{f1['id']}/close", json={"reversal_type": "REMBOURSEMENT", "reason": "Essai"}, headers=k()).status_code == 409)

# ---------- refund (superior authority) ----------
f2 = ok(receive("8000"))
check("Remboursement : refusé au caissier (autorité supérieure)", cash.post(f"finance/checkout/advance-funds/{f2['id']}/close", json={"reversal_type": "REMBOURSEMENT", "reason": "Parent parti"}, headers=k()).status_code == 403)
check("Remboursement : motif trop court refusé", ges.post(f"finance/checkout/advance-funds/{f2['id']}/close", json={"reversal_type": "REMBOURSEMENT", "reason": "ab"}, headers=k()).status_code == 422)
r = ges.post(f"finance/checkout/advance-funds/{f2['id']}/close", json={"reversal_type": "REMBOURSEMENT", "reason": "Parent parti en cours d'année"}, headers=k())
check("Remboursement par le gestionnaire : fonds remboursé", r.status_code == 200 and r.json()["status"] == "REMBOURSE" and Decimal(r.json()["available_amount"]) == 0, r.text[:120])
check("Fonds remboursé : plus d'imputation", cash.post(f"finance/checkout/advance-funds/{f2['id']}/allocate", json={}, headers=k()).status_code == 409)
day = ges.get("finance/cash/day").json()
srcs = {d["source"]: Decimal(d["amount"]) for d in day["details"] if d["currency"] == "CDF"}
check("Journée : entrée FONDS_ANTICIPE et sortie RESTITUTION_FONDS_ANTICIPE", srcs.get("FONDS_ANTICIPE") == Decimal("38000") and srcs.get("RESTITUTION_FONDS_ANTICIPE") == Decimal("8000"), srcs)

# ---------- decision credit (G-DEC-6) ----------
first = next(i for i in cash.get(f"finance/checkout/balance/{e2}").json()["items"] if i["eligible"])
ok(cash.post("finance/checkout/collect", json={"enrollment_id": e2, "charge_ids": [first["id"]], "amount": "20000", "currency": "CDF"}, headers=k()))
dec = ok(ges.post("finance/controls/decisions", json={"enrollment_id": e2, "decision_type": "EXEMPTION", "scope_type": "CHARGE", "scope_ref": first["id"], "reason": "Exonération après paiement", "effective_date": f"{sy}-09-01"}, headers=k()))
credits = [f for f in funds(e2) if f["origin_type"] == "DECISION_CREDIT"]
check("Décision après paiement : crédit de 20 000 (sans reçu ni entrée de caisse)", len(credits) == 1 and Decimal(credits[0]["amount"]) == Decimal("20000") and not credits[0]["receipt_number"], credits)
check("Crédit : pas de reçu de caisse", cash.get(f"finance/checkout/advance-funds/{credits[0]['id']}/receipt.pdf").status_code == 409 if credits else False)
ok(ges.post(f"finance/controls/decisions/{dec['id']}/cancel", json={"reason": "Exonération retirée"}, headers=k()))
st = {f["id"]: f["status"] for f in funds(e2)}
check("Annulation de la décision : crédit non utilisé clôturé", credits and st.get(credits[0]["id"]) == "ANNULE", st)
dec2 = ok(ges.post("finance/controls/decisions", json={"enrollment_id": e2, "decision_type": "EXEMPTION", "scope_type": "CHARGE", "scope_ref": first["id"], "reason": "Exonération confirmée", "effective_date": f"{sy}-09-01"}, headers=k()))
c2 = [f for f in funds(e2) if f["origin_type"] == "DECISION_CREDIT" and f["status"] == "ACTIF"]
ok(cash.post(f"finance/checkout/advance-funds/{c2[0]['id']}/allocate", json={}, headers=k()))
r = ges.post(f"finance/controls/decisions/{dec2['id']}/cancel", json={"reason": "Essai d'annulation"}, headers=k())
check("Crédit déjà utilisé : annulation de la décision refusée (Desktop)", r.status_code == 409 and "déjà utilisé" in r.text, r.status_code)
reg = ges.get("finance/controls/credits", params={"status": "ALL"}).json()["items"]
check("Registre des crédits et trop-perçus : fonds et crédits de l'école", len([x for x in reg if x["enrollment_id"] in (e1, e2)]) >= 4, len(reg))

# ---------- separation from plans, evidence ----------
with owner.connect() as c:
    plan_rows = c.execute(text("""SELECT (SELECT count(*) FROM anticipation_memberships WHERE school_id=:s) + (SELECT count(*) FROM anticipation_payment_links WHERE school_id=:s)
        + (SELECT count(*) FROM finance_advance_allocations WHERE school_id=:s)"""), {"s": school["school_id"]}).scalar_one()
    priv = {t: c.execute(text("SELECT has_table_privilege('edusync_tenant', :t, 'UPDATE') OR has_table_privilege('edusync_tenant', :t, 'DELETE')"), {"t": t}).scalar_one()
            for t in ("finance_advance_funds", "finance_advance_fund_allocations", "finance_advance_fund_closures")}
    acts = {a: n for a, n in c.execute(text("""SELECT action, count(*) FROM audit_events WHERE school_id=:s AND action IN
        ('RECEIVE_ADVANCE_FUND','ALLOCATE_ADVANCE_FUND','ADVANCE_FUND_REMBOURSEMENT') GROUP BY action"""), {"s": school["school_id"]})}
check("Plan anticipé ≠ fonds anticipé : aucune ligne de plan ni de l'ancien mécanisme", plan_rows == 0, plan_rows)
check("Fonds, imputations et clôtures : aucun UPDATE / DELETE possible", not any(priv.values()), priv)
check("Audit : réception, imputation et remboursement tracés", set(acts) == {"RECEIVE_ADVANCE_FUND", "ALLOCATE_ADVANCE_FUND", "ADVANCE_FUND_REMBOURSEMENT"}, acts)
ok_n = sum(r["pass"] for r in results)
Path(__file__).with_name("advance-funds-live.json").write_text(json.dumps({"school": school["code"], "results": results}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print(f"== {ok_n}/{len(results)} PASS -> advance-funds-live.json")
