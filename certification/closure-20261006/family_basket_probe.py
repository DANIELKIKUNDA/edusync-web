"""Live probe: family basket (real API + PostgreSQL, tenant role under FORCE RLS).

Fixture: one-off charges are inserted by the owner role (no tariff->charge generator exists, see report);
every payment goes through the public API.
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
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
fam = A["family"]
family_id = fam.get("family_id") or q("SELECT s.family_id FROM enrollments e JOIN students s ON s.id=e.student_id WHERE e.id=:e", e=fam["enrollment_ids"][0])[0]["family_id"]
e0, e1, e2 = fam["enrollment_ids"][:3]
tag = uuid4().hex[:6]


def charge(eid, label, cur, amount):
    return str(q("""INSERT INTO finance_charges(school_id,enrollment_id,label,currency,net_amount,periodicity)
                    VALUES(:s,:e,:l,:c,:a,'ONE_OFF') RETURNING id""", s=A["school_id"], e=eid, l=f"Panier {tag} · {label}", c=cur, a=amount)[0]["id"])


def paid(cid):
    return Decimal(str(q("SELECT paid_amount FROM finance_charges WHERE id=:i", i=cid)[0]["paid_amount"]))


x0 = charge(e0, "Uniforme", "CDF", 50000)
x1 = charge(e1, "Transport", "USD", 20)
x2 = charge(e2, "Activités", "CDF", 60000)
cash = user_client(A, "CAISSIER1")
if not cash.get("finance/cash/current").json().get("session"):
    cash.post("finance/cash/open", json={"opening_cdf": 0, "opening_usd": 0}, headers={"Idempotency-Key": str(uuid4())})

payments_before = q("SELECT count(*) n FROM finance_payments WHERE school_id=:s", s=A["school_id"])[0]["n"]
body = {"family_id": str(family_id), "lines": [
    {"enrollment_id": e0, "charge_ids": [x0], "amount": "30000", "currency": "CDF"},
    {"enrollment_id": e1, "charge_ids": [x1], "amount": "15", "currency": "USD"},
    {"enrollment_id": e2, "charge_ids": [x2], "amount": "60000", "currency": "CDF"}]}
key = "basket-" + uuid4().hex
r = cash.post("finance/checkout/family-collect", json=body, headers={"Idempotency-Key": key})
res = r.json() if r.status_code == 200 else {}
check("panier familial de 3 enfants encaissé", r.status_code == 200 and len(res.get("lines", [])) == 3, r.text[:200])
receipts = [l["receipt_number"] for l in res.get("lines", [])]
check("un reçu distinct par ligne (par enfant)", len(set(receipts)) == 3, receipts)
check("CDF et USD totalisés séparément", res.get("totals") == {"CDF": "90000", "USD": "15"}, res.get("totals"))
check("allocations explicites sur les frais choisis", (paid(x0), paid(x1), paid(x2)) == (Decimal(30000), Decimal(15), Decimal(60000)))
check("chaque ligne : allocation = montant", all(sum(Decimal(a["amount"]) for a in l["allocations"]) == Decimal(l["amount"]) for l in res.get("lines", [])))

again = cash.post("finance/checkout/family-collect", json=body, headers={"Idempotency-Key": key})
check("rejeu même clé : même panier, aucun nouveau paiement", again.status_code == 200 and again.json()["replayed"] is True and again.json()["basket_id"] == res.get("basket_id")
      and q("SELECT count(*) n FROM finance_payments WHERE school_id=:s", s=A["school_id"])[0]["n"] == payments_before + 3)
other = dict(body, lines=body["lines"][:1])
check("même clé, autre contenu : refusé", cash.post("finance/checkout/family-collect", json=other, headers={"Idempotency-Key": key}).status_code == 409)

# Atomicity: second line overpays -> the whole basket is refused, first line not persisted.
y0 = charge(e0, "Cantine", "CDF", 10000)
y1 = charge(e1, "Sortie", "CDF", 5000)
bad = {"family_id": str(family_id), "lines": [{"enrollment_id": e0, "charge_ids": [y0], "amount": "10000", "currency": "CDF"},
                                              {"enrollment_id": e1, "charge_ids": [y1], "amount": "7000", "currency": "CDF"}]}
r = cash.post("finance/checkout/family-collect", json=bad, headers={"Idempotency-Key": str(uuid4())})
check("ligne invalide : panier entier refusé (tout ou rien)", r.status_code == 409 and paid(y0) == 0 and paid(y1) == 0, f"{r.status_code} {paid(y0)}")

foreign = {"family_id": str(family_id), "lines": [{"enrollment_id": B["family"]["enrollment_ids"][0], "charge_ids": [y0], "amount": "1", "currency": "CDF"}]}
check("élève d'une autre école/famille : refusé", cash.post("finance/checkout/family-collect", json=foreign, headers={"Idempotency-Key": str(uuid4())}).status_code == 409)
mixed = {"family_id": str(family_id), "lines": [{"enrollment_id": e0, "charge_ids": [y0], "amount": "1", "currency": "USD"}]}
check("devise incohérente dans une ligne : refusée", cash.post("finance/checkout/family-collect", json=mixed, headers={"Idempotency-Key": str(uuid4())}).status_code == 409)
dup = {"family_id": str(family_id), "lines": [{"enrollment_id": e0, "charge_ids": [y0], "amount": "1", "currency": "CDF"}, {"enrollment_id": e0, "charge_ids": [y0], "amount": "1", "currency": "CDF"}]}
check("deux lignes même élève/devise : refusées (à regrouper)", cash.post("finance/checkout/family-collect", json=dup, headers={"Idempotency-Key": str(uuid4())}).status_code == 409)
check("sans Idempotency-Key : refusé", cash.post("finance/checkout/family-collect", json=bad).status_code == 400)

gest = user_client(A, "GEST")
r = gest.post("finance/checkout/family-collect", json=bad, headers={"Idempotency-Key": str(uuid4())})
check("rôle sans finance.checkout.family.collect : 403", r.status_code == 403, r.status_code)
u = ensure_user(A, "CLOSURE_CASH_NOSESSION", ("CAISSIER",))
nos = login(u["email"], u["password"], "SCHOOL", A["code"])
r = nos.post("finance/checkout/family-collect", json={"family_id": str(family_id), "lines": [bad["lines"][0]]}, headers={"Idempotency-Key": str(uuid4())})
check("caissier sans caisse ouverte : refusé", r.status_code == 409 and "caisse" in r.text.lower(), r.text[:120])

# Concurrency: two cashiers, same charge, simultaneous baskets -> exactly one succeeds, no over-allocation.
z = charge(e2, "Concours", "CDF", 20000)
c2 = user_client(A, "CAISSIER2")
if not c2.get("finance/cash/current").json().get("session"):
    c2.post("finance/cash/open", json={"opening_cdf": 0, "opening_usd": 0}, headers={"Idempotency-Key": str(uuid4())})
race = {"family_id": str(family_id), "lines": [{"enrollment_id": e2, "charge_ids": [z], "amount": "20000", "currency": "CDF"}]}
with ThreadPoolExecutor(2) as pool:
    codes = list(pool.map(lambda c: c.post("finance/checkout/family-collect", json=race, headers={"Idempotency-Key": str(uuid4())}).status_code, (cash, c2)))
check("2 caissiers simultanés sur le même frais : un seul encaissement", sorted(codes) == [200, 409] and paid(z) == Decimal(20000), codes)
w = charge(e0, "Bibliothèque", "CDF", 8000)
k = str(uuid4()); same = {"family_id": str(family_id), "lines": [{"enrollment_id": e0, "charge_ids": [w], "amount": "8000", "currency": "CDF"}]}
with ThreadPoolExecutor(3) as pool:
    outs = list(pool.map(lambda _: cash.post("finance/checkout/family-collect", json=same, headers={"Idempotency-Key": k}), range(3)))
check("même clé envoyée 3 fois en parallèle : 1 panier, réponses identiques", all(o.status_code == 200 for o in outs) and len({o.json()["basket_id"] for o in outs}) == 1 and paid(w) == Decimal(8000)
      and q("SELECT count(*) n FROM finance_family_baskets WHERE school_id=:s AND idempotency_key=:k", s=A["school_id"], k=k)[0]["n"] == 1, [o.status_code for o in outs])

ledger = q("""SELECT count(*) n FROM finance_family_basket_payments bp JOIN finance_payments p ON p.id=bp.payment_id
              WHERE p.amount <> (SELECT coalesce(sum(a.amount),0) FROM finance_payment_allocations a WHERE a.payment_id=p.id)""")[0]["n"]
check("grand livre : chaque paiement de panier = somme de ses allocations", ledger == 0, ledger)
admin_b = user_client(B, "ADMIN")
check("école B : panier de A introuvable", admin_b.get(f"finance/checkout/family-baskets/{res.get('basket_id')}").status_code in (403, 404))
try:
    with owner.begin() as c:
        c.execute(text("SET LOCAL ROLE edusync_tenant"))
        c.execute(text("SELECT set_config('app.current_school_id',:s,true)"), {"s": A["school_id"]})
        c.execute(text("DELETE FROM finance_family_basket_payments WHERE basket_id=:b"), {"b": res.get("basket_id")})
    check("panier append-only pour le rôle applicatif", False)
except Exception as exc:  # noqa: BLE001
    check("panier append-only pour le rôle applicatif", getattr(getattr(exc, "orig", None), "sqlstate", "") == "42501", type(exc).__name__)

out = Path(__file__).with_name("family-basket-live.json")
out.write_text(json.dumps({"passed": sum(x["pass"] for x in results), "total": len(results), "results": results}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print(f"{sum(x['pass'] for x in results)}/{len(results)} PASS")
sys.exit(0 if all(x["pass"] for x in results) else 1)
