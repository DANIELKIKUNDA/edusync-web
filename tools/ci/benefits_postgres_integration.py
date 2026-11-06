"""Benefits driven by the school's policy — real HTTP + real PostgreSQL (owner request 2026-11-06).

The owner's rule: in Settings → Avantages the school decides « dès 5 enfants inscrits, 1 enfant gratuit » on every
monthly fee. The designated child then pays no month at all, while the other children pay normally; the benefit is
refused before the threshold, beyond the limit, and when the school has not enabled it. Proven end to end:
settings API → enrollment API (charges generated) → cash desk (registration bundle and recommendation).

    python tools/local/isolated_db.py env <db> -- ../.venv/Scripts/python.exe ../tools/ci/benefits_postgres_integration.py

Reuses tools/ci/three_roles_postgres_integration.py (CI=true, localhost only). Exits 1 on any FAIL.
"""
from __future__ import annotations

import sys
import uuid
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_roles_postgres_integration as H  # noqa: E402
from three_roles_postgres_integration import actor_for, as_, check, key, one, school, sql  # noqa: E402

MONTHS = [("09", "Septembre", 1, "2026-09-30"), ("10", "Octobre", 2, "2026-10-31"), ("06", "Juin", 10, "2027-06-30")]
ENGLISH = ("required", "Invalid", "must", "not found", "Positive")


def fees(A: dict) -> None:
    """INSCRIPTION (once) + two monthly fees, each monthly fee under an active annual policy (every month fully due)."""
    sid, y, cls = A["id"], A["year"], A["classes"]["PRIMAIRE"]
    ins, sco, tra = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for fid, code, label, per in ((ins, "INSCRIPTION", "Frais d'inscription", "ONE_TIME"), (sco, "SCOLARITE", "Frais scolaires mensuels", "MONTHLY"),
                                  (tra, "TRANSPORT", "Transport mensuel", "MONTHLY")):
        sql("""INSERT INTO fee_types(id,school_id,code,label,periodicity,default_currency,regulatory,enabled)
               VALUES(:i,:s,:c,:l,:p,'CDF',false,true)""", i=fid, s=sid, c=code, l=label, p=per)
    sql("""INSERT INTO fee_schedules(id,school_id,academic_year_id,class_id,fee_type_id,period_code,period_label,period_order,due_date,amount,currency)
           VALUES(:i,:s,:y,:c,:f,'*','Inscription',NULL,'2026-09-01',15000,'CDF')""", i=uuid.uuid4(), s=sid, y=y, c=cls, f=ins)
    for fid, amount in ((sco, 20000), (tra, 5000)):
        for code, label, order, due in MONTHS:
            sql("""INSERT INTO fee_schedules(id,school_id,academic_year_id,class_id,fee_type_id,period_code,period_label,period_order,due_date,amount,currency)
                   VALUES(:i,:s,:y,:c,:f,:p,:l,:o,:d,:a,'CDF')""", i=uuid.uuid4(), s=sid, y=y, c=cls, f=fid, p=code, l=label, o=order, d=due, a=amount)
    policy = uuid.uuid4()
    sql("""INSERT INTO finance_exigibility_policies(id,school_id,academic_year_id,version,status,effective_from,approved_at)
           VALUES(:i,:s,:y,1,'ACTIVE','2026-09-01',now())""", i=policy, s=sid, y=y)
    for fid in (sco, tra):
        rule = uuid.uuid4()
        sql("INSERT INTO finance_exigibility_rules(id,school_id,policy_id,fee_type_id,prior_mode) VALUES(:i,:s,:p,:f,'FULL')", i=rule, s=sid, p=policy, f=fid)
        sql("INSERT INTO finance_exigibility_day_bands(school_id,rule_id,first_day,last_day,percent) VALUES(:s,:r,1,NULL,100)", s=sid, r=rule)


def child(first: str, cls, *, free: bool = False) -> dict:
    return {"last_name": "KASONGO", "middle_name": "BWANGA", "first_name": first, "class_id": str(cls), "gender": "F", "large_family_beneficiary": free}


def charges(first: str, family_code_like: str) -> list[tuple]:
    rows = sql("""SELECT f.periodicity, fc.net_amount, fc.gross_amount, fc.discount_percent FROM finance_charges fc
                   JOIN enrollments e ON e.id=fc.enrollment_id JOIN students s ON s.id=e.student_id JOIN families fa ON fa.id=s.family_id
                   JOIN fee_types f ON f.id=fc.fee_type_id
                  WHERE s.first_name=:n AND fa.id::text LIKE :fam""", n=first, fam=family_code_like).all()
    return [tuple(r) for r in rows]


def run(A: dict) -> None:
    print("\n== Avantages selon la politique de l'école (famille nombreuse : 1 enfant gratuit dès 5, tous les frais mensuels)")
    fees(A)
    cls = A["classes"]["PRIMAIRE"]
    admin_actor, cashier_actor = actor_for("ADMIN_SYSTEME_ECOLE", A["id"]), actor_for("CAISSIER", A["id"])
    admin = as_(admin_actor)
    r = admin.put("/api/v1/settings/benefit-policies/LARGE_FAMILY", headers=key(), json={
        "academic_year_id": str(A["year"]), "enabled": True, "min_children": 5, "free_beneficiaries": 1,
        "applies_to_fee_codes": ["SCOLARITE", "TRANSPORT"]})
    check("paramètres : politique Famille nombreuse enregistrée (5 enfants, 1 gratuit, frais mensuels)", r.status_code in (200, 201), r.text[:200])
    version = (r.json() or {}).get("version") if r.status_code in (200, 201) else None

    cashier = as_(cashier_actor)
    b = cashier.get("/api/v1/schooling/enrollment-benefits").json()
    lf = b.get("large_family") or {}
    check("formulaire : la règle de l'école est transmise en mots (libellés des frais, seuil, limite)",
          lf.get("min_children") == 5 and lf.get("beneficiary_limit") == 1 and lf.get("fee_labels") == ["Frais scolaires mensuels", "Transport mensuel"], lf)

    guardian = {"full_name": "KASONGO Bwanga", "role": "PERE", "phone": "+243 97 000 0001"}
    enroll = lambda kids: cashier.post("/api/v1/schooling/enrollments/family", headers=key(),
                                       json={"household_confidence": "NONE", "primary_guardian": guardian, "children": kids})
    r = enroll([child("Un", cls), child("Deux", cls), child("Trois", cls, free=True)])
    check("3 enfants avec un gratuit → refusé : seuil de 5 non atteint, message en français",
          r.status_code == 409 and "seuil" in r.text and not any(w in r.text for w in ENGLISH), f"{r.status_code} {r.text[:160]}")
    r = enroll([child("A", cls, free=True), child("B", cls, free=True), child("C", cls), child("D", cls), child("E", cls)])
    check("5 enfants avec deux gratuits → refusé : 1 bénéficiaire au plus", r.status_code == 409 and "1 bénéficiaire" in r.text, f"{r.status_code} {r.text[:160]}")

    r = enroll([child("Esther", cls), child("Joel", cls), child("Grace", cls), child("Daniel", cls), child("Ruth", cls, free=True)])
    check("5 enfants dont Ruth gratuite → inscription réussie (plus d'erreur « Positive due amount »)", r.status_code == 201, f"{r.status_code} {r.text[:200]}")
    if r.status_code != 201:
        return
    fam = r.json()["family_id"]
    ruth, esther = charges("Ruth", fam), charges("Esther", fam)
    monthly_ruth = [c for c in ruth if c[0] == "MONTHLY"]
    check("Ruth : 6 mois générés (3 minerval + 3 transport), tous à 0 avec remise de 100 %",
          len(monthly_ruth) == 6 and all(Decimal(c[1]) == 0 and Decimal(c[2]) > 0 and Decimal(c[3]) == 100 for c in monthly_ruth), monthly_ruth)
    check("Ruth : les frais d'inscription restent dus (non couverts par la politique)",
          any(c[0] != "MONTHLY" and Decimal(c[1]) == 15000 for c in ruth), ruth)
    check("Esther (non bénéficiaire) paie tous ses mois normalement",
          sum(Decimal(c[1]) for c in esther if c[0] == "MONTHLY") == Decimal(3 * 20000 + 3 * 5000), esther)

    enr_ruth = one("""SELECT e.id FROM enrollments e JOIN students s ON s.id=e.student_id WHERE s.first_name='Ruth' AND s.family_id=:f""", f=fam)[0]
    bundle = cashier.get(f"/api/v1/finance/checkout/registration-bundle/{enr_ruth}").json()
    check("caisse : le lot d'inscription de Ruth ne réclame que les frais d'inscription (juin gratuit = 0)",
          bundle.get("totals", {}).get("CDF") in ("15000", "15000.00"), bundle.get("totals"))
    rec = cashier.get(f"/api/v1/finance/checkout/recommended/{enr_ruth}").json()
    check("caisse : la recommandation ne propose aucun mois à payer pour Ruth",
          rec.get("total") in ("15000", "15000.00") and all(a.get("amount") not in ("0", "0.00") for a in rec.get("allocations", [])), rec)

    b = cashier.get(f"/api/v1/schooling/enrollment-benefits?family_id={fam}").json().get("large_family") or {}
    check("formulaire : le foyer compte 5 enfants et a déjà son bénéficiaire (la case ne sera plus proposée)",
          b.get("family_enrolled_children") == 5 and b.get("family_beneficiaries") == 1, b)
    r = cashier.post("/api/v1/schooling/enrollments/family", headers=key(),
                     json={"family_id": fam, "household_confidence": "CERTAIN", "children": [child("Sixieme", cls, free=True)]})
    check("6e enfant du même foyer marqué gratuit → refusé (limite de 1 déjà utilisée)", r.status_code == 409, f"{r.status_code} {r.text[:160]}")

    r = as_(admin_actor).put("/api/v1/settings/benefit-policies/LARGE_FAMILY", headers=key(), json={
        "academic_year_id": str(A["year"]), "enabled": False, "min_children": 5, "free_beneficiaries": 1,
        "applies_to_fee_codes": ["SCOLARITE", "TRANSPORT"], "expected_version": version})
    check("paramètres : l'école désactive la politique Famille nombreuse", r.status_code in (200, 201), f"{r.status_code} {r.text[:160]}")
    as_(cashier_actor)
    b = cashier.get("/api/v1/schooling/enrollment-benefits").json()
    check("politique désactivée par l'école → le formulaire n'affiche plus rien", b.get("large_family") is None, b)
    r = enroll([child("V1", cls), child("V2", cls), child("V3", cls), child("V4", cls), child("V5", cls, free=True)])
    check("politique désactivée → gratuité refusée par le serveur aussi", r.status_code == 409, f"{r.status_code} {r.text[:160]}")


def run_per_group(C: dict) -> None:
    print("\n== Famille nombreuse « par tranche » : 1 enfant gratuit pour chaque groupe de 5 (10 enfants → 2)")
    fees(C)
    cls = C["classes"]["PRIMAIRE"]
    r = as_(actor_for("ADMIN_SYSTEME_ECOLE", C["id"])).put("/api/v1/settings/benefit-policies/LARGE_FAMILY", headers=key(), json={
        "academic_year_id": str(C["year"]), "enabled": True, "min_children": 5, "free_beneficiaries": 1, "per_group": True,
        "applies_to_fee_codes": ["SCOLARITE", "TRANSPORT"]})
    check("paramètres : politique « par tranche » enregistrée", r.status_code in (200, 201) and r.json().get("per_group") is True, r.text[:200])
    cashier = as_(actor_for("CAISSIER", C["id"]))
    guardian = {"full_name": "MUKENDI Ilunga", "role": "PERE", "phone": "+243 97 000 0002"}
    enroll = lambda kids: cashier.post("/api/v1/schooling/enrollments/family", headers=key(),
                                       json={"household_confidence": "NONE", "primary_guardian": guardian, "children": kids})
    names = [f"T{i}" for i in range(1, 11)]
    r = enroll([child(n, cls, free=i in (0, 1)) for i, n in enumerate(names[:8])])
    check("8 enfants avec deux gratuits → refusé (une seule tranche de 5)", r.status_code == 409 and "par tranche" in r.text, f"{r.status_code} {r.text[:200]}")
    r = enroll([child(n, cls, free=i in (0, 1, 2)) for i, n in enumerate(names)])
    check("10 enfants avec trois gratuits → refusé (deux tranches = 2 bénéficiaires)", r.status_code == 409, f"{r.status_code} {r.text[:160]}")
    r = enroll([child(n, cls, free=i in (3, 7)) for i, n in enumerate(names)])
    check("10 enfants avec deux gratuits → inscription réussie", r.status_code == 201, f"{r.status_code} {r.text[:200]}")
    if r.status_code == 201:
        fam = r.json()["family_id"]
        free_months = [c for n in ("T4", "T8") for c in charges(n, fam) if c[0] == "MONTHLY"]
        check("les deux bénéficiaires ont tous leurs mois à 0", len(free_months) == 12 and all(Decimal(c[1]) == 0 for c in free_months), free_months)
        paying = [c for c in charges("T1", fam) if c[0] == "MONTHLY"]
        check("les huit autres paient normalement", paying and all(Decimal(c[1]) > 0 for c in paying), paying)


def main() -> int:
    A = school("B")
    run(A)
    C = school("C")
    run_per_group(C)
    H.CLIENT.__exit__(None, None, None)
    fails = [r for r in H.RESULTS if r[0] == "FAIL"]
    print(f"\n{len(H.RESULTS) - len(fails)}/{len(H.RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
