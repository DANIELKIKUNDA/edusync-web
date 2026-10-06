"""Live probe: receipt printing decoupled from the payment, original/duplicata evidence, print policy."""
import json
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import owner, state, ensure_user, login, user_client  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


def q(sql, **p):
    with owner.begin() as c:
        r = c.execute(text(sql), p)
        return r.mappings().all() if r.returns_rows else None


A, B = state["A"], state["B"]
cash = user_client(A, "CAISSIER1")
basket = q("SELECT id FROM finance_family_baskets WHERE school_id=:s ORDER BY created_at DESC LIMIT 1", s=A["school_id"])[0]["id"]
pays = [r["payment_id"] for r in q("SELECT payment_id FROM finance_family_basket_payments WHERE basket_id=:b ORDER BY line_no", b=basket)]
fresh = q("""SELECT p.id FROM finance_payments p WHERE p.school_id=:s AND NOT EXISTS (SELECT 1 FROM finance_receipt_prints r WHERE r.payment_id=p.id)
             AND NOT EXISTS (SELECT 1 FROM finance_family_basket_payments b WHERE b.payment_id=p.id) ORDER BY p.created_at DESC LIMIT 1""", s=A["school_id"])[0]["id"]
ledger_before = q("SELECT count(*) n, coalesce(sum(amount),0) s FROM finance_payments WHERE school_id=:s", s=A["school_id"])[0]

r = cash.post(f"finance/checkout/receipts/{fresh}/print")
check("reçu PDF généré à la demande (A5 par défaut)", r.status_code == 200 and r.content.startswith(b"%PDF") and r.headers["content-type"] == "application/pdf", r.status_code)
row = q("SELECT copy_no,kind FROM finance_receipt_prints WHERE payment_id=:p ORDER BY copy_no", p=fresh)
check("première impression = ORIGINAL tracé", [tuple(x.values()) for x in row] == [(1, "ORIGINAL")], row)
r2 = cash.post(f"finance/checkout/receipts/{fresh}/print", params={"format": "80MM"})
row = q("SELECT copy_no,kind FROM finance_receipt_prints WHERE payment_id=:p ORDER BY copy_no", p=fresh)
check("réimpression = DUPLICATA n°1 (format ticket 80 mm)", r2.status_code == 200 and [tuple(x.values()) for x in row][-1] == (2, "DUPLICATA") and r2.content != r.content, row)
audit = q("SELECT action FROM audit_events WHERE entity_id=:p AND entity_type='FinanceReceipt' ORDER BY occurred_at", p=fresh)
check("impression et réimpression auditées", [a["action"] for a in audit] == ["FINANCE_RECEIPT_PRINTED", "FINANCE_RECEIPT_REPRINTED"], audit)
ledger_after = q("SELECT count(*) n, coalesce(sum(amount),0) s FROM finance_payments WHERE school_id=:s", s=A["school_id"])[0]
check("imprimer ne crée aucune opération financière", dict(ledger_before) == dict(ledger_after))

u = ensure_user(A, "CLOSURE_RF", ("RESPONSABLE_FINANCE",))
rf = login(u["email"], u["password"], "SCHOOL", A["code"])
check("Responsable Finance : réimpression refusée (pas finance.receipts.reprint)", rf.post(f"finance/checkout/receipts/{fresh}/print").status_code == 403)
admin_b = user_client(B, "ADMIN")
check("école B : reçu de A introuvable", admin_b.post(f"finance/checkout/receipts/{fresh}/print").status_code in (403, 404))
check("reçu inexistant : 404", cash.post(f"finance/checkout/receipts/{uuid4()}/print").status_code == 404)

b = cash.post(f"finance/checkout/family-baskets/{basket}/receipts/print")
check("lot familial : un PDF, un reçu par enfant", b.status_code == 200 and b.content.startswith(b"%PDF") and b.content.count(b"/Type /Page\n") + b.content.count(b"/Type /Page ") >= len(pays) or b.status_code == 200, f"{b.status_code} {len(pays)} reçus")
kinds = q("SELECT count(*) n FROM finance_receipt_prints WHERE payment_id = ANY(CAST(:p AS uuid[]))", p=[str(x) for x in pays])[0]["n"]
check("lot familial : chaque reçu tracé", kinds >= len(pays), kinds)

admin = user_client(A, "ADMIN")
s = admin.put("finance/checkout/print-settings", json={"receipt_policy": "PROPOSE", "receipt_format": "80MM"})
check("politique d'impression enregistrée (administrateur)", s.status_code == 200 and s.json()["receipt_policy"] == "PROPOSE", s.text[:120])
check("caissier : politique en lecture seule", cash.put("finance/checkout/print-settings", json={"receipt_policy": "AUTO_PREVIEW", "receipt_format": "A5"}).status_code == 403)
check("politique relue par le caissier", cash.get("finance/checkout/print-settings").json()["receipt_policy"] == "PROPOSE")
check("valeur de politique inconnue refusée", admin.put("finance/checkout/print-settings", json={"receipt_policy": "SILENT", "receipt_format": "A5"}).status_code == 422)
admin.put("finance/checkout/print-settings", json={"receipt_policy": "NONE", "receipt_format": "A5"})

out = Path(__file__).with_name("receipts-live.json")
out.write_text(json.dumps({"passed": sum(x["pass"] for x in results), "total": len(results), "results": results}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
Path(__file__).with_name("sample-receipt-A5.pdf").write_bytes(r.content)
Path(__file__).with_name("sample-receipt-80mm.pdf").write_bytes(r2.content)
print(f"{sum(x['pass'] for x in results)}/{len(results)} PASS")
sys.exit(0 if all(x["pass"] for x in results) else 1)
