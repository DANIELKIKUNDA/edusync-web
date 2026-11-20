"""Exonération en groupe et date d'une décision — real HTTP + real PostgreSQL (owner, 2026-11-20).

1. A decision created without a date covers the whole school year (September stays exempted).
2. « Exonérer les enfants du personnel » : the preview lists the staff children (not the others) without writing;
   « Enregistrer » creates one decision per child and fee; a child already exempted is skipped; their fee is then 0.

    python tools/local/isolated_db.py env <db> -- ../.venv/Scripts/python.exe ../tools/ci/group_decision_postgres_integration.py

CI=true, localhost only (three_roles_postgres_integration). Exits 1 on any FAIL.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_roles_postgres_integration as H  # noqa: E402
from three_roles_postgres_integration import RUN, actor_for, as_, check, key, one, school, sql  # noqa: E402

C = "/api/v1/finance/controls"


def pupil(A, name):
    sid, st, enr = A["id"], uuid.uuid4(), uuid.uuid4()
    sql("""INSERT INTO students(id,school_id,family_id,matricule,last_name,middle_name,first_name,gender)
           VALUES(:i,:s,:f,:m,:n,'GROUPE','Eleve','F')""", i=st, s=sid, f=A["families"]["PRIMAIRE"], m=f"GRP-{name}-{RUN}", n=name)
    sql("INSERT INTO enrollments(id,school_id,student_id,academic_year_id,class_id,status,enrolled_on) VALUES(:i,:s,:st,:y,:c,'VALIDATED','2026-09-01')",
        i=enr, s=sid, st=st, y=A["year"], c=A["classes"]["PRIMAIRE"])
    for code, label in (("ETAT", "Frais de l Etat"), ("MINERVAL", "Septembre")):
        sql("""INSERT INTO finance_charges(id,school_id,enrollment_id,label,currency,net_amount,paid_amount,periodicity,due_date,fee_type_id)
               VALUES(:i,:s,:e,:l,'CDF',10000,0,'ONE_OFF','2026-09-01',(SELECT id FROM fee_types WHERE school_id=:s AND code=:c))""",
            i=uuid.uuid4(), s=sid, e=enr, l=label, c=code)
    return st, enr


def owed(enr, code) -> float:
    return float(one("""SELECT coalesce(sum(fc.effective_net_amount),0) FROM finance_charge_effective fc JOIN fee_types ft ON ft.id=fc.fee_type_id
        WHERE fc.enrollment_id=:e AND ft.code=:c AND fc.status='ACTIVE'""", e=enr, c=code)[0])


def run(A: dict) -> None:
    print("\n== Exonération en groupe et date des décisions (20/11/2026)")
    sid = A["id"]
    for code, label, reg in (("ETAT", "Frais de l Etat", True), ("MINERVAL", "Minerval", False)):
        sql("INSERT INTO fee_types(id,school_id,code,label,periodicity,default_currency,regulatory,enabled) VALUES(:i,:s,:c,:l,'ONE_TIME','CDF',:r,true)",
            i=uuid.uuid4(), s=sid, c=code, l=label, r=reg)
    staff = uuid.uuid4()
    sql("INSERT INTO staff_members(id,school_id,employee_no,last_name) VALUES(:i,:s,:n,'AGENT')", i=staff, s=sid, n=f"AG-{RUN}")
    kids = [pupil(A, f"ENFANT{i}") for i in range(3)]
    other = pupil(A, "AUTRE")
    for st, _ in kids:
        sql("INSERT INTO staff_student_links(school_id,staff_id,student_id) VALUES(:s,:a,:st)", s=sid, a=staff, st=st)
    g = lambda: as_(actor_for("GESTIONNAIRE", sid))  # noqa: E731

    r = g().post(C + "/decisions", json={"enrollment_id": str(kids[0][1]), "decision_type": "EXEMPTION", "scope_type": "FEE_CODE", "scope_ref": "MINERVAL",
                                         "value_type": "PERCENT", "amount": "100", "reason": "Gratuit toute l annee"}, headers=key())
    check("décision sans date : septembre est bien exonéré (toute l'année)", r.status_code == 200 and owed(kids[0][1], "MINERVAL") == 0,
          (r.text[:200], owed(kids[0][1], "MINERVAL")))

    body = {"fee_codes": ["ETAT"], "amount": "100", "reason": "Enfants du personnel - frais de l Etat", "execute": False}
    r = g().post(C + "/decisions/group", json=body, headers=key())
    j = r.json() if r.status_code == 200 else {}
    names = {i["student"].split()[0] for i in j.get("items", [])}
    check("aperçu : les 3 enfants du personnel, pas les autres élèves", r.status_code == 200 and j["children"] == 3
          and names == {"ENFANT0", "ENFANT1", "ENFANT2"}, j)
    check("l'aperçu n'écrit rien", all(owed(e, "ETAT") == 10000 for _, e in kids), [owed(e, "ETAT") for _, e in kids])
    r = g().post(C + "/decisions/group", json={**body, "execute": True}, headers=key())
    check("enregistrement : 3 décisions créées", r.status_code == 200 and r.json()["created"] == 3, r.text[:200])
    check("les frais de l'État des enfants du personnel sont à 0, pas ceux des autres",
          all(owed(e, "ETAT") == 0 for _, e in kids) and owed(other[1], "ETAT") == 10000,
          ([owed(e, "ETAT") for _, e in kids], owed(other[1], "ETAT")))
    r = g().post(C + "/decisions/group", json={**body, "execute": True}, headers=key())
    check("relancer ne crée rien en double", r.status_code == 200 and r.json()["created"] == 0
          and all(i["status"] == "ALREADY" for i in r.json()["items"]), r.text[:200])
    n = as_(actor_for("CAISSIER", sid)).post(C + "/decisions/group", json=body, headers=key())
    check("sans le droit de créer des décisions → refusé", n.status_code == 403, n.status_code)


def main() -> int:
    A = school("A")
    run(A)
    H.CLIENT.__exit__(None, None, None)
    fails = [r for r in H.RESULTS if r[0] == "FAIL"]
    print(f"\n{len(H.RESULTS) - len(fails)}/{len(H.RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
