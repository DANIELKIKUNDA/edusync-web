from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock
from typing import Iterator
from uuid import UUID

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import Connection


@dataclass
class DatabaseRuntime:
    """Dedicated lazy SQLAlchemy engine for one database role.

    WEB-0C uses separate credentials for Atelier Pro and tenant traffic. Keeping the
    engine lazy also lets health/configuration tests run without a PostgreSQL driver;
    the production container still installs psycopg before any database transaction.
    """

    url: str
    role_kind: str
    _engine: Engine | None = field(default=None, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    @classmethod
    def from_url(cls, url: str, *, role_kind: str) -> "DatabaseRuntime":
        return cls(url=url, role_kind=role_kind)

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            with self._lock:
                if self._engine is None:
                    self._engine = create_engine(
                        self.url,
                        pool_pre_ping=True,
                        pool_recycle=1800,
                        future=True,
                    )
        return self._engine

    @contextmanager
    def platform_transaction(self) -> Iterator[Connection]:
        if self.role_kind != "platform":
            raise PermissionError("Ce pool PostgreSQL n'est pas autorisé pour Atelier Pro")
        with self.engine.begin() as conn:
            yield conn

    @contextmanager
    def tenant_transaction(self, *, school_id: UUID, user_id: UUID | None = None) -> Iterator[Connection]:
        if self.role_kind != "tenant":
            raise PermissionError("Ce pool PostgreSQL n'est pas le pool tenant")
        if school_id is None:
            raise ValueError("school_id obligatoire pour une transaction tenant")
        with self.engine.begin() as conn:
            # Canonical tenant context is app.current_school_id.  Some historical
            # migrations (finance/effectifs/intendance/communications) still use the
            # legacy alias app.school_id in their FORCE RLS policies.  Set both in the
            # same transaction until those policies are normalized by a future live
            # PostgreSQL migration; otherwise those tables fail closed for legitimate
            # tenant requests.
            conn.execute(
                text("SELECT set_config('app.current_school_id', :sid, true), "
                     "set_config('app.school_id', :sid, true)"),
                {"sid": str(school_id)},
            )
            if user_id is not None:
                conn.execute(
                    text("SELECT set_config('app.current_user_id', :uid, true)"),
                    {"uid": str(user_id)},
                )
            yield conn

    @contextmanager
    def transaction(self, *, school_id: UUID | None = None, platform: bool = False,
                    user_id: UUID | None = None) -> Iterator[Connection]:
        if platform:
            with self.platform_transaction() as conn:
                yield conn
            return
        if school_id is None:
            raise ValueError("school_id obligatoire pour une transaction tenant")
        with self.tenant_transaction(school_id=school_id, user_id=user_id) as conn:
            yield conn
