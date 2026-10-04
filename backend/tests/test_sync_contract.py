from uuid import uuid4
from edusync.modules.sync.domain.contracts import SyncOperation, FINANCE_OFFLINE_POLICY

def test_sync_operation_requires_idempotency_key_by_contract():
    op = SyncOperation(school_id=uuid4(), user_id=uuid4(), device_id=uuid4(),
                       operation_type="STUDENT_NOTE_CHANGED", aggregate_type="Student", aggregate_id=uuid4(),
                       payload={"note":"x"}, idempotency_key="device-1:42")
    assert op.idempotency_key
    assert FINANCE_OFFLINE_POLICY["final_cash_payment_allowed"] is True
    assert FINANCE_OFFLINE_POLICY["default_enabled"] is False
