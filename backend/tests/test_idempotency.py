from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
import time

import pytest

from edusync.adapters.memory_idempotency import MemoryIdempotencyRepository
from edusync.shared.application.idempotency import IdempotentExecutor, canonical_request_hash
from edusync.shared.domain.concurrency import IdempotencyConflict, IdempotencyInProgress


def test_canonical_hash_ignores_dict_order():
    assert canonical_request_hash({"a": 1, "b": 2}) == canonical_request_hash({"b": 2, "a": 1})


def test_replay_returns_same_response_without_second_side_effect():
    repo = MemoryIdempotencyRepository()
    executor = IdempotentExecutor(repo)
    calls = 0
    def action():
        nonlocal calls
        calls += 1
        return 201, {"payment_id": "P1"}
    first = executor.execute(scope_key="school-1", idempotency_key="cash-42", operation="PAYMENT",
        payload={"amount": 100}, school_id="school-1", actor_user_id="u1", action=action)
    second = executor.execute(scope_key="school-1", idempotency_key="cash-42", operation="PAYMENT",
        payload={"amount": 100}, school_id="school-1", actor_user_id="u1", action=action)
    assert calls == 1
    assert first.replayed is False
    assert second.replayed is True
    assert second.body == {"payment_id": "P1"}


def test_same_key_different_payload_is_rejected():
    repo = MemoryIdempotencyRepository(); executor = IdempotentExecutor(repo)
    executor.execute(scope_key="school-1", idempotency_key="k", operation="PAYMENT",
        payload={"amount": 100}, school_id="school-1", actor_user_id="u1", action=lambda: (201, {"id":"x"}))
    with pytest.raises(IdempotencyConflict):
        executor.execute(scope_key="school-1", idempotency_key="k", operation="PAYMENT",
            payload={"amount": 200}, school_id="school-1", actor_user_id="u1", action=lambda: (201, {"id":"y"}))


def test_same_key_isolated_by_school_scope():
    repo = MemoryIdempotencyRepository(); executor = IdempotentExecutor(repo)
    a = executor.execute(scope_key="school-A", idempotency_key="same", operation="SAVE",
        payload={"x":1}, school_id="school-A", actor_user_id="u", action=lambda:(201,{"school":"A"}))
    b = executor.execute(scope_key="school-B", idempotency_key="same", operation="SAVE",
        payload={"x":1}, school_id="school-B", actor_user_id="u", action=lambda:(201,{"school":"B"}))
    assert a.body["school"] == "A" and b.body["school"] == "B"


def test_concurrent_duplicate_only_one_action_runs():
    repo = MemoryIdempotencyRepository(); executor = IdempotentExecutor(repo)
    barrier = Barrier(2); lock = Lock(); calls = 0
    def run():
        nonlocal calls
        barrier.wait()
        def action():
            nonlocal calls
            with lock: calls += 1
            time.sleep(0.05)
            return 201, {"ok": True}
        try:
            return executor.execute(scope_key="school", idempotency_key="simultaneous", operation="PAYMENT",
                payload={"amount": 10}, school_id="school", actor_user_id="u", action=action)
        except IdempotencyInProgress:
            return "in-progress"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [f.result() for f in [pool.submit(run), pool.submit(run)]]
    assert calls == 1
    assert "in-progress" in results


def test_failed_transactional_operation_can_retry_same_key():
    repo = MemoryIdempotencyRepository(); executor = IdempotentExecutor(repo)
    calls = 0
    def first_action():
        nonlocal calls
        calls += 1
        raise RuntimeError("transient")
    with pytest.raises(RuntimeError):
        executor.execute(scope_key="school-1", idempotency_key="retry-1", operation="SAVE",
            payload={"x":1}, school_id="school-1", actor_user_id="u", action=first_action)
    second = executor.execute(scope_key="school-1", idempotency_key="retry-1", operation="SAVE",
        payload={"x":1}, school_id="school-1", actor_user_id="u", action=lambda:(200,{"ok":True}))
    assert second.body == {"ok": True}
    assert second.replayed is False
    assert calls == 1
