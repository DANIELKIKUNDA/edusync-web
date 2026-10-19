from __future__ import annotations

from uuid import UUID, uuid4

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from edusync.adapters.postgres_authorization import PostgresAuthorizationRepository
from edusync.adapters.postgres_repositories import (
    PostgresMembershipRepository,
    PostgresSchoolRepository,
    PostgresUserRepository,
)
from edusync.bootstrap.services import AppServices
from edusync.modules.platform.domain.school import SchoolStatus
from edusync.shared.application.context import ActorContext
from edusync.shared.infrastructure.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def get_services(request: Request) -> AppServices:
    services = getattr(request.app.state, "services", None)
    if services is None:
        raise HTTPException(status_code=503, detail="Services EduSync non initialisés")
    return services


def _claims(credentials: HTTPAuthorizationCredentials | None, services: AppServices) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Jeton Bearer requis", headers={"WWW-Authenticate": "Bearer"})
    try:
        return decode_access_token(
            credentials.credentials,
            secret=services.settings.jwt_secret,
            issuer=services.settings.jwt_issuer,
            audience=services.settings.jwt_audience,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Jeton invalide ou expiré", headers={"WWW-Authenticate": "Bearer"}) from exc


def _assert_device_session_live(conn, claims: dict, user_id: UUID, *, require_mfa: bool = False) -> None:
    """Access tokens are bound to a device session: logout or device revocation is immediate. A platform token also
    needs a session that passed the second factor (option B), so an old or forged session cannot reach the console."""
    from sqlalchemy import text
    try:
        session_id = UUID(str(claims["sid"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Session du jeton invalide", headers={"WWW-Authenticate": "Bearer"}) from exc
    live = conn.execute(
        text("SELECT mfa_verified_at, mfa_required FROM user_device_sessions WHERE id=:id AND user_id=:uid AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>now())"),
        {"id": str(session_id), "uid": str(user_id)},
    ).first()
    if live is None:
        raise HTTPException(status_code=401, detail="Session révoquée; reconnectez-vous", headers={"WWW-Authenticate": "Bearer"})
    # A session that owes the second factor (platform console, or any space of an account equipped with one) is
    # refused until it has passed it.
    if (require_mfa or live[1]) and live[0] is None:
        raise HTTPException(status_code=401, detail="Validation en deux étapes requise; reconnectez-vous", headers={"WWW-Authenticate": "Bearer"})


def platform_permissions(conn, user_id: UUID) -> frozenset[str]:
    """Effective platform capabilities, recomputed on every request (no cache: a revocation counts at the next call).

    UNION(capabilities of the ACTIVE platform roles) ∪ (active, currently valid individual grants). Only ACTIVE roles of
    level PLATFORM count (a DRAFT or ARCHIVED role, standard or custom, grants nothing), only platform-scoped
    assignments (school_id NULL). An individual grant only supplements a role: without an active platform role the
    account has no platform capability at all. A set: the order of the roles never changes the result."""
    authz = PostgresAuthorizationRepository(conn)
    assignments = authz.effective_role_assignments(user_id, None)
    roles = [role for role in authz.roles({a.role_id for a in assignments}).values()
             if role.level.value == "PLATFORM" and role.status.value == "ACTIVE"]
    if not roles:
        return frozenset()
    from sqlalchemy import text as _text
    grants = conn.execute(_text("""SELECT capability_code FROM platform_capability_grants
        WHERE user_id=:u AND active AND valid_from<=now() AND (valid_until IS NULL OR valid_until>now())"""), {"u": str(user_id)}).scalars()
    return frozenset({code for role in roles for code in role.capability_codes} | set(grants))


def platform_account_suspended(conn, user_id: UUID) -> bool:
    from sqlalchemy import text as _text
    return bool(conn.execute(_text("SELECT 1 FROM platform_account_status WHERE user_id=:u AND status='SUSPENDED'"), {"u": str(user_id)}).first())


def require_platform_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    services: AppServices = Depends(get_services),
) -> ActorContext:
    claims = _claims(credentials, services)
    if claims.get("scope") != "platform":
        raise HTTPException(status_code=403, detail="Jeton de la plateforme EduSync requis")
    try:
        user_id = UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Sujet du jeton invalide") from exc
    with services.platform_db.platform_transaction() as conn:
        user = PostgresUserRepository(conn).get(user_id)
        if user is None or not user.active:
            raise HTTPException(status_code=403, detail="Accès à la plateforme EduSync révoqué", headers=SPACE_WITHDRAWN)
        if int(claims.get("user_version", 0)) != user.version:
            raise HTTPException(status_code=401, detail="Jeton de la plateforme EduSync obsolète ; reconnectez-vous")
        from edusync.modules.iam.application.platform_mfa import mfa_needed
        _assert_device_session_live(conn, claims, user_id, require_mfa=mfa_needed(conn, services.settings, user_id))
        if platform_account_suspended(conn, user_id):
            raise HTTPException(status_code=403, detail="Accès à la plateforme EduSync suspendu", headers=SPACE_WITHDRAWN)
        permissions = platform_permissions(conn, user_id)
        if not permissions:
            raise HTTPException(status_code=403, detail="Aucun rôle actif sur la plateforme EduSync", headers=SPACE_WITHDRAWN)
    return ActorContext(
        user_id=user_id,
        school_id=None,
        membership_id=None,
        permissions=permissions,
        is_platform_admin=False,
        correlation_id=uuid4(),
        source="WEB",
        session_id=UUID(str(claims["sid"])),
    )


# The space of the token was withdrawn (role, suspension, membership, school): the client offers the other spaces of
# the identity instead of a generic error (change of space without signing out, lot 2026-10).
SPACE_WITHDRAWN = {"X-EduSync-Space": "WITHDRAWN"}

STEP_UP_DETAIL = {"code": "MFA_STEP_UP_REQUIRED", "message": "Confirmez avec votre code de vérification pour effectuer cette action."}


def require_recent_mfa(services: AppServices, actor: ActorContext, capability: str | None = None) -> None:
    """Step-up (owner decision 2026-10-13): a sensitive platform action needs a code confirmed on this device within
    EDUSYNC_MFA_STEPUP_SECONDS. Checked only when the actor otherwise holds the capability, so an unauthorised call
    keeps its plain 403. The client asks for the code, calls POST /auth/platform/mfa/step-up, then retries."""
    if capability and capability not in actor.permissions:
        return
    from edusync.modules.iam.application import platform_mfa
    with services.platform_db.platform_transaction() as conn:
        if not platform_mfa.mfa_needed(conn, services.settings, actor.user_id):
            return
        if actor.session_id is None or not platform_mfa.recent_step_up(conn, actor.session_id, services.settings.mfa_stepup_seconds):
            raise HTTPException(status_code=403, detail=STEP_UP_DETAIL)


def require_school_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    services: AppServices = Depends(get_services),
) -> ActorContext:
    claims = _claims(credentials, services)
    if claims.get("scope") != "school":
        raise HTTPException(status_code=403, detail="Jeton école requis")
    try:
        user_id = UUID(str(claims["sub"]))
        school_id = UUID(str(claims["school_id"]))
        membership_id = UUID(str(claims["membership_id"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Contexte école du jeton invalide") from exc

    # Permissions are reloaded from PostgreSQL on every request. They are not trusted from JWT,
    # so role revocation takes effect immediately even with a still-valid access token.
    with services.tenant_db.tenant_transaction(school_id=school_id, user_id=user_id) as conn:
        schools = PostgresSchoolRepository(conn)
        memberships = PostgresMembershipRepository(conn)
        users = PostgresUserRepository(conn)
        school = schools.get(school_id)
        user = users.get(user_id)
        membership = memberships.get(membership_id)
        if user is None or not user.active:
            raise HTTPException(status_code=403, detail="Compte utilisateur désactivé ou inaccessible")
        if int(claims.get("user_version", 0)) != user.version:
            raise HTTPException(status_code=401, detail="Jeton utilisateur obsolète; reconnectez-vous")
        _assert_device_session_live(conn, claims, user_id)
        if school is None or school.status != SchoolStatus.ACTIVE:
            raise HTTPException(status_code=403, detail="École inactive ou inaccessible", headers=SPACE_WITHDRAWN)
        if membership is None or not membership.active:
            raise HTTPException(status_code=403, detail="Appartenance école révoquée", headers=SPACE_WITHDRAWN)
        if membership.user_id != user_id or membership.school_id != school_id:
            raise HTTPException(status_code=403, detail="Contexte d'appartenance incohérent")
        if int(claims.get("membership_version", 0)) != membership.version:
            raise HTTPException(status_code=401, detail="Jeton d'appartenance obsolète; reconnectez-vous")
        permissions = memberships.permissions(membership.id)
        capability_scopes = PostgresAuthorizationRepository(conn).effective_capability_grants(user_id, school_id)

    return ActorContext(
        user_id=user_id,
        school_id=school_id,
        membership_id=membership_id,
        permissions=permissions,
        capability_scopes=capability_scopes,
        is_platform_admin=False,
        correlation_id=uuid4(),
        source="WEB",
    )
