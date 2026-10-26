from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID

from edusync.modules.documents.api.router import document_history


class Rows:
    def __init__(self, rows):
        self.rows = rows
    def mappings(self):
        return self
    def all(self):
        return self.rows


class Connection:
    def __init__(self):
        self.calls = []
    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return Rows([])


class DB:
    def __init__(self, conn):
        self.conn = conn
    @contextmanager
    def tenant_transaction(self, **_):
        yield self.conn


def test_personal_and_school_document_views_keep_tenant_and_permission_filters():
    conn = Connection()
    school = UUID("00000000-0000-0000-0000-000000000001")
    user = UUID("00000000-0000-0000-0000-000000000002")
    actor = SimpleNamespace(school_id=school, user_id=user,
        permissions=frozenset({"documents.history.read", "finance.reports.periodic.generate"}),
        require=lambda _: None, scopes_for=lambda _: [("SCHOOL", None)])
    services = SimpleNamespace(tenant_db=DB(conn), object_storage=None)
    mine = document_history(offset=0, limit=50, scope="mine", actor=actor, services=services)
    school_view = document_history(offset=0, limit=50, scope="school", actor=actor, services=services)
    personal_sql, personal_params = conn.calls[0]
    school_sql, school_params = conn.calls[1]
    assert "FROM generated_documents g" in personal_sql
    assert "g.school_id=:s AND g.generated_by=:u" in personal_sql
    assert personal_params["s"] == str(school) and personal_params["u"] == str(user)
    assert "FROM current_documents c" in school_sql
    assert "g.required_capability=ANY" in school_sql
    assert "finance.reports.periodic.generate" in school_params["caps"]
    assert mine["items"] == school_view["items"] == []
