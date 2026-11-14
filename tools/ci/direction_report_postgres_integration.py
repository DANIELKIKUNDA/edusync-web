"""Rapport de recouvrement de direction — real HTTP + real PostgreSQL (owner, 2026-11-14).

Checks, on a freshly migrated isolated database, that the report counts what the school's rules say:
  paid / partial / unpaid / regularised outside the cash desk; pupil arrived after the cut-off day (no charge, listed apart);
  exonerated pupil (net 0, listed apart); abandon before the month (not owed); « tous les frais » keeps only what is due
  at the situation date; a section-scoped reader sees only his section; the PDF needs the export right.

    python tools/local/isolated_db.py env <db> -- ../.venv/Scripts/python.exe ../tools/ci/direction_report_postgres_integration.py

Reuses tools/ci/three_roles_postgres_integration.py (CI=true, localhost only). Exits 1 on any FAIL.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_roles_postgres_integration as H  # noqa: E402
from three_roles_postgres_integration import RUN, actor_for, as_, check, school, sql  # noqa: E402

READ = {"finance.recovery.monthly.read"}
EXPORT = {"finance.recovery.monthly.read", "finance.views.vf01.export"}


def pupil(A: dict, sec: str, name: str, phone: str | None = None, enrolled_on: str = "2026-09-01"):
    sid, fam, st, enr = A["id"], uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    sql("INSERT INTO families(id,school_id,code,display_name,phone) VALUES(:i,:s,:c,:n,:p)", i=fam, s=sid, c=f"F-{name}-{RUN}", n=f"Famille {name}", p=phone)
    sql("""INSERT INTO students(id,school_id,family_id,matricule,last_name,middle_name,first_name,gender)
           VALUES(:i,:s,:f,:m,:n,'TEST','Élève','F')""", i=st, s=sid, f=fam, m=f"M-{name}-{RUN}", n=name)
    sql("INSERT INTO enrollments(id,school_id,student_id,academic_year_id,class_id,status,enrolled_on) VALUES(:i,:s,:st,:y,:c,'VALIDATED',:d)",
        i=enr, s=sid, st=st, y=A["year"], c=A["classes"][sec], d=enrolled_on)
    return st, enr


def fixture(A: dict) -> dict:
    sid, y = A["id"], A["year"]
    sco, bus = uuid.uuid4(), uuid.uuid4()
    sql("INSERT INTO fee_types(id,school_id,code,label,periodicity,default_currency,regulatory,enabled) VALUES(:i,:s,'SCOLARITE','Minerval','MONTHLY','CDF',false,true)", i=sco, s=sid)
    sql("INSERT INTO fee_types(id,school_id,code,label,periodicity,default_currency,regulatory,enabled) VALUES(:i,:s,'BUS','Frais de bus','ONE_TIME','CDF',false,true)", i=bus, s=sid)
    sched = {}
    for sec in ("PRIMAIRE", "SECONDAIRE"):
        for code, label, order, due in (("10", "Octobre", 2, "2026-10-31"), ("06", "Juin", 10, "2027-06-30")):
            sched[(sec, code)] = uuid.uuid4()
            sql("""INSERT INTO fee_schedules(id,school_id,academic_year_id,class_id,fee_type_id,period_code,period_label,period_order,due_date,amount,currency)
                   VALUES(:i,:s,:y,:c,:f,:p,:l,:o,:d,20000,'CDF')""", i=sched[(sec, code)], s=sid, y=y, c=A["classes"][sec], f=sco, p=code, l=label, o=order, d=due)

    def charge(enr, sec, code, net, paid=0):
        ch = uuid.uuid4(); label, order, due = {"10": ("Octobre", 2, "2026-10-31"), "06": ("Juin", 10, "2027-06-30")}[code]
        sql("""INSERT INTO finance_charges(id,school_id,enrollment_id,label,currency,net_amount,paid_amount,periodicity,period_label,period_order,due_date,fee_type_id,schedule_id)
               VALUES(:i,:s,:e,:l,'CDF',:n,:p,'MONTHLY',:l,:o,:d,:f,:sch)""", i=ch, s=sid, e=enr, l=label, n=net, p=paid, o=order, d=due, f=sco, sch=sched[(sec, code)])
        return ch

    out = {"sco": sco}
    _, e = pupil(A, "SECONDAIRE", "PAYE", "0990000001"); charge(e, "SECONDAIRE", "10", 20000, 20000); charge(e, "SECONDAIRE", "06", 20000, 0)
    _, e = pupil(A, "SECONDAIRE", "PARTIEL", "0990000002"); charge(e, "SECONDAIRE", "10", 20000, 5000)
    _, e = pupil(A, "SECONDAIRE", "IMPAYE"); charge(e, "SECONDAIRE", "10", 20000, 0)            # aucun téléphone
    _, e = pupil(A, "SECONDAIRE", "HORSCAISSE", "0990000003"); reg = charge(e, "SECONDAIRE", "10", 20000, 0)
    uid = uuid.uuid4()
    sql("INSERT INTO users(id,email,full_name,password_hash,active,version) VALUES(:i,:e,'Comptable','x',true,1)", i=uid, e=f"compta-{uid.hex[:8]}@example.test")
    sql("INSERT INTO finance_charge_regularizations(school_id,charge_id,amount,reason,actor_user_id) VALUES(:s,:c,20000,'Retenue sur salaire',:u)", s=sid, c=reg, u=uid)
    _, e = pupil(A, "SECONDAIRE", "EXONERE", "0990000004"); charge(e, "SECONDAIRE", "10", 0, 0)
    st, e = pupil(A, "SECONDAIRE", "PARTI", "0990000005"); charge(e, "SECONDAIRE", "10", 20000, 0)
    sql("INSERT INTO student_status_events(school_id,student_id,event_type,effective_date,reason) VALUES(:s,:st,'ABANDON','2026-10-10','Départ')", s=sid, st=st)
    _, e = pupil(A, "SECONDAIRE", "TARDIF", "0990000006", enrolled_on="2026-10-22")
    pol, rule = uuid.uuid4(), uuid.uuid4()
    sql("INSERT INTO finance_exigibility_policies(id,school_id,academic_year_id,version,status,effective_from,approved_at) VALUES(:i,:s,:y,1,'ACTIVE','2026-09-01',now())", i=pol, s=sid, y=y)
    sql("INSERT INTO finance_exigibility_assessments(school_id,enrollment_id,schedule_id,policy_id,status,tariff_amount,exigible_amount) VALUES(:s,:e,:sch,:p,'NOT_EXIGIBLE',20000,0)",
        s=sid, e=e, sch=sched[("SECONDAIRE", "10")], p=pol)
    _, e = pupil(A, "PRIMAIRE", "PRIMAIRE", "0990000007"); charge(e, "PRIMAIRE", "10", 20000, 0)
    return out


def run(A: dict) -> None:
    print("\n== Rapport de recouvrement de direction (14/11/2026)")
    f = fixture(A)
    c = as_(actor_for("CAISSIER", A["id"], extra=EXPORT))
    base = "/api/v1/finance/recovery/direction-report"
    q = f"?fee_type_id={f['sco']}&period_order=2&as_of=2026-11-14"
    r = c.get(base + q)
    check("rapport « Minerval d’octobre » lisible", r.status_code == 200, r.text[:200])
    if r.status_code != 200:
        return
    d = r.json(); t = d["total"]
    check("titre et période", d["title"] == "Minerval — Octobre", d["title"])
    check("5 élèves concernés : payé, partiel, impayé, hors caisse, primaire (exonéré, parti et tardif exclus)", t["concerned"] == 5, t)
    check("2 à jour (dont la régularisation hors caisse), 3 pas à jour dont 1 partiel", (t["in_order"], t["not_in_order"], t["partial"]) == (2, 3, 1), t)
    check("attendu 100 000, régularisé 45 000, reste 55 000, taux 45 %",
          (float(t["expected"]), float(t["collected"]), float(t["remaining"]), float(t["rate"])) == (100000, 45000, 55000, 45.0), t)
    check("élève inscrit après la date limite listé à part", [g["student_name"] for g in d["exempted"] if g["reason"] == "ARRIVAL"] == ["TARDIF TEST Élève"], d["exempted"])
    check("élève exonéré listé à part", [g["student_name"] for g in d["exempted"] if g["reason"] == "EXEMPTION"] == ["EXONERE TEST Élève"], d["exempted"])
    check("élève parti avant octobre : ni dû ni relancé", all("PARTI " not in u["student_name"] for u in d["unpaid"]), d["unpaid"])
    check("sans téléphone compté (1)", d["analysis"]["without_contact"] == 1, d["analysis"])
    check("contact de la famille repris pour les relances", any(u["contact_phone"] == "0990000002" for u in d["unpaid"]), d["unpaid"])

    r = c.get(base + "?as_of=2026-11-14")
    check("tous les frais échus : juin (pas encore échu) n’est pas compté", r.status_code == 200 and float(r.json()["total"]["expected"]) == 100000, r.text[:200])

    sec = as_(actor_for("CAISSIER", A["id"], scope=("SECTION", "PRIMAIRE"), extra=EXPORT))
    r = sec.get(base + q)
    check("lecteur limité au primaire : ne voit que le primaire", r.status_code == 200 and r.json()["total"]["concerned"] == 1
          and [s["label"] for s in r.json()["sections"]] == ["PRIMAIRE"], r.text[:200])

    pdf = as_(actor_for("CAISSIER", A["id"], extra=EXPORT)).get(base + ".pdf" + q)
    check("PDF produit", pdf.status_code == 200 and pdf.content[:4] == b"%PDF", pdf.status_code)
    no = as_(actor_for("INTENDANT", A["id"], extra=READ)).get(base + ".pdf" + q)   # lit le recouvrement, sans aucun droit d’export
    check("PDF refusé sans le droit d’export", no.status_code == 403, no.status_code)
    bad = c.get(base + "?period_order=2")
    check("période sans type de frais → refusée", bad.status_code == 422, bad.status_code)


def main() -> int:
    A = school("A")
    run(A)
    H.CLIENT.__exit__(None, None, None)
    fails = [r for r in H.RESULTS if r[0] == "FAIL"]
    print(f"\n{len(H.RESULTS) - len(fails)}/{len(H.RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
