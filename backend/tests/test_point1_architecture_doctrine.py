from edusync.modules.sync.domain.offline_policy import (
    LOCKED_OFFLINE_INVARIANTS,
    OFFLINE_OPERATION_POLICIES,
    ConflictStrategy,
    OfflineDecision,
    policy_for,
)


def test_all_declared_operations_have_explicit_policy():
    assert len(OFFLINE_OPERATION_POLICIES) >= 10
    for name, policy in OFFLINE_OPERATION_POLICIES.items():
        assert name == policy.operation
        assert policy.rationale.strip()


def test_cash_is_available_offline_but_strongly_preauthorized():
    policy = policy_for("CASH_PAYMENT_FINAL")
    assert policy.decision is OfflineDecision.AUTHORIZED_CRITICAL_WRITE
    assert policy.preauthorization_required is True
    assert policy.conflict is ConflictStrategy.NO_AUTOMATIC_MERGE


def test_external_settlements_are_not_falsely_finalized_offline():
    for name in ("MOBILE_MONEY_PAYMENT_FINAL", "BANK_PAYMENT_FINAL"):
        policy = policy_for(name)
        assert policy.decision is OfflineDecision.ONLINE_EXTERNAL_PROOF_REQUIRED
        assert policy.external_proof_required is True


def test_security_authority_changes_require_live_server_authority():
    for name in ("ROLE_PERMISSION_CHANGE", "SCHOOL_LIFECYCLE_ADMIN"):
        assert policy_for(name).decision is OfflineDecision.ONLINE_SECURITY_ADMIN_REQUIRED


def test_mutable_school_data_has_explicit_concurrency_strategy():
    assert policy_for("STUDENT_PROFILE_WRITE").base_version_required is True
    assert policy_for("ENROLLMENT_WRITE").conflict is ConflictStrategy.REJECT_STALE
    assert policy_for("CONFIGURATION_WRITE").conflict is ConflictStrategy.REJECT_STALE
    assert policy_for("STOCK_MOVEMENT").conflict is ConflictStrategy.TRANSACTIONAL_RECOMPUTE


def test_locked_invariants_cover_tenant_idempotency_audit_and_finance():
    required = {
        "school_id-isolation",
        "idempotency-key",
        "server-inbox-deduplication",
        "financial-posting-is-one-postgresql-transaction",
        "audit-append-only",
        "redis-never-source-of-truth",
    }
    assert required.issubset(set(LOCKED_OFFLINE_INVARIANTS))


def test_unknown_operation_fails_closed_at_policy_boundary():
    try:
        policy_for("UNKNOWN_WRITE")
    except KeyError as exc:
        assert "non classifiée" in str(exc)
    else:
        raise AssertionError("Une opération inconnue ne doit pas hériter d'une autorisation offline implicite")
