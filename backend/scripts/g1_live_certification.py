from __future__ import annotations

import concurrent.futures
import os
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import create_engine, text

from edusync.bootstrap.settings import Settings


@dataclass
class Result:
    name: str
    ok: bool
    detail: str = ""


def main() -> None:
    s = Settings()
    if s.env.lower() in {"prod", "production"} and os.environ.get("EDUSYNC_ALLOW_G1_PROBE_PRODUCTION") != "YES":
        raise SystemExit("Refus d'exécuter G1 DB probe en production sans EDUSYNC_ALLOW_G1_PROBE_PRODUCTION=YES")

    owner = create_engine(s.owner_database_url, future=True, pool_pre_ping=True)
    platform = create_engine(s.platform_database_url, future=True, pool_pre_ping=True)
    tenant = create_engine(s.tenant_database_url, future=True, pool_pre_ping=True)
    results: list[Result] = []
    created: dict[str, object] = {}
    idem_key = f"g1:{uuid4()}"

    try:
        with owner.begin() as c:
            rows = c.execute(text("""
                SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolbypassrls
                  FROM pg_roles WHERE rolname IN ('edusync_tenant','edusync_platform') ORDER BY rolname
            """)).all()
            ok = len(rows) == 2 and all(not any(bool(v) for v in r[1:]) for r in rows)
            results.append(Result("roles_least_privilege", ok, str(rows)))

        code_a, code_b = f"G1A-{uuid4().hex[:8]}", f"G1B-{uuid4().hex[:8]}"
        ua, ub = uuid4(), uuid4()
        with platform.begin() as c:
            a = c.execute(text("INSERT INTO schools(code,name) VALUES (:c,'G1 École A') RETURNING id"), {"c": code_a}).scalar_one()
            b = c.execute(text("INSERT INTO schools(code,name) VALUES (:c,'G1 École B') RETURNING id"), {"c": code_b}).scalar_one()
            c.execute(text("""
                INSERT INTO users(id,email,full_name,password_hash) VALUES
                (:ua,:ea,'G1 User A','probe'),(:ub,:eb,'G1 User B','probe')
            """), {"ua": ua, "ub": ub, "ea": f"{ua}@g1.test", "eb": f"{ub}@g1.test"})
            ma = c.execute(text("INSERT INTO school_memberships(school_id,user_id) VALUES (:s,:u) RETURNING id"), {"s": a, "u": ua}).scalar_one()
            mb = c.execute(text("INSERT INTO school_memberships(school_id,user_id) VALUES (:s,:u) RETURNING id"), {"s": b, "u": ub}).scalar_one()
            created.update(a=a, b=b, ua=ua, ub=ub, ma=ma, mb=mb)

        with tenant.begin() as c:
            c.execute(text("SELECT set_config('app.current_school_id', :sid, true)"), {"sid": str(a)})
            c.execute(text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(ua)})
            visible_schools = c.execute(text("SELECT id FROM schools ORDER BY id")).scalars().all()
            visible_users = c.execute(text("SELECT id FROM users ORDER BY id")).scalars().all()
            visible_memberships = c.execute(text("SELECT id FROM school_memberships ORDER BY id")).scalars().all()
            results.append(Result("rls_school_a_cannot_read_b", visible_schools == [a], f"visible={visible_schools}"))
            results.append(Result("rls_user_a_cannot_read_user_b", visible_users == [ua], f"visible={visible_users}"))
            results.append(Result("rls_school_a_cannot_read_membership_b", visible_memberships == [ma], f"visible={visible_memberships}"))

        denied = False
        try:
            with tenant.begin() as c:
                c.execute(text("SELECT set_config('app.current_school_id', :sid, true)"), {"sid": str(a)})
                c.execute(text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(ua)})
                c.execute(text("INSERT INTO audit_events(school_id,action,entity_type,source,result) VALUES (:b,'G1','Probe','SYSTEM','SUCCESS')"), {"b": b})
        except Exception:
            denied = True
        results.append(Result("rls_school_a_cannot_write_b", denied))

        cannot_set_platform_role = False
        try:
            with tenant.begin() as c:
                c.exec_driver_sql("SET ROLE edusync_platform")
        except Exception:
            cannot_set_platform_role = True
        results.append(Result("tenant_cannot_set_platform_role", cannot_set_platform_role))

        # Optimistic concurrency: both sessions read the same version; exactly one CAS update wins.
        with platform.begin() as c:
            expected = int(c.execute(text("SELECT version FROM schools WHERE id=:id"), {"id": a}).scalar_one())

        def cas(name: str) -> int:
            with platform.begin() as c:
                row = c.execute(text("""
                    UPDATE schools SET name=:name, version=version+1, updated_at=now()
                     WHERE id=:id AND version=:v RETURNING version
                """), {"name": name, "id": a, "v": expected}).first()
                return 0 if row is None else int(row[0])

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            wins = [x for x in pool.map(cas, ["G1 A - writer 1", "G1 A - writer 2"]) if x]
        results.append(Result("optimistic_concurrency_exactly_one_winner", len(wins) == 1, f"wins={wins}"))

        # Database-level idempotency uniqueness under concurrent inserts.
        def reserve_idem() -> str:
            with platform.begin() as c:
                row = c.execute(text("""
                    INSERT INTO idempotency_registry(scope_key,idempotency_key,request_hash,operation,status)
                    VALUES ('platform',:k,repeat('a',64),'G1_PROBE','PROCESSING')
                    ON CONFLICT(scope_key,idempotency_key) DO NOTHING
                    RETURNING id
                """), {"k": idem_key}).first()
                return "owner" if row is not None else "duplicate"

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            idem = list(pool.map(lambda _: reserve_idem(), range(2)))
        results.append(Result("idempotency_unique_one_owner", sorted(idem) == ["duplicate", "owner"], str(idem)))

    finally:
        # Probe data is temporary at DB level. The API probe, in contrast, intentionally leaves
        # an audited suspended school as evidence in a non-production certification database.
        if created:
            try:
                with platform.begin() as c:
                    c.execute(text("DELETE FROM idempotency_registry WHERE scope_key='platform' AND idempotency_key=:k"), {"k": idem_key})
                    c.execute(text("DELETE FROM school_memberships WHERE id IN (:ma,:mb)"), {"ma": created["ma"], "mb": created["mb"]})
                    c.execute(text("DELETE FROM users WHERE id IN (:ua,:ub)"), {"ua": created["ua"], "ub": created["ub"]})
                    c.execute(text("DELETE FROM schools WHERE id IN (:a,:b)"), {"a": created["a"], "b": created["b"]})
            except Exception as exc:
                results.append(Result("probe_cleanup", False, repr(exc)))

    failed = [r for r in results if not r.ok]
    for r in results:
        print(f"{'PASS' if r.ok else 'FAIL'} | {r.name} | {r.detail}")
    if failed:
        raise SystemExit(f"G1 LIVE FAIL: {len(failed)} scenario(s)")
    print(f"G1 LIVE PASS: {len(results)}/{len(results)}")


if __name__ == "__main__":
    main()
