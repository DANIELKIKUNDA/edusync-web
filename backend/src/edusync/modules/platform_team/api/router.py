"""Atelier Pro — platform team governance (N1 certification 2026-10).

Platform accounts, PLATFORM_CUSTOM roles, assignments, suspension, sessions and password reset.

Anti-escalation rules (enforced here, and partly in the database by migration 0052):
  * every team mutation requires `platform.collaborators.manage` (reserved capability, never delegable);
  * a role can only be given capabilities the actor holds, never a reserved one, only PLATFORM-scoped ones;
  * nobody changes their own roles, status or password through these routes (self-service is /auth/platform/*);
  * an actor cannot act on an account holding capabilities the actor lacks;
  * the last active Manager système can be neither suspended nor stripped of the role.
Every mutation is audited (actor, target, before/after, reason, idempotency key).
"""
from __future__ import annotations

import re
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from edusync.adapters.postgres_repositories import PostgresAuditRepository
from edusync.bootstrap.dependencies import get_services, platform_permissions, require_platform_actor, require_recent_mfa
from edusync.bootstrap.services import AppServices
from edusync.modules.audit.domain.audit import AuditRecord
from edusync.modules.iam.application import platform_mfa
from edusync.shared.application.context import ActorContext
from edusync.shared.infrastructure.security import hash_password

router = APIRouter(tags=["Atelier Pro — équipe"])

TEAM_CAP = "platform.collaborators.manage"
MANAGER_ROLE = "MANAGER_SYSTEME"
CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")

# Menu entries of Atelier Pro and the capability that opens each one (the server decides, the UI only renders).
MENU = (
    ("dashboard", "Tableau de bord", "platform.schools.read"),
    ("schools", "Écoles", "platform.schools.read"),
    ("access", "Accès écoles", "platform.schools.read"),
    ("team", "Équipe plateforme", TEAM_CAP),
    ("notifications", "Notifications", "platform.notifications.system.send"),
    ("audit", "Audit", "platform.audit.read"),
    ("diagnostics", "Santé du système", "platform.health.read"),
)


class RoleInput(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    label: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=1000)
    capabilities: list[str] = Field(default_factory=list, max_length=64)


class RoleUpdate(BaseModel):
    label: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=1000)
    capabilities: list[str] = Field(default_factory=list, max_length=64)
    version: int


class ReasonInput(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class CloneInput(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    label: str = Field(min_length=3, max_length=180)


class UserCreate(BaseModel):
    email: str = Field(min_length=5, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    full_name: str = Field(min_length=3, max_length=180)
    password: str = Field(min_length=12, max_length=512)
    role_codes: list[str] = Field(min_length=1, max_length=8)
    reason: str = Field(min_length=5, max_length=500)


class RoleAssignInput(BaseModel):
    role_code: str = Field(min_length=3, max_length=64)
    reason: str = Field(min_length=5, max_length=500)


class PasswordResetInput(BaseModel):
    new_password: str = Field(min_length=12, max_length=512)
    reason: str = Field(min_length=5, max_length=500)


class MfaResetInput(BaseModel):
    reason: str = Field(min_length=5, max_length=500)
    # Owner decision 2026-10-13 (option): a lost phone may mean a compromised password too; reset both at once.
    new_password: str | None = Field(default=None, min_length=12, max_length=512)


def _key(value: str | None) -> str:
    key = (value or "").strip()
    if not key or len(key) > 180:
        raise HTTPException(status_code=400, detail="En-tête Idempotency-Key obligatoire pour cette mutation")
    return key


def _audit(c, actor: ActorContext, action: str, entity_type: str, entity_id, *, reason: str | None = None,
           old: dict | None = None, new: dict | None = None, key: str | None = None) -> None:
    PostgresAuditRepository(c).append(AuditRecord(
        action=action, entity_type=entity_type, entity_id=entity_id, actor_user_id=actor.user_id, school_id=None,
        source=actor.source, reason=reason, old_data=old, new_data=new, correlation_id=actor.correlation_id,
        idempotency_key=key))


def _replayed(c, actor: ActorContext, key: str, action: str):
    """Same Idempotency-Key from the same actor for the same action: return the first result (lost response, double click)."""
    row = c.execute(text("""SELECT new_json FROM audit_events WHERE idempotency_key=:k AND action=:a AND actor_user_id=:u
        ORDER BY occurred_at LIMIT 1"""), {"k": key, "a": action, "u": str(actor.user_id)}).first()
    return row[0] if row else None


def _platform_catalog(c) -> dict[str, dict]:
    rows = c.execute(text("""SELECT cc.code, cc.label, cc.group_name, cc.risk, cc.sensitive,
          (rc.capability_code IS NOT NULL) AS reserved, rc.reason AS reserved_reason
        FROM capability_catalog cc LEFT JOIN platform_reserved_capabilities rc ON rc.capability_code=cc.code
        WHERE cc.scope_types ? 'PLATFORM' ORDER BY cc.code""")).mappings().all()
    return {r["code"]: dict(r) for r in rows}


def _check_capabilities(c, actor: ActorContext, caps: list[str]) -> list[str]:
    catalog = _platform_catalog(c)
    wanted = sorted(set(caps))
    unknown = [x for x in wanted if x not in catalog]
    if unknown:
        raise HTTPException(422, "Capacités inconnues ou non plateforme : " + ", ".join(unknown))
    reserved = [x for x in wanted if catalog[x]["reserved"]]
    if reserved:
        raise HTTPException(403, "Capacités réservées, non délégables dans un rôle personnalisé : " + ", ".join(reserved))
    lacking = [x for x in wanted if x not in actor.permissions]
    if lacking:
        raise HTTPException(403, "Vous ne pouvez pas déléguer une capacité que vous ne détenez pas : " + ", ".join(lacking))
    return wanted


def _role(c, role_id: UUID | None = None, code: str | None = None, lock: bool = False):
    sql = """SELECT r.id, r.code, r.label, r.description, r.kind, r.status, r.version, r.created_at, r.updated_at,
          r.archived_at, r.cloned_from_role_id, coalesce(array_agg(rc.capability_code ORDER BY rc.capability_code)
          FILTER (WHERE rc.capability_code IS NOT NULL), '{}') AS capabilities
        FROM rbac_roles r LEFT JOIN rbac_role_capabilities rc ON rc.role_id=r.id
        WHERE r.level='PLATFORM' AND """ + ("r.id=:v" if role_id else "r.code=:v") + " GROUP BY r.id"
    row = c.execute(text(sql), {"v": str(role_id) if role_id else code}).mappings().first()
    if row and lock:
        c.execute(text("SELECT 1 FROM rbac_roles WHERE id=:id FOR UPDATE"), {"id": row["id"]})
    return dict(row) if row else None


def _guard_target(c, actor: ActorContext, user_id: UUID, *, allow_self: bool = False) -> None:
    if not allow_self and user_id == actor.user_id:
        raise HTTPException(403, "Action impossible sur votre propre compte : utilisez « Sécurité et appareils », ou demandez à un autre Manager.")
    target = platform_permissions(c, user_id)
    lacking = sorted(target - actor.permissions)
    if lacking:
        raise HTTPException(403, "Ce compte détient des capacités que vous n’avez pas : action refusée.")


def _active_managers(c, exclude_user: UUID | None = None) -> int:
    return int(c.execute(text("""SELECT count(DISTINCT a.user_id) FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id
        JOIN users u ON u.id=a.user_id LEFT JOIN platform_account_status ps ON ps.user_id=a.user_id
        WHERE r.code=:m AND r.level='PLATFORM' AND r.status='ACTIVE' AND a.school_id IS NULL AND a.active
          AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now()) AND u.active
          AND coalesce(ps.status,'ACTIVE')='ACTIVE' AND (CAST(:x AS uuid) IS NULL OR a.user_id<>:x)"""),
        {"m": MANAGER_ROLE, "x": str(exclude_user) if exclude_user else None}).scalar_one())


def _revoke_platform_sessions(c, user_id: UUID, reason: str) -> int:
    return c.execute(text("""UPDATE user_device_sessions SET revoked_at=coalesce(revoked_at,now()),revoked_reason=coalesce(revoked_reason,:r)
        WHERE user_id=:u AND school_id IS NULL AND revoked_at IS NULL"""), {"u": str(user_id), "r": reason}).rowcount


# ---------------------------------------------------------------- me / menu

@router.get("/me")
def team_me(actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    """Who am I in Atelier Pro: roles, effective capabilities and the menu they open (server-computed)."""
    with services.platform_db.platform_transaction() as c:
        user = c.execute(text("SELECT id, email, full_name FROM users WHERE id=:u"), {"u": str(actor.user_id)}).mappings().one()
        roles = c.execute(text("""SELECT r.code, r.label, r.kind FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id
            WHERE a.user_id=:u AND a.school_id IS NULL AND a.active AND r.level='PLATFORM' AND r.status='ACTIVE'
              AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now()) ORDER BY r.label"""),
            {"u": str(actor.user_id)}).mappings().all()
        # Owner decision 2026-10-13: keep at least two active Managers so a lost access can always be recovered
        # from the console (the operator script stays exceptional). The team governors see the count.
        managers = _active_managers(c) if TEAM_CAP in actor.permissions else None
    perms = sorted(actor.permissions)
    return {"user": dict(user), "roles": [dict(r) for r in roles], "permissions": perms,
            "menu": [{"key": k, "label": label, "capability": cap} for k, label, cap in MENU if cap in actor.permissions],
            "active_managers": managers, "recommended_managers": 2}


# ---------------------------------------------------------------- capabilities & roles

@router.get("/capabilities")
def team_capabilities(actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require(TEAM_CAP)
    with services.platform_db.platform_transaction() as c:
        catalog = _platform_catalog(c)
    return {"items": [{**v, "held": k in actor.permissions, "delegable": (not v["reserved"]) and k in actor.permissions} for k, v in catalog.items()]}


@router.get("/roles")
def team_roles(actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require(TEAM_CAP)
    with services.platform_db.platform_transaction() as c:
        rows = c.execute(text("""SELECT r.id, r.code, r.label, r.description, r.kind, r.status, r.version, r.updated_at, r.archived_at,
              coalesce(array_agg(DISTINCT rc.capability_code) FILTER (WHERE rc.capability_code IS NOT NULL), '{}') AS capabilities,
              count(DISTINCT a.user_id) FILTER (WHERE a.active AND a.school_id IS NULL) AS active_users
            FROM rbac_roles r LEFT JOIN rbac_role_capabilities rc ON rc.role_id=r.id LEFT JOIN rbac_assignments a ON a.role_id=r.id
            WHERE r.level='PLATFORM' GROUP BY r.id ORDER BY (r.kind='PLATFORM_STANDARD') DESC, r.status, lower(r.label)""")).mappings().all()
    return {"items": [dict(r) for r in rows]}


@router.post("/roles", status_code=201)
def team_create_role(body: RoleInput, idempotency_key: str | None = Header(default=None), actor: ActorContext = Depends(require_platform_actor),
                     services: AppServices = Depends(get_services)):
    actor.require(TEAM_CAP)
    key = _key(idempotency_key)
    code = body.code.strip().upper()
    if not CODE_RE.match(code):
        raise HTTPException(422, "Code de rôle : majuscules, chiffres et _ (3 à 64 caractères), commençant par une lettre.")
    try:
        with services.platform_db.platform_transaction() as c:
            prior = _replayed(c, actor, key, "PLATFORM_ROLE_CREATED")
            if prior:
                return prior
            caps = _check_capabilities(c, actor, body.capabilities)
            if _role(c, code=code):
                raise HTTPException(409, "Un rôle plateforme porte déjà ce code.")
            rid = c.execute(text("""INSERT INTO rbac_roles(code,label,description,level,kind,status,created_by_user_id)
                VALUES(:c,:l,:d,'PLATFORM','PLATFORM_CUSTOM','DRAFT',:u) RETURNING id"""),
                {"c": code, "l": body.label.strip(), "d": body.description.strip(), "u": str(actor.user_id)}).scalar_one()
            for cap in caps:
                c.execute(text("INSERT INTO rbac_role_capabilities(role_id,capability_code) VALUES(:r,:c)"), {"r": rid, "c": cap})
            result = {"id": str(rid), "code": code, "status": "DRAFT", "capabilities": caps, "version": 1}
            _audit(c, actor, "PLATFORM_ROLE_CREATED", "PlatformRole", rid, new=result, key=key)
            return result
    except IntegrityError as exc:
        raise HTTPException(409, "Un rôle plateforme porte déjà ce code.") from exc


@router.put("/roles/{role_id}")
def team_update_role(role_id: UUID, body: RoleUpdate, idempotency_key: str | None = Header(default=None),
                     actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require(TEAM_CAP)
    key = _key(idempotency_key)
    with services.platform_db.platform_transaction() as c:
        role = _role(c, role_id=role_id, lock=True)
        if not role:
            raise HTTPException(404, "Rôle introuvable")
        if role["kind"] != "PLATFORM_CUSTOM":
            raise HTTPException(403, "Les rôles standard ne se modifient pas ici : ils relèvent d’une décision du propriétaire.")
        if role["status"] == "ARCHIVED":
            raise HTTPException(409, "Rôle archivé : clonez-le pour en créer une nouvelle version.")
        if int(role["version"]) != body.version:
            raise HTTPException(409, "Ce rôle a été modifié entre-temps ; rechargez-le.")
        caps = _check_capabilities(c, actor, body.capabilities)
        c.execute(text("UPDATE rbac_roles SET label=:l, description=:d, version=version+1, updated_at=now() WHERE id=:id"),
                  {"l": body.label.strip(), "d": body.description.strip(), "id": str(role_id)})
        c.execute(text("DELETE FROM rbac_role_capabilities WHERE role_id=:id"), {"id": str(role_id)})
        for cap in caps:
            c.execute(text("INSERT INTO rbac_role_capabilities(role_id,capability_code) VALUES(:r,:c)"), {"r": str(role_id), "c": cap})
        new = {"label": body.label.strip(), "capabilities": caps, "version": int(role["version"]) + 1}
        _audit(c, actor, "PLATFORM_ROLE_UPDATED", "PlatformRole", role_id,
               old={"label": role["label"], "capabilities": list(role["capabilities"]), "version": int(role["version"])}, new=new, key=key)
    return {"id": str(role_id), **new}


def _set_role_status(role_id: UUID, target: str, action: str, body: ReasonInput, key: str, actor: ActorContext, services: AppServices):
    with services.platform_db.platform_transaction() as c:
        role = _role(c, role_id=role_id, lock=True)
        if not role:
            raise HTTPException(404, "Rôle introuvable")
        if role["kind"] != "PLATFORM_CUSTOM":
            raise HTTPException(403, "Le statut des rôles standard relève d’une décision du propriétaire.")
        if role["status"] == target:
            return {"id": str(role_id), "status": target, "unchanged": True}
        if target == "ACTIVE":
            if role["status"] != "DRAFT":
                raise HTTPException(409, "Seul un brouillon peut être activé.")
            if not role["capabilities"]:
                raise HTTPException(409, "Un rôle sans capacité ne peut pas être activé.")
            _check_capabilities(c, actor, list(role["capabilities"]))
        affected = 0
        if target == "ARCHIVED":
            affected = int(c.execute(text("SELECT count(*) FROM rbac_assignments WHERE role_id=:r AND active AND school_id IS NULL"), {"r": str(role_id)}).scalar_one())
        c.execute(text("""UPDATE rbac_roles SET status=CAST(:s AS varchar), version=version+1, updated_at=now(),
            archived_at=CASE WHEN CAST(:s AS varchar)='ARCHIVED' THEN now() ELSE archived_at END WHERE id=:id"""), {"s": target, "id": str(role_id)})
        _audit(c, actor, action, "PlatformRole", role_id, reason=body.reason, old={"status": role["status"]},
               new={"status": target, "users_losing_role": affected}, key=key)
    return {"id": str(role_id), "status": target, "users_losing_role": affected}


@router.post("/roles/{role_id}/activate")
def team_activate_role(role_id: UUID, body: ReasonInput, idempotency_key: str | None = Header(default=None),
                       actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require(TEAM_CAP)
    return _set_role_status(role_id, "ACTIVE", "PLATFORM_ROLE_ACTIVATED", body, _key(idempotency_key), actor, services)


@router.post("/roles/{role_id}/archive")
def team_archive_role(role_id: UUID, body: ReasonInput, idempotency_key: str | None = Header(default=None),
                      actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require(TEAM_CAP)
    return _set_role_status(role_id, "ARCHIVED", "PLATFORM_ROLE_ARCHIVED", body, _key(idempotency_key), actor, services)


@router.post("/roles/{role_id}/clone", status_code=201)
def team_clone_role(role_id: UUID, body: CloneInput, idempotency_key: str | None = Header(default=None),
                    actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require(TEAM_CAP)
    key = _key(idempotency_key)
    code = body.code.strip().upper()
    if not CODE_RE.match(code):
        raise HTTPException(422, "Code de rôle invalide.")
    try:
        with services.platform_db.platform_transaction() as c:
            prior = _replayed(c, actor, key, "PLATFORM_ROLE_CLONED")
            if prior:
                return prior
            src = _role(c, role_id=role_id)
            if not src:
                raise HTTPException(404, "Rôle introuvable")
            # Cloning a standard role is allowed (starting point) but reserved capabilities never travel.
            reserved = set(c.execute(text("SELECT capability_code FROM platform_reserved_capabilities")).scalars())
            caps = _check_capabilities(c, actor, [x for x in src["capabilities"] if x not in reserved])
            rid = c.execute(text("""INSERT INTO rbac_roles(code,label,description,level,kind,status,created_by_user_id,cloned_from_role_id)
                VALUES(:c,:l,:d,'PLATFORM','PLATFORM_CUSTOM','DRAFT',:u,:src) RETURNING id"""),
                {"c": code, "l": body.label.strip(), "d": src["description"], "u": str(actor.user_id), "src": str(role_id)}).scalar_one()
            for cap in caps:
                c.execute(text("INSERT INTO rbac_role_capabilities(role_id,capability_code) VALUES(:r,:c)"), {"r": rid, "c": cap})
            result = {"id": str(rid), "code": code, "status": "DRAFT", "capabilities": caps, "cloned_from": src["code"], "version": 1}
            _audit(c, actor, "PLATFORM_ROLE_CLONED", "PlatformRole", rid, new=result, key=key)
            return result
    except IntegrityError as exc:
        raise HTTPException(409, "Un rôle plateforme porte déjà ce code.") from exc


# ---------------------------------------------------------------- users

def _user_roles(c, user_id: UUID) -> list[dict]:
    return [dict(r) for r in c.execute(text("""SELECT r.code, r.label, r.kind, r.status, a.active, a.created_at, a.reason
        FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id
        WHERE a.user_id=:u AND a.school_id IS NULL AND r.level='PLATFORM' ORDER BY a.active DESC, r.label"""), {"u": str(user_id)}).mappings()]


@router.get("/users")
def team_users(q: str | None = None, actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require(TEAM_CAP)
    with services.platform_db.platform_transaction() as c:
        rows = c.execute(text("""SELECT u.id, u.email, u.full_name, u.active AS account_active, u.created_at,
              coalesce(ps.status,'ACTIVE') AS platform_status,
              coalesce(array_agg(DISTINCT r.code) FILTER (WHERE a.active AND r.status='ACTIVE'), '{}') AS roles,
              (SELECT max(s.last_seen_at) FROM user_device_sessions s WHERE s.user_id=u.id AND s.school_id IS NULL) AS last_activity,
              (SELECT count(*) FROM user_device_sessions s WHERE s.user_id=u.id AND s.school_id IS NULL AND s.revoked_at IS NULL) AS open_sessions,
              EXISTS (SELECT 1 FROM user_mfa_factors f WHERE f.user_id=u.id AND f.status='ACTIVE') AS mfa_enrolled
            FROM users u JOIN rbac_assignments a ON a.user_id=u.id AND a.school_id IS NULL JOIN rbac_roles r ON r.id=a.role_id AND r.level='PLATFORM'
            LEFT JOIN platform_account_status ps ON ps.user_id=u.id
            WHERE (CAST(:q AS text) IS NULL OR u.full_name ILIKE '%'||:q||'%' OR u.email::text ILIKE '%'||:q||'%')
            GROUP BY u.id, ps.status ORDER BY lower(u.full_name), u.id LIMIT 200"""), {"q": (q or "").strip() or None}).mappings().all()
    return {"items": [{**dict(r), "is_me": r["id"] == actor.user_id} for r in rows]}


@router.post("/users", status_code=201)
def team_create_user(body: UserCreate, idempotency_key: str | None = Header(default=None), actor: ActorContext = Depends(require_platform_actor),
                     services: AppServices = Depends(get_services)):
    actor.require(TEAM_CAP)
    require_recent_mfa(services, actor)  # step-up: code confirmed in the last minutes
    key = _key(idempotency_key)
    email = body.email.strip().lower()
    try:
        with services.platform_db.platform_transaction() as c:
            prior = _replayed(c, actor, key, "PLATFORM_USER_CREATED")
            if prior:
                return prior
            roles = []
            for code in sorted(set(x.strip().upper() for x in body.role_codes)):
                role = _role(c, code=code)
                if not role or role["status"] != "ACTIVE":
                    raise HTTPException(422, f"Rôle plateforme actif introuvable : {code}")
                lacking = sorted(set(role["capabilities"]) - actor.permissions)
                if lacking:
                    raise HTTPException(403, f"Vous ne pouvez pas attribuer le rôle {code} : il contient des capacités que vous n’avez pas.")
                roles.append(role)
            if c.execute(text("SELECT 1 FROM users WHERE lower(email::text)=:e"), {"e": email}).first():
                raise HTTPException(409, "Un compte existe déjà avec cette adresse : attribuez-lui un rôle depuis sa fiche.")
            uid = c.execute(text("""INSERT INTO users(email,full_name,password_hash,active,is_platform_admin)
                VALUES(:e,:n,:p,true,true) RETURNING id"""), {"e": email, "n": body.full_name.strip(), "p": hash_password(body.password)}).scalar_one()
            for role in roles:
                aid = c.execute(text("""INSERT INTO rbac_assignments(user_id,role_id,granted_by_user_id,reason)
                    VALUES(:u,:r,:by,:reason) RETURNING id"""), {"u": uid, "r": role["id"], "by": str(actor.user_id), "reason": body.reason}).scalar_one()
                c.execute(text("INSERT INTO rbac_assignment_scopes(assignment_id,scope_type,scope_value) VALUES(:id,'PLATFORM',NULL)"), {"id": aid})
            c.execute(text("INSERT INTO platform_account_status(user_id,status,reason,changed_by_user_id) VALUES(:u,'ACTIVE',:r,:by)"),
                      {"u": uid, "r": body.reason, "by": str(actor.user_id)})
            result = {"id": str(uid), "email": email, "full_name": body.full_name.strip(), "roles": [r["code"] for r in roles]}
            _audit(c, actor, "PLATFORM_USER_CREATED", "User", uid, reason=body.reason, new=result, key=key)
            return result
    except IntegrityError as exc:
        raise HTTPException(409, "Un compte existe déjà avec cette adresse.") from exc


@router.get("/users/{user_id}")
def team_user_detail(user_id: UUID, actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require(TEAM_CAP)
    with services.platform_db.platform_transaction() as c:
        user = c.execute(text("""SELECT u.id, u.email, u.full_name, u.active AS account_active, u.created_at,
              coalesce(ps.status,'ACTIVE') AS platform_status, ps.reason AS status_reason, ps.changed_at AS status_changed_at
            FROM users u LEFT JOIN platform_account_status ps ON ps.user_id=u.id WHERE u.id=:u"""), {"u": str(user_id)}).mappings().first()
        if not user:
            raise HTTPException(404, "Compte introuvable")
        roles = _user_roles(c, user_id)
        if not roles:
            raise HTTPException(404, "Ce compte n’appartient pas à l’équipe plateforme")
        perms = sorted(platform_permissions(c, user_id))
        sessions = [dict(r) for r in c.execute(text("""SELECT id, label, created_at, last_seen_at FROM user_device_sessions
            WHERE user_id=:u AND school_id IS NULL AND revoked_at IS NULL ORDER BY last_seen_at DESC LIMIT 50"""), {"u": str(user_id)}).mappings()]
        audit = [dict(r) for r in c.execute(text("""SELECT a.occurred_at, a.action, a.reason, u.full_name AS actor FROM audit_events a
            LEFT JOIN users u ON u.id=a.actor_user_id WHERE a.entity_id=:u OR (a.actor_user_id=:u AND a.entity_type='UserSecurity')
            ORDER BY a.occurred_at DESC LIMIT 30"""), {"u": str(user_id)}).mappings()]
        mfa = platform_mfa.status(c, user_id)
    # Second-factor status only (enrolled, date, codes left): never the secret nor the codes.
    return {**dict(user), "roles": roles, "effective_permissions": perms, "sessions": sessions, "audit": audit, "is_me": user_id == actor.user_id,
            "mfa": {"enrolled": mfa["enrolled"], "confirmed_at": mfa["confirmed_at"], "recovery_codes_remaining": mfa["recovery_codes_remaining"]}}


@router.post("/users/{user_id}/roles")
def team_assign_role(user_id: UUID, body: RoleAssignInput, idempotency_key: str | None = Header(default=None),
                     actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require(TEAM_CAP)
    require_recent_mfa(services, actor)  # step-up: code confirmed in the last minutes
    key = _key(idempotency_key)
    with services.platform_db.platform_transaction() as c:
        c.execute(text("SELECT 1 FROM users WHERE id=:u FOR UPDATE"), {"u": str(user_id)})
        _guard_target(c, actor, user_id)
        role = _role(c, code=body.role_code.strip().upper())
        if not role or role["status"] != "ACTIVE":
            raise HTTPException(404, "Rôle plateforme actif introuvable")
        if set(role["capabilities"]) - actor.permissions:
            raise HTTPException(403, "Vous ne pouvez pas attribuer un rôle contenant des capacités que vous n’avez pas.")
        if not c.execute(text("SELECT 1 FROM users WHERE id=:u AND active"), {"u": str(user_id)}).first():
            raise HTTPException(404, "Compte actif introuvable")
        existing = c.execute(text("SELECT id, active FROM rbac_assignments WHERE user_id=:u AND role_id=:r AND school_id IS NULL ORDER BY created_at DESC LIMIT 1 FOR UPDATE"),
                             {"u": str(user_id), "r": role["id"]}).mappings().first()
        if existing and existing["active"]:
            return {"user_id": str(user_id), "role_code": role["code"], "status": "already_assigned"}
        if existing:
            c.execute(text("""UPDATE rbac_assignments SET active=true, valid_from=now(), valid_until=NULL, granted_by_user_id=:by, reason=:reason,
                version=version+1, updated_at=now() WHERE id=:id"""), {"id": existing["id"], "by": str(actor.user_id), "reason": body.reason})
        else:
            aid = c.execute(text("INSERT INTO rbac_assignments(user_id,role_id,granted_by_user_id,reason) VALUES(:u,:r,:by,:reason) RETURNING id"),
                            {"u": str(user_id), "r": role["id"], "by": str(actor.user_id), "reason": body.reason}).scalar_one()
            c.execute(text("INSERT INTO rbac_assignment_scopes(assignment_id,scope_type,scope_value) VALUES(:id,'PLATFORM',NULL)"), {"id": aid})
        c.execute(text("UPDATE users SET is_platform_admin=true WHERE id=:u"), {"u": str(user_id)})
        _audit(c, actor, "PLATFORM_ROLE_ASSIGNED", "User", user_id, reason=body.reason, new={"role_code": role["code"]}, key=key)
    return {"user_id": str(user_id), "role_code": role["code"], "status": "assigned"}


@router.post("/users/{user_id}/roles/{role_code}/revoke")
def team_revoke_role(user_id: UUID, role_code: str, body: ReasonInput, idempotency_key: str | None = Header(default=None),
                     actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require(TEAM_CAP)
    require_recent_mfa(services, actor)  # step-up: code confirmed in the last minutes
    key = _key(idempotency_key)
    code = role_code.strip().upper()
    with services.platform_db.platform_transaction() as c:
        c.execute(text("SELECT 1 FROM users WHERE id=:u FOR UPDATE"), {"u": str(user_id)})
        _guard_target(c, actor, user_id)
        if code == MANAGER_ROLE:
            # Serialise Manager changes so two concurrent revocations cannot remove the last Manager.
            c.execute(text("SELECT pg_advisory_xact_lock(hashtext('edusync:platform:managers'))"))
            if _active_managers(c, exclude_user=user_id) == 0:
                raise HTTPException(409, "Impossible : ce compte est le dernier Manager système actif.")
        a = c.execute(text("""SELECT a.id FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id
            WHERE a.user_id=:u AND a.school_id IS NULL AND a.active AND r.code=:c AND r.level='PLATFORM' FOR UPDATE OF a"""),
            {"u": str(user_id), "c": code}).first()
        if not a:
            raise HTTPException(404, "Attribution active introuvable")
        c.execute(text("UPDATE rbac_assignments SET active=false, reason=:r, version=version+1, updated_at=now() WHERE id=:id"), {"id": a[0], "r": body.reason})
        remaining = platform_permissions(c, user_id)
        revoked = 0
        if not remaining:
            c.execute(text("UPDATE users SET is_platform_admin=false WHERE id=:u"), {"u": str(user_id)})
            revoked = _revoke_platform_sessions(c, user_id, "PLATFORM_ROLE_REVOKED")
        _audit(c, actor, "PLATFORM_ROLE_REVOKED", "User", user_id, reason=body.reason, old={"role_code": code},
               new={"remaining_capabilities": len(remaining), "sessions_revoked": revoked}, key=key)
    return {"user_id": str(user_id), "role_code": code, "status": "revoked", "sessions_revoked": revoked}


def _set_status(user_id: UUID, target: str, body: ReasonInput, key: str, actor: ActorContext, services: AppServices):
    with services.platform_db.platform_transaction() as c:
        c.execute(text("SELECT 1 FROM users WHERE id=:u FOR UPDATE"), {"u": str(user_id)})
        _guard_target(c, actor, user_id)
        if not _user_roles(c, user_id):
            raise HTTPException(404, "Ce compte n’appartient pas à l’équipe plateforme")
        current = c.execute(text("SELECT status FROM platform_account_status WHERE user_id=:u FOR UPDATE"), {"u": str(user_id)}).scalar_one_or_none() or "ACTIVE"
        if current == target:
            return {"user_id": str(user_id), "platform_status": target, "unchanged": True}
        if target == "SUSPENDED":
            c.execute(text("SELECT pg_advisory_xact_lock(hashtext('edusync:platform:managers'))"))
            is_manager = c.execute(text("""SELECT 1 FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id
                WHERE a.user_id=:u AND a.school_id IS NULL AND a.active AND r.code=:m"""), {"u": str(user_id), "m": MANAGER_ROLE}).first()
            if is_manager and _active_managers(c, exclude_user=user_id) == 0:
                raise HTTPException(409, "Impossible : ce compte est le dernier Manager système actif.")
        c.execute(text("""INSERT INTO platform_account_status(user_id,status,reason,changed_by_user_id) VALUES(:u,:s,:r,:by)
            ON CONFLICT (user_id) DO UPDATE SET status=EXCLUDED.status, reason=EXCLUDED.reason, changed_by_user_id=EXCLUDED.changed_by_user_id,
              changed_at=now(), version=platform_account_status.version+1"""), {"u": str(user_id), "s": target, "r": body.reason, "by": str(actor.user_id)})
        revoked = _revoke_platform_sessions(c, user_id, "PLATFORM_ACCOUNT_SUSPENDED") if target == "SUSPENDED" else 0
        _audit(c, actor, "PLATFORM_USER_SUSPENDED" if target == "SUSPENDED" else "PLATFORM_USER_REACTIVATED", "User", user_id,
               reason=body.reason, old={"platform_status": current}, new={"platform_status": target, "sessions_revoked": revoked}, key=key)
    return {"user_id": str(user_id), "platform_status": target, "sessions_revoked": revoked}


@router.post("/users/{user_id}/suspend")
def team_suspend_user(user_id: UUID, body: ReasonInput, idempotency_key: str | None = Header(default=None),
                      actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require(TEAM_CAP)
    require_recent_mfa(services, actor)  # step-up: code confirmed in the last minutes
    return _set_status(user_id, "SUSPENDED", body, _key(idempotency_key), actor, services)


@router.post("/users/{user_id}/reactivate")
def team_reactivate_user(user_id: UUID, body: ReasonInput, idempotency_key: str | None = Header(default=None),
                         actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require(TEAM_CAP)
    return _set_status(user_id, "ACTIVE", body, _key(idempotency_key), actor, services)


@router.post("/users/{user_id}/sessions/{session_id}/revoke")
def team_revoke_user_session(user_id: UUID, session_id: UUID, body: ReasonInput, idempotency_key: str | None = Header(default=None),
                             actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require(TEAM_CAP)
    key = _key(idempotency_key)
    with services.platform_db.platform_transaction() as c:
        _guard_target(c, actor, user_id)
        n = c.execute(text("""UPDATE user_device_sessions SET revoked_at=coalesce(revoked_at,now()),revoked_reason='PLATFORM_ADMIN_REVOKED'
            WHERE id=:s AND user_id=:u AND school_id IS NULL AND revoked_at IS NULL"""), {"s": str(session_id), "u": str(user_id)}).rowcount
        if not n:
            raise HTTPException(404, "Session active introuvable pour ce compte")
        _audit(c, actor, "PLATFORM_USER_SESSION_REVOKED", "User", user_id, reason=body.reason, new={"session_id": str(session_id)}, key=key)
    return {"user_id": str(user_id), "session_id": str(session_id), "revoked": True}


@router.post("/users/{user_id}/sessions/revoke-all")
def team_revoke_user_sessions(user_id: UUID, body: ReasonInput, idempotency_key: str | None = Header(default=None),
                              actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require(TEAM_CAP)
    key = _key(idempotency_key)
    with services.platform_db.platform_transaction() as c:
        _guard_target(c, actor, user_id)
        n = _revoke_platform_sessions(c, user_id, "PLATFORM_ADMIN_REVOKED")
        _audit(c, actor, "PLATFORM_USER_SESSIONS_REVOKED", "User", user_id, reason=body.reason, new={"sessions_revoked": n}, key=key)
    return {"user_id": str(user_id), "sessions_revoked": n}


@router.post("/users/{user_id}/password-reset")
def team_reset_password(user_id: UUID, body: PasswordResetInput, idempotency_key: str | None = Header(default=None),
                        actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    """Sets a temporary password chosen by the Manager and signs the account out everywhere (audited, never logged)."""
    actor.require(TEAM_CAP)
    require_recent_mfa(services, actor)  # step-up: code confirmed in the last minutes
    key = _key(idempotency_key)
    with services.platform_db.platform_transaction() as c:
        c.execute(text("SELECT 1 FROM users WHERE id=:u FOR UPDATE"), {"u": str(user_id)})
        _guard_target(c, actor, user_id)
        if not _user_roles(c, user_id):
            raise HTTPException(404, "Ce compte n’appartient pas à l’équipe plateforme")
        c.execute(text("UPDATE users SET password_hash=:p, version=version+1 WHERE id=:u"), {"p": hash_password(body.new_password), "u": str(user_id)})
        n = c.execute(text("""UPDATE user_device_sessions SET revoked_at=coalesce(revoked_at,now()),revoked_reason='PASSWORD_RESET'
            WHERE user_id=:u AND revoked_at IS NULL"""), {"u": str(user_id)}).rowcount
        _audit(c, actor, "PLATFORM_USER_PASSWORD_RESET", "User", user_id, reason=body.reason, new={"sessions_revoked": n}, key=key)
    return {"user_id": str(user_id), "sessions_revoked": n}


@router.post("/users/{user_id}/mfa-reset")
def team_reset_mfa(user_id: UUID, body: MfaResetInput, idempotency_key: str | None = Header(default=None),
                   actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    """Lost phone: another Manager removes the second factor of an account (never their own, never an account holding
    capabilities they lack), with a reason. Platform sessions end; the account enrols a new factor at its next sign-in.
    There is no master code and no reset by e-mail: identity is checked out of band by the Manager, then audited."""
    actor.require(TEAM_CAP)
    require_recent_mfa(services, actor)  # step-up: code confirmed in the last minutes
    key = _key(idempotency_key)
    with services.platform_db.platform_transaction() as c:
        prior = _replayed(c, actor, key, "PLATFORM_USER_MFA_RESET")
        if prior:
            return prior
        c.execute(text("SELECT 1 FROM users WHERE id=:u FOR UPDATE"), {"u": str(user_id)})
        _guard_target(c, actor, user_id)
        if not _user_roles(c, user_id):
            raise HTTPException(404, "Ce compte n’appartient pas à l’équipe plateforme")
        removed = platform_mfa.reset(c, user_id=user_id, reason="RESET_BY_MANAGER")
        sessions = _revoke_platform_sessions(c, user_id, "MFA_RESET")
        password_reset = False
        if body.new_password:
            # Password changed too: the account version moves on, so every session of every space ends.
            c.execute(text("UPDATE users SET password_hash=:p, version=version+1 WHERE id=:u"), {"p": hash_password(body.new_password), "u": str(user_id)})
            sessions += c.execute(text("""UPDATE user_device_sessions SET revoked_at=coalesce(revoked_at,now()),revoked_reason='PASSWORD_RESET'
                WHERE user_id=:u AND revoked_at IS NULL"""), {"u": str(user_id)}).rowcount
            password_reset = True
        manager = c.execute(text("SELECT full_name FROM users WHERE id=:u"), {"u": str(actor.user_id)}).scalar_one()
        # The account is told at once: if the reset was not legitimate, its owner can react (decision 2026-10-13).
        platform_mfa.notify_security(c, user_id=user_id, title="Validation en deux étapes réinitialisée",
            body=(f"{manager} a réinitialisé votre validation en deux étapes" + (" et votre mot de passe" if password_reset else "")
                  + f". Motif : {body.reason.strip()}. Vous configurerez une nouvelle application à votre prochaine connexion. "
                  "Si vous n’êtes pas à l’origine de cette demande, prévenez immédiatement un autre Manager système."))
        result = {"user_id": str(user_id), "mfa_reset": True, "password_reset": password_reset, "sessions_revoked": sessions, **removed}
        _audit(c, actor, "PLATFORM_USER_MFA_RESET", "User", user_id, reason=body.reason, new=result, key=key)
    from edusync.shared.infrastructure.realtime import publish_inbox_changed
    publish_inbox_changed(services.settings.redis_url, [(str(user_id), None)])  # the bell of the account updates at once
    return result
