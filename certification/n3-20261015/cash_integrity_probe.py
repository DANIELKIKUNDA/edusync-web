"""N3-B — real probe: payment / cash-desk integrity (G-REV-1/2, G-CAI-1/2/3/4, G-DOC-3).

Desktop reference: app/db/operations.py (reverse_payment, record_expense, close_cash_day, reopen_cash_day,
daily_financial_report), app/services/documents.py (export_cash_journal_pdf, export_daily_financial_report_pdf).
Web transposition (owner decision 2026-10-15): individual sessions per cashier kept, global closure of the school's day by
the GESTIONNAIRE; a cashier corrects only his own payment while his session is open; everything else is superior.
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
s = ok(platform().post("platform/schools", json={"code": f"N3B-{run}", "name": f"École caisse N3-B {run}"}, headers=k()))
school = {"code": f"N3B-{run}", "school_id": s["id"], "users": {}}
state.setdefault("N3B", {})[run] = school
save()
ensure_user(school, "ADMIN", ("ADMIN_SYSTEME_ECOLE",))
ensure_user(school, "CASH_A", ("CAISSIER",))
ensure_user(school, "CASH_B", ("CAISSIER",))
ensure_user(school, "GES", ("GESTIONNAIRE",))
adm, ca, cb, ges = (user_client(school, x) for x in ("ADMIN", "CASH_A", "CASH_B", "GES"))
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
    return ok(ca.post("schooling/enrollments/family", json={"primary_guardian": {"full_name": f"Tuteur {name}", "is_primary": True},
              "children": [{"last_name": name, "middle_name": "Recette", "first_name": "N3B", "gender": "M", "class_id": p1["id"]}]}, headers=k()))["enrollment_ids"][0]


e1, e2 = enroll(f"CAI{run}"), enroll(f"CAJ{run}")
ok(ca.post("finance/cash/open", json={"opening_cdf": 5000, "opening_usd": 0}))


def first_due(enr):
    return next(i for i in ca.get(f"finance/checkout/balance/{enr}").json()["items"] if i["eligible"])


def pay(client, enr):
    c = first_due(enr)
    return ok(client.post("finance/checkout/collect", json={"enrollment_id": enr, "charge_ids": [c["id"]], "amount": c["remaining"], "currency": "CDF"}, headers=k())), c["id"]


def remaining(enr, charge_id):
    row = next((i for i in ca.get(f"finance/checkout/balance/{enr}").json()["items"] if i["id"] == charge_id), None)
    return Decimal(row["remaining"]) if row else Decimal("0")   # a settled charge leaves the payable list


def reverse(client, pid, kind="ANNULATION", reason="Erreur de saisie au guichet"):
    return client.post(f"finance/cash/payments/{pid}/reverse", json={"reversal_type": kind, "reason": reason}, headers=k())


# ---------- G-CAI-1 expenses ----------
r = ca.post("finance/cash/expenses", json={"category": "Fournitures", "amount": "1500", "currency": "CDF", "reason": "Craies et marqueurs", "reference": "BON-1"}, headers=k())
check("Dépense : le caissier l'enregistre dans sa caisse ouverte", r.status_code == 201, r.status_code)
check("Dépense : motif trop court refusé (Desktop : motif >= 3)", ca.post("finance/cash/expenses", json={"category": "X", "amount": "10", "currency": "CDF", "reason": "ab"}, headers=k()).status_code == 422)
check("Dépense : devise inconnue refusée", ca.post("finance/cash/expenses", json={"category": "X", "amount": "10", "currency": "EUR", "reason": "Essai"}, headers=k()).status_code == 422)
check("Dépense : l'administrateur technique n'a pas le droit", adm.post("finance/cash/expenses", json={"category": "X", "amount": "10", "currency": "CDF", "reason": "Essai"}, headers=k()).status_code == 403)
check("Dépense : sans caisse ouverte, refus", cb.post("finance/cash/expenses", json={"category": "X", "amount": "10", "currency": "CDF", "reason": "Essai"}, headers=k()).status_code == 409)

# ---------- G-REV-1 own correction ----------
(p1pay, c1) = pay(ca, e1)
check("Paiement initial : mois soldé", remaining(e1, c1) == 0)
r = reverse(ca, p1pay["id"])
check("Contre-opération : le caissier annule son propre paiement (caisse ouverte)", r.status_code == 200 and r.json().get("authority") == "OWN", (r.status_code, r.text[:120]))
check("Contre-opération : le mois redevient payable (le paiement ne compte plus)", remaining(e1, c1) == Decimal("20000"), remaining(e1, c1))
check("Contre-opération : une seconde fois refusée", reverse(ca, p1pay["id"]).status_code == 409)
check("Contre-opération : motif trop court refusé", reverse(ca, pay(ca, e1)[0]["id"], reason="ab").status_code == 422)
with owner.connect() as cx:
    row = cx.execute(text("SELECT amount, receipt_number FROM finance_payments WHERE id=:p"), {"p": p1pay["id"]}).mappings().one()
    priv = {t: cx.execute(text("SELECT has_table_privilege('edusync_tenant', :t, 'UPDATE') OR has_table_privilege('edusync_tenant', :t, 'DELETE')"), {"t": t}).scalar_one()
            for t in ("finance_payments", "finance_payment_reversals", "finance_cash_day_snapshots")}
check("Paiement jamais modifié ni supprimé : le paiement annulé reste intact", Decimal(row["amount"]) == Decimal("20000") and row["receipt_number"] == p1pay["receipt_number"])
check("Aucun UPDATE / DELETE possible sur paiements, contre-opérations, instantanés (droits SQL)", not any(priv.values()), priv)

# ---------- superior authority ----------
(p2pay, c2) = pay(ca, e2)
ok(cb.post("finance/cash/open", json={"opening_cdf": 0, "opening_usd": 0}))
r = reverse(cb, p2pay["id"])
check("Paiement d'un autre caissier : refusé au caissier (autorité supérieure)", r.status_code == 403, r.status_code)
(p3pay, c3) = pay(ca, e1)   # stays valid until after the global closure
cur = ca.get("finance/cash/current").json()["session"]
check("Session : la contre-opération du caissier est une sortie de sa caisse", Decimal(cur["cdf"]["reversals"]) == Decimal("20000")
      and Decimal(cur["cdf"]["expected_cash"]) == Decimal("5000") + Decimal(cur["cdf"]["receipts"]) - Decimal("1500") - Decimal("20000"), cur["cdf"])
ok(ca.post("finance/cash/close", json={"counted_cdf": cur["cdf"]["expected_cash"], "counted_usd": "0"}))
r = reverse(ca, p2pay["id"])
check("Caisse clôturée : le caissier ne corrige plus son paiement (autorité supérieure)", r.status_code == 403, r.status_code)
r = reverse(ges, p2pay["id"], kind="REMBOURSEMENT", reason="Remboursement validé par la gestion")
check("Le gestionnaire rembourse un paiement d'une caisse clôturée", r.status_code == 200 and r.json().get("authority") == "SUPERVISOR", (r.status_code, r.text[:120]))
check("Remboursement : le mois redevient payable", remaining(e2, c2) == Decimal("20000"))
check("L'administrateur technique ne fait aucune contre-opération", reverse(adm, p3pay["id"]).status_code == 403)
summary = ges.get("finance/cash/day-summary").json()
check("Synthèse de la journée : remboursement supérieur compté en sortie", Decimal(summary["currencies"]["CDF"]["supervisor_reversals"]) == Decimal("20000"), summary["currencies"]["CDF"])

# ---------- G-CAI-3/4 global closure ----------
check("Clôture globale : refusée au caissier", ca.post("finance/cash/day/close", headers=k()).status_code == 403)
check("Clôture globale : refusée à l'administrateur technique", adm.post("finance/cash/day/close", headers=k()).status_code == 403)
r = ges.post("finance/cash/day/close", headers=k())
check("Clôture globale : refusée tant qu'une caisse individuelle est ouverte", r.status_code == 409 and "caisses individuelles" in r.text, r.status_code)
ok(cb.post("finance/cash/close", json={"counted_cdf": "0", "counted_usd": "0"}))
r = ges.post("finance/cash/day/close", headers=k())
day = r.json() if r.status_code == 200 else {}
check("Clôture globale par le gestionnaire : instantanés par devise", r.status_code == 200 and day.get("closed") and len(day.get("closure_snapshots", [])) >= 1, (r.status_code, r.text[:160]))
snap = next((x for x in day.get("closure_snapshots", []) if x["currency"] == "CDF"), {})
check("Instantané CDF = entrées − sorties (paiements, dépense, contre-opérations)", snap and Decimal(str(snap["net"])) == Decimal(str(snap["entries"])) - Decimal(str(snap["outflows"]))
      and Decimal(str(snap["outflows"])) == Decimal("41500"), snap)
check("Clôture globale : une seconde fois sans effet (Desktop)", ges.post("finance/cash/day/close", headers=k()).status_code == 200)
check("Journée clôturée : ouverture d'une caisse refusée", ca.post("finance/cash/open", json={"opening_cdf": 0, "opening_usd": 0}).status_code == 409)
check("Journée clôturée : contre-opération refusée", reverse(ges, p3pay["id"]).status_code == 409)

# ---------- G-CAI-2 reopening ----------
check("Réouverture : refusée au caissier", ca.post("finance/cash/day/reopen", json={"reason": "Correction d'un oubli"}, headers=k()).status_code == 403)
check("Réouverture : motif trop court refusé (Desktop : >= 5)", ges.post("finance/cash/day/reopen", json={"reason": "abc"}, headers=k()).status_code == 422)
r = ges.post("finance/cash/day/reopen", json={"reason": "Dépense oubliée à saisir"}, headers=k())
check("Réouverture par le gestionnaire avec motif", r.status_code == 200 and not r.json().get("closed"), r.status_code)
check("Après réouverture : le caissier rouvre une caisse", ca.post("finance/cash/open", json={"opening_cdf": 0, "opening_usd": 0}).status_code in (200, 201))

# ---------- G-DOC-3 documents ----------
r = ges.get("finance/cash/day/journal.pdf")
check("Journal de caisse PDF (gestionnaire)", r.status_code == 200 and r.content[:4] == b"%PDF", r.status_code)
r = ca.get("finance/cash/day/report.pdf")
check("Rapport financier journalier PDF (caissier)", r.status_code == 200 and r.content[:4] == b"%PDF", r.status_code)
rep = ges.get("finance/cash/day").json()
srcs = {d["source"] for d in rep["details"]}
check("Rapport journalier : détail par source (paiement, dépense, annulation, remboursement)", {"PAIEMENT_ELEVE", "DEPENSE_JOURNALIERE", "ANNULATION", "REMBOURSEMENT"} <= srcs, sorted(srcs))

# ---------- G-REV-2 duplicata (already Web) ----------
r1 = ca.post(f"finance/checkout/receipts/{p3pay['id']}/print", headers=k())
r2 = ca.post(f"finance/checkout/receipts/{p3pay['id']}/print", headers=k())
with owner.connect() as cx:
    kinds = [x for (x,) in cx.execute(text("SELECT kind FROM finance_receipt_prints WHERE payment_id=:p ORDER BY copy_no"), {"p": p3pay["id"]})]
check("Réimpression : la 2e impression est un DUPLICATA compté et tracé", r1.status_code == 200 and r2.status_code == 200 and kinds[:2] == ["ORIGINAL", "DUPLICATA"], kinds)

# ---------- audit and isolation ----------
with owner.connect() as cx:
    acts = {a: n for a, n in cx.execute(text("SELECT action, count(*) FROM audit_events WHERE school_id=:s AND action IN ('PAYMENT_ANNULATION','PAYMENT_REMBOURSEMENT','RECORD_EXPENSE','CLOSE_CASH_DAY','REOPEN_CASH_DAY') GROUP BY action"), {"s": school["school_id"]})}
check("Audit : annulation, remboursement, dépense, clôture et réouverture tracées", set(acts) == {"PAYMENT_ANNULATION", "PAYMENT_REMBOURSEMENT", "RECORD_EXPENSE", "CLOSE_CASH_DAY", "REOPEN_CASH_DAY"}, acts)
other = next(iter(state.get("L5", {}).values()), None)
if other and "CASH" in other.get("users", {}):
    oc = user_client(other, "CASH")
    check("Autre école : paiement de N3-B introuvable", oc.post(f"finance/cash/payments/{p3pay['id']}/reverse", json={"reversal_type": "ANNULATION", "reason": "Essai croisé"}, headers=k()).status_code in (403, 404))

ok_n = sum(r["pass"] for r in results)
Path(__file__).with_name("cash-integrity-live.json").write_text(json.dumps({"school": school["code"], "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"== {ok_n}/{len(results)} PASS -> cash-integrity-live.json")
