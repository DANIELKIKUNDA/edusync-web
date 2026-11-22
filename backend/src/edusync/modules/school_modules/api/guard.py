"""Server-side module gate (V2 lot 0). Hiding a menu is not enough (plan §2.6): every V2 route depends on
require_pedagogy, which refuses a school that does not have the module — whatever the role of the user.

    @router.get("/…")
    def view(actor: ActorContext = Depends(require_pedagogy)): …
"""
from __future__ import annotations

from fastapi import Depends, HTTPException

from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.modules.school_modules.application.service import active_codes, has_module
from edusync.modules.school_modules.domain.catalog import NOT_ACTIVE_MESSAGE, PEDAGOGY
from edusync.shared.application.context import ActorContext

MODULE_NOT_ACTIVE = "MODULE_NOT_ACTIVE"


def school_has_module(services: AppServices, school_id, code: str) -> bool:
    with services.platform_db.platform_transaction() as conn:       # the tenant role cannot read the commercial tables
        return has_module(conn, school_id, code)


def school_module_codes(services: AppServices, school_id) -> list[str]:
    """For /access/me: never breaks the session — on error the school simply shows no V2 entry."""
    try:
        with services.platform_db.platform_transaction() as conn:
            return sorted(active_codes(conn, school_id))
    except Exception:  # noqa: BLE001
        return []


def require_module(code: str):
    def dependency(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)) -> ActorContext:
        if actor.school_id is None or not school_has_module(services, actor.school_id, code):
            raise HTTPException(403, {"code": MODULE_NOT_ACTIVE, "module": code,
                                      "message": NOT_ACTIVE_MESSAGE.get(code, "Module non activé pour cette école.")})
        return actor
    return dependency


require_pedagogy = require_module(PEDAGOGY)
