"""Finances limitées au périmètre — real HTTP + real PostgreSQL (owner, 2026-11-17).

« L'interface ne doit jamais afficher une classe qui n'est pas de son périmètre » : a préfet (SECTION SECONDAIRE) given
the finances sees, in every finance screen, only the classes and pupils of the Secondaire; a pupil of the Primaire is
refused (403); a reader with « toute l'école » (SCHOOL scope) still sees everything. Same fixture as the direction report.

    python tools/local/isolated_db.py env <db> -- ../.venv/Scripts/python.exe ../tools/ci/finance_scope_postgres_integration.py

CI=true, localhost only (three_roles_postgres_integration). Exits 1 on any FAIL.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_roles_postgres_integration as H  # noqa: E402
from three_roles_postgres_integration import actor_for, as_, check, one, school  # noqa: E402
import direction_report_postgres_integration as D  # noqa: E402

F = "/api/v1/finance"


def run(A: dict) -> None:
    print("\n== Finances limitées au périmètre (17/11/2026)")
    D.fixture(A)
    sid, y = A["id"], A["year"]
    prim_enr = one("SELECT e.id FROM enrollments e JOIN finance_charges fc ON fc.enrollment_id=e.id WHERE e.school_id=:s AND e.class_id=:c LIMIT 1",
                   s=sid, c=A["classes"]["PRIMAIRE"])[0]
    sec_enr = one("SELECT e.id FROM enrollments e JOIN finance_charges fc ON fc.enrollment_id=e.id WHERE e.school_id=:s AND e.class_id=:c LIMIT 1",
                  s=sid, c=A["classes"]["SECONDAIRE"])[0]
    prim_st = one("SELECT student_id FROM enrollments WHERE id=:e", e=prim_enr)[0]
    sec_st = one("SELECT student_id FROM enrollments WHERE id=:e", e=sec_enr)[0]
    prim_cls, sec_cls = str(A["classes"]["PRIMAIRE"]), str(A["classes"]["SECONDAIRE"])

    for who, scope, sees_primary in (("préfet (Secondaire)", ("SECTION", "SECONDAIRE"), False),
                                     ("préfet avec « toute l'école »", ("SCHOOL", None), True)):
        c = as_(actor_for("PREFET_ETUDES", sid, scope=scope))
        tag = f"[{who}] "
        # 1. Class pickers: never a class outside the scope.
        r = c.get(f"{F}/recovery/classes")
        ids = {x["id"] for x in r.json().get("items", [])} if r.status_code == 200 else set()
        check(tag + "registre des classes : liste des classes", r.status_code == 200 and sec_cls in ids and (prim_cls in ids) == sees_primary, r.text[:200])
        r = c.get(f"{F}/recovery/sections")
        labels = {x["label"] for x in r.json().get("items", [])} if r.status_code == 200 else set()
        check(tag + "liste des sections", r.status_code == 200 and "SECONDAIRE" in labels and ("PRIMAIRE" in labels) == sees_primary, r.text[:200])
        r = c.get("/api/v1/settings/classes/selector?capability=finance.recovery.monthly.read")
        ids = {x["id"] for x in r.json()} if r.status_code == 200 else set()
        check(tag + "sélecteur « Qui est en ordre ? »", r.status_code == 200 and sec_cls in ids and (prim_cls in ids) == sees_primary, r.text[:200])
        r = c.get("/api/v1/settings/classes/selector?capability=finance.analysis.by_fee.read")
        ids = {x["id"] for x in r.json()} if r.status_code == 200 else set()
        check(tag + "sélecteur « Suivi par frais »", r.status_code == 200 and sec_cls in ids and (prim_cls in ids) == sees_primary, r.text[:200])
        # 2. Registers and summaries.
        r = c.get(f"{F}/recovery/class-register?class_id={prim_cls}")
        check(tag + "registre d'une classe du primaire", r.status_code == (200 if sees_primary else 403), r.status_code)
        r = c.get(f"{F}/recovery/followup?class_id={prim_cls}")
        check(tag + "« Qui est en ordre ? » d'une classe du primaire", r.status_code == (200 if sees_primary else 403), r.status_code)
        r = c.get(f"{F}/recovery/class-register?class_id={sec_cls}")
        check(tag + "registre d'une classe du secondaire", r.status_code == 200, r.status_code)
        r = c.get(f"{F}/recovery/summary/class?class_id={prim_cls}")
        check(tag + "synthèse par classe (primaire)", r.status_code == (200 if sees_primary else 403), r.status_code)
        r = c.get(f"{F}/recovery/summary/section")
        rows = [x["label"] for x in r.json().get("items", [])] if r.status_code == 200 else []
        check(tag + "synthèse par section : classes visibles", r.status_code == 200 and ("PRI-1A" in rows) == sees_primary and "SEC-1A" in rows, rows)
        r = c.get(f"{F}/recovery/summary/school")
        rows = [x["label"] for x in r.json().get("items", [])] if r.status_code == 200 else []
        title = r.json().get("title", "") if r.status_code == 200 else ""
        check(tag + "synthèse globale : sections visibles et titre", r.status_code == 200 and ("PRIMAIRE" in rows) == sees_primary
              and ("PÉRIMÈTRE" in title) != sees_primary, (rows, title))
        # 3. Suivi par frais.
        r = c.get(f"{F}/fees/students?limit=500")
        classes = {x["class_label"] for x in r.json().get("items", [])} if r.status_code == 200 else set()
        check(tag + "suivi par frais : élèves visibles", r.status_code == 200 and "SEC-1A" in classes and ("PRI-1A" in classes) == sees_primary, classes)
        for path in ("/fees/taxonomy", "/fees/overview", f"/fees/student/{prim_st}", f"/fees/family/{A['families']['PRIMAIRE']}"):
            r = c.get(F + path)
            check(tag + f"suivi par frais {path.split('/')[2]} lisible", r.status_code == 200, r.text[:160])
        r = c.get(f"{F}/fees/student/{prim_st}")
        check(tag + "fiche d'un élève du primaire", r.status_code == 200 and bool(r.json().get("items")) == sees_primary, r.text[:160])
        # 4. Decisions, responsibilities, credits.
        for path in ("/controls/decisions?status=ALL", "/controls/responsibilities", "/controls/credits?status=ALL", "/controls/follow-up"):
            r = c.get(F + path)
            check(tag + f"registre {path.split('?')[0]}", r.status_code == 200, r.text[:160])
        r = c.get(f"{F}/controls/students/{prim_st}/view")
        check(tag + "vue financière d'un élève du primaire", r.status_code == (200 if sees_primary else 403), r.status_code)
        r = c.get(f"{F}/controls/students/{sec_st}/view")
        check(tag + "vue financière d'un élève du secondaire", r.status_code == 200, r.status_code)
        # 5. Pupil balances read from the cash desk screens.
        r = c.get(f"{F}/checkout/balance/{prim_enr}")
        check(tag + "solde d'un élève du primaire", r.status_code == (200 if sees_primary else 403), r.status_code)
        r = c.get(f"{F}/checkout/balance/{sec_enr}")
        check(tag + "solde d'un élève du secondaire", r.status_code == 200, r.status_code)
        r = c.get(f"{F}/checkout/old-debts/{prim_st}")
        check(tag + "anciennes dettes d'un élève du primaire", r.status_code == (200 if sees_primary else 403), r.status_code)
        r = c.get(f"{F}/checkout/advance-funds")
        check(tag + "fonds anticipés lisibles", r.status_code == 200, r.text[:160])


def main() -> int:
    A = school("A")
    run(A)
    H.CLIENT.__exit__(None, None, None)
    fails = [r for r in H.RESULTS if r[0] == "FAIL"]
    print(f"\n{len(H.RESULTS) - len(fails)}/{len(H.RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
