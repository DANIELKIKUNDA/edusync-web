"""Volume seed for the performance database only (owner SQL, set-based).

School A: 30 classes, 12 000 pupils, 11 charges each (10 monthly CDF + 1 USD), ~21 600 payments.
School B: 60 000 pupils, 660 000 charges — multi-tenant "noise" that RLS must filter out for A.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa: E402,F403

assert DB_URL.endswith("/edusync_claude_perf"), "perf seed runs only on the dedicated performance database"
MONTHS = ["SEPTEMBRE", "OCTOBRE", "NOVEMBRE", "DECEMBRE", "JANVIER", "FEVRIER", "MARS", "AVRIL", "MAI", "JUIN"]


def seed(school, n_students, prefix, with_payments):
    t0 = time.time()
    sid, year, sec = school["school_id"], school["year_id"], school["section_id"]
    with owner.begin() as c:
        c.execute(text("""INSERT INTO school_classes(school_id,academic_year_id,section_id,code,label)
                          SELECT :s,:y,:sec,'P'||g,'Classe perf '||g FROM generate_series(1,30) g ON CONFLICT DO NOTHING"""), {"s": sid, "y": year, "sec": sec})
        c.execute(text("""INSERT INTO families(school_id,code,display_name,phone)
                          SELECT :s,:p||'-F'||lpad(g::text,6,'0'),'FAMILLE '||:p||' '||g,'+2438'||lpad(g::text,8,'0') FROM generate_series(1,:n/2) g"""),
                  {"s": sid, "p": prefix, "n": n_students})
        c.execute(text("""INSERT INTO students(school_id,family_id,matricule,last_name,middle_name,first_name,gender)
                          SELECT :s,f.id,:p||'-'||lpad(g::text,6,'0'),'NOM'||(g%997),'POST'||(g%389),'Prenom'||(g%211),CASE WHEN g%2=0 THEN 'F' ELSE 'M' END
                          FROM generate_series(1,:n) g JOIN families f ON f.school_id=:s AND f.code=:p||'-F'||lpad(((g+1)/2)::text,6,'0')"""),
                  {"s": sid, "p": prefix, "n": n_students})
        c.execute(text("""INSERT INTO enrollments(school_id,student_id,academic_year_id,class_id,status)
                          SELECT :s,st.id,:y,(SELECT id FROM school_classes WHERE school_id=:s AND academic_year_id=:y AND code='P'||(1+abs(hashtext(st.matricule))%30)),'VALIDATED'
                          FROM students st WHERE st.school_id=:s AND st.matricule LIKE :p||'-%'"""), {"s": sid, "y": year, "p": prefix})
        c.execute(text("""INSERT INTO finance_charges(school_id,enrollment_id,label,currency,net_amount,periodicity,period_label,period_order)
                          SELECT :s,e.id,'Minerval · '||m.label,'CDF',50000,'MONTHLY',m.label,m.ord
                          FROM enrollments e JOIN students st ON st.id=e.student_id AND st.matricule LIKE :p||'-%'
                          CROSS JOIN unnest(CAST(:months AS text[])) WITH ORDINALITY m(label,ord) WHERE e.school_id=:s"""),
                  {"s": sid, "p": prefix, "months": MONTHS})
        c.execute(text("""INSERT INTO finance_charges(school_id,enrollment_id,label,currency,net_amount,periodicity)
                          SELECT :s,e.id,'Frais d''inscription','USD',20,'ONE_OFF'
                          FROM enrollments e JOIN students st ON st.id=e.student_id AND st.matricule LIKE :p||'-%' WHERE e.school_id=:s"""), {"s": sid, "p": prefix})
        if with_payments:
            cs = c.execute(text("SELECT id FROM finance_cash_sessions WHERE school_id=:s ORDER BY opened_at LIMIT 1"), {"s": sid}).scalar_one()
            actor = c.execute(text("SELECT user_id FROM school_memberships WHERE school_id=:s LIMIT 1"), {"s": sid}).scalar_one()
            # 60% of pupils paid SEPTEMBRE..NOVEMBRE: one payment + one allocation per month, counters kept consistent
            c.execute(text("""CREATE TEMP TABLE perf_pay ON COMMIT DROP AS
                              SELECT gen_random_uuid() pid, fc.id charge_id, fc.enrollment_id, fc.net_amount amount
                              FROM finance_charges fc JOIN enrollments e ON e.id=fc.enrollment_id JOIN students st ON st.id=e.student_id
                              WHERE fc.school_id=:s AND st.matricule LIKE :p||'-%' AND fc.period_order<=3 AND abs(hashtext(st.matricule))%10<6"""), {"s": sid, "p": prefix})
            c.execute(text("""INSERT INTO finance_payments(id,school_id,enrollment_id,cash_session_id,actor_user_id,amount,currency,receipt_number,idempotency_key)
                              SELECT pid,:s,enrollment_id,:cs,:u,amount,'CDF','PERF-'||replace(pid::text,'-',''),'perf-'||pid FROM perf_pay"""),
                      {"s": sid, "cs": cs, "u": actor})
            c.execute(text("INSERT INTO finance_payment_allocations(school_id,payment_id,charge_id,amount) SELECT :s,pid,charge_id,amount FROM perf_pay"), {"s": sid})
            c.execute(text("UPDATE finance_charges fc SET paid_amount=p.amount FROM perf_pay p WHERE fc.id=p.charge_id"))
    print(f"{prefix}: {n_students} pupils seeded in {time.time() - t0:.1f}s", flush=True)


seed(state["A"], 12000, "PA", True)
seed(state["B"], 60000, "PB", False)
with owner.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
    c.exec_driver_sql("ANALYZE")
    c.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
for t in ("students", "enrollments", "finance_charges", "finance_payments", "finance_payment_allocations"):
    print(t, sql(f"SELECT count(*) n FROM {t}")[0]["n"])
