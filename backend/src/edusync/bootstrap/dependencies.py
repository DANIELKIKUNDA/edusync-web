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


def _assert_device_session_live(conn, claims: dict, user_id: UUID) -> None:
    """Access tokens are bound to a device session: logout or device revocation is immediate."""
    from sqlalchemy import text
    try:
        session_id = UUID(str(claims["sid"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Session du jeton invalide", headers={"WWW-Authenticate": "Bearer"}) from exc
    live = conn.execute(
        text("SELECT 1 FROM user_device_sessions WHERE id=:id AND user_id=:uid AND revoked_at IS NULL"),
        {"id": str(session_id), "uid": str(user_id)},
    ).first()
    if live is None:
        raise HTTPException(status_code=401, detail="Session révoquée; reconnectez-vous", headers={"WWW-Authenticate": "Bearer"})


def require_platform_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    services: AppServices = Depends(get_services),
) -> ActorContext:
    claims = _claims(credentials, services)
    if claims.get("scope") != "platform":
        raise HTTPException(status_code=403, detail="Jeton Atelier Pro requis")
    try:
        user_id = UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Sujet du jeton invalide") from exc
    with services.platform_db.platform_transaction() as conn:
        user = PostgresUserRepository(conn).get(user_id)
        if user is None or not user.active:
            raise HTTPException(status_code=403, detail="Accès Atelier Pro révoqué")
        if int(claims.get("user_version", 0)) != user.version:
            raise HTTPException(status_code=401, detail="Jeton Atelier Pro obsolète; reconnectez-vous")
        _assert_device_session_live(conn, claims, user_id)
        authz = PostgresAuthorizationRepository(conn)
        assignments = authz.effective_role_assignments(user_id, None)
        roles = authz.roles({a.role_id for a in assignments})
        permissions = frozenset(code for role in roles.values() for code in role.capability_codes)
        if not permissions:
            raise HTTPException(status_code=403, detail="Aucun rôle Atelier Pro actif")
    return ActorContext(
        user_id=user_id,
        school_id=None,
        membership_id=None,
        permissions=permissions,
        is_platform_admin=False,
        correlation_id=uuid4(),
        source="WEB",
    )


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
            raise HTTPException(status_code=403, detail="École inactive ou inaccessible")
        if membership is None or not membership.active:
            raise HTTPException(status_code=403, detail="Appartenance école révoquée")
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
