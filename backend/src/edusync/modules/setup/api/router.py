"""First-run setup: create the very first Manager Système of an empty installation.

Security model (local closure 2026-10):
  * open only while platform_setup_completion is empty (singleton row = irreversible lock);
  * creation runs under a transaction-scoped advisory lock and re-checks inside it, so two concurrent
    requests can never both succeed (the primary key on the singleton is the last line of defence);
  * in dev, only a loopback client may use it without a token; anywhere else (or in staging/production)
    the one-time EDUSYNC_SETUP_TOKEN known only to the operator is mandatory;
  * once closed, every call answers 409 and the page no longer offers the form.
"""
from __future__ import annotations

import hmac
from ipaddress import ip_address

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from edusync.bootstrap.dependencies import get_services
from edusync.bootstrap.services import AppServices
from edusync.bootstrap.settings import is_protected_env
from edusync.shared.infrastructure.security import hash_password

router = APIRouter(tags=["Première installation"])
_LOCK = "edusync:platform:first-manager-setup"


def _is_loopback(request: Request) -> bool:
    host = request.client.host if request.client else ""
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return host in ("localhost", "testclient")


def _production(services: AppServices) -> bool:
    return is_protected_env(services.settings.env)


def _token_required(services: AppServices, request: Request) -> bool:
    return _production(services) or not _is_loopback(request)


def _setup_completed(conn) -> bool:
    return conn.execute(text("SELECT 1 FROM platform_setup_completion LIMIT 1")).first() is not None


@router.get("/status")
def setup_status(request: Request, services: AppServices = Depends(get_services)):
    with services.platform_db.platform_transaction() as conn:
        completed = _setup_completed(conn)
    required = _token_required(services, request)
    available = not completed and (not required or bool(services.settings.setup_token))
    return {"setup_required": not completed, "setup_available": available, "token_required": required and not completed}


class FirstManagerInput(BaseModel):
    full_name: str = Field(min_length=3, max_length=160)
    email: str = Field(min_length=5, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=12, max_length=512)
    setup_token: str | None = Field(default=None, max_length=512)


@router.post("/first-manager", status_code=201)
def create_first_manager(body: FirstManagerInput, request: Request, services: AppServices = Depends(get_services)):
    if _token_required(services, request):
        expected = services.settings.setup_token
        if not expected:
            raise HTTPException(403, "La première installation se fait par l'opérateur sur ce serveur.")
        if not hmac.compare_digest((body.setup_token or "").encode(), expected.encode()):
            raise HTTPException(403, "Code d'installation invalide.")
    email = body.email.strip().lower()
    try:
        password_hash = hash_password(body.password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        with services.platform_db.platform_transaction() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k,0))"), {"k": _LOCK})
            if _setup_completed(conn):
                raise HTTPException(409, "EduSync est déjà initialisé. Connectez-vous avec un compte existant.")
            if conn.execute(text("SELECT 1 FROM users WHERE lower(email)=:e"), {"e": email}).first():
                raise HTTPException(409, "Cette adresse e-mail est déjà utilisée.")
            role = conn.execute(text("SELECT id FROM rbac_roles WHERE code='MANAGER_SYSTEME' AND kind='PLATFORM_STANDARD' AND status='ACTIVE'")).first()
            if role is None:
                raise HTTPException(503, "Installation incomplète : le rôle Manager Système est absent.")
            user_id = conn.execute(text("""INSERT INTO users(email,full_name,password_hash,active,is_platform_admin,version)
                VALUES(:e,:n,:h,true,true,1) RETURNING id"""), {"e": email, "n": body.full_name.strip(), "h": password_hash}).scalar_one()
            aid = conn.execute(text("""INSERT INTO rbac_assignments(user_id,role_id,school_id,membership_id,active,reason)
                VALUES(:u,:r,NULL,NULL,true,'PLATFORM_FIRST_SETUP') RETURNING id"""), {"u": str(user_id), "r": role[0]}).scalar_one()
            conn.execute(text("INSERT INTO rbac_assignment_scopes(assignment_id,scope_type,scope_value) VALUES(:a,'PLATFORM',NULL)"), {"a": aid})
            conn.execute(text("INSERT INTO platform_setup_completion(singleton,manager_user_id,method) VALUES(true,:u,'SETUP_PAGE')"), {"u": str(user_id)})
            conn.execute(text("""INSERT INTO audit_events(action,entity_type,entity_id,actor_user_id,source,new_json,reason)
                VALUES('PLATFORM_FIRST_MANAGER_CREATED','User',:u,:u,'WEB',jsonb_build_object('email',CAST(:e AS text),'method','SETUP_PAGE'),'Première installation')"""),
                {"u": str(user_id), "e": email})
    except IntegrityError as exc:
        # Concurrent request lost the race on the singleton primary key.
        raise HTTPException(409, "EduSync est déjà initialisé. Connectez-vous avec un compte existant.") from exc
    return {"status": "created", "email": email}
