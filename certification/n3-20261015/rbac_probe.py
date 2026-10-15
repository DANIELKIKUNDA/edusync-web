"""N3-A — real RBAC probe (owner decisions 2026-10-15: G-PLAN-1, G-ROLE-1).

Creates an isolated school, one account per standard role, and reads the effective rights through the API (/auth/me),
then checks a few real refusals. Run through the private runner (.local/closure/run.py); nothing secret is printed.
"""
import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import ensure_user, owner, platform, save, state, user_client  # noqa: E402
from sqlalchemy import text  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


run = uuid4().hex[:5].upper()
r = platform().post("platform/schools", json={"code": f"RBAC-{run}", "name": f"École droits N3 {run}"}, headers={"Idempotency-Key": str(uuid4())})
assert r.status_code in (200, 201), r.text[:200]
school = {"code": f"RBAC-{run}", "school_id": r.json()["id"], "users": {}}
state.setdefault("N3A", {})[run] = school
save()
ROLES = ("ADMIN_SYSTEME_ECOLE", "GESTIONNAIRE", "CAISSIER", "PROMOTEUR", "RESPONSABLE_FINANCE")  # section-scoped roles: read from the baseline below
perms = {}
for role in ROLES:
    key = "ADMIN" if role == "ADMIN_SYSTEME_ECOLE" else role
    ensure_user(school, key, (role,))
    c = user_client(school, key)
    perms[role] = set(c.get("auth/me").json().get("permissions") or [])

SUPERIOR = ("finance.payments.reverse.supervisor", "finance.advance_funds.refund", "finance.cash.reopen", "finance.cash.day.close",
            "finance.decisions.create", "finance.decisions.cancel", "finance.responsibility.set", "personnel.staff_children.finance_mode",
            "personnel.payroll_deduction.confirm", "personnel.payroll_deduction.cancel")
missing = [c for c in SUPERIOR if c not in perms["GESTIONNAIRE"]]
check("GESTIONNAIRE : autorité financière supérieure (10 droits)", not missing, missing)
leak = [c for c in SUPERIOR if c in perms["ADMIN_SYSTEME_ECOLE"]]
check("ADMIN_SYSTEME_ECOLE : aucune mutation financière opérationnelle", not leak, leak)
check("ADMIN_SYSTEME_ECOLE : définit les plans anticipés", "finance.anticipation_plans.manage" in perms["ADMIN_SYSTEME_ECOLE"])
check("CAISSIER : dépense de caisse", "finance.cash.expense.create" in perms["CAISSIER"])
check("CAISSIER : correction de son propre paiement conservée", "finance.payments.reverse" in perms["CAISSIER"])
check("CAISSIER : ni remboursement de fonds anticipé, ni correction supérieure, ni clôture globale",
      not ({"finance.advance_funds.refund", "finance.payments.reverse.supervisor", "finance.cash.day.close", "finance.cash.reopen"} & perms["CAISSIER"]))
check("CAISSIER : ne crée pas de plan anticipé", "finance.anticipation_plans.manage" not in perms["CAISSIER"])
# PREFET_ETUDES / DIRECTION_SECTION need a section scope to be assigned: their standard baseline is read in the database.
with owner.connect() as c:
    for role in ("PREFET_ETUDES", "DIRECTION_SECTION"):
        perms[role] = {x for (x,) in c.execute(text("""SELECT rc.capability_code FROM rbac_role_capabilities rc JOIN rbac_roles r ON r.id=rc.role_id
            WHERE r.code=:r AND r.kind='SCHOOL_STANDARD'"""), {"r": role})}
for role in ("PROMOTEUR", "RESPONSABLE_FINANCE", "PREFET_ETUDES", "DIRECTION_SECTION"):
    check(f"{role} : baseline inchangée (aucun droit N3-A)", not ({*SUPERIOR, "finance.cash.expense.create", "finance.anticipation_plans.manage"} & perms[role]),
          sorted({*SUPERIOR, "finance.cash.expense.create"} & perms[role]))
# Real refusals through the API (routes already present).
cash = user_client(school, "CAISSIER")
BODY = {"enrollment_id": str(uuid4()), "decision_type": "EXEMPTION", "currency": "CDF", "amount": "0", "reason": "Sonde de droits N3-A", "effective_date": "2026-10-15"}
r1 = cash.post("finance/controls/decisions", json=BODY, headers={"Idempotency-Key": str(uuid4())})
check("Refus réel : le caissier ne crée pas de décision financière (403)", r1.status_code == 403, r1.status_code)
admin = user_client(school, "ADMIN")
r2 = admin.post("finance/controls/decisions", json=BODY, headers={"Idempotency-Key": str(uuid4())})
check("Refus réel : l'administrateur technique ne crée pas de décision financière (403)", r2.status_code == 403, r2.status_code)
ges = user_client(school, "GESTIONNAIRE")
r3 = ges.post("finance/controls/decisions", json=BODY, headers={"Idempotency-Key": str(uuid4())})
check("Le gestionnaire passe le contrôle de droit (inscription inconnue : refus métier, pas 403)", r3.status_code not in (401, 403), r3.status_code)

ok = sum(r["pass"] for r in results)
Path(__file__).with_name("rbac-live.json").write_text(json.dumps({"school": school["code"], "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"== {ok}/{len(results)} PASS -> rbac-live.json")
