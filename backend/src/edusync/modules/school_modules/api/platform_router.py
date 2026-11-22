"""Platform — modules of a school (V2 lot 0, owner 2026-11-22).

GET  /platform/schools/{id}/modules                      platform.school_modules.read
POST /platform/schools/{id}/modules/{code}/activate      platform.school_modules.manage + recent code (step-up)
POST /platform/schools/{id}/modules/{code}/withdraw      idem
Each change: motif required, Idempotency-Key, audit record. No payment involved (subscriptions paused).
"""
from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from edusync.adapters.postgres_idempotency import PostgresIdempotencyRepository
from edusync.adapters.postgres_repositories import PostgresAuditRepository
from edusync.bootstrap.dependencies import get_services, require_platform_actor, require_recent_mfa
from edusync.bootstrap.services import AppServices
from edusync.modules.audit.domain.audit import AuditRecord
from edusync.modules.school_modules.application import service
from edusync.modules.school_modules.domain.catalog import ModuleRuleError, check_activation, check_withdrawal, clean_reason
from edusync.shared.application.context import ActorContext
from edusync.shared.application.idempotency import IdempotentExecutor
from edusync.shared.domain.concurrency import IdempotencyConflict, IdempotencyInProgress

router = APIRouter(tags=["Plateforme EduSync — modules des écoles"])
READ, MANAGE = "platform.school_modules.read", "platform.school_modules.manage"


class ModuleChange(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


def _key(value: str | None) -> str:
    key = (value or "").strip()
    if not key:
        raise HTTPException(400, "En-tête Idempotency-Key obligatoire pour cette mutation")
    if len(key) > 180:
        raise HTTPException(400, "Idempotency-Key trop longue")
    return key


def _school(conn, school_id: UUID) -> dict:
    row = conn.execute(text("SELECT id,code,name,status FROM schools WHERE id=:s"), {"s": str(school_id)}).mappings().first()
    if row is None:
        raise HTTPException(404, "École introuvable")
    return dict(row)


@router.get("/schools/{school_id}/modules")
def list_school_modules(school_id: UUID, actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require(READ)
    with services.platform_db.platform_transaction() as conn:
        school = _school(conn, school_id)
        return {"school": {"id": str(school["id"]), "code": school["code"], "name": school["name"], "status": school["status"]},
                "modules": service.school_modules(conn, school_id), "can_manage": MANAGE in actor.permissions or actor.is_platform_admin}


def _change(kind: str, school_id: UUID, code: str, body: ModuleChange, response: Response, idempotency_key: str | None,
            actor: ActorContext, services: AppServices):
    key = _key(idempotency_key)
    actor.require(MANAGE)
    require_recent_mfa(services, actor, MANAGE)
    code = code.strip().upper()
    request_actor = replace(actor, correlation_id=uuid4(), idempotency_key=key)
    payload = {"school_id": str(school_id), "module": code, "kind": kind, "reason": body.reason}
    try:
        with services.platform_db.platform_transaction() as conn:
            idem = IdempotentExecutor(PostgresIdempotencyRepository(conn))

            def action():
                reason = clean_reason(body.reason)
                school = _school(conn, school_id)
                cat = service.catalogue(conn)
                active = service.active_codes(conn, school_id)
                if kind == "activate":
                    check_activation(code, known=set(cat), active=active, dependencies=cat.get(code, {}).get("dependencies", []),
                                     school_status=school["status"])
                    result = service.activate(conn, school_id, code, reason)
                else:
                    check_withdrawal(code, known=set(cat), active=active, dependents={c: m["dependencies"] for c, m in cat.items()})
                    result = service.withdraw(conn, school_id, code, reason)
                PostgresAuditRepository(conn).append(AuditRecord(
                    action="SCHOOL_MODULE_ACTIVATED" if kind == "activate" else "SCHOOL_MODULE_WITHDRAWN",
                    entity_type="SchoolModule", entity_id=UUID(result["id"]), actor_user_id=request_actor.user_id,
                    school_id=school_id, source=request_actor.source, reason=reason,
                    old_data={"module": code, "active": kind != "activate"}, new_data={"module": code, "active": kind == "activate"},
                    correlation_id=request_actor.correlation_id, idempotency_key=key))
                return 200, {"school_id": str(school_id), "module": code, "active": kind == "activate",
                             "modules": service.school_modules(conn, school_id)}

            result = idem.execute(scope_key="platform", idempotency_key=key, operation=f"PLATFORM_SCHOOL_MODULE_{kind.upper()}",
                                  payload=payload, school_id=None, actor_user_id=str(actor.user_id), action=action)
        response.headers["Idempotent-Replayed"] = "true" if result.replayed else "false"
        return result.body
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ModuleRuleError, IdempotencyConflict) as exc:
        raise HTTPException(409, str(exc)) from exc
    except IdempotencyInProgress as exc:
        raise HTTPException(409, str(exc), headers={"Retry-After": "1"}) from exc


@router.post("/schools/{school_id}/modules/{code}/activate")
def activate_school_module(school_id: UUID, code: str, body: ModuleChange, response: Response,
                           idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                           actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    return _change("activate", school_id, code, body, response, idempotency_key, actor, services)


@router.post("/schools/{school_id}/modules/{code}/withdraw")
def withdraw_school_module(school_id: UUID, code: str, body: ModuleChange, response: Response,
                           idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                           actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    return _change("withdraw", school_id, code, body, response, idempotency_key, actor, services)
