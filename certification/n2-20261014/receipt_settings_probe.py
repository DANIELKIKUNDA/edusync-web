"""Live probe — parity lot L7: receipt settings copied from the Desktop golden master.

Desktop reference (EduSync École Offline 0.11.0-rc.1): configuration.py::save_document_settings; database.py::next_receipt_no
(PREFIX-YEAR-000123, atomic counter per calendar year, one sequence for every cash entry); services/documents.py (receipt
copies 1..5, formats 80 mm / 58 mm / A5). Fresh school, real cash desk.
"""
import json
import re
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


def new_school(tag):
    s = ok(platform().post("platform/schools", json={"code": f"L7{tag}-{run}", "name": f"École reçus L7{tag} {run}"}, headers=k()))
    sch = {"code": f"L7{tag}-{run}", "school_id": s["id"], "users": {}}
    state.setdefault("L7", {})[f"{tag}{run}"] = sch
    save()
    ensure_user(sch, "ADMIN", ("ADMIN_SYSTEME_ECOLE",))
    ensure_user(sch, "CASH", ("CAISSIER",))
    adm, cash = user_client(sch, "ADMIN"), user_client(sch, "CASH")
    today = date.today(); sy = today.year if today.month >= 9 else today.year - 1
    y = ok(adm.post("settings/academic-years", json={"code": f"{sy}-{sy+1}", "label": f"{sy}-{sy+1}", "start_date": f"{sy}-09-01", "end_date": f"{sy+1}-06-30"}, headers=k()))
    y = ok(adm.post(f"settings/academic-years/{y['id']}/activate", headers=k({"If-Match": str(y["version"])})))
    sec = ok(adm.put("settings/sections/PRIMAIRE", json={"code": "PRIMAIRE", "label": "Primaire", "enabled": True}, headers=k()))
    cl = ok(adm.post("settings/classes", json={"academic_year_id": y["id"], "section_id": sec["id"], "reference_code": "P1", "code": "P1A", "label": "P1A"}, headers=k()))
    fee = ok(adm.post("settings/fee-types", json={"code": "INSCRIPTION", "label": "Inscription", "periodicity": "ONE_TIME", "default_currency": "CDF"}, headers=k()))
    ok(adm.put("settings/tariff-rules", json={"academic_year_id": y["id"], "fee_type_id": fee["id"], "scope_type": "SCHOOL", "amount": "15000", "currency": "CDF"}, headers=k()))
    ok(adm.post("settings/admission-conditions/review", headers=k()))
    ok(adm.post("settings/tariffs/apply", json={"academic_year_id": y["id"]}, headers=k()))
    d = ok(cash.post("schooling/enrollments/family", json={"primary_guardian": {"full_name": f"Tuteur {tag}", "is_primary": True},
            "children": [{"last_name": f"REC{tag}{run}", "middle_name": "Recette", "first_name": "L7", "gender": "F", "class_id": cl["id"]}]}, headers=k()))
    if not cash.get("finance/cash/current").json().get("session"):
        ok(cash.post("finance/cash/open", json={"opening_cdf": 0, "opening_usd": 0}))
    return adm, cash, d["enrollment_ids"][0], d["student_ids"][0]


run = uuid4().hex[:5].upper()
adm, cash, enr, stu = new_school("A")
year = date.today().year


def pay(amount="5000"):
    ch = next(i for i in cash.get(f"finance/checkout/balance/{enr}").json()["items"] if i["eligible"])
    return cash.post("finance/checkout/collect", json={"enrollment_id": enr, "charge_ids": [ch["id"]], "amount": amount, "currency": "CDF"}, headers=k())


p0 = cash.get("finance/checkout/print-settings").json()
check("Réglages par défaut : préfixe REC, 1 copie", p0.get("receipt_prefix") == "REC" and p0.get("receipt_copies") == 1, p0)
r1 = ok(pay())
check("Reçu numéroté PRÉFIXE-ANNÉE-000001 (Desktop)", r1["receipt_number"] == f"REC-{year}-000001", r1["receipt_number"])
r = adm.put("finance/checkout/print-settings", json={"receipt_policy": "PROPOSE", "receipt_format": "58MM", "receipt_prefix": "rcu", "receipt_copies": 2}, headers=k())
check("Réglages : préfixe RCU (mis en majuscules), 2 copies, ticket 58 mm", r.status_code == 200 and r.json()["receipt_prefix"] == "RCU" and r.json()["receipt_copies"] == 2, r.text[:160])
r2 = ok(pay())
check("Reçu suivant : nouveau préfixe, compteur continu (000002)", r2["receipt_number"] == f"RCU-{year}-000002", r2["receipt_number"])
prod = ok(adm.post("settings/products", json={"code": "PULL", "label": "Pull", "currency": "CDF", "unit_price": "12000", "stock_tracking": False}, headers=k()))
sale = cash.post("finance/checkout/products/sell", json={"enrollment_id": enr, "student_id": stu, "product_id": prod["id"], "quantity": "1"}, headers=k())
sale_no = sale.json().get("receipt_number") if sale.status_code in (200, 201) else None
check("Vente d'article : même séquence de reçus (000003)", sale_no == f"RCU-{year}-000003", (sale.status_code, sale_no, sale.text[:120]))
pdf = cash.post(f"finance/checkout/receipts/{r2['id']}/print")
pages = len(re.findall(rb"/Type\s*/Page[^s]", pdf.content))
mbox = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)", pdf.content)
width_mm = round(float(mbox.group(1)) / 72 * 25.4) if mbox else None
check("Impression : 2 exemplaires dans le PDF", pdf.status_code == 200 and pages == 2, (pdf.status_code, pages))
check("Impression : ticket de 58 mm de large", width_mm == 58, width_mm)
check("Préfixe invalide (caractères spéciaux) refusé", adm.put("finance/checkout/print-settings", json={"receipt_policy": "NONE", "receipt_format": "A5", "receipt_prefix": "R-1", "receipt_copies": 1}, headers=k()).status_code == 422)
check("Plus de 5 copies refusé", adm.put("finance/checkout/print-settings", json={"receipt_policy": "NONE", "receipt_format": "A5", "receipt_prefix": "REC", "receipt_copies": 6}, headers=k()).status_code == 422)
check("Sans droit : le caissier ne modifie pas les réglages d'impression (403)",
      cash.put("finance/checkout/print-settings", json={"receipt_policy": "NONE", "receipt_format": "A5", "receipt_prefix": "REC", "receipt_copies": 1}, headers=k()).status_code == 403)
adm_b, cash_b, enr_b, _ = new_school("B")
ch_b = next(i for i in cash_b.get(f"finance/checkout/balance/{enr_b}").json()["items"] if i["eligible"])
rb = ok(cash_b.post("finance/checkout/collect", json={"enrollment_id": enr_b, "charge_ids": [ch_b["id"]], "amount": "1000", "currency": "CDF"}, headers=k()))
check("Autre école : sa propre séquence (000001), indépendante", rb["receipt_number"] == f"REC-{year}-000001", rb["receipt_number"])
with owner.connect() as c:
    audit = c.execute(text("SELECT new_json FROM audit_events WHERE action='PRINT_SETTINGS_UPDATED' AND school_id=(SELECT school_id FROM finance_payments WHERE id=:p) ORDER BY occurred_at DESC LIMIT 1"),
                      {"p": r2["id"]}).scalar_one()
check("Audit : préfixe et copies tracés", audit.get("receipt_prefix") == "RCU" and audit.get("receipt_copies") == 2, audit)

passed = sum(r["pass"] for r in results)
out = Path(__file__).with_name("receipt-settings-live.json")
out.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"== {passed}/{len(results)} PASS -> {out.name}")
sys.exit(0 if passed == len(results) else 1)
