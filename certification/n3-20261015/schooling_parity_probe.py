"""N3-H — real probe: schooling and other parity items copied from the Desktop golden master (schooling.py
find_probable_students, student_historical_arrears, family_contact_diagnostics, family_kpi_details, change_student_status,
product_sales_report; terrain.contribution_register; finance_checkout.finalize_historical_financial_import spread;
documents.historical_student_suggestions, preview_enrollment_date_repair). Fresh school, real API. Nothing secret printed.
Import and reintegration rights use a test-only role (no standard role holds them).
"""
import io
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from openpyxl import Workbook
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
s = ok(platform().post("platform/schools", json={"code": f"N3H-{run}", "name": f"École scolarité N3-H {run}"}, headers=k()))
school = {"code": f"N3H-{run}", "school_id": s["id"], "users": {}}
state.setdefault("N3H", {})[run] = school
save()
ensure_user(school, "ADMIN", ("ADMIN_SYSTEME_ECOLE",))
ensure_user(school, "CASH", ("CAISSIER",))
ensure_user(school, "GES", ("GESTIONNAIRE",))
ensure_user(school, "OPS", ())
grant_test_role(school, "OPS", "RECETTE_N3H", ("migration.finance_history.analyze", "migration.finance_history.execute", "migration.students.analyze",
                                               "students.lifecycle.reintegrate", "students.read"))
adm, cash, ges, ops = (user_client(school, x) for x in ("ADMIN", "CASH", "GES", "OPS"))
today = date.today()
sy = today.year if today.month >= 9 else today.year - 1
pri = ok(adm.put("settings/sections/PRIMAIRE", json={"code": "PRIMAIRE", "label": "Primaire", "enabled": True}, headers=k()))
sco = ok(adm.post("settings/fee-types", json={"code": "SCOLARITE", "label": "Frais scolaires", "periodicity": "MONTHLY", "default_currency": "CDF"}, headers=k()))


def year(start, label):
    y = ok(adm.post("settings/academic-years", json={"code": label, "label": label, "start_date": f"{start}-09-01", "end_date": f"{start+1}-06-30"}, headers=k()))
    y = ok(adm.post(f"settings/academic-years/{y['id']}/activate", headers=k({"If-Match": str(y["version"])})))
    cls = ok(adm.post("settings/classes", json={"academic_year_id": y["id"], "section_id": pri["id"], "reference_code": "P1", "code": f"P1{label[-2:]}", "label": f"P1 {label}"}, headers=k()))
    ok(adm.put("settings/tariff-rules", json={"academic_year_id": y["id"], "fee_type_id": sco["id"], "scope_type": "SCHOOL", "amount": "20000", "currency": "CDF"}, headers=k()))
    ok(adm.post("settings/admission-conditions/review", headers=k()))
    ok(adm.post("settings/tariffs/apply", json={"academic_year_id": y["id"]}, headers=k()))
    return y, cls


# ---------- previous year with unpaid charges, then the current year ----------
y1, c1 = year(sy - 1, f"{sy-1}-{sy}")
d1 = ok(cash.post("schooling/enrollments/family", json={"primary_guardian": {"full_name": f"Tuteur {run}", "is_primary": True},
        "children": [{"last_name": f"DUPONT{run}", "middle_name": "Recette", "first_name": "Jean", "gender": "M", "birth_date": f"{sy-8}-03-14", "class_id": c1["id"]}]}, headers=k()))
student, family_enr1 = d1["student_ids"][0], d1["enrollment_ids"][0]
y1 = adm.get("settings/academic-years").json()
y1 = next(x for x in (y1 if isinstance(y1, list) else y1.get("items", [])) if x["code"] == f"{sy-1}-{sy}")
ok(adm.post(f"settings/academic-years/{y1['id']}/close", headers=k({"If-Match": str(y1["version"])})))
y2, c2 = year(sy, f"{sy}-{sy+1}")
fam = ok(cash.get(f"schooling/students/{student}"))
with owner.connect() as _c:
    fam_id = str(_c.execute(text("SELECT family_id FROM students WHERE id=:s"), {"s": student}).scalar_one())
# G-SCO-1 probable duplicates
pr = ok(cash.get("schooling/students/probable", params={"last_name": f"dupont{run}"}))["items"]
check("Doublons probables : l'élève existant est proposé avant toute nouvelle fiche", len(pr) == 1 and pr[0]["id"] == student, [p["matricule"] for p in pr])
check("Doublons probables : filtre par date de naissance", ok(cash.get("schooling/students/probable", params={"last_name": f"DUPONT{run}", "birth_date": f"{sy-8}-03-15"}))["items"] == [])
# G-SCO-2 historical arrears
arr = ok(cash.get(f"schooling/students/{student}/historical-arrears"))["items"]
check("Arriérés historiques : l'année précédente, jamais mêlée à la nouvelle", len(arr) == 1 and arr[0]["year_label"] == f"{sy-1}-{sy}" and Decimal(arr[0]["balance"]) == Decimal("200000"), arr)
# G-SCO-6 re-enrollment of the existing pupil
d2 = cash.post("schooling/enrollments/family", json={"family_id": fam_id, "children": [{"student_id": student, "last_name": f"DUPONT{run}", "middle_name": "Recette", "first_name": "Jean", "gender": "M", "class_id": c2["id"]}]}, headers=k())
check("Réinscription de l'élève existant dans la nouvelle année (même matricule)", d2.status_code in (200, 201), d2.text[:160])
enr2 = d2.json()["enrollment_ids"][0] if d2.status_code in (200, 201) else None
d3 = cash.post("schooling/enrollments/family", json={"family_id": fam_id, "children": [{"student_id": student, "last_name": f"DUPONT{run}", "middle_name": "Recette", "first_name": "Jean", "gender": "M", "class_id": c2["id"]}]}, headers=k())
check("Réinscription : une seconde fois dans la même année refusée", d3.status_code in (409, 422), d3.status_code)
# G-SCO-4 / G-SCO-3 families
d4 = ok(cash.post("schooling/enrollments/family", json={"primary_guardian": {"full_name": f"Sans Téléphone {run}", "is_primary": True},
        "children": [{"last_name": f"MARTIN{run}", "middle_name": "Recette", "first_name": "Lea", "gender": "F", "class_id": c2["id"]}]}, headers=k()))
diag = ok(ges.get("schooling/families/diagnostics"))
check("Diagnostic des contacts famille (sans responsable, plusieurs principaux, sans téléphone, téléphones partagés)",
      set(diag) == {"without_responsible", "multiple_primary", "responsible_without_phone", "shared_phones"} and diag["responsible_without_phone"] >= 1, diag)
ov = ok(ges.get("schooling/families/overview"))
check("Vue d'ensemble des familles (familles, familles nombreuses, bénéficiaires, enfants du personnel)", ov["families"] == 2 and ov["large_family_min_children"] == 5, ov)
check("Indicateurs détaillés : familles nombreuses, bénéficiaires, enfants du personnel", all(ges.get(f"schooling/families/kpi/{m}").status_code == 200 for m in ("LARGE_ELIGIBLE", "BENEFICIARIES", "STAFF_CHILDREN"))
      and ges.get("schooling/families/kpi/INCONNU").status_code == 409)
# G-SCO-5 suspension
st = ok(cash.get(f"schooling/students/{student}"))
r = cash.post(f"schooling/students/{student}/suspend", json={"effective_date": str(today), "reason": "Suspension disciplinaire"}, headers=k({"If-Match": str(st["version"])}))
check("Suspension par le caissier (même périmètre que l'abandon, Desktop)", r.status_code == 200 and r.json().get("status") == "SUSPENDED", r.text[:160])
with owner.connect() as c:
    neutral = c.execute(text("SELECT count(*) FROM finance_charge_lifecycle_states ls JOIN finance_charges fc ON fc.id=ls.charge_id WHERE fc.enrollment_id=:e"), {"e": enr2}).scalar_one()
check("Suspension : les mensualités futures impayées sont neutralisées (réversible)", neutral >= 1, neutral)
st = ok(cash.get(f"schooling/students/{student}"))
r = cash.post(f"schooling/students/{student}/suspend", json={"effective_date": str(today), "reason": "Encore"}, headers=k({"If-Match": str(st["version"])}))
check("Suspension : statut déjà suspendu refusé (message Desktop)", r.status_code == 409 and "possède déjà ce statut" in r.text, r.status_code)
other = ok(cash.get(f"schooling/students/{d4['student_ids'][0]}"))
r = ops.post(f"schooling/students/{other['id']}/reintegrate", json={"effective_date": str(today), "reason": "Essai"}, headers=k({"If-Match": str(other["version"])}))
check("Réintégration d'un élève actif refusée (Desktop : statut déjà actif)", r.status_code == 409 and "possède déjà ce statut" in r.text, (r.status_code, r.text[:100]))
r = ops.post(f"schooling/students/{student}/reintegrate", json={"effective_date": str(today), "reason": "Fin de la suspension"}, headers=k({"If-Match": str(st["version"])}))
with owner.connect() as c:
    neutral2 = c.execute(text("SELECT count(*) FROM finance_charge_lifecycle_states ls JOIN finance_charges fc ON fc.id=ls.charge_id WHERE fc.enrollment_id=:e"), {"e": enr2}).scalar_one()
check("Réintégration après suspension : frais futurs rétablis", r.status_code == 200 and neutral2 == 0, (r.status_code, neutral2))
# G-EFF-1 contribution register
ct = ok(adm.post("settings/contributions", json={"code": f"RAM{run}", "label": "Rames de papier", "unit": "rame", "required_quantity": "2"}, headers=k()))
ok(cash.post("effectifs/deposits", json={"student_id": student, "enrollment_id": enr2, "contribution_type_id": ct["id"], "quantity": "1", "deposited_on": str(today)}, headers=k()))
reg = ok(ges.get("effectifs/contribution-register"))
cell = next(r2 for r2 in reg["rows"] if r2["student_id"] == student)["items"][ct["id"]]
check("Registre des contributions : exigé 2, déposé 1, reste 1 (jamais un paiement)", (Decimal(cell["required"]), Decimal(cell["delivered"]), Decimal(cell["remaining"])) == (Decimal("2"), Decimal("1"), Decimal("1")), cell)
# G-ART-1 product sales report
prod = ok(adm.post("settings/products", json={"code": f"TEN{run}", "label": "Tenue de sport", "unit_price": "15000", "currency": "CDF", "stock_tracking": False}, headers=k()))
if not cash.get("finance/cash/current").json().get("session"):
    ok(cash.post("finance/cash/open", json={"opening_cdf": 0, "opening_usd": 0}))
ok(cash.post("finance/checkout/products/sell", json={"student_id": student, "enrollment_id": enr2, "product_id": prod["id"], "quantity": "2"}, headers=k()))
ps = ok(ges.get("finance/reports/product-sales", params={"start": str(today), "end": str(today)}))
check("Rapport des ventes d'articles : ligne, caissier, total FC", len(ps["rows"]) == 1 and ps["rows"][0]["cashier_name"] not in ("—", None) and ps["totals"] == [{"currency": "CDF", "amount": "30000.00"}], ps["totals"])
# G-IMP-1 historical spread (outside cash)
mat = fam["matricule"]


def fin_xlsx(amount, period="Septembre"):
    from openpyxl import load_workbook
    tpl = ops.get("import/finance-history/template.xlsx").content          # official template, filled as a school would
    wb = load_workbook(io.BytesIO(tpl)); ws = wb.worksheets[0]
    head = next(r for r in range(1, 30) if any(str(c.value or "").startswith("Année scolaire") for c in ws[r]))
    cols = {str(c.value): c.column for c in ws[head] if c.value}
    row = head + 1
    while any(ws.cell(row, cc).value for cc in cols.values()):
        row += 1
    vals = {"Année scolaire*": f"{sy}-{sy+1}", "Matricule élève*": mat, "Frais*": "SCOLARITE", "Période": period, "Montant*": amount, "Devise*": "CDF",
            "Date paiement*": f"{sy}-09-20", "Référence historique": f"HIST-{uuid4().hex[:6]}", "Observation": "Reprise N3-H"}
    for k2, v in vals.items():
        if k2 in cols:
            ws.cell(row, cols[k2]).value = v
    out = io.BytesIO(); wb.save(out); return out.getvalue()


an = ops.post("import/finance-history/analyze", params={"filename": "reprise.xlsx"}, content=fin_xlsx(30000), headers={"Content-Type": "application/octet-stream"})
a = an.json() if an.status_code == 200 else {}
line = (a.get("preview") or [{}])[0]
check("Reprise historique : montant au-delà du mois réparti sur les mois suivants (Desktop)", an.status_code == 200 and line.get("status") == "WARNING"
      and [x["amount"] for x in line.get("data", {}).get("allocations", [])] == ["20000.00", "10000"] or [Decimal(x["amount"]) for x in line.get("data", {}).get("allocations", [])] == [Decimal("20000"), Decimal("10000")], line.get("data", {}).get("allocations"))
with owner.connect() as c:
    pays_before = c.execute(text("SELECT count(*) FROM finance_payments WHERE school_id=:s"), {"s": school["school_id"]}).scalar_one()
    row_id = c.execute(text("SELECT id FROM financial_history_import_rows WHERE batch_id=:b"), {"b": a.get("batch_id")}).scalar_one()
ex = ops.post(f"import/finance-history/batches/{a.get('batch_id')}/execute", json={"accept_warnings": True, "confirm_outside_cash": True}, headers=k())
with owner.connect() as c:
    pays_after = c.execute(text("SELECT count(*) FROM finance_payments WHERE school_id=:s"), {"s": school["school_id"]}).scalar_one()
    regs = c.execute(text("SELECT count(*) FROM finance_charge_regularizations r JOIN finance_charges fc ON fc.id=r.charge_id WHERE fc.enrollment_id=:e"), {"e": enr2}).scalar_one()
check("Reprise exécutée hors caisse : 2 régularisations (septembre, octobre), aucun paiement ni reçu", ex.status_code == 200 and regs == 2 and pays_after == pays_before, (ex.status_code, regs, pays_before, pays_after))
an2 = ops.post("import/finance-history/analyze", params={"filename": "reprise2.xlsx"}, content=fin_xlsx(99999999), headers={"Content-Type": "application/octet-stream"})
check("Reprise : montant qu'aucun mois ne peut absorber refusé", an2.status_code == 200 and an2.json()["preview"][0]["status"] == "ERROR", an2.status_code)
sug = ok(ops.get(f"import/finance-history/rows/{row_id}/suggestions"))
check("Suggestions d'élève pour une ligne de reprise (classées, confiance)", sug["suggestions"] and sug["suggestions"][0]["matricule"] == mat and sug["suggestions"][0]["confidence"] == "FORTE", sug["suggestions"][:1])
# G-IMP-2 enrollment date repair preview (read only)
wb = Workbook(); ws = wb.active
ws.append(["Nom", "Postnom", "Prénom", "Sexe", "Classe", "Date inscription"])
ws.append([f"DUPONT{run}", "Recette", "Jean", "M", f"P1 {sy}-{sy+1}", f"{sy}-08-30"])
ws.append([f"INCONNU{run}", "X", "Y", "F", "P1", f"{sy}-09-02"])
ws.append([f"MARTIN{run}", "Recette", "Lea", "F", "", ""])
buf = io.BytesIO(); wb.save(buf)
pv = ops.post("import/students/date-repair/preview", content=buf.getvalue(), headers={"Content-Type": "application/octet-stream"})
items = pv.json().get("items", []) if pv.status_code == 200 else []
check("Contrôle des dates d'inscription : correspondance certaine → correction proposée", items and items[0]["status"] == "MATCH_CERTAIN" and items[0]["action"].startswith("Corriger"), items[:1])
check("Contrôle des dates : élève inconnu et date absente signalés, rien n'est modifié", len(items) == 3 and items[1]["status"] == "NON_TROUVE" and items[2]["status"] == "A_VERIFIER", [i["status"] for i in items])
ok_n = sum(r["pass"] for r in results)
Path(__file__).with_name("schooling-parity-live.json").write_text(json.dumps({"school": school["code"], "results": results}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print(f"== {ok_n}/{len(results)} PASS -> schooling-parity-live.json")
