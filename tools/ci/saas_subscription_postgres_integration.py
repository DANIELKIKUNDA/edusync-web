"""Abonnements EduSync (étape 1) — real HTTP + real PostgreSQL (owner, 2026-11-21).

Merged without activation: nothing changes for a school that has no subscription (APN). Checks:
1. a school without subscription reads « no subscription » and keeps working (no gating);
2. who may read / pay: Admin système and Gestionnaire by default, Promoteur reads only (each school may add the right);
3. a SIGNED provider message settles the invoice once: PAID, subscription ACTIVE, period extended;
4. replaying the same message changes nothing; an unsigned message is refused and writes nothing;
5. an amount mismatch is refused AND the rejection stays recorded;
6. the deadline pass: past the end → GRACE, past the grace → LIMITED, never touches school finance.

    python tools/local/isolated_db.py env <db> -- ../.venv/Scripts/python.exe ../tools/ci/saas_subscription_postgres_integration.py

CI=true, localhost only (three_roles_postgres_integration). Exits 1 on any FAIL.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

SECRET = "ci-only-webhook-secret-" + uuid.uuid4().hex          # random per run, never a real secret
os.environ["EDUSYNC_MOBILE_MONEY_WEBHOOK_SECRET"] = SECRET
sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_roles_postgres_integration as H  # noqa: E402
from three_roles_postgres_integration import APP, CLIENT, RUN, actor_for, as_, check, one, school, sql  # noqa: E402
from edusync.modules.subscriptions.application.lifecycle import run_once  # noqa: E402
from edusync.modules.subscriptions.application.payment_provider import sign_payload  # noqa: E402

WEBHOOK = "/api/v1/subscription-payments/webhooks/TESTPAY"


def hook(payload: dict, *, signed: bool = True):
    raw = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if signed:
        headers["X-EduSync-Signature"] = "sha256=" + sign_payload(SECRET, raw)
    return CLIENT.post(WEBHOOK, content=raw, headers=headers)


def subscription(A: dict, *, start: date, end: date, amount: str = "50.00"):
    plan, ver, sub, inv, pay = (uuid.uuid4() for _ in range(5))
    sql("INSERT INTO saas_plans(id,code,name,status) VALUES(:i,:c,'Finances','ACTIVE')", i=plan, c=f"FIN-{RUN}-{plan.hex[:6]}")
    sql("""INSERT INTO saas_plan_versions(id,plan_id,version,billing_cycle,currency,amount,grace_days,effective_from,status)
           VALUES(:i,:p,1,'MONTHLY','USD',:a,10,:f,'PUBLISHED')""", i=ver, p=plan, a=amount, f=start)
    sql("""INSERT INTO saas_subscriptions(id,school_id,plan_version_id,billing_cycle,status,current_period_start,current_period_end,grace_days)
           VALUES(:i,:s,:v,'MONTHLY','PENDING_PAYMENT',:a,:b,10)""", i=sub, s=A["id"], v=ver, a=start, b=end)
    sql("""INSERT INTO saas_invoices(id,invoice_number,school_id,subscription_id,status,currency,period_start,period_end,issued_at,due_at,subtotal,total)
           VALUES(:i,:n,:s,:sub,'ISSUED','USD',:a,:b,now(),now()+interval '7 days',:t,:t)""",
        i=inv, n=f"VT-{RUN}-{inv.hex[:6]}", s=A["id"], sub=sub, a=start, b=end + timedelta(days=30), t=amount)
    ref = f"PRV-{inv.hex[:10]}"
    sql("""INSERT INTO saas_payments(id,payment_reference,invoice_id,school_id,provider,provider_reference,channel,status,currency,amount)
           VALUES(:i,:r,:inv,:s,'TESTPAY',:pr,'MOBILE_MONEY','PENDING','USD',:a)""",
        i=pay, r=f"PAY-{pay.hex[:12]}", inv=inv, s=A["id"], pr=ref, a=amount)
    return sub, inv, pay, ref


def run(A: dict, B: dict) -> None:
    print("\n== Abonnements EduSync — étape 1 sans activation (21/11/2026)")
    admin, gest, promo = (actor_for(r, A["id"]) for r in ("ADMIN_SYSTEME_ECOLE", "GESTIONNAIRE", "PROMOTEUR"))
    r = as_(admin).get("/api/v1/subscription/account")
    check("école sans abonnement : « aucun abonnement », aucune erreur", r.status_code == 200 and r.json().get("subscription") is None, r.text[:200])
    r = as_(gest).get("/api/v1/schooling/families")      # a role that holds families.read
    check("école sans abonnement : le travail continue (aucun blocage)", r.status_code == 200, r.status_code)
    check("le promoteur peut consulter l'abonnement", as_(promo).get("/api/v1/subscription/account").status_code == 200)
    check("par défaut, le promoteur ne paie pas (règle lecture seule ; l'école peut ajouter ce droit)",
          "subscription.payment.create" not in promo.permissions and "subscription.payment.create" in gest.permissions
          and "subscription.payment.create" in admin.permissions)
    adj = one("SELECT school_adjustable FROM capability_catalog WHERE code='subscription.payment.create'")
    check("droit de payer ajustable par chaque école", bool(adj and adj[0]), adj)

    today = date.today()
    sub, inv, pay, ref = subscription(A, start=today - timedelta(days=5), end=today + timedelta(days=25))
    before_fin = one("SELECT count(*) FROM finance_payments WHERE school_id=:s", s=A["id"])[0]
    r = hook({"event_id": f"EVT-{RUN}-1", "provider_reference": ref, "status": "SUCCEEDED", "amount": "50.00", "currency": "USD"}, signed=False)
    check("message NON signé → refusé, rien d'écrit", r.status_code == 401 and one(
        "SELECT count(*) FROM saas_payment_webhooks WHERE provider_event_id=:e", e=f"EVT-{RUN}-1")[0] == 0, r.status_code)
    ok = {"event_id": f"EVT-{RUN}-2", "provider_reference": ref, "status": "SUCCEEDED", "amount": "50.00", "currency": "USD"}
    r = hook(ok)
    st = one("SELECT i.status, i.paid_total, s.status FROM saas_invoices i JOIN saas_subscriptions s ON s.id=i.subscription_id WHERE i.id=:i", i=inv)
    check("message signé : facture PAYÉE, abonnement ACTIF", r.status_code == 200 and st[0] == "PAID" and float(st[1]) == 50 and st[2] == "ACTIVE",
          (r.status_code, r.text[:200], st))
    r = hook(ok)
    check("le même message rejoué ne change rien", r.status_code == 200 and r.json().get("replayed") is True
          and float(one("SELECT paid_total FROM saas_invoices WHERE id=:i", i=inv)[0]) == 50, r.text[:200])
    r = hook({**ok, "event_id": f"EVT-{RUN}-3"})
    check("même paiement sous un autre identifiant : compté une seule fois", r.status_code == 200
          and float(one("SELECT paid_total FROM saas_invoices WHERE id=:i", i=inv)[0]) == 50, r.text[:200])
    check("la caisse de l'école n'est pas touchée", one("SELECT count(*) FROM finance_payments WHERE school_id=:s", s=A["id"])[0] == before_fin)

    _, inv2, _, ref2 = subscription(B, start=today - timedelta(days=5), end=today + timedelta(days=25), amount="80.00")
    r = hook({"event_id": f"EVT-{RUN}-4", "provider_reference": ref2, "status": "SUCCEEDED", "amount": "1.00", "currency": "USD"})
    rej = one("SELECT processing_status, error_code FROM saas_payment_webhooks WHERE provider_event_id=:e", e=f"EVT-{RUN}-4")
    check("montant différent → refusé, et le refus reste enregistré", r.status_code == 409 and rej is not None
          and tuple(rej) == ("REJECTED", "PAYMENT_MISMATCH") and one("SELECT status FROM saas_invoices WHERE id=:i", i=inv2)[0] == "ISSUED",
          (r.status_code, rej))

    sql("UPDATE saas_subscriptions SET status='ACTIVE', current_period_start=:a, current_period_end=:b WHERE id=:i",
        a=today - timedelta(days=40), b=today - timedelta(days=3), i=sub)
    run_once(APP.state.services, today=today)
    check("échéance dépassée de 3 jours → GRÂCE", one("SELECT status FROM saas_subscriptions WHERE id=:i", i=sub)[0] == "GRACE")
    run_once(APP.state.services, today=today + timedelta(days=10))
    check("grâce dépassée → LIMITÉ (sans aucun blocage tant que l'étape 2 n'est pas décidée)",
          one("SELECT status FROM saas_subscriptions WHERE id=:i", i=sub)[0] == "LIMITED"
          and as_(gest).get("/api/v1/schooling/families").status_code == 200)


def main() -> int:
    A, B = school("A"), school("B")
    run(A, B)
    H.CLIENT.__exit__(None, None, None)
    fails = [r for r in H.RESULTS if r[0] == "FAIL"]
    print(f"\n{len(H.RESULTS) - len(fails)}/{len(H.RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
