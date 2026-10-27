from uuid import uuid4

from edusync.adapters.postgres_finance_checkout import PostgresFinanceCheckoutRepository


class FakeResult:
    def __init__(self, value=None):
        self.value = value

    def mappings(self):
        return self

    def first(self):
        return self.value

    def all(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value


class FakeConnection:
    def __init__(self, enrollments, session):
        self.enrollments = enrollments
        self.session = session
        self.digests = []

    def execute(self, statement, params):
        sql = str(statement)
        if 'SELECT id,request_sha256 FROM finance_family_baskets' in sql:
            return FakeResult(None)
        if 'SELECT e.id FROM enrollments' in sql:
            return FakeResult([(enrollment,) for enrollment in self.enrollments])
        if 'SELECT id FROM finance_cash_sessions' in sql:
            return FakeResult(self.session)
        if 'INSERT INTO finance_family_baskets' in sql:
            self.digests.append(params['h'])
        return FakeResult()


def test_family_basket_passes_selected_mode_to_every_payment_and_binds_it_to_idempotency(monkeypatch):
    school, user, membership, family, first, second, session = (uuid4() for _ in range(7))
    lines = [
        {'enrollment_id': first, 'charge_ids': [uuid4()], 'amount': '50000', 'currency': 'CDF'},
        {'enrollment_id': second, 'charge_ids': [uuid4()], 'amount': '50000', 'currency': 'CDF'},
    ]
    conn = FakeConnection({str(first), str(second)}, session)
    repo = PostgresFinanceCheckoutRepository(conn)
    calls = []
    monkeypatch.setattr(repo, '_lock_idempotency_key', lambda *_: None)
    monkeypatch.setattr(repo, '_require_day_open', lambda *_: None)
    monkeypatch.setattr(repo, 'family_basket', lambda *args: {'basket_id': str(args[1]), 'lines': []})

    def collect(*args):
        calls.append(args)
        return {'id': str(uuid4()), 'amount': str(args[5]), 'currency': args[6], 'replayed': False}

    monkeypatch.setattr(repo, 'collect', collect)
    repo.family_collect(school, user, membership, family, lines, 'basket-mobile', 'MOBILE_MONEY', 'MM-1234')
    assert len(calls) == 2
    assert all(args[-2:] == ('MOBILE_MONEY', 'MM-1234') for args in calls)
    mobile_digest = conn.digests[-1]

    calls.clear()
    repo.family_collect(school, user, membership, family, lines, 'basket-cash')
    assert all(args[-2:] == ('CASH', None) for args in calls)
    assert conn.digests[-1] != mobile_digest
