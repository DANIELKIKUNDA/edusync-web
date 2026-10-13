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
from edusync.bootstrap.dependencies import get_services, platform_account_suspended, require_platform_actor, require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.shared.application.context import ActorContext
from edusync.modules.platform.domain.school import SchoolStatus
from edusync.shared.infrastructure.security import create_access_token, verify_password, hash_password
from edusync.shared.infrastructure.login_guard import LoginAttemptGuard
from sqlalchemy import text
from datetime import datetime, timezone
from edusync.shared.infrastructure.persistent_sessions import new_session_token, hash_token, hash_user_agent, describe_user_agent
from edusync.modules.iam.application import platform_mfa
from edusync.shared.infrastructure.mfa import DIGITS as MFA_DIGITS, ISSUER as MFA_ISSUER, STEP_SECONDS as MFA_PERIOD

router = APIRouter(tags=["Authentification"])
# Unknown accounts still pay one Argon2 verification so response time does not reveal which emails exist.
_DUMMY_PASSWORD_HASH = hash_password(new_session_token()[0])


def _set_session_cookie(response: Response, services: AppServices, raw: str, expires_at: datetime | None) -> None:
    """Opaque device-session cookie: HttpOnly, SameSite=Lax, limited to /api/v1/auth. Re-issued at every renewal, so an
    approved device stays signed in; never beyond a server-side expiry when the owner configures one."""
    max_age = services.settings.session_cookie_max_age_days * 86400
    if expires_at is not None:
        max_age = min(max_age, max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds())))
    response.set_cookie(services.settings.persistent_session_cookie, raw, max_age=max_age, httponly=True, secure=services.settings.env.lower() in {"prod","production"}, samesite="lax", path="/api/v1/auth")


def _new_device_session(conn, settings, *, user, school=None, membership=None, user_agent: str = "", mfa_method: str | None = None) -> tuple[str, str, datetime]:
    raw_session, session_hash = new_session_token()
    row = conn.execute(text("""INSERT INTO user_device_sessions(user_id,school_id,membership_id,token_hash,label,user_agent_hash,user_version,membership_version,expires_at,mfa_verified_at,mfa_method)
        VALUES(:uid,:sid,:mid,:th,:label,:uah,:uv,:mv,CASE WHEN :days>0 THEN now()+make_interval(days=>:days) END,
               CASE WHEN CAST(:mfa AS text) IS NOT NULL THEN now() END,:mfa) RETURNING id,expires_at"""), {
        "uid": str(user.id), "sid": str(school.id) if school else None, "mid": str(membership.id) if membership else None,
        "th": session_hash, "label": describe_user_agent(user_agent), "uah": hash_user_agent(user_agent), "uv": user.version,
        "mv": membership.version if membership else None, "days": settings.session_absolute_days, "mfa": mfa_method}).one()
    return raw_session, str(row[0]), row[1]


def _issue_platform_session(conn, services: AppServices, request: Request, response: Response, user, *, mfa_method: str | None) -> dict:
    """Platform device session + access token. Reached only after the password and, under option B, the second factor."""
    raw_session, session_id, session_expires = _new_device_session(conn, services.settings, user=user, user_agent=request.headers.get("user-agent", ""), mfa_method=mfa_method)
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


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=512)
    # AUTO: the context is derived from the account after authentication (no school code to type).
    scope: Literal["AUTO", "PLATFORM", "SCHOOL"] = "AUTO"
    school_code: str | None = Field(default=None, max_length=32)


def _login_contexts(conn, user_id) -> list[dict]:
    """Every context this account may open: active memberships of active schools, plus the platform console."""
    rows = conn.execute(text("""SELECT s.code, s.name FROM school_memberships m JOIN schools s ON s.id=m.school_id
        WHERE m.user_id=:u AND m.active AND s.status='ACTIVE' ORDER BY s.name"""), {"u": str(user_id)}).mappings().all()
    out = [{"scope": "SCHOOL", "school_code": r["code"], "label": r["name"]} for r in rows]
    platform = conn.execute(text("""SELECT 1 FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id
        WHERE a.user_id=:u AND a.school_id IS NULL AND a.active AND r.level='PLATFORM' AND r.status='ACTIVE'
          AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now()) LIMIT 1"""), {"u": str(user_id)}).first()
    if platform and not platform_account_suspended(conn, user_id):
        out.append({"scope": "PLATFORM", "school_code": None, "label": "Atelier Pro — administration de la plateforme"})
    return out


def _assert_same_origin(request: Request, services: AppServices) -> None:
    """CSRF defence for cookie-authenticated endpoints (refresh, logout, logout-all, login): a browser always sends
    Origin on POST; a foreign origin is refused. SameSite=Lax is the first layer, this is the second."""
    origin = request.headers.get("origin")
    if not origin:
        if request.headers.get("sec-fetch-site", "same-origin") not in {"same-origin", "same-site", "none"}:
            raise HTTPException(403, "Origine refusée")
        return
    host = request.headers.get("host", "")
    allowed = set(services.settings.cors_origin_list) | {f"http://{host}", f"https://{host}"}
    if origin not in allowed:
        raise HTTPException(403, "Origine refusée")


@router.post("/login")
def login(body: LoginInput, request: Request, response: Response, services: AppServices = Depends(get_services)):
    _assert_same_origin(request, services)
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

        if body.scope == "AUTO":
            contexts = _login_contexts(conn, user.id)
            if not contexts:
                raise HTTPException(status_code=403, detail="Connexion impossible")
            if len(contexts) > 1:
                # No session yet: the client asks the user which space to open, then signs in with that choice.
                return {"choice_required": True, "contexts": contexts}
            body = body.model_copy(update={"scope": contexts[0]["scope"], "school_code": contexts[0]["school_code"]})

        if body.scope == "PLATFORM":
            authz = PostgresAuthorizationRepository(conn)
            assignments = authz.effective_role_assignments(user.id, None)
            roles = authz.roles({a.role_id for a in assignments})
            if not any(r.level.value == 'PLATFORM' and r.status.value == 'ACTIVE' for r in roles.values()) or platform_account_suspended(conn, user.id):
                raise HTTPException(status_code=403, detail="Connexion impossible")
            if platform_mfa.mfa_needed(conn, services.settings, user.id):
                # Option B: no session, no cookie, no access token before the second factor. The client receives an
                # opaque single-use step token, valid a few minutes, that only the /auth/mfa/* routes accept.
                purpose = "LOGIN" if platform_mfa.active_factor(conn, user.id) else "ENROLL"
                step_token = platform_mfa.create_challenge(conn, services.settings, user_id=user.id, user_version=user.version, purpose=purpose)
                return {"mfa_required": purpose == "LOGIN", "mfa_enrollment_required": purpose == "ENROLL", "mfa_token": step_token,
                        "expires_in": services.settings.mfa_challenge_seconds, "scope": "PLATFORM",
                        "methods": ["TOTP", "RECOVERY_CODE"] if purpose == "LOGIN" else ["TOTP"]}
            return _issue_platform_session(conn, services, request, response, user, mfa_method=None)

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


# ---------------------------------------------------------------- second factor (option B, platform accounts)

class MfaStepInput(BaseModel):
    mfa_token: str = Field(min_length=20, max_length=128)


class MfaVerifyInput(MfaStepInput):
    code: str | None = Field(default=None, max_length=16)
    recovery_code: str | None = Field(default=None, max_length=32)


class MfaConfirmInput(MfaStepInput):
    code: str = Field(min_length=6, max_length=16)


class MfaReauthInput(BaseModel):
    code: str = Field(min_length=6, max_length=16)


_MFA_EXPIRED = "Vérification expirée : reconnectez-vous."
_MFA_WRONG = "Code de vérification incorrect. Vérifiez l’heure de votre téléphone, puis saisissez le nouveau code."
_MFA_LOCKED = "Trop de codes incorrects. Pour votre sécurité, réessayez dans quelques minutes."


def _mfa_guard(services: AppServices) -> LoginAttemptGuard:
    s = services.settings
    return LoginAttemptGuard(s.redis_url, window_seconds=s.mfa_lock_seconds, max_attempts=s.mfa_max_attempts, lock_seconds=s.mfa_lock_seconds, namespace="mfa")


def _platform_access_ok(conn, user_id) -> bool:
    """The account may still open the console (role not revoked, account not suspended since the password step)."""
    return bool(conn.execute(text("""SELECT 1 FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id
        WHERE a.user_id=:u AND a.school_id IS NULL AND a.active AND r.level='PLATFORM' AND r.status='ACTIVE'
          AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now()) LIMIT 1"""), {"u": str(user_id)}).first()) \
        and not platform_account_suspended(conn, user_id)


def _raise_mfa_outcome(outcome: tuple[str, int]) -> None:
    kind, value = outcome
    if kind == "locked":
        raise HTTPException(status_code=429, detail=_MFA_LOCKED, headers={"Retry-After": str(max(1, value))})
    if kind == "wrong" and value > 0:
        raise HTTPException(status_code=400, detail=_MFA_WRONG)
    raise HTTPException(status_code=401, detail=_MFA_EXPIRED)


@router.post("/mfa/verify")
def mfa_verify(body: MfaVerifyInput, request: Request, response: Response, services: AppServices = Depends(get_services)):
    """Second step of a platform sign-in: a TOTP code or a single-use recovery code creates the device session."""
    _assert_same_origin(request, services)
    response.headers["Cache-Control"] = "no-store"
    if bool((body.code or "").strip()) == bool((body.recovery_code or "").strip()):
        raise HTTPException(status_code=422, detail="Saisissez soit le code à 6 chiffres, soit un code de secours.")
    ip = request.client.host if request.client else "unknown"
    cipher = platform_mfa.cipher_for(services.settings)
    method = "TOTP" if (body.code or "").strip() else "RECOVERY_CODE"
    outcome = ("expired", 0)
    # Failures are written in this transaction, which commits before the refusal is answered.
    with services.platform_db.platform_transaction() as conn:
        challenge = platform_mfa.load_challenge(conn, services.settings, body.mfa_token, "LOGIN")
        if challenge is not None and _platform_access_ok(conn, challenge.user_id):
            guard = _mfa_guard(services)
            decision = guard.check(str(challenge.user_id), ip)
            if not decision.allowed:
                platform_mfa.security_audit(conn, user_id=challenge.user_id, action="MFA_LOCKED", detail={"method": method}, rejected=True)
                outcome = ("locked", decision.retry_after)
            else:
                user = PostgresUserRepository(conn).get(challenge.user_id)
                remaining = None
                if method == "TOTP":
                    ok = platform_mfa.verify_totp(conn, cipher, user_id=user.id, code=body.code or "")
                else:
                    remaining = platform_mfa.use_recovery_code(conn, user_id=user.id, code=body.recovery_code or "")
                    ok = remaining is not None
                if ok:
                    guard.success(str(user.id), ip)
                    platform_mfa.consume_challenge(conn, challenge)
                    platform_mfa.security_audit(conn, user_id=user.id, action="MFA_RECOVERY_CODE_USED" if remaining is not None else "MFA_VERIFIED",
                                                detail={"method": method, **({"recovery_codes_remaining": remaining} if remaining is not None else {})})
                    result = _issue_platform_session(conn, services, request, response, user, mfa_method=method)
                    if remaining is not None:
                        result["recovery_codes_remaining"] = remaining
                    return result
                guard.failure(str(user.id), ip)
                left = max(0, services.settings.mfa_max_attempts - platform_mfa.record_failed_attempt(conn, challenge))
                platform_mfa.security_audit(conn, user_id=user.id, action="MFA_FAILED", detail={"method": method, "attempts_left": left}, rejected=True)
                outcome = ("wrong", left)
    _raise_mfa_outcome(outcome)


@router.post("/mfa/enroll/start")
def mfa_enroll_start(body: MfaStepInput, request: Request, response: Response, services: AppServices = Depends(get_services)):
    """Mandatory enrolment of a platform account without a factor: new secret, QR code and manual key (shown once)."""
    _assert_same_origin(request, services)
    response.headers["Cache-Control"] = "no-store"
    cipher = platform_mfa.cipher_for(services.settings)
    with services.platform_db.platform_transaction() as conn:
        challenge = platform_mfa.load_challenge(conn, services.settings, body.mfa_token, "ENROLL")
        if challenge is None or not _platform_access_ok(conn, challenge.user_id):
            raise HTTPException(status_code=401, detail=_MFA_EXPIRED)
        user = PostgresUserRepository(conn).get(challenge.user_id)
        try:
            data = platform_mfa.start_enrollment(conn, cipher, user_id=user.id, account=user.email)
        except ValueError:
            raise HTTPException(status_code=409, detail="La validation en deux étapes est déjà configurée : reconnectez-vous.")
        platform_mfa.security_audit(conn, user_id=user.id, action="MFA_ENROLLMENT_STARTED")
    return {**data, "account": user.email, "issuer": MFA_ISSUER, "digits": MFA_DIGITS, "period": MFA_PERIOD}


@router.post("/mfa/enroll/confirm")
def mfa_enroll_confirm(body: MfaConfirmInput, request: Request, response: Response, services: AppServices = Depends(get_services)):
    """First valid code activates the factor, returns the recovery codes once and opens the session."""
    _assert_same_origin(request, services)
    response.headers["Cache-Control"] = "no-store"
    ip = request.client.host if request.client else "unknown"
    cipher = platform_mfa.cipher_for(services.settings)
    outcome = ("expired", 0)
    with services.platform_db.platform_transaction() as conn:
        challenge = platform_mfa.load_challenge(conn, services.settings, body.mfa_token, "ENROLL")
        if challenge is not None and _platform_access_ok(conn, challenge.user_id):
            guard = _mfa_guard(services)
            decision = guard.check(str(challenge.user_id), ip)
            if not decision.allowed:
                outcome = ("locked", decision.retry_after)
            else:
                user = PostgresUserRepository(conn).get(challenge.user_id)
                codes = platform_mfa.confirm_enrollment(conn, cipher, user_id=user.id, code=body.code)
                if codes:
                    guard.success(str(user.id), ip)
                    platform_mfa.consume_challenge(conn, challenge)
                    platform_mfa.security_audit(conn, user_id=user.id, action="MFA_ENROLLED", detail={"method": "TOTP", "recovery_codes": len(codes)})
                    result = _issue_platform_session(conn, services, request, response, user, mfa_method="TOTP")
                    result["recovery_codes"] = codes
                    return result
                guard.failure(str(user.id), ip)
                left = max(0, services.settings.mfa_max_attempts - platform_mfa.record_failed_attempt(conn, challenge))
                platform_mfa.security_audit(conn, user_id=user.id, action="MFA_FAILED", detail={"method": "TOTP", "stage": "ENROLMENT", "attempts_left": left}, rejected=True)
                outcome = ("wrong", left)
    _raise_mfa_outcome(outcome)


@router.get("/platform/mfa")
def platform_mfa_status(actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    """Second-factor status of the signed-in platform account. Disabling it oneself is never offered (policy)."""
    with services.platform_db.platform_transaction() as conn:
        state = platform_mfa.status(conn, actor.user_id)
    return {**state, "required": bool(services.settings.mfa_platform_required), "self_disable_allowed": False}


@router.post("/platform/mfa/recovery-codes")
def platform_mfa_regenerate(body: MfaReauthInput, request: Request, response: Response, actor: ActorContext = Depends(require_platform_actor),
                            services: AppServices = Depends(get_services)):
    """New recovery codes (the previous ones stop working), after a fresh TOTP code: a stolen session alone cannot do it."""
    response.headers["Cache-Control"] = "no-store"
    ip = request.client.host if request.client else "unknown"
    cipher = platform_mfa.cipher_for(services.settings)
    guard = _mfa_guard(services)
    decision = guard.check(str(actor.user_id), ip)
    if not decision.allowed:
        raise HTTPException(status_code=429, detail=_MFA_LOCKED, headers={"Retry-After": str(max(1, decision.retry_after))})
    with services.platform_db.platform_transaction() as conn:
        if platform_mfa.verify_totp(conn, cipher, user_id=actor.user_id, code=body.code):
            codes = platform_mfa.regenerate_recovery_codes(conn, user_id=actor.user_id)
            guard.success(str(actor.user_id), ip)
            platform_mfa.security_audit(conn, user_id=actor.user_id, action="MFA_RECOVERY_CODES_REGENERATED", detail={"recovery_codes": len(codes or [])})
            return {"recovery_codes": codes}
        guard.failure(str(actor.user_id), ip)
        platform_mfa.security_audit(conn, user_id=actor.user_id, action="MFA_FAILED", detail={"method": "TOTP", "stage": "RECOVERY_CODES"}, rejected=True)
    raise HTTPException(status_code=400, detail=_MFA_WRONG)


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

def _security_audit(conn, *, user_id, action: str, school_id=None, detail: dict | None = None) -> None:
    """Security events of an account (password, sessions) are audited like any sensitive operation."""
    import json as _json
    conn.execute(text("""INSERT INTO audit_events(school_id,actor_user_id,action,entity_type,entity_id,source,new_json)
        VALUES(:sid,:uid,:a,'UserSecurity',:uid,'WEB',CAST(:d AS jsonb))"""),
        {"sid": str(school_id) if school_id else None, "uid": str(user_id), "a": action, "d": _json.dumps(detail or {})})


def _change_password(services: AppServices, user_id, body: "PasswordChangeInput", school_id=None) -> dict:
    if body.current_password == body.new_password:
        raise HTTPException(status_code=422, detail="Le nouveau mot de passe doit être différent")
    with services.platform_db.platform_transaction() as conn:
        user = PostgresUserRepository(conn).get(user_id)
        if user is None or not user.active or not verify_password(body.current_password, user.password_hash):
            raise HTTPException(status_code=400, detail="Modification impossible")
        encoded = hash_password(body.new_password)
        result = conn.execute(text("UPDATE users SET password_hash=:password_hash, version=version+1 WHERE id=:user_id AND version=:version"), {"password_hash": encoded, "user_id": user_id, "version": user.version})
        n = conn.execute(text("UPDATE user_device_sessions SET revoked_at=coalesce(revoked_at,now()),revoked_reason='PASSWORD_CHANGED' WHERE user_id=:uid AND revoked_at IS NULL"), {'uid': user_id}).rowcount
        conn.execute(text("UPDATE push_subscriptions SET revoked_at=now(),revoked_reason='PASSWORD_CHANGED' WHERE user_id=:uid AND revoked_at IS NULL"), {'uid': user_id})
        if result.rowcount != 1:
            raise HTTPException(status_code=409, detail="Compte modifié; reconnectez-vous")
        _security_audit(conn, user_id=user_id, action="PASSWORD_CHANGED", school_id=school_id, detail={"sessions_revoked": n})
    return {"status": "changed", "sessions_invalidated": True}


@router.post("/platform/password")
def change_platform_password(body: PasswordChangeInput, actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    """Platform accounts change their own password with the same guarantees as school accounts."""
    return _change_password(services, actor.user_id, body)


@router.post("/password")
def change_password(body: PasswordChangeInput, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    return _change_password(services, actor.user_id, body, actor.school_id)


@router.post('/refresh')
def refresh_session(request:Request,response:Response,services:AppServices=Depends(get_services)):
    _assert_same_origin(request, services)
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
              -- optional owner policies (disabled by default: no periodic re-authentication)
              OR (token_hash=:th AND (expires_at<=now() OR (:idle>0 AND last_seen_at<=now()-make_interval(days=>:idle)))))
            RETURNING id"""),{'th':th,'idle':cfg.session_idle_days}).first()
    if revoked:
        denied=JSONResponse(status_code=401,content={'detail':'Session à renouveler'})
        denied.delete_cookie(cfg.persistent_session_cookie,path='/api/v1/auth')
        return denied
    with services.platform_db.platform_transaction() as conn:
        row=conn.execute(text("""SELECT s.*,u.active,u.version current_user_version,u.is_platform_admin,(s.token_hash=:th) current_token
            FROM user_device_sessions s JOIN users u ON u.id=s.user_id
            WHERE s.revoked_at IS NULL AND (s.expires_at IS NULL OR s.expires_at>now()) AND (s.token_hash=:th OR (s.previous_token_hash=:th AND s.previous_valid_until>now())) FOR UPDATE OF s"""),{'th':th}).mappings().first()
        if not row: raise HTTPException(401,'Session à renouveler')
        if not row['active'] or int(row['user_version'])!=int(row['current_user_version']): raise HTTPException(401,'Session à renouveler')
        claims={'scope':'platform','user_version':row['current_user_version'],'sid':str(row['id'])}
        if row['school_id']:
            m=conn.execute(text("SELECT active,version FROM school_memberships WHERE id=:id AND user_id=:uid AND school_id=:sid"),{'id':row['membership_id'],'uid':row['user_id'],'sid':row['school_id']}).mappings().first()
            if not m or not m['active'] or int(row['membership_version'] or 0)!=int(m['version']): raise HTTPException(401,'Session à renouveler')
            # A suspended school gets no new token (the API would refuse it anyway): back to the sign-in screen.
            if conn.execute(text("SELECT status FROM schools WHERE id=:sid"),{'sid':row['school_id']}).scalar_one_or_none()!='ACTIVE': raise HTTPException(401,'Session à renouveler')
            claims.update({'scope':'school','school_id':str(row['school_id']),'membership_id':str(row['membership_id']),'membership_version':m['version']})
        elif not conn.execute(text("SELECT 1 FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id WHERE a.user_id=:uid AND a.school_id IS NULL AND a.active=true AND r.level='PLATFORM' AND r.status='ACTIVE' AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now()) LIMIT 1"),{'uid':row['user_id']}).first() or platform_account_suspended(conn,row['user_id']): raise HTTPException(401,'Session à renouveler')
        # Option B: a platform session opened without the second factor (before the policy, or by any bypass) is never renewed.
        elif row['mfa_verified_at'] is None and platform_mfa.mfa_needed(conn,cfg,row['user_id']): raise HTTPException(401,'Session à renouveler')
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
    _assert_same_origin(request, services)
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


@router.post('/logout-all', status_code=204)
def logout_all(request: Request, response: Response, services: AppServices = Depends(get_services)):
    """Sign out of every device of this account (cookie-authenticated, CSRF-checked, audited)."""
    _assert_same_origin(request, services)
    raw = request.cookies.get(services.settings.persistent_session_cookie)
    if not raw:
        raise HTTPException(401, 'Session à renouveler')
    th = hash_token(raw)
    with services.platform_db.platform_transaction() as conn:
        uid = conn.execute(text("SELECT user_id FROM user_device_sessions WHERE revoked_at IS NULL AND (token_hash=:th OR previous_token_hash=:th)"), {'th': th}).scalar_one_or_none()
        if uid is None:
            raise HTTPException(401, 'Session à renouveler')
        n = conn.execute(text("UPDATE user_device_sessions SET revoked_at=now(),revoked_reason='USER_LOGOUT_ALL' WHERE user_id=:u AND revoked_at IS NULL"), {'u': str(uid)}).rowcount
        conn.execute(text("UPDATE push_subscriptions SET revoked_at=now(),revoked_reason='USER_LOGOUT_ALL' WHERE user_id=:u AND revoked_at IS NULL"), {'u': str(uid)})
        _security_audit(conn, user_id=uid, action='SESSIONS_REVOKED_ALL', detail={'sessions_revoked': n})
    response.delete_cookie(services.settings.persistent_session_cookie, path='/api/v1/auth')


@router.get('/platform/sessions')
def platform_sessions(request: Request, actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    """All devices of this platform account (its platform and school sessions alike: the account owns them)."""
    raw = request.cookies.get(services.settings.persistent_session_cookie)
    th = hash_token(raw) if raw else ''
    with services.platform_db.platform_transaction() as conn:
        rows = conn.execute(text("""SELECT s.id,s.label,s.created_at,s.last_seen_at,s.revoked_at,(s.token_hash=:th OR s.previous_token_hash=:th) AS current,
              coalesce(sc.name,'Atelier Pro') AS context
            FROM user_device_sessions s LEFT JOIN schools sc ON sc.id=s.school_id
            WHERE s.user_id=:u AND s.revoked_at IS NULL ORDER BY s.last_seen_at DESC LIMIT 100"""), {'u': str(actor.user_id), 'th': th}).mappings()
        return {'items': [dict(r) for r in rows]}


@router.post('/platform/sessions/{session_id}/revoke', status_code=204)
def platform_revoke_session(session_id: UUID, actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    with services.platform_db.platform_transaction() as conn:
        n = conn.execute(text("UPDATE user_device_sessions SET revoked_at=coalesce(revoked_at,now()),revoked_reason='USER_REVOKED' WHERE id=:id AND user_id=:u AND revoked_at IS NULL"), {'id': str(session_id), 'u': str(actor.user_id)}).rowcount
        if n:
            _security_audit(conn, user_id=actor.user_id, action='SESSION_REVOKED', detail={'session_id': str(session_id)})
