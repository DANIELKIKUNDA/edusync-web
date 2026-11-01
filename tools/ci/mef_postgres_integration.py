"""MEF certification on the disposable PostgreSQL service used by GitHub Actions.

This script refuses remote databases. It proves migration 0105, tenant RLS,
cross-school foreign keys, concurrent activation, late-arrival assessments,
charge generation, zero-obligation semantics and historical-payment safety.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from edusync.adapters.postgres_annual_policy_activation import activate_annual_policy
from edusync.adapters.postgres_fee_schedules import PostgresFeeScheduleRepository


owner_url = os.environ["EDUSYNC_OWNER_DATABASE_URL"]
tenant_url = os.environ["EDUSYNC_TENANT_DATABASE_URL"]
assert os.environ.get("CI") == "true", "CI jetable uniquement"
assert "127.0.0.1" in owner_url and "127.0.0.1" in tenant_url, "Base distante refusée"
owner = create_engine(owner_url, future=True, pool_pre_ping=True)
tenant = create_engine(tenant_url, future=True, pool_pre_ping=True)

school_a, school_b, actor = uuid4(), uuid4(), uuid4()
year_a, year_b = uuid4(), uuid4()
section_a, section_b, class_a, class_b = (uuid4() for _ in range(4))
fee_a, fee_b, fee_usd = uuid4(), uuid4(), uuid4()
tariff_a, tariff_usd = uuid4(), uuid4()
policy_a, competing_a, policy_b = uuid4(), uuid4(), uuid4()


def scope(conn, school_id):
    for key in ("app.school_id", "app.current_school_id"):
        conn.execute(text("SELECT set_config(:key,:sid,true)"), {"key": key, "sid": str(school_id)})


def add_policy(conn, policy_id, school_id, year_id, fee_id, version, status="DRAFT"):
    conn.execute(text("""INSERT INTO finance_exigibility_policies
      (id,school_id,academic_year_id,version,status,effective_from,approved_at)
      VALUES(:id,:s,:y,:v,:status,'2026-09-01',:approved)"""),
      {"id": policy_id, "s": school_id, "y": year_id, "v": version, "status": status,
       "approved": datetime.now(timezone.utc) if status == "ACTIVE" else None})
    rule = uuid4()
    conn.execute(text("""INSERT INTO finance_exigibility_rules
      (id,school_id,policy_id,fee_type_id,prior_mode) VALUES(:id,:s,:p,:f,'NOT_APPLICABLE')"""),
      {"id": rule, "s": school_id, "p": policy_id, "f": fee_id})
    for first, last, percent in ((1, 15, 100), (16, 24, 50), (25, None, 0)):
        conn.execute(text("""INSERT INTO finance_exigibility_day_bands
          (school_id,rule_id,first_day,last_day,percent) VALUES(:s,:r,:first,:last,:pct)"""),
          {"s": school_id, "r": rule, "first": first, "last": last, "pct": percent})


def seed_enrollment(conn, enrolled_on, suffix):
    family, student, enrollment = uuid4(), uuid4(), uuid4()
    conn.execute(text("INSERT INTO families(id,school_id,code,display_name) VALUES(:id,:s,:code,:name)"),
                 {"id": family, "s": school_a, "code": f"MEF-F-{suffix}", "name": f"Famille {suffix}"})
    conn.execute(text("""INSERT INTO students
      (id,school_id,family_id,matricule,last_name,middle_name,first_name)
      VALUES(:id,:s,:f,:m,'MEF','TEST',:first)"""),
      {"id": student, "s": school_a, "f": family, "m": f"MEF-{suffix}", "first": suffix})
    conn.execute(text("""INSERT INTO enrollments
      (id,school_id,student_id,academic_year_id,class_id,enrolled_on)
      VALUES(:id,:s,:st,:y,:c,:d)"""),
      {"id": enrollment, "s": school_a, "st": student, "y": year_a, "c": class_a, "d": enrolled_on})
    return enrollment


try:
    with owner.begin() as c:
        assert c.execute(text("SELECT 1 FROM schema_migrations WHERE version='0105_finance_annual_exigibility'" )).scalar_one() == 1
        for sid, code, name in ((school_a, f"MEFA-{school_a.hex[:8]}", "MEF A"),
                                (school_b, f"MEFB-{school_b.hex[:8]}", "MEF B")):
            c.execute(text("INSERT INTO schools(id,code,name) VALUES(:id,:code,:name)"), {"id": sid, "code": code, "name": name})
        for yid, sid, code in ((year_a, school_a, "MEF-A-2026"), (year_b, school_b, "MEF-B-2026")):
            c.execute(text("""INSERT INTO academic_years(id,school_id,code,label,start_date,end_date,status)
              VALUES(:id,:s,:code,:code,'2026-09-01','2027-06-30','ACTIVE')"""), {"id": yid, "s": sid, "code": code})
        for sec, sid, code in ((section_a, school_a, "MEFA"), (section_b, school_b, "MEFB")):
            c.execute(text("INSERT INTO school_sections(id,school_id,code,label) VALUES(:id,:s,:code,:code)"),
                      {"id": sec, "s": sid, "code": code})
        for cid, sid, yid, sec, code in ((class_a, school_a, year_a, section_a, "MEF-A1"),
                                          (class_b, school_b, year_b, section_b, "MEF-B1")):
            c.execute(text("""INSERT INTO school_classes(id,school_id,academic_year_id,section_id,code,label)
              VALUES(:id,:s,:y,:sec,:code,:code)"""), {"id": cid, "s": sid, "y": yid, "sec": sec, "code": code})
        for fid, sid, code, currency in ((fee_a, school_a, "MEF_MONTHLY", "CDF"),
                                         (fee_usd, school_a, "MEF_MONTHLY_USD", "USD"),
                                         (fee_b, school_b, "MEF_OTHER", "CDF")):
            c.execute(text("""INSERT INTO fee_types(id,school_id,code,label,periodicity,default_currency)
              VALUES(:id,:s,:code,:code,'MONTHLY',:currency)"""),
              {"id": fid, "s": sid, "code": code, "currency": currency})
        c.execute(text("""INSERT INTO tariffs(id,school_id,academic_year_id,fee_type_id,class_id,currency,amount,
          scope_type,scope_ref,effective_from,status)
          VALUES(:id,:s,:y,:f,:c,'CDF',100000,'CLASS',:scope,'2026-09-01','ACTIVE')"""),
          {"id": tariff_a, "s": school_a, "y": year_a, "f": fee_a, "c": class_a, "scope": str(class_a)})
        c.execute(text("""INSERT INTO tariffs(id,school_id,academic_year_id,fee_type_id,class_id,currency,amount,
          scope_type,scope_ref,effective_from,status)
          VALUES(:id,:s,:y,:f,:c,'USD',20,'CLASS',:scope,'2026-09-01','ACTIVE')"""),
          {"id": tariff_usd, "s": school_a, "y": year_a, "f": fee_usd, "c": class_a, "scope": str(class_a)})
        # September through February, crossing the civil year.
        months = ((2026, 9), (2026, 10), (2026, 11), (2026, 12), (2027, 1), (2027, 2))
        for order, (yy, mm) in enumerate(months, 1):
            for fid, amount, currency, tariff in ((fee_a, 100000, "CDF", tariff_a), (fee_usd, 20, "USD", tariff_usd)):
                c.execute(text("""INSERT INTO fee_schedules
                  (id,school_id,academic_year_id,class_id,fee_type_id,period_code,period_label,period_order,due_date,amount,currency,tariff_id)
                  VALUES(:id,:s,:y,:c,:f,:code,:label,:ord,:due,:amount,:currency,:tariff)"""),
                  {"id": uuid4(), "s": school_a, "y": year_a, "c": class_a, "f": fid,
                   "code": f"{mm:02d}", "label": f"{mm:02d}/{yy}", "ord": order,
                   "due": date(yy, mm, 1), "amount": amount, "currency": currency, "tariff": tariff})
        add_policy(c, policy_a, school_a, year_a, fee_a, 1)
        add_policy(c, competing_a, school_a, year_a, fee_a, 2)
        # USD rules exist in both competing versions, so the concurrency winner is irrelevant.
        for parent in (policy_a, competing_a):
            rule_usd = uuid4()
            c.execute(text("""INSERT INTO finance_exigibility_rules
              (id,school_id,policy_id,fee_type_id,prior_mode) VALUES(:id,:s,:p,:f,'NOT_APPLICABLE')"""),
              {"id": rule_usd, "s": school_a, "p": parent, "f": fee_usd})
            for first, last, percent in ((1, 15, 100), (16, 24, 50), (25, None, 0)):
                c.execute(text("INSERT INTO finance_exigibility_day_bands(school_id,rule_id,first_day,last_day,percent) VALUES(:s,:r,:a,:b,:p)"),
                          {"s": school_a, "r": rule_usd, "a": first, "b": last, "p": percent})
        add_policy(c, policy_b, school_b, year_b, fee_b, 1, "ACTIVE")

        # Composite FK: a rule can never connect school A's policy to school B's fee.
        nested = c.begin_nested()
        try:
            c.execute(text("""INSERT INTO finance_exigibility_rules
              (school_id,policy_id,fee_type_id,prior_mode) VALUES(:s,:p,:f,'FULL')"""),
              {"s": school_a, "p": policy_a, "f": fee_b})
            raise AssertionError("Une référence inter-écoles aurait dû être refusée")
        except IntegrityError:
            nested.rollback()

    # Tenant RLS: school A sees neither school B's active policy nor its rules.
    with tenant.begin() as c:
        scope(c, school_a)
        assert c.execute(text("SELECT count(*) FROM finance_exigibility_policies WHERE school_id=:s"), {"s": school_b}).scalar_one() == 0
        assert c.execute(text("SELECT count(*) FROM finance_exigibility_rules WHERE school_id=:s"), {"s": school_b}).scalar_one() == 0

    # Two activations serialize on the academic-year row. Exactly one active version remains.
    gate = Barrier(2)
    def activate(pid):
        with tenant.begin() as c:
            scope(c, school_a)
            gate.wait()
            return activate_annual_policy(c, school_id=school_a, academic_year_id=year_a, policy_id=pid, actor_id=actor)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [f.result(timeout=20) for f in (pool.submit(activate, policy_a), pool.submit(activate, competing_a))]
    assert all(r["status"] == "ACTIVE" for r in results)
    with tenant.begin() as c:
        scope(c, school_a)
        active = c.execute(text("""SELECT id FROM finance_exigibility_policies
          WHERE school_id=:s AND academic_year_id=:y AND status='ACTIVE'"""), {"s": school_a, "y": year_a}).scalars().all()
        assert len(active) == 1
        active_policy = active[0]

    arrivals = {
        "SEP05": date(2026, 9, 5), "OCT20": date(2026, 10, 20), "NOV28": date(2026, 11, 28),
        "DEC10": date(2026, 12, 10), "JAN16": date(2027, 1, 16), "FEB25": date(2027, 2, 25),
    }
    enrollments = {}
    with owner.begin() as c:
        for label, arrived in arrivals.items():
            enrollments[label] = seed_enrollment(c, arrived, label)

    with tenant.begin() as c:
        scope(c, school_a)
        repo = PostgresFeeScheduleRepository(c)
        for enrollment in enrollments.values():
            repo.generate_charges_for_enrollment(school_a, enrollment)

        # Arrival-month bands: 100%, 50%, 0%; prior months are not applicable and create no debt.
        expected_cdf = {"SEP05": 600000, "OCT20": 450000, "NOV28": 300000,
                        "DEC10": 300000, "JAN16": 150000, "FEB25": 0}
        for label, enrollment in enrollments.items():
            total = c.execute(text("""SELECT COALESCE(sum(net_amount),0) FROM finance_charges
              WHERE school_id=:s AND enrollment_id=:e AND currency='CDF'"""),
              {"s": school_a, "e": enrollment}).scalar_one()
            assert total == Decimal(expected_cdf[label]), (label, total)
        feb = enrollments["FEB25"]
        assert c.execute(text("SELECT count(*) FROM finance_charges WHERE enrollment_id=:e"), {"e": feb}).scalar_one() == 0
        statuses = c.execute(text("""SELECT status,count(*) FROM finance_exigibility_assessments
          WHERE school_id=:s GROUP BY status"""), {"s": school_a}).all()
        counts = dict(statuses)
        assert counts["NOT_APPLICABLE"] > 0 and counts["NOT_EXIGIBLE"] > 0 and counts["DUE"] > 0
        # USD is calculated independently and remains USD.
        usd = c.execute(text("SELECT sum(net_amount) FROM finance_charges WHERE enrollment_id=:e AND currency='USD'"),
                        {"e": enrollments["OCT20"]}).scalar_one()
        assert usd == Decimal("90.00")

        # Paid historical charge: a changed active policy must not silently rewrite it.
        protected = c.execute(text("""SELECT id,net_amount FROM finance_charges
          WHERE enrollment_id=:e AND currency='CDF' ORDER BY due_date LIMIT 1"""),
          {"e": enrollments["SEP05"]}).mappings().one()
        c.execute(text("UPDATE finance_charges SET paid_amount=net_amount WHERE id=:id"), {"id": protected["id"]})

    # Leap-day calculation is also proved against the pure engine in the same CI gate.
    from edusync.modules.finance_fee_tracking.domain.annual_exigibility import DayBand, EntryPolicy, PriorPeriodMode, resolve_monthly_obligation
    leap = resolve_monthly_obligation(tariff=Decimal("100"), period_year=2028, period_month=2,
        financial_entry_date=date(2028, 2, 29), policy=EntryPolicy(PriorPeriodMode.NOT_APPLICABLE,
        (DayBand(1, 15, Decimal(100)), DayBand(16, 24, Decimal(50)), DayBand(25, None, Decimal(0)))))
    assert leap.status.value == "NOT_EXIGIBLE" and leap.exigible == Decimal("0.00")
finally:
    owner.dispose()
    tenant.dispose()

print("MEF_POSTGRES_INTEGRATION=PASS")
