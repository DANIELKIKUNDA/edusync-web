"""First V2 route (lot 0): proves the module gate end to end. The V2 screens read it to know the state of the module.

GET /api/v1/pedagogy/overview — any member of a school that HAS the pedagogy module; 403 MODULE_NOT_ACTIVE otherwise.
The referential (lot 1) and the rest of the V2 come behind the same gate.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from edusync.modules.school_modules.api.guard import require_pedagogy
from edusync.modules.school_modules.domain.catalog import PEDAGOGY
from edusync.shared.application.context import ActorContext

router = APIRouter(tags=["Pédagogie (V2)"])


@router.get("/overview")
def pedagogy_overview(actor: ActorContext = Depends(require_pedagogy)):
    return {"module": PEDAGOGY, "active": True, "school_id": str(actor.school_id), "referential": None}
