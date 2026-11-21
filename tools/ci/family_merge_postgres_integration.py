"""Regrouper les frères et sœurs — real HTTP + real PostgreSQL (owner, 2026-11-21).

Pupils taken over from the old software arrived each in a family of their own. Checks:
1. the proposal groups the families with the same responsible AND the same phone (written differently), not the others;
2. the proposal writes nothing;
3. merging moves the children (primaire AND secondaire) to the main family; the other family is kept, marked merged,
   no longer listed; the same responsible is not duplicated; the reason is audited;
4. no amount changes: every charge keeps its amounts and its child;
5. merging an already merged family, a role without the right, and a section-scoped actor are refused.

    python tools/local/isolated_db.py env <db> -- ../.venv/Scripts/python.exe ../tools/ci/family_merge_postgres_integration.py

CI=true, localhost only (three_roles_postgres_integration). Exits 1 on any FAIL.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_roles_postgres_integration as H  # noqa: E402
from three_roles_postgres_integration import RUN, actor_for, as_, check, key, one, school, sql  # noqa: E402

S = "/api/v1/schooling"


def family(A, code, guardian, phone, kids):
    sid, fam, g = A["id"], uuid.uuid4(), uuid.uuid4()
    sql("INSERT INTO families(id,school_id,code,display_name,phone) VALUES(:i,:s,:c,:n,:p)", i=fam, s=sid, c=f"{code}-{RUN}", n=f"Famille {code}", p=phone)
    sql("INSERT INTO guardians(id,school_id,full_name,phone,normalized_phone) VALUES(:i,:s,:n,:p,:np)",
        i=g, s=sid, n=guardian, p=phone, np="".join(ch for ch in phone if ch.isdigit()))
    sql("INSERT INTO family_guardians(school_id,family_id,guardian_id,role,is_primary,active) VALUES(:s,:f,:g,'TUTEUR',true,true)", s=sid, f=fam, g=g)
    pupils = []
    for name, sec in kids:
        st, enr = uuid.uuid4(), uuid.uuid4()
        sql("""INSERT INTO students(id,school_id,family_id,matricule,last_name,middle_name,first_name,gender)
               VALUES(:i,:s,:f,:m,:n,'FRATRIE','Enfant','M')""", i=st, s=sid, f=fam, m=f"FR-{name}-{RUN}", n=name)
        sql("INSERT INTO enrollments(id,school_id,student_id,academic_year_id,class_id,status) VALUES(:i,:s,:st,:y,:c,'VALIDATED')",
            i=enr, s=sid, st=st, y=A["year"], c=A["classes"][sec])
        sql("""INSERT INTO finance_charges(id,school_id,enrollment_id,label,currency,net_amount,paid_amount,periodicity,due_date)
               VALUES(:i,:s,:e,'Minerval septembre','CDF',25000,10000,'ONE_OFF','2026-09-01')""", i=uuid.uuid4(), s=sid, e=enr)
        pupils.append(st)
    return fam, pupils


def charges(A):
    return sql("""SELECT fc.id, fc.net_amount, fc.paid_amount, e.student_id FROM finance_charges fc JOIN enrollments e ON e.id=fc.enrollment_id
                  WHERE fc.school_id=:s ORDER BY fc.id""", s=A["id"]).all()


def run(A: dict) -> None:
    print("\n== Regrouper les frères et sœurs (21/11/2026)")
    f1, k1 = family(A, "FRA1", "KABEYA MUTOMBO Jean", "+243 97 123 4567", [("AINE", "SECONDAIRE")])
    f2, k2 = family(A, "FRA2", "kabeya  mutombo jean", "0971234567", [("CADET", "PRIMAIRE"), ("BENJAMIN", "PRIMAIRE")])
    f3, _ = family(A, "AUTRE", "KABEYA MUTOMBO Jean", "0820000000", [("VOISIN", "PRIMAIRE")])   # same name, other phone
    caissier = actor_for("CAISSIER", A["id"])
    before = charges(A)

    r = as_(caissier).get(S + "/families/merge/suggestions")
    groups = r.json().get("groups", []) if r.status_code == 200 else []
    mine = [g for g in groups if {f["id"] for f in g["families"]} & {str(f1), str(f2), str(f3)}]
    check("proposition : même responsable + même téléphone (écrits différemment) → un groupe de 2 familles, 3 enfants",
          r.status_code == 200 and len(mine) == 1 and {f["id"] for f in mine[0]["families"]} == {str(f1), str(f2)}
          and mine[0]["children"] == 3, (r.status_code, r.text[:300]))
    check("la proposition n'écrit rien", one("SELECT count(*) FROM families WHERE school_id=:s AND merged_into_family_id IS NOT NULL", s=A["id"])[0] == 0)

    body = {"target_family_id": str(f2), "source_family_ids": [str(f1)], "reason": "Frères et sœurs : même responsable et même téléphone"}
    r = as_(caissier).post(S + "/families/merge", json=body, headers=key())
    check("regroupement : l'aîné du secondaire rejoint la famille du primaire", r.status_code == 200
          and one("SELECT family_id FROM students WHERE id=:i", i=k1[0])[0] == f2 and len(r.json()["children_moved"]) == 1, r.text[:300])
    check("l'ancienne famille est conservée, marquée regroupée", one(
        "SELECT merged_into_family_id FROM families WHERE id=:i", i=f1)[0] == f2)
    lst = as_(caissier).get(S + "/families", params={"q": f"FRA1-{RUN}"})
    check("l'ancienne famille n'apparaît plus dans la liste", lst.status_code == 200 and not lst.json().get("items"), lst.text[:200])
    fam = as_(caissier).get(f"{S}/families/{f2}").json()
    check("la famille principale a 3 enfants et un seul responsable (pas de doublon)",
          len(fam.get("children", [])) == 3 and len(fam.get("guardians", [])) == 1, (len(fam.get("children", [])), fam.get("guardians")))
    check("aucun montant modifié : mêmes frais, mêmes montants, mêmes enfants", charges(A) == before)
    aud = one("SELECT reason FROM audit_events WHERE action='FAMILY_MERGED' AND entity_id=:f ORDER BY occurred_at DESC LIMIT 1", f=f2)
    check("journal d'audit avec le motif", bool(aud) and aud[0].startswith("Frères et sœurs"), aud)
    r = as_(caissier).get(S + "/families/merge/suggestions")
    check("le groupe regroupé n'est plus proposé", r.status_code == 200 and not any(
        str(f2) in {f["id"] for f in g["families"]} for g in r.json()["groups"]), r.text[:200])

    r = as_(caissier).post(S + "/families/merge", json={**body, "source_family_ids": [str(f1)]}, headers=key())
    check("regrouper une famille déjà regroupée → refusé", r.status_code == 409, (r.status_code, r.text[:150]))
    r = as_(actor_for("SECRETARIAT", A["id"])).post(S + "/families/merge",
                                                    json={"target_family_id": str(f2), "source_family_ids": [str(f3)], "reason": "Sans droit"}, headers=key())
    check("sans le droit de modifier les familles → refusé", r.status_code == 403, r.status_code)
    sect = actor_for("CAISSIER", A["id"], scope=("SECTION", "PRIMAIRE"))
    r = as_(sect).post(S + "/families/merge", json={"target_family_id": str(f2), "source_family_ids": [str(f3)], "reason": "Périmètre section"}, headers=key())
    check("périmètre limité à une section → refusé (réservé à toute l'école)", r.status_code == 403, r.status_code)


def main() -> int:
    A = school("A")
    run(A)
    H.CLIENT.__exit__(None, None, None)
    fails = [r for r in H.RESULTS if r[0] == "FAIL"]
    print(f"\n{len(H.RESULTS) - len(fails)}/{len(H.RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
