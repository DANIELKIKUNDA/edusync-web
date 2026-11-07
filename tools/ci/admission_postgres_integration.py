"""Atomic enrollment against the school's enrollment conditions — real HTTP + real PostgreSQL (owner report 2026-11-06).

« La base de données permet d'inscrire les enfants même s'ils n'ont pas rempli les conditions : c'est une erreur grave. »

Proven end to end (settings → preview → enrollment + family payment in one transaction → pending dossier → waiver):
* without payment of the conditions nothing is written: no pupil, no family, no charge;
* with payment, the pupils, their charges and one receipt per child are committed together;
* the school may exempt staff children / benefit beneficiaries; the direction may waive a child (reason, audit);
* a user who cannot collect keeps a dossier « en attente » (nobody enrolled); the cashier completes it atomically.

    python tools/local/isolated_db.py env <db> -- ../.venv/Scripts/python.exe ../tools/ci/admission_postgres_integration.py
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_roles_postgres_integration as H  # noqa: E402
from three_roles_postgres_integration import actor_for, as_, check, key, one, school, sql  # noqa: E402
from benefits_postgres_integration import child, fees  # noqa: E402

ENGLISH = ("required", "Invalid", "must", "not found", "Positive")


def students(family_name_like: str) -> int:
    return int(one("SELECT count(*) FROM students WHERE last_name='KASONGO' AND first_name LIKE :p", p=family_name_like)[0])


def run(A: dict) -> None:
    print("\n== Inscription atomique : conditions d'inscription (inscription + juin) payées dans la même opération")
    fees(A)
    cls = A["classes"]["PRIMAIRE"]
    admin, cashier_actor = actor_for("ADMIN_SYSTEME_ECOLE", A["id"]), actor_for("CAISSIER", A["id"])
    clerk_actor = actor_for("CAISSIER", A["id"], drop={"finance.checkout.collect", "finance.checkout.family.collect"})
    director_actor = actor_for("GESTIONNAIRE", A["id"])
    cashier = as_(cashier_actor)
    o = cashier.post("/api/v1/finance/cash/open", json={"opening_cdf": "0", "opening_usd": "0"}, headers=key())
    check("caisse ouverte", o.status_code in (200, 201), o.text[:150])
    guardian = {"full_name": "KASONGO Bwanga", "role": "PERE", "phone": "+243 97 000 0009"}
    body = lambda kids, pay=True: {"household_confidence": "NONE", "primary_guardian": guardian, "children": kids, **({"payment": {"mode": "CASH"}} if pay else {})}
    kids = lambda p: [child(f"{p}1", cls), child(f"{p}2", cls)]

    r = cashier.post("/api/v1/schooling/enrollments/family/preview", json=body(kids("P")))
    pv = r.json() if r.status_code == 200 else {}
    check("aperçu : chaque enfant avec sa classe et ses conditions (inscription 15 000 + juin 20 000), total famille 70 000",
          r.status_code == 200 and Decimal(pv["conditions"]["totals"]["CDF"]) == 70000 and all(c["class_label"] for c in pv["conditions"]["children"]), r.text[:300])
    check("aperçu : rien n'est enregistré (simulation annulée)", students("P%") == 0, students("P%"))

    r = cashier.post("/api/v1/schooling/enrollments/family", headers=key(), json=body(kids("N"), pay=False))
    check("sans paiement → refusé, message en français, aucun élève enregistré",
          r.status_code == 409 and "Aucun enfant n’a été inscrit" in r.text and not any(w in r.text for w in ENGLISH) and students("N%") == 0, f"{r.status_code} {r.text[:200]}")

    r = cashier.post("/api/v1/schooling/enrollments/family", headers=key(), json=body(kids("Y")))
    ok = r.status_code == 201
    check("avec paiement → 2 élèves inscrits et leurs conditions payées dans la même opération", ok and students("Y%") == 2, f"{r.status_code} {r.text[:200]}")
    if ok:
        fam = r.json()["family_id"]
        n = tuple(one("""SELECT count(*), count(DISTINCT receipt_number), coalesce(sum(p.amount),0) FROM finance_payments p JOIN enrollments e ON e.id=p.enrollment_id
                         JOIN students s ON s.id=e.student_id WHERE s.family_id=:f""", f=fam))
        check("paiement familial : un reçu par enfant, 70 000 au total", n[0] == 2 and n[1] == 2 and Decimal(n[2]) == 70000, n)

    # A cash desk closed by mistake: the payment fails → the enrollment is rolled back too.
    as_(clerk_actor)
    r = H.CLIENT.post("/api/v1/schooling/enrollments/family", headers=key(), json=body(kids("Z")))
    check("compte sans droit d'encaisser qui tente d'inscrire → refusé, rien d'enregistré", r.status_code == 403 and students("Z%") == 0, f"{r.status_code} {r.text[:160]}")

    print("\n== Dossier en attente : saisi sans droit d'encaisser, dérogation de la direction, encaissé par le caissier")
    r = H.CLIENT.post("/api/v1/schooling/enrollment-dossiers", json=body([child("DQ1", cls), child("DQ2", cls), child("DQ3", cls)], pay=False))
    dos = r.json() if r.status_code == 201 else {}
    check("dossier en attente créé, aucun élève inscrit", r.status_code == 201 and dos.get("status") == "PENDING" and students("DQ%") == 0, f"{r.status_code} {r.text[:200]}")
    if r.status_code != 201:
        return
    as_(director_actor)
    w = H.CLIENT.post(f"/api/v1/schooling/enrollment-dossiers/{dos['id']}/waivers", json={"index": 2, "reason": "Orphelin pris en charge par la paroisse", "expected_version": dos["version"]})
    check("la direction accorde une dérogation à D3 (motif tracé)", w.status_code == 200 and w.json()["waivers"][0]["status"] == "APPROVED", w.text[:200])
    as_(cashier_actor)
    pv = H.CLIENT.get(f"/api/v1/schooling/enrollment-dossiers/{dos['id']}/preview").json()
    check("aperçu du dossier : D3 exempté, la famille paie 70 000 pour D1 et D2",
          Decimal(pv["conditions"]["totals"]["CDF"]) == 70000 and pv["conditions"]["children"][2]["exemption"]["kind"] == "WAIVER", str(pv)[:300])
    c = H.CLIENT.post(f"/api/v1/schooling/enrollment-dossiers/{dos['id']}/complete", headers=key(), json={"payment": {"mode": "CASH"}, "expected_version": w.json()["version"]})
    check("le caissier encaisse et inscrit en une opération : 3 élèves inscrits, dossier terminé",
          c.status_code == 201 and students("DQ%") == 3 and one("SELECT status FROM enrollment_dossiers WHERE id=:i", i=dos["id"])[0] == "COMPLETED", f"{c.status_code} {c.text[:200]}")
    if c.status_code == 201:
        fam = c.json()["family_id"]
        n = one("""SELECT count(*) FROM finance_payments p JOIN enrollments e ON e.id=p.enrollment_id JOIN students s ON s.id=e.student_id WHERE s.family_id=:f""", f=fam)[0]
        check("deux reçus (D1, D2) ; D3 dérogé n'a rien payé à l'inscription (ses frais restent dus plus tard)", int(n) == 2, n)
    again = H.CLIENT.post(f"/api/v1/schooling/enrollment-dossiers/{dos['id']}/complete", headers=key(), json={"payment": {"mode": "CASH"}, "expected_version": w.json()["version"] + 1})
    check("un dossier déjà inscrit ne peut pas l'être une seconde fois", again.status_code == 409, again.status_code)

    print("\n== Exemption par la politique de l'école : enfants du personnel et bénéficiaires d'avantages")
    as_(admin)
    p = H.CLIENT.put("/api/v1/settings/policies/ENROLLMENT", headers=key(), json={"payload": {"required_student_fields": ["last_name", "middle_name", "first_name", "class_id"],
                     "conditions_exempt_benefit_beneficiaries": True}, "status": "ACTIVE"})
    check("paramètres : les bénéficiaires d'avantages sont exemptés des conditions", p.status_code in (200, 201), p.text[:200])
    H.CLIENT.put("/api/v1/settings/benefit-policies/LARGE_FAMILY", headers=key(), json={"academic_year_id": str(A["year"]), "enabled": True, "min_children": 2,
                 "free_beneficiaries": 1, "applies_to_fee_codes": ["TRANSPORT"]})
    as_(cashier_actor)
    r = H.CLIENT.post("/api/v1/schooling/enrollments/family/preview", json=body([child("B1", cls), child("B2", cls, free=True)]))
    pv = r.json() if r.status_code == 200 else {}
    check("aperçu : B2 bénéficiaire exempté, la famille ne paie que pour B1 (35 000)",
          r.status_code == 200 and Decimal(pv["conditions"]["totals"]["CDF"]) == 35000 and pv["conditions"]["children"][1]["exemption"]["kind"] == "BENEFIT", r.text[:300])


def main() -> int:
    A = school("D")
    run(A)
    H.CLIENT.__exit__(None, None, None)
    fails = [r for r in H.RESULTS if r[0] == "FAIL"]
    print(f"\n{len(H.RESULTS) - len(fails)}/{len(H.RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
