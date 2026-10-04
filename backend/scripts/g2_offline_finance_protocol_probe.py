"""WEB-0D live PostgreSQL probe for the exclusive offline CASH protocol.

This probe is intentionally run only on a development / disposable database after
provision_database.py. It seeds one school/user/device, performs all protocol writes
inside a tenant transaction, then ROLLS THAT TRANSACTION BACK before removing the seed.
It does not pretend to certify the canonical Finance ledger adapter; that gate is run
when charges/payments/allocations/receipts/cash are ported to Web.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from edusync.adapters.postgres_offline_finance import PostgresOfflineFinanceRepository
from edusync.bootstrap.settings import Settings
from edusync.modules.finance_offline.domain.models import (
    ChargeSnapshot, OfflineAllocation, OfflineFinanceConflict, OfflinePaymentCommand
)


def main() -> None:
    settings = Settings()
    if settings.env.lower() in {"prod", "production"}:
        raise SystemExit("G2 probe interdit sur une base de production")

    owner = create_engine(settings.owner_database_url, future=True, pool_pre_ping=True)
    tenant = create_engine(settings.tenant_database_url, future=True, pool_pre_ping=True)

    school_a, school_b = uuid4(), uuid4()
    user_a = uuid4()
    device_a = uuid4()
    cash_session = uuid4()
    code_a = f"G2A-{str(school_a)[:8]}".upper()
    code_b = f"G2B-{str(school_b)[:8]}".upper()

    # Seed only non-audited foundation identities. Protocol writes below are rolled back.
    with owner.begin() as c:
        c.execute(text("INSERT INTO schools(id,code,name) VALUES(:id,:code,'G2 Offline Probe A')"), {"id": school_a, "code": code_a})
        c.execute(text("INSERT INTO schools(id,code,name) VALUES(:id,:code,'G2 Offline Probe B')"), {"id": school_b, "code": code_b})
        c.execute(text("INSERT INTO users(id,full_name,password_hash) VALUES(:id,'G2 Cashier','probe-not-login')"), {"id": user_a})
        c.execute(text("""
            INSERT INTO devices(id,school_id,user_id,label,platform)
            VALUES(:id,:sid,:uid,'G2 Device','PROBE')
        """), {"id": device_a, "sid": school_a, "uid": user_a})

    conn = tenant.connect()
    tx = conn.begin()
    try:
        conn.execute(text("SELECT set_config('app.current_school_id',:sid,true)"), {"sid": str(school_a)})
        conn.execute(text("SELECT set_config('app.current_user_id',:uid,true)"), {"uid": str(user_a)})
        repo = PostgresOfflineFinanceRepository(conn)

        lease, tokens = repo.acquire_exclusive_lease(
            school_id=school_a, cashier_user_id=user_a, device_id=device_a,
            cash_session_id=cash_session, max_payments=10,
            max_cdf="500000.00", max_usd="500.00", receipt_count=3, local_minutes=60,
        )
        assert lease.status == "PREPARING"
        assert len(tokens) == 3 and len({x.receipt_no for x in tokens}) == 3

        # Same school cannot arm a second writer, even before activation.
        try:
            repo.acquire_exclusive_lease(
                school_id=school_a, cashier_user_id=user_a, device_id=device_a,
                cash_session_id=uuid4(), max_payments=2, max_cdf="1", max_usd="1",
                receipt_count=1, local_minutes=10,
            )
        except OfflineFinanceConflict:
            pass
        else:
            raise AssertionError("Second exclusive lease unexpectedly accepted")

        charge, enrollment, student = uuid4(), uuid4(), uuid4()
        repo.store_charge_snapshots(lease.id, [
            ChargeSnapshot(charge, enrollment, student, "CDF", Decimal("1000.00"), 1)
        ])
        lease = repo.activate_lease(lease.id)
        assert lease.status == "ACTIVE"

        # RLS: switching the same tenant transaction to School B hides School A protocol rows.
        conn.execute(text("SELECT set_config('app.current_school_id',:sid,true)"), {"sid": str(school_b)})
        hidden = conn.execute(text("SELECT count(*) FROM offline_finance_leases WHERE id=:id"), {"id": lease.id}).scalar_one()
        assert hidden == 0
        conn.execute(text("SELECT set_config('app.current_school_id',:sid,true)"), {"sid": str(school_a)})

        # The owner lease can pass the global Finance write guard.
        conn.execute(text("SELECT assert_finance_writer_allowed(:sid,:uid,:did,:cs,:lid)"), {
            "sid": school_a, "uid": user_a, "did": device_a, "cs": cash_session, "lid": lease.id,
        })

        # Any other device is blocked while the lease is ACTIVE.
        try:
            with conn.begin_nested():
                conn.execute(text("SELECT assert_finance_writer_allowed(:sid,:uid,:did,:cs,:lid)"), {
                    "sid": school_a, "uid": user_a, "did": uuid4(), "cs": cash_session, "lid": lease.id,
                })
        except DBAPIError as exc:
            # Protocol V2 (migration 0005) replaced the V1 guard message; both mean "foreign writer refused".
            assert any(m in str(exc.orig) for m in ("finance_offline_lease_identity_mismatch", "finance_locked_by_offline_lease")), str(exc.orig)
        else:
            raise AssertionError("Foreign Finance writer unexpectedly accepted")

        token = tokens[0]
        cmd = OfflinePaymentCommand(
            school_id=school_a, lease_id=lease.id, device_id=device_a, cashier_user_id=user_a,
            cash_session_id=cash_session, student_id=student, enrollment_id=enrollment,
            currency="CDF", amount=Decimal("100.00"), receipt_token_id=token.id,
            receipt_no=token.receipt_no, allocations=(OfflineAllocation(charge, Decimal("100.00")),),
            journal_seq=1, operation_id=uuid4(), idempotency_key=f"g2:{uuid4()}",
            client_time=datetime.now(timezone.utc), previous_entry_hash=None,
        ).with_computed_hash()
        assert repo.store_received_command(cmd) is True
        assert repo.store_received_command(cmd) is False  # exact replay is a no-op

        # A lease cannot close while a protocol command is merely RECEIVED, not APPLIED.
        try:
            repo.close_lease_if_reconciled(
                lease.id, expected_count=0, expected_cdf="0", expected_usd="0", final_entry_hash=None
            )
        except OfflineFinanceConflict:
            pass
        else:
            raise AssertionError("Lease closed with an unapplied payment command")

        # Protocol-only reconciliation proof. The future canonical Finance adapter will supply
        # the real payment_id inside the same transaction before these two calls.
        fake_payment_id = uuid4()
        repo.consume_receipt_token(token_id=token.id, lease_id=lease.id, operation_id=cmd.operation_id)
        repo.mark_command_applied(cmd.operation_id, payment_id=fake_payment_id)
        repo.mark_lease_draining(lease.id)
        repo.close_lease_if_reconciled(
            lease.id, expected_count=1, expected_cdf="100.00", expected_usd="0.00",
            final_entry_hash=cmd.entry_hash,
        )
        closed = conn.execute(text("SELECT status FROM offline_finance_leases WHERE id=:id"), {"id": lease.id}).scalar_one()
        assert closed == "CLOSED"
        remaining = conn.execute(text("SELECT count(*) FROM offline_receipt_tokens WHERE lease_id=:id AND status='AVAILABLE'"), {"id": lease.id}).scalar_one()
        assert remaining == 0  # unused preallocated numbers were VOIDed

        print("G2_OFFLINE_FINANCE_PROTOCOL_POSTGRES_PASS")
    finally:
        tx.rollback()  # removes lease, tokens, inbox and their append-only audit rows together
        conn.close()
        with owner.begin() as c:
            c.execute(text("DELETE FROM devices WHERE id=:id"), {"id": device_a})
            c.execute(text("DELETE FROM users WHERE id=:id"), {"id": user_a})
            c.execute(text("DELETE FROM schools WHERE id IN (:a,:b)"), {"a": school_a, "b": school_b})


if __name__ == "__main__":
    main()
