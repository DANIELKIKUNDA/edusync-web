"""First V2 route (lot 0): proves the module gate end to end. The V2 screens read it to know the state of the module.

GET /api/v1/pedagogy/overview — any member of a school that HAS the pedagogy module; 403 MODULE_NOT_ACTIVE otherwise.
Lot 1: also returns the version of the official referential loaded (None before the first provisioning).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text

from edusync.bootstrap.dependencies import get_services
from edusync.bootstrap.services import AppServices
from edusync.modules.school_modules.api.guard import require_pedagogy
from edusync.modules.school_modules.domain.catalog import PEDAGOGY
from edusync.shared.application.context import ActorContext

router = APIRouter(tags=["Pédagogie (V2)"])


@router.get("/overview")
def pedagogy_overview(actor: ActorContext = Depends(require_pedagogy), services: AppServices = Depends(get_services)):
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        version = conn.execute(text("SELECT code FROM ref_programme_versions ORDER BY loaded_at DESC LIMIT 1")).scalar()
    return {"module": PEDAGOGY, "active": True, "school_id": str(actor.school_id), "referential": version}
