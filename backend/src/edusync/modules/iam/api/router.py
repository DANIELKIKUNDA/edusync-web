from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Cookie
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from edusync.adapters.postgres_authorization import PostgresAuthorizationRepository
from edusync.adapters.postgres_repositories import (
    PostgresMembershipRepository,
    PostgresSchoolRepository,
    PostgresUserRepository,
)
from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.shared.application.context import ActorContext
from edusync.modules.platform.domain.school import SchoolStatus
from edusync.shared.infrastructure.security import create_access_token, verify_password, hash_password
from edusync.shared.infrastructure.login_guard import LoginAttemptGuard
from sqlalchemy import text
from datetime import datetime, timezone
from edusync.shared.infrastructure.persistent_sessions import new_session_token, hash_token, hash_user_agent, describe_user_agent

router = APIRouter(tags=["Authentification"])
# Unknown accounts still pay one Argon2 verification so response time does not reveal which emails exist.
_DUMMY_PASSWORD_HASH = hash_password(new_session_token()[0])


def _set_session_cookie(response: Response, services: AppServices, raw: str, expires_at: datetime) -> None:
    """Opaque device-session cookie: HttpOnly, SameSite=Lax, limited to /api/v1/auth, never beyond the server-side expiry."""
    max_age = max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
    response.set_cookie(services.settings.persistent_session_cookie, raw, max_age=max_age, httponly=True, secure=services.settings.env.lower() in {"prod","production"}, samesite="lax", path="/api/v1/auth")


def _new_device_session(conn, settings, *, user, school=None, membership=None, user_agent: str = "") -> tuple[str, str, datetime]:
    raw_session, session_hash = new_session_token()
    row = conn.execute(text("""INSERT INTO user_device_sessions(user_id,school_id,membership_id,token_hash,label,user_agent_hash,user_version,membership_version,expires_at)
        VALUES(:uid,:sid,:mid,:th,:label,:uah,:uv,:mv,now()+make_interval(days=>:days)) RETURNING id,expires_at"""), {
        "uid": str(user.id), "sid": str(school.id) if school else None, "mid": str(membership.id) if membership else None,
        "th": session_hash, "label": describe_user_agent(user_agent), "uah": hash_user_agent(user_agent), "uv": user.version,
        "mv": membership.version if membership else None, "days": settings.session_absolute_days}).one()
    return raw_session, str(row[0]), row[1]


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=512)
    scope: Literal["PLATFORM", "SCHOOL"] = "SCHOOL"
    school_code: str | None = Field(default=None, max_length=32)


@router.post("/login")
def login(body: LoginInput, request: Request, response: Response, services: AppServices = Depends(get_services)):
    ip = request.client.host if request.client else "unknown"
    guard = LoginAttemptGuard(services.settings.redis_url, window_seconds=services.settings.login_window_seconds, max_attempts=services.settings.login_max_attempts, lock_seconds=services.settings.login_lock_seconds)
    decision = guard.check(body.email, ip)
    if not decision.allowed:
        raise HTTPException(status_code=429, detail="Connexion temporairement indisponible", headers={"Retry-After": str(decision.retry_after)})
    # IAM lookup is global and therefore uses the dedicated platform/IAM database role.
    with services.platform_db.platform_transaction() as conn:
        users = PostgresUserRepository(conn)
        schools = PostgresSchoolRepository(conn)
        memberships = PostgresMembershipRepository(conn)
        user = users.get_by_email(body.email)
        password_ok = verify_password(body.password, user.password_hash if user is not None else _DUMMY_PASSWORD_HASH)
        if user is None or not user.active or not password_ok:
            guard.failure(body.email, ip)
            raise HTTPException(status_code=401, detail="Connexion impossible")
        guard.success(body.email, ip)

        if body.scope == "PLATFORM":
            authz = PostgresAuthorizationRepository(conn)
            assignments = authz.effective_role_assignments(user.id, None)
            roles = authz.roles({a.role_id for a in assignments})
            if not any(r.level.value == 'PLATFORM' and r.status.value == 'ACTIVE' for r in roles.values()):
                raise HTTPException(status_code=403, detail="Connexion impossible")
            raw_session, session_id, session_expires = _new_device_session(conn, services.settings, user=user, user_agent=request.headers.get("user-agent", ""))
            # The access token is bound to its device session ("sid"), so logout/revocation is immediate.
            token = create_access_token(
                subject=str(user.id), secret=services.settings.jwt_secret,
                issuer=services.settings.jwt_issuer, audience=services.settings.jwt_audience,
                minutes=services.settings.access_token_minutes,
                claims={"scope": "platform", "user_version": user.version, "sid": str(session_id)},
            )
            _set_session_cookie(response, services, raw_session, session_expires)
            return {
                "access_token": token, "token_type": "bearer",
                "expires_in": services.settings.access_token_minutes * 60,
                "scope": "PLATFORM",
                "user": {"id": str(user.id), "email": user.email, "full_name": user.full_name},
            }

        code = (body.school_code or "").strip().upper()
        if not code:
            raise HTTPException(status_code=422, detail="school_code obligatoire pour une connexion école")
        school = schools.get_by_code(code)
        if school is None or school.status != SchoolStatus.ACTIVE:
            raise HTTPException(status_code=403, detail="Connexion impossible")
        membership = memberships.get_for_user_school(user.id, school.id)
        if membership is None or not membership.active:
            raise HTTPException(status_code=403, detail="Connexion impossible")
        permissions = memberships.permissions(membership.id)
        raw_session, session_id, session_expires = _new_device_session(conn, services.settings, user=user, school=school, membership=membership, user_agent=request.headers.get("user-agent", ""))
        token = create_access_token(
            subject=str(user.id), secret=services.settings.jwt_secret,
            issuer=services.settings.jwt_issuer, audience=services.settings.jwt_audience,
            minutes=services.settings.access_token_minutes,
            claims={
                "scope": "school",
                "school_id": str(school.id),
                "membership_id": str(membership.id),
                "user_version": user.version,
                "membership_version": membership.version,
                "sid": str(session_id),
            },
        )
        _set_session_cookie(response, services, raw_session, session_expires)
        return {
            "access_token": token, "token_type": "bearer",
            "expires_in": services.settings.access_token_minutes * 60,
            "scope": "SCHOOL",
            "user": {"id": str(user.id), "email": user.email, "full_name": user.full_name},
            "school": {"id": str(school.id), "code": school.code, "name": school.name},
            "permissions": sorted(permissions),
        }


@router.get("/me")
def me(actor: ActorContext = Depends(require_school_actor)):
    return {
        "user_id": str(actor.user_id),
        "school_id": str(actor.school_id),
        "membership_id": str(actor.membership_id),
        "permissions": sorted(actor.permissions),
    }


class PasswordChangeInput(BaseModel):
    current_password: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=10, max_length=512)

@router.post("/password")
def change_password(body: PasswordChangeInput, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    if body.current_password == body.new_password:
        raise HTTPException(status_code=422, detail="Le nouveau mot de passe doit être différent")
    # Accounts and their sessions span schools, like login/refresh. The target is
    # exclusively the authenticated actor, never a user id supplied by the client.
    # Keep tenant SQL credentials unable to update global account rows.
    with services.platform_db.platform_transaction() as conn:
        user = PostgresUserRepository(conn).get(actor.user_id)
        if user is None or not user.active or not verify_password(body.current_password, user.password_hash):
            raise HTTPException(status_code=400, detail="Modification impossible")
        encoded = hash_password(body.new_password)
        result = conn.execute(text("UPDATE users SET password_hash=:password_hash, version=version+1 WHERE id=:user_id AND version=:version"), {"password_hash": encoded, "user_id": actor.user_id, "version": user.version})
        conn.execute(text("UPDATE user_device_sessions SET revoked_at=coalesce(revoked_at,now()),revoked_reason='PASSWORD_CHANGED' WHERE user_id=:uid"),{'uid':actor.user_id})
        if result.rowcount != 1:
            raise HTTPException(status_code=409, detail="Compte modifié; reconnectez-vous")
    return {"status": "changed", "sessions_invalidated": True}


@router.post('/refresh')
def refresh_session(request:Request,response:Response,services:AppServices=Depends(get_services)):
    raw=request.cookies.get(services.settings.persistent_session_cookie)
    if not raw: raise HTTPException(401,'Session à renouveler')
    th=hash_token(raw)
    cfg=services.settings
    # Revocations must be committed before answering 401, so they are decided in their own transaction.
    with services.platform_db.platform_transaction() as conn:
        revoked=conn.execute(text("""UPDATE user_device_sessions SET revoked_at=now(),revoked_reason=CASE
              WHEN token_hash<>:th THEN 'ROTATED_TOKEN_REUSED' WHEN expires_at<=now() THEN 'ABSOLUTE_EXPIRY' ELSE 'IDLE_TIMEOUT' END
            WHERE revoked_at IS NULL AND (
              -- a rotated token replayed after its grace window: the cookie was copied, kill the whole session
              (previous_token_hash=:th AND previous_valid_until<=now())
              OR (token_hash=:th AND (expires_at<=now() OR last_seen_at<=now()-make_interval(days=>:idle))))
            RETURNING id"""),{'th':th,'idle':cfg.session_idle_days}).first()
    if revoked:
        denied=JSONResponse(status_code=401,content={'detail':'Session à renouveler'})
        denied.delete_cookie(cfg.persistent_session_cookie,path='/api/v1/auth')
        return denied
    with services.platform_db.platform_transaction() as conn:
        row=conn.execute(text("""SELECT s.*,u.active,u.version current_user_version,u.is_platform_admin,(s.token_hash=:th) current_token
            FROM user_device_sessions s JOIN users u ON u.id=s.user_id
            WHERE s.revoked_at IS NULL AND s.expires_at>now() AND (s.token_hash=:th OR (s.previous_token_hash=:th AND s.previous_valid_until>now())) FOR UPDATE OF s"""),{'th':th}).mappings().first()
        if not row: raise HTTPException(401,'Session à renouveler')
        if not row['active'] or int(row['user_version'])!=int(row['current_user_version']): raise HTTPException(401,'Session à renouveler')
        claims={'scope':'platform','user_version':row['current_user_version'],'sid':str(row['id'])}
        if row['school_id']:
            m=conn.execute(text("SELECT active,version FROM school_memberships WHERE id=:id AND user_id=:uid AND school_id=:sid"),{'id':row['membership_id'],'uid':row['user_id'],'sid':row['school_id']}).mappings().first()
            if not m or not m['active'] or int(row['membership_version'] or 0)!=int(m['version']): raise HTTPException(401,'Session à renouveler')
            claims.update({'scope':'school','school_id':str(row['school_id']),'membership_id':str(row['membership_id']),'membership_version':m['version']})
        elif not conn.execute(text("SELECT 1 FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id WHERE a.user_id=:uid AND a.school_id IS NULL AND a.active=true AND r.level='PLATFORM' AND r.status='ACTIVE' AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now()) LIMIT 1"),{'uid':row['user_id']}).first(): raise HTTPException(401,'Session à renouveler')
        token=create_access_token(subject=str(row['user_id']),secret=services.settings.jwt_secret,issuer=services.settings.jwt_issuer,audience=services.settings.jwt_audience,minutes=services.settings.access_token_minutes,claims=claims)
        if row['current_token']:
            # Rotate the opaque token; the previous one stays valid a few seconds for concurrent tabs only.
            new_raw,new_hash=new_session_token()
            conn.execute(text("""UPDATE user_device_sessions SET token_hash=:nh,previous_token_hash=:oh,previous_valid_until=now()+make_interval(secs=>:grace),
                rotated_at=now(),last_seen_at=now() WHERE id=:id"""),{'id':row['id'],'nh':new_hash,'oh':th,'grace':cfg.session_rotation_grace_seconds})
            _set_session_cookie(response, services, new_raw, row['expires_at'])
        else:
            # Concurrent tab inside the grace window: the browser already holds the rotated cookie.
            conn.execute(text("UPDATE user_device_sessions SET last_seen_at=now() WHERE id=:id"),{'id':row['id']})
        user_row=conn.execute(text("SELECT id,email,full_name FROM users WHERE id=:id"),{'id':row['user_id']}).mappings().one()
        result={'access_token':token,'token_type':'bearer','expires_in':services.settings.access_token_minutes*60,'scope':claims['scope'].upper(),'user':dict(user_row)}
        if row['school_id']:
            school_row=conn.execute(text("SELECT id,code,name FROM schools WHERE id=:id"),{'id':row['school_id']}).mappings().one()
            permissions=PostgresMembershipRepository(conn).permissions(row['membership_id'])
            result.update({'school':dict(school_row),'permissions':sorted(permissions)})
        return result

@router.post('/logout',status_code=204)
def logout(request:Request,response:Response,services:AppServices=Depends(get_services)):
    raw=request.cookies.get(services.settings.persistent_session_cookie)
    if raw:
        with services.platform_db.platform_transaction() as conn: conn.execute(text("UPDATE user_device_sessions SET revoked_at=coalesce(revoked_at,now()),revoked_reason=coalesce(revoked_reason,'USER_LOGOUT') WHERE token_hash=:th OR previous_token_hash=:th"),{'th':hash_token(raw)})
    response.delete_cookie(services.settings.persistent_session_cookie,path='/api/v1/auth')

@router.get('/sessions')
def sessions(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
        rows=c.execute(text("SELECT id,label,created_at,last_seen_at,revoked_at FROM user_device_sessions WHERE user_id=:uid AND school_id=:sid ORDER BY last_seen_at DESC"),{'uid':actor.user_id,'sid':actor.school_id}).mappings()
        return {'items':[dict(r) for r in rows]}

@router.post('/sessions/{session_id}/revoke',status_code=204)
def revoke_session(session_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
        c.execute(text("UPDATE user_device_sessions SET revoked_at=coalesce(revoked_at,now()),revoked_reason='USER_REVOKED' WHERE id=:id AND user_id=:uid AND school_id=:sid"),{'id':str(session_id),'uid':actor.user_id,'sid':actor.school_id})
