from uuid import uuid4
import pytest

from edusync.modules.platform.domain.school import School
from edusync.modules.sync.domain.contracts import SyncOperation, FINANCE_OFFLINE_POLICY, CONFLICT_POLICIES
from edusync.shared.domain.concurrency import VersionToken


def test_school_is_versioned():
    s = School(name="École", code="EC")
    assert s.version == 1


def test_version_token_refuses_zero():
    with pytest.raises(ValueError):
        VersionToken("Student", uuid4(), 0)


def test_sync_requires_valid_base_version_when_present():
    with pytest.raises(ValueError):
        SyncOperation(school_id=uuid4(), user_id=uuid4(), device_id=uuid4(),
            operation_type="UPDATE", aggregate_type="Student", aggregate_id=uuid4(),
            payload={}, idempotency_key="dev:1", base_version=0)


def test_finance_offline_requires_certified_partitioned_multi_cashier_protocol():
    assert FINANCE_OFFLINE_POLICY["final_payment_allowed"] is True
    assert FINANCE_OFFLINE_POLICY["default_enabled"] is False
    assert FINANCE_OFFLINE_POLICY["protocol"] == "AUTHORIZED_PARTITIONED_CASH_V2"
    assert FINANCE_OFFLINE_POLICY["server_auto_release"] is False
    assert CONFLICT_POLICIES["FINANCE"] == "NO_AUTOMATIC_MERGE"
