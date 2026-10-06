from __future__ import annotations

from dataclasses import dataclass

from edusync.bootstrap.settings import Settings
from edusync.shared.infrastructure.object_storage import ObjectStoragePort, build_object_storage
from edusync.shared.infrastructure.postgres import DatabaseRuntime


@dataclass(frozen=True, slots=True)
class AppServices:
    settings: Settings
    tenant_db: DatabaseRuntime
    platform_db: DatabaseRuntime
    object_storage: ObjectStoragePort | None = None

    @classmethod
    def build(cls, settings: Settings) -> "AppServices":
        settings.assert_runtime_safe()
        return cls(
            settings=settings,
            tenant_db=DatabaseRuntime.from_url(settings.tenant_database_url, role_kind="tenant"),
            platform_db=DatabaseRuntime.from_url(settings.platform_database_url, role_kind="platform"),
            object_storage=build_object_storage(settings),
        )
