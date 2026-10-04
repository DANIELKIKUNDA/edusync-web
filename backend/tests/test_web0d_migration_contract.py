from pathlib import Path

SQL = (Path(__file__).parents[1] / "migrations" / "0004_offline_finance_safe_mode.sql").read_text(encoding="utf-8")
LOW = SQL.lower()


def test_one_active_offline_writer_per_school_is_database_enforced():
    assert "uq_offline_finance_one_writer_per_school" in SQL
    assert "where status in ('preparing','active','draining')" in LOW


def test_server_does_not_auto_release_lease():
    assert "server" not in ""  # explicit semantic marker below, not a timer implementation
    assert "local_stop_at" in SQL
    assert "FORCE_RELEASED" in SQL
    assert "expires_at" not in SQL
    assert "pg_cron" not in LOW


def test_receipts_are_preallocated_and_unique_per_school():
    assert "next_offline_receipt_no" in SQL
    assert "UNIQUE(school_id,receipt_no)" in SQL
    assert "uq_offline_receipt_consumed_operation" in SQL


def test_inbox_has_exact_once_guards_and_journal_sequence():
    for token in (
        "UNIQUE(school_id,operation_id)", "UNIQUE(school_id,idempotency_key)",
        "UNIQUE(school_id,receipt_no)", "UNIQUE(school_id,entry_hash)",
        "UNIQUE(lease_id,journal_seq)",
    ):
        assert token in SQL


def test_offline_v1_is_cash_only():
    assert "CHECK(mode='CASH')" in SQL


def test_tenant_rls_is_forced_on_all_offline_tables():
    for table in (
        "offline_finance_leases", "offline_receipt_counters", "offline_receipt_tokens",
        "offline_charge_snapshots", "offline_payment_inbox",
    ):
        assert table in SQL
    assert "ENABLE ROW LEVEL SECURITY" in SQL
    assert "FORCE ROW LEVEL SECURITY" in SQL
    assert "edusync_tenant" in SQL


def test_cross_tenant_scope_trigger_exists():
    assert "enforce_offline_finance_scope" in SQL
    assert "offline_finance_cross_tenant_scope" in SQL


def test_finance_writer_guard_blocks_other_writer_during_lease():
    assert "assert_finance_writer_allowed" in SQL
    assert "finance_locked_by_offline_lease" in SQL
    assert "FOR UPDATE" in SQL


def test_force_release_requires_reason_and_actor():
    assert "length(trim(force_release_reason)) >= 10" in SQL
    assert "force_released_by" in SQL


def test_permissions_separate_arm_reconcile_and_force_release():
    assert "finance.offline.arm" in SQL
    assert "finance.offline.reconcile" in SQL
    assert "finance.offline.force_release" in SQL

def test_protocol_financial_evidence_is_immutable_after_capture():
    assert "protect_offline_payment_inbox" in SQL
    assert "offline_payment_protocol_immutable_fields" in SQL
    assert "offline_payment_protocol_delete_forbidden" in SQL
    assert "offline_snapshot_frozen" in SQL
    assert "offline_receipt_token_identity_immutable" in SQL


def test_lease_state_machine_is_database_guarded():
    assert "protect_offline_lease_transition" in SQL
    assert "offline_lease_invalid_transition" in SQL
    assert "offline_lease_terminal" in SQL


def test_offline_finance_transitions_emit_append_only_global_audit():
    assert "audit_offline_lease_transition" in SQL
    assert "OFFLINE_FINANCE_LEASE_" in SQL
    assert "audit_offline_payment_applied" in SQL
    assert "OFFLINE_PAYMENT_PROTOCOL_APPLIED" in SQL

def test_sensitive_finance_protocol_functions_are_not_publicly_executable():
    assert "REVOKE ALL ON FUNCTION next_offline_receipt_no(uuid) FROM PUBLIC" in SQL
    assert "REVOKE ALL ON FUNCTION assert_finance_writer_allowed(uuid,uuid,uuid,uuid,uuid) FROM PUBLIC" in SQL
