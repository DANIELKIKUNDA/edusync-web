"""Point 2 live PostgreSQL probe for Finance offline multi-caissier V2.

Run ONLY on the disposable Docker/dev database. This proves that two cashier leases in the
same school can coexist on disjoint charges, while one charge can never be reserved by two
leases and charge-scoped Finance guards reject foreign writers.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from edusync.adapters.postgres_offline_finance import PostgresOfflineFinanceRepository
from edusync.bootstrap.settings import Settings
from edusync.modules.finance_offline.domain.models import ChargeSnapshot, OfflineFinanceConflict


def _set_scope(conn, school_id, user_id):
    conn.execute(text("SELECT set_config('app.current_school_id',:sid,true)"), {"sid": str(school_id)})
    conn.execute(text("SELECT set_config('app.current_user_id',:uid,true)"), {"uid": str(user_id)})


def main() -> None:
    settings = Settings()
    if settings.env.lower() in {"prod", "production"}:
        raise SystemExit("G3 interdit sur une base de production")

    owner = create_engine(settings.owner_database_url, future=True, pool_pre_ping=True)
    tenant = create_engine(settings.tenant_database_url, future=True, pool_pre_ping=True)

    school = uuid4()
    school_b = uuid4()
    users = [uuid4() for _ in range(5)]
    devices = [uuid4() for _ in range(5)]
    sessions = [uuid4() for _ in range(5)]
    student_a, student_b = uuid4(), uuid4()
    enrollment_a, enrollment_b = uuid4(), uuid4()
    charge_a, charge_b = uuid4(), uuid4()

    # Identity seed is committed so separate tenant transactions see it.
    with owner.begin() as c:
        c.execute(text("INSERT INTO schools(id,code,name) VALUES(:id,:code,'G3 School')"),
                  {"id": school, "code": f"G3-{str(school)[:8]}".upper()})
        c.execute(text("INSERT INTO schools(id,code,name) VALUES(:id,:code,'G3 Other School')"),
                  {"id": school_b, "code": f"G3B-{str(school_b)[:8]}".upper()})
        for i, (user, device) in enumerate(zip(users, devices), start=1):
            c.execute(text("INSERT INTO users(id,full_name,password_hash) VALUES(:id,:name,'probe')"),
                      {"id": user, "name": f"G3 Cashier {i}"})
            c.execute(text("INSERT INTO devices(id,school_id,user_id,label,platform) VALUES(:id,:sid,:uid,:label,'PROBE')"),
                      {"id": device, "sid": school, "uid": user, "label": f"G3 Device {i}"})

    lease_ids = []
    try:
        # Cashier A reserves Charge A.
        with tenant.begin() as c:
            _set_scope(c, school, users[0])
            repo = PostgresOfflineFinanceRepository(c)
            lease_a, tokens_a = repo.acquire_multi_writer_lease(
                school_id=school, cashier_user_id=users[0], device_id=devices[0], cash_session_id=sessions[0],
                max_payments=20, max_cdf="1000000", max_usd="1000", receipt_count=5, local_minutes=120,
            )
            repo.reserve_charge_snapshots(lease_a.id, [
                ChargeSnapshot(charge_a, enrollment_a, student_a, "CDF", Decimal("100000"), 1)
            ])
            lease_a = repo.activate_multi_writer_lease(lease_a.id)
            lease_ids.append(lease_a.id)
            assert lease_a.status == "ACTIVE" and len(tokens_a) == 5

        # Cashier B simultaneously coexists in the same school on Charge B.
        with tenant.begin() as c:
            _set_scope(c, school, users[1])
            repo = PostgresOfflineFinanceRepository(c)
            lease_b, tokens_b = repo.acquire_multi_writer_lease(
                school_id=school, cashier_user_id=users[1], device_id=devices[1], cash_session_id=sessions[1],
                max_payments=20, max_cdf="1000000", max_usd="1000", receipt_count=5, local_minutes=120,
            )
            repo.reserve_charge_snapshots(lease_b.id, [
                ChargeSnapshot(charge_b, enrollment_b, student_b, "CDF", Decimal("80000"), 1)
            ])
            lease_b = repo.activate_multi_writer_lease(lease_b.id)
            lease_ids.append(lease_b.id)
            assert lease_b.status == "ACTIVE" and len(tokens_b) == 5

        # Third cashier may arm, but cannot reserve Charge A while A owns it.
        with tenant.begin() as c:
            _set_scope(c, school, users[2])
            repo = PostgresOfflineFinanceRepository(c)
            lease_c, _ = repo.acquire_multi_writer_lease(
                school_id=school, cashier_user_id=users[2], device_id=devices[2], cash_session_id=sessions[2],
                max_payments=5, max_cdf="100000", max_usd="100", receipt_count=2, local_minutes=60,
            )
            lease_ids.append(lease_c.id)
            try:
                repo.reserve_charge_snapshots(lease_c.id, [
                    ChargeSnapshot(charge_a, enrollment_a, student_a, "CDF", Decimal("100000"), 1)
                ])
            except OfflineFinanceConflict:
                pass
            else:
                raise AssertionError("Charge A was granted to two offline cashiers")

        # Real two-connection race: both cashiers ask for the SAME charge authority. Exactly one wins.
        charge_race, student_race, enrollment_race = uuid4(), uuid4(), uuid4()
        race_leases = []
        for idx in (3, 4):
            with tenant.begin() as c:
                _set_scope(c, school, users[idx])
                repo = PostgresOfflineFinanceRepository(c)
                l, _ = repo.acquire_multi_writer_lease(
                    school_id=school, cashier_user_id=users[idx], device_id=devices[idx],
                    cash_session_id=sessions[idx], max_payments=5, max_cdf="200000", max_usd="100",
                    receipt_count=1, local_minutes=60,
                )
                race_leases.append((idx, l.id))
                lease_ids.append(l.id)

        def reserve_same_charge(pair):
            idx, lease_id = pair
            try:
                with tenant.begin() as c:
                    _set_scope(c, school, users[idx])
                    PostgresOfflineFinanceRepository(c).reserve_charge_snapshots(lease_id, [
                        ChargeSnapshot(charge_race, enrollment_race, student_race, "CDF", Decimal("50000"), 1)
                    ])
                return "WON"
            except OfflineFinanceConflict:
                return "BLOCKED"

        with ThreadPoolExecutor(max_workers=2) as pool:
            race_results = list(pool.map(reserve_same_charge, race_leases))
        assert sorted(race_results) == ["BLOCKED", "WON"], race_results

        # Charge-scoped guard: owner lease passes; foreign/no lease fails; unreserved charge passes online.
        with tenant.begin() as c:
            _set_scope(c, school, users[0])
            c.execute(text("SELECT assert_finance_charge_writer_allowed(:sid,:cid,:lid)"),
                      {"sid": school, "cid": charge_a, "lid": lease_a.id})
            for foreign in (None, lease_b.id):
                try:
                    with c.begin_nested():
                        c.execute(text("SELECT assert_finance_charge_writer_allowed(:sid,:cid,:lid)"),
                                  {"sid": school, "cid": charge_a, "lid": foreign})
                except DBAPIError as exc:
                    assert "finance_charge_reserved_by_offline_cashier" in str(exc.orig)
                else:
                    raise AssertionError("Foreign writer unexpectedly touched reserved charge")
            c.execute(text("SELECT assert_finance_charge_writer_allowed(:sid,:cid,NULL)"),
                      {"sid": school, "cid": uuid4()})

            # RLS: same tenant role switched to another school cannot see G3 leases.
            c.execute(text("SELECT set_config('app.current_school_id',:sid,true)"), {"sid": str(school_b)})
            assert c.execute(text("SELECT count(*) FROM offline_finance_leases WHERE school_id=:sid"),
                             {"sid": school}).scalar_one() == 0

        print("G3_MULTI_CASHIER_POSTGRES_PASS")
        print("NOTE: probe data remains in this disposable dev database; reset Docker volume after certification if desired.")
    finally:
        # We intentionally do not attempt destructive cleanup of append-only/protected financial proof tables.
        # This script is restricted to a disposable dev database for that reason.
        pass


if __name__ == "__main__":
    main()
