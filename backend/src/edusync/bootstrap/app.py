from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from edusync.shared.application.context import CapabilityDenied
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from edusync.bootstrap.services import AppServices
from edusync.bootstrap.settings import Settings
from edusync.modules.iam.api.router import router as auth_router
from edusync.modules.platform.api.router import router as platform_router
from edusync.modules.platform_team.api.router import router as platform_team_router
from edusync.modules.platform_health.api.router import router as platform_health_router
from edusync.modules.platform_audit.api.router import router as platform_audit_router
from edusync.modules.notifications_center.api.router import router as notifications_center_router
from edusync.modules.personnel.api.router import router as personnel_router
from edusync.modules.settings.api.router import router as settings_router
from edusync.modules.schooling.api.router import router as schooling_router
from edusync.modules.effectifs.api.router import router as effectifs_router
from edusync.modules.documents.api.router import router as documents_router
from edusync.modules.finance_checkout.api.router import router as finance_checkout_router
from edusync.modules.finance_recovery.api.router import router as finance_recovery_router
from edusync.modules.finance_cash.api.router import router as finance_cash_router
from edusync.modules.finance_reports.api.router import router as finance_reports_router
from edusync.modules.finance_controls.api.router import router as finance_controls_router
from edusync.modules.finance_fee_tracking.api.router import router as finance_fee_tracking_router
from edusync.modules.stewardship.api.router import router as stewardship_router
from edusync.modules.audit.api.router import router as audit_router
from edusync.modules.notifications.api.router import router as notifications_router
from edusync.modules.sync.api.router import router as sync_router
from edusync.modules.communications.api.router import router as communications_router
from edusync.modules.migration_import.api.router import router as migration_import_router
from edusync.modules.access.api.router import router as access_router
from edusync.modules.setup.api.router import router as setup_router
from edusync.shared.infrastructure.observability import CorrelationLoggingMiddleware, configure_logging
from edusync.shared.infrastructure.security_headers import SecurityHeadersMiddleware
from edusync.shared.infrastructure.api_guard import ApiGuardMiddleware
from edusync.shared.infrastructure.rate_limit import RateLimitMiddleware


def _exact_decimal_json() -> None:
    """Money is exact end to end: every Decimal leaves the API as a plain decimal string ("50000.00"),
    never a binary float. Applies to all routes returning dicts or models."""
    from decimal import Decimal
    from fastapi import encoders
    encoders.ENCODERS_BY_TYPE[Decimal] = lambda d: format(d, 'f')


def create_app(*, settings: Settings | None = None, services: AppServices | None = None) -> FastAPI:
    _exact_decimal_json()
    cfg = settings or Settings()
    configure_logging()
    app = FastAPI(title="EduSync Web API", version="0.52.0-point17-environment-closure")
    app.state.services = services or AppServices.build(cfg)
    from edusync.modules.documents.application.object_store import configure_storage
    configure_storage(getattr(app.state.services, "object_storage", None))
    # Resilience (N0/N1 hardening): an unavailable dependency is a 503 the client can retry, never a 500,
    # and the operator message names the component without leaking technical details.
    from sqlalchemy.exc import InterfaceError as _DbInterfaceError, OperationalError as _DbOperationalError
    from edusync.shared.infrastructure.object_storage import ObjectStorageError

    @app.exception_handler(_DbOperationalError)
    @app.exception_handler(_DbInterfaceError)
    async def database_unavailable_handler(request, exc):
        return JSONResponse(status_code=503, headers={"Retry-After": "5"},
                            content={"detail": "Service momentanément indisponible (base de données). Réessayez dans un instant."})

    @app.exception_handler(ObjectStorageError)
    async def storage_unavailable_handler(request, exc):
        return JSONResponse(status_code=503, headers={"Retry-After": "10"},
                            content={"detail": "Stockage des documents momentanément indisponible. Réessayez dans un instant."})

    @app.exception_handler(CapabilityDenied)
    async def capability_denied_handler(request, exc):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(ApiGuardMiddleware, max_body_bytes=cfg.api_max_body_bytes, max_query_bytes=cfg.api_max_query_bytes)
    app.add_middleware(CorrelationLoggingMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=cfg.trusted_host_list)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "If-Match", "X-Device-Id"],
        expose_headers=["Idempotent-Replayed", "ETag", "X-Correlation-ID"],
    )

    @app.on_event("startup")
    def warm_up_database_pools() -> None:
        """Open the tenant/platform pools before the first user request, so the first login after a deploy
        or restart is not slowed by connection setup. Best effort: the API still starts if PostgreSQL is down."""
        from sqlalchemy import text as _sql
        for runtime in (getattr(app.state.services, "tenant_db", None), getattr(app.state.services, "platform_db", None)):
            try:
                with runtime.engine.connect() as conn:
                    conn.execute(_sql("SELECT 1"))
            except Exception:  # noqa: BLE001 — warm-up must never prevent startup
                pass

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        # POINT-5-DOCUMENTS-EXPORTS extends the certified Point 4D baseline without invalidating its health contract.
        return {"status": "ok", "lot": "POINT-4D-EFFECTIFS-DEPOTS"}

    app.include_router(auth_router, prefix="/api/v1/auth")
    app.include_router(platform_team_router, prefix="/api/v1/platform/team")
    app.include_router(platform_health_router, prefix="/api/v1/platform/system")
    app.include_router(platform_audit_router, prefix="/api/v1/platform/audit-log")
    app.include_router(notifications_center_router, prefix="/api/v1")
    app.include_router(platform_router, prefix="/api/v1/platform")
    app.include_router(settings_router, prefix="/api/v1/settings")
    app.include_router(personnel_router, prefix="/api/v1/personnel")
    app.include_router(schooling_router, prefix="/api/v1/schooling")
    app.include_router(effectifs_router, prefix="/api/v1/effectifs")
    app.include_router(documents_router, prefix="/api/v1/documents")
    app.include_router(finance_checkout_router, prefix="/api/v1/finance/checkout")
    app.include_router(finance_recovery_router, prefix="/api/v1/finance/recovery")
    app.include_router(finance_cash_router, prefix="/api/v1/finance/cash")
    app.include_router(finance_reports_router, prefix="/api/v1/finance/reports")
    app.include_router(finance_controls_router, prefix="/api/v1/finance/controls")
    app.include_router(finance_fee_tracking_router, prefix="/api/v1/finance/fees")
    app.include_router(stewardship_router, prefix="/api/v1/stewardship")
    app.include_router(audit_router, prefix="/api/v1/audit")
    app.include_router(notifications_router, prefix="/api/v1/notifications")
    app.include_router(sync_router, prefix="/api/v1/sync")
    app.include_router(communications_router, prefix="/api/v1/communications")
    app.include_router(migration_import_router, prefix="/api/v1/import")
    app.include_router(access_router, prefix="/api/v1/access")
    app.include_router(setup_router, prefix="/api/v1/setup")
    return app
