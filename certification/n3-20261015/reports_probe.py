"""N3-G — real probe: reports and documents copied from the Desktop golden master (terrain.financial_report_rows,
_settled_only_report_rows, register_generated_report; operations.analysis_*; financial_views.historical_recovery_status;
documents.export_periodic_financial_report_pdf/xlsx, export_student_account_pdf, money_in_words).
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
s = ok(platform().post("platform/schools", json={"code": f"N3G-{run}", "name": f"École rapports N3-G {run}"}, headers=k()))
school = {"code": f"N3G-{run}", "school_id": s["id"], "users": {}}
state.setdefault("N3G", {})[run] = school
save()
ensure_user(school, "ADMIN", ("ADMIN_SYSTEME_ECOLE",))
ensure_user(school, "CASH", ("CAISSIER",))
ensure_user(school, "GES", ("GESTIONNAIRE",))
ensure_user(school, "RF", ("RESPONSABLE_FINANCE",))
adm, cash, ges, rf = (user_client(school, x) for x in ("ADMIN", "CASH", "GES", "RF"))
today = date.today()
sy = today.year if today.month >= 9 else today.year - 1
y = ok(adm.post("settings/academic-years", json={"code": f"{sy}-{sy+1}", "label": f"{sy}-{sy+1}", "start_date": f"{sy}-09-01", "end_date": f"{sy+1}-06-30"}, headers=k()))
y = ok(adm.post(f"settings/academic-years/{y['id']}/activate", headers=k({"If-Match": str(y["version"])})))
pri = ok(adm.put("settings/sections/PRIMAIRE", json={"code": "PRIMAIRE", "label": "Primaire", "enabled": True}, headers=k()))
p1 = ok(adm.post("settings/classes", json={"academic_year_id": y["id"], "section_id": pri["id"], "reference_code": "P1", "code": "P1A", "label": "P1A"}, headers=k()))
fees = {}
for code, label, per, amount in (("SCOLARITE", "Frais scolaires", "MONTHLY", "20000"), ("INSCRIPTION", "Inscription", "ONE_TIME", "15000"),
                                  ("JOURNAL_CLASSE", "Journal de classe", "ONE_TIME", "3000"), ("ECUSSON", "Écusson", "ONE_TIME", "2000")):
    fees[code] = ok(adm.post("settings/fee-types", json={"code": code, "label": label, "periodicity": per, "default_currency": "CDF"}, headers=k()))
    ok(adm.put("settings/tariff-rules", json={"academic_year_id": y["id"], "fee_type_id": fees[code]["id"], "scope_type": "SCHOOL", "amount": amount, "currency": "CDF"}, headers=k()))
ok(adm.post("settings/admission-conditions/review", headers=k()))
ok(adm.post("settings/tariffs/apply", json={"academic_year_id": y["id"]}, headers=k()))
d = ok(cash.post("schooling/enrollments/family", json={"primary_guardian": {"full_name": f"Tuteur {run}", "is_primary": True},
       "children": [{"last_name": f"RAP{run}", "middle_name": "Recette", "first_name": "N3G", "gender": "F", "class_id": p1["id"]}]}, headers=k()))
enr, student = d["enrollment_ids"][0], d["student_ids"][0]
ok(cash.post("finance/cash/open", json={"opening_cdf": 0, "opening_usd": 0}))
with owner.connect() as c:
    ch = {(r[1], r[2]): str(r[0]) for r in c.execute(text("""SELECT fc.id, upper(ft.code), coalesce(fs.period_code,'') FROM finance_charges fc
        JOIN fee_types ft ON ft.id=fc.fee_type_id LEFT JOIN fee_schedules fs ON fs.id=fc.schedule_id WHERE fc.enrollment_id=:e"""), {"e": enr})}


def one(code):
    return next(v for (c2, _), v in ch.items() if c2 == code)


def collect(ids, amount):
    return ok(cash.post("finance/checkout/collect", json={"enrollment_id": enr, "charge_ids": ids, "amount": str(amount), "currency": "CDF"}, headers=k()))


def policy(mode):
    cur = adm.get("settings/payment-policy").json()
    body = {k2: cur[k2] for k2 in ("partial_payments_enabled", "partial_min_amount", "advance_payments_enabled", "future_charge_payments_enabled", "accepted_modes")}
    ok(adm.put("settings/payment-policy", json={**body, "partial_reporting_mode": mode, "expected_version": cur.get("version")}, headers=k()))


def report(profile="CONSOLIDE"):
    return ok(ges.get("finance/reports/periodic", params={"profile_code": profile, "period_type": "JOURNALIER", "start": str(today), "end": str(today)}))


p_ins = collect([one("INSCRIPTION")], 15000)
p_acompte = collect([ch[("SCOLARITE", "09")]], 5000)                                     # deposit on September
p_two = collect([ch[("SCOLARITE", "09")], ch[("SCOLARITE", "10")]], 25000)               # September settled + October deposit, ONE receipt
p_bundle = collect([one("JOURNAL_CLASSE"), one("ECUSSON")], 5000)
prod = ok(adm.post("settings/products", json={"code": f"PULL{run}", "label": "Pull", "unit_price": "12000", "currency": "CDF", "stock_tracking": False}, headers=k())) if True else None
sale = cash.post("finance/checkout/products/sell", json={"student_id": student, "enrollment_id": enr, "product_id": prod["id"], "quantity": "1"}, headers=k())
p_rev = collect([ch[("SCOLARITE", "10")]], 10000)   # October remainder, then reversed
ok(cash.post(f"finance/cash/payments/{p_rev['id']}/reverse", json={"reversal_type": "ANNULATION", "reason": "Erreur de saisie"}, headers=k()))

policy("SEPARATE")
cons = report()
rows = {r["payment_id"]: r for r in cons["rows"]}
check("Consolidé : une ligne par paiement (le paiement sur 2 mois compté une seule fois, 25 000)", p_two["id"] in rows and Decimal(rows[p_two["id"]]["amount"]) == Decimal("25000"), rows.get(p_two["id"], {}).get("amount"))
check("Paiement annulé exclu des rapports", p_rev["id"] not in rows)
check("Acompte présenté à part (SEPARATE) : « Acompte · … (acompte) »", rows[p_acompte["id"]]["observation"].startswith("Acompte ·") and "(acompte)" in rows[p_acompte["id"]]["observation"], rows[p_acompte["id"]]["observation"])
check("Paiement mixte (solde + acompte) signalé", rows[p_two["id"]]["reporting_status"] == "MIXTE" and rows[p_two["id"]]["observation"].startswith("Paiement mixte"), rows[p_two["id"]]["observation"])
total_expected = Decimal("15000") + Decimal("5000") + Decimal("25000") + Decimal("5000") + (Decimal("12000") if sale.status_code in (200, 201) else 0)
check("Consolidé : total FC = encaissements valides de la journée", Decimal(cons["totals"]["CDF"]) == total_expected, (cons["totals"], str(total_expected)))
ins = report("INSCRIPTION_JUIN")
check("Profil Inscriptions + juin : seulement le paiement d'inscription", [r["payment_id"] for r in ins["rows"]] == [p_ins["id"]], [r["observation"] for r in ins["rows"]])
fs = report("FRAIS_SCOLAIRES")
check("Profil Frais scolaires : mensualités seulement (sans inscription, sans journal)", {r["payment_id"] for r in fs["rows"]} == {p_acompte["id"], p_two["id"]}, [r["observation"] for r in fs["rows"]])
je = report("JOURNAL_ECUSSON")
check("Profil Journal + écusson", [r["payment_id"] for r in je["rows"]] == [p_bundle["id"]] and Decimal(je["totals"]["CDF"]) == Decimal("5000"), je["totals"])
art = report("ARTICLES_SCOLAIRES")
check("Profil Articles : ventes d'articles", sale.status_code in (200, 201) and len(art["rows"]) == 1 and "Pull" in art["rows"][0]["observation"], [r["observation"] for r in art["rows"]])
policy("INCLUDE")
inc = {r["payment_id"]: r for r in report()["rows"]}
check("Mode INCLUDE : acompte inclus sans préfixe", not inc[p_acompte["id"]]["observation"].startswith("Acompte ·") and "(acompte)" in inc[p_acompte["id"]]["observation"])
policy("EXCLUDE_UNTIL_SETTLED")
exc = report("FRAIS_SCOLAIRES")
amounts = sorted(Decimal(r["amount"]) for r in exc["rows"])
check("Mode « exclure jusqu'au solde » : septembre reconnu une fois soldé (20 000), octobre partiel non compté", amounts == [Decimal("20000")] and exc["rows"][0]["observation"].endswith("· soldé"), [(r["observation"], r["amount"]) for r in exc["rows"]])
policy("SEPARATE")
# official numbering
r1 = ges.post("finance/reports/periodic/pdf", json={"profile_code": "CONSOLIDE", "period_type": "JOURNALIER", "start": str(today), "end": str(today)}, headers=k())
r2 = ges.post("finance/reports/periodic/pdf", json={"profile_code": "FRAIS_SCOLAIRES", "period_type": "JOURNALIER", "start": str(today), "end": str(today)}, headers=k())
check("PDF officiel numéroté par année : RAP-001 puis RAP-002", r1.status_code == 200 and b"%PDF" in r1.content[:16] and r1.headers.get("X-Report-Number") == "RAP-001"
      and r2.headers.get("X-Report-Number") == "RAP-002", (r1.status_code, r1.content[:8], r1.headers.get("X-Report-Number"), r2.headers.get("X-Report-Number")))
xl = ges.get("finance/reports/periodic.xlsx", params={"profile_code": "CONSOLIDE", "period_type": "JOURNALIER", "start": str(today), "end": str(today)})
gen = ok(ges.get("finance/reports/generated"))["items"]
check("Excel compagnon : ne consomme aucun numéro officiel", xl.status_code == 200 and xl.content[:2] == b"PK" and len(gen) == 2, (xl.status_code, len(gen)))
ps = ok(cash.get("finance/checkout/print-settings"))
ok(adm.put("finance/checkout/print-settings", json={"receipt_policy": ps["receipt_policy"], "receipt_format": ps["receipt_format"], "receipt_prefix": ps["receipt_prefix"], "receipt_copies": ps["receipt_copies"], "report_prefix": "RPT"}, headers=k()))
r3 = ges.post("finance/reports/periodic/pdf", json={"profile_code": "CONSOLIDE", "period_type": "MENSUEL", "start": f"{today.year}-{today.month:02d}-01", "end": str(today)}, headers=k())
check("Préfixe des rapports paramétrable (RPT-003)", r3.headers.get("X-Report-Number") == "RPT-003", r3.headers.get("X-Report-Number"))
check("Période invalide refusée", ges.get("finance/reports/periodic", params={"profile_code": "CONSOLIDE", "period_type": "JOURNALIER", "start": str(today), "end": f"{sy}-09-01"}).status_code == 409)
check("Profil inconnu refusé", ges.get("finance/reports/periodic", params={"profile_code": "INCONNU", "period_type": "JOURNALIER", "start": str(today), "end": str(today)}).status_code == 409)
# analyses
fee = {r["fee_code"]: r for r in ok(rf.get("finance/reports/analysis/fees"))["items"]}
check("Analyse par frais : attendu, réglé et reste par type de frais", Decimal(fee["SCOLARITE"]["paid"]) == Decimal("30000") and Decimal(fee["INSCRIPTION"]["balance"]) == 0, {k2: (v["paid"], v["balance"]) for k2, v in fee.items()})
cas = ok(rf.get("finance/reports/analysis/cashiers"))["items"]
check("Analyse par caissier : paiements valides seulement, nom du caissier", len(cas) == 1 and cas[0]["payment_count"] == 5 and cas[0]["cashier_name"] != "Utilisateur inconnu", cas)
check("Analyse des fonds anticipés disponible", ok(rf.get("finance/reports/analysis/advance-funds"))["items"] == [])
hs = ok(ges.get("finance/reports/historical-status", params={"currency": "CDF"}))
check("Statut de l'import historique (prêt / à vérifier / importé)", set(hs) == {"ready", "to_verify", "posted", "total"}, hs)
mon = ok(ges.get("finance/recovery/monthly", params={"currency": "CDF"}))
check("Recouvrement mensuel : colonne hors caisse séparée et taux d'encaissement", "noncash" in mon["items"][0] and "cash_recovery_rate" in mon["items"][0] and "noncash" in mon["total"], list(mon["items"][0].keys()))
acc = ok(cash.get(f"finance/reports/students/{student}/account"))
check("Relevé du compte : synthèse par devise, paiement annulé marqué ANNULE", acc["summary"] and any(p["status"] == "ANNULE" for p in acc["payments"]), [p["status"] for p in acc["payments"]])
pdf = cash.get(f"finance/reports/students/{student}/account.pdf")
check("Relevé du compte élève PDF", pdf.status_code == 200 and pdf.content[:4] == b"%PDF", pdf.status_code)
rec = cash.post(f"finance/checkout/receipts/{p_two['id']}/print", headers=k())
check("Reçu PDF avec montant en lettres (génération)", rec.status_code == 200 and rec.content[:4] == b"%PDF", rec.status_code)
check("Droits : le caissier ne génère pas le rapport périodique officiel", cash.post("finance/reports/periodic/pdf", json={"profile_code": "CONSOLIDE", "period_type": "JOURNALIER", "start": str(today), "end": str(today)}, headers=k()).status_code == 403)
ok_n = sum(r["pass"] for r in results)
Path(__file__).with_name("reports-live.json").write_text(json.dumps({"school": school["code"], "results": results}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print(f"== {ok_n}/{len(results)} PASS -> reports-live.json")
