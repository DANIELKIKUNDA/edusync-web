"""School access governance — each school sets its own policy (owner decision 2026-10-02).

Standard roles are product baselines (read-only here). A school adapts them by cloning into
SCHOOL_CUSTOM roles, assigning roles to its members with a scope (school / section / class) and an
optional end date. No approval workflow: governance is enforced by automatic guardrails and full
transparency (every change is in the audit journal, readable by holders of audit.school.read).

Guardrails, enforced server-side for every school:
  * no self-service: nobody changes their own roles;
  * a school role can never carry a platform capability;
  * the school can never lose its last access manager (access.roles.manage);
  * standard roles are immutable; custom roles belong to one school only (RLS + trigger).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from edusync.adapters.postgres_idempotency import PostgresIdempotencyRepository
from edusync.adapters.postgres_repositories import PostgresAuditRepository
from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.modules.audit.domain.audit import AuditRecord
from edusync.shared.application.context import ActorContext
from edusync.shared.application.idempotency import IdempotentExecutor
from edusync.shared.domain.concurrency import IdempotencyConflict, IdempotencyInProgress

router = APIRouter(tags=["Accès & rôles de l'école"])
MANAGER_CAPABILITY = "access.roles.manage"
SECTION_EXISTS = text("SELECT 1 FROM school_sections WHERE school_id=:s AND upper(code)=:v LIMIT 1")
CLASS_EXISTS = text("SELECT 1 FROM school_classes WHERE school_id=:s AND upper(code)=:v LIMIT 1")


def _need(actor: ActorContext, capability: str) -> None:
    try:
        actor.require(capability)
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e


def _json(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json(v) for v in value]
    if isinstance(value, (UUID, datetime)):
        return str(value)
    return value


def _audit(conn, actor: ActorContext, action: str, entity_type: str, entity_id: UUID, new: dict, reason: str | None = None, old: dict | None = None) -> None:
    PostgresAuditRepository(conn).append(AuditRecord(
        action=action, entity_type=entity_type, entity_id=entity_id, actor_user_id=actor.user_id,
        membership_id=actor.membership_id, school_id=actor.school_id, source=actor.source,
        old_data=_json(old) if old else None, new_data=_json(new), reason=reason,
        correlation_id=actor.correlation_id, idempotency_key=actor.idempotency_key))


def _idempotent(services: AppServices, actor: ActorContext, key: str | None, operation: str, payload: dict, action):
    if not (key or "").strip():
        raise HTTPException(400, "Idempotency-Key obligatoire")
    try:
        with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
            result = IdempotentExecutor(PostgresIdempotencyRepository(conn)).execute(
                scope_key=str(actor.school_id), idempotency_key=key, operation=operation, payload=payload,
                school_id=str(actor.school_id), actor_user_id=str(actor.user_id), action=lambda: action(conn))
            return result.body
    except (IdempotencyConflict, IdempotencyInProgress) as e:
        raise HTTPException(409, str(e)) from e


def _user_cards(services: AppServices, user_ids: set[str]) -> dict[str, dict]:
    """Names/e-mails for user ids already proven to belong to this school (read under tenant RLS).

    Tenant RLS on users only exposes the caller's own row (privacy); the platform pool resolves
    display names for exactly these ids and nothing else."""
    ids = sorted(i for i in user_ids if i)
    if not ids:
        return {}
    with services.platform_db.platform_transaction() as conn:
        rows = conn.execute(text("SELECT id,full_name,email FROM users WHERE id=ANY(CAST(:ids AS uuid[]))"), {"ids": ids}).mappings().all()
    return {str(r["id"]): {"full_name": r["full_name"], "email": str(r["email"])} for r in rows}


def _school_capabilities(conn) -> dict[str, dict]:
    rows = conn.execute(text("""SELECT code,domain_name,group_name,label,risk,scope_types FROM capability_catalog
                                WHERE code NOT LIKE 'platform.%' AND NOT (scope_types ? 'PLATFORM')
                                ORDER BY domain_name,group_name,code""")).mappings().all()
    return {r["code"]: dict(r) for r in rows}


def _assert_managers_remain(conn, school_id: UUID) -> None:
    left = conn.execute(text("""SELECT count(DISTINCT a.membership_id) FROM rbac_assignments a
          JOIN rbac_roles r ON r.id=a.role_id AND r.status='ACTIVE'
          JOIN rbac_role_capabilities rc ON rc.role_id=r.id AND rc.capability_code=:cap
          JOIN school_memberships m ON m.id=a.membership_id AND m.active=true
          WHERE a.school_id=:sid AND a.active=true AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now())"""),
                        {"cap": MANAGER_CAPABILITY, "sid": str(school_id)}).scalar_one()
    if left == 0:
        raise HTTPException(409, "Refusé : l'école doit garder au moins un gestionnaire des accès")


def _role(conn, role_id: UUID, *, for_update: bool = False) -> dict:
    row = conn.execute(text("""SELECT id,school_id,code,label,description,kind,status,version FROM rbac_roles
                               WHERE id=:id AND level='SCHOOL'"""), {"id": str(role_id)}).mappings().first()
    if not row:
        raise HTTPException(404, "Rôle introuvable")
    if for_update:
        if row["kind"] != "SCHOOL_CUSTOM":
            raise HTTPException(409, "Les rôles standards ne se modifient pas : clonez-le pour l'adapter")
        conn.execute(text("SELECT 1 FROM rbac_roles WHERE id=:id FOR UPDATE"), {"id": str(role_id)})
    return dict(row)


def _role_caps(conn, role_id) -> list[str]:
    return [r[0] for r in conn.execute(text("SELECT capability_code FROM rbac_role_capabilities WHERE role_id=:r ORDER BY 1"), {"r": str(role_id)})]


# --------------------------------------------------------------------------------------- reads
@router.get("/catalog")
def catalog(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, "access.roles.read")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        caps = _school_capabilities(conn)
    groups: dict[str, list] = {}
    for c in caps.values():
        groups.setdefault(c["domain_name"], []).append({"code": c["code"], "label": c["label"], "group": c["group_name"], "risk": c["risk"]})
    return {"domains": [{"domain": d, "capabilities": items} for d, items in groups.items()], "total": len(caps)}


@router.get("/roles")
def roles(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, "access.roles.read")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        rows = conn.execute(text("""SELECT r.id,r.code,r.label,r.description,r.kind,r.status,r.version,
              (SELECT count(*) FROM rbac_assignments a WHERE a.role_id=r.id AND a.school_id=:sid AND a.active=true
                 AND (a.valid_until IS NULL OR a.valid_until>now())) holders,
              coalesce((SELECT array_agg(rc.capability_code ORDER BY rc.capability_code) FROM rbac_role_capabilities rc WHERE rc.role_id=r.id),'{}') capabilities
              FROM rbac_roles r WHERE r.level='SCHOOL' AND r.status IN ('ACTIVE','ARCHIVED')
              ORDER BY CASE r.kind WHEN 'SCHOOL_CUSTOM' THEN 0 ELSE 1 END, r.label"""), {"sid": str(actor.school_id)}).mappings().all()
    return {"items": [{**_json(dict(r)), "editable": r["kind"] == "SCHOOL_CUSTOM"} for r in rows]}


@router.get("/members")
def members(q: str | None = Query(None, max_length=120), actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, "access.roles.read")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        rows = conn.execute(text("""SELECT m.id membership_id,m.user_id,m.active,
              coalesce(json_agg(json_build_object('assignment_id',a.id,'role_id',r.id,'role_label',r.label,'role_kind',r.kind,
                 'valid_until',a.valid_until,'scopes',(SELECT coalesce(json_agg(json_build_object('type',s.scope_type,'value',s.scope_value)),'[]')
                                                        FROM rbac_assignment_scopes s WHERE s.assignment_id=a.id)) ORDER BY r.label)
                 FILTER (WHERE a.id IS NOT NULL),'[]') roles
              FROM school_memberships m
              LEFT JOIN rbac_assignments a ON a.membership_id=m.id AND a.school_id=m.school_id AND a.active=true AND (a.valid_until IS NULL OR a.valid_until>now())
              LEFT JOIN rbac_roles r ON r.id=a.role_id
              WHERE m.school_id=:sid GROUP BY m.id,m.user_id,m.active"""), {"sid": str(actor.school_id)}).mappings().all()
    cards = _user_cards(services, {str(r["user_id"]) for r in rows})
    needle = (q or "").strip().lower()
    items = []
    for r in rows:
        card = cards.get(str(r["user_id"]), {"full_name": "Compte inconnu", "email": ""})
        item = {**_json(dict(r)), **card, "is_me": str(r["membership_id"]) == str(actor.membership_id)}
        item.pop("user_id", None)
        hay = f"{card['full_name']} {card['email']} {' '.join(x['role_label'] for x in r['roles'])}".lower()
        if not needle or needle in hay:
            items.append(item)
    items.sort(key=lambda x: x["full_name"].lower())
    return {"items": items[:300]}


@router.get("/scope-options")
def scope_options(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """Sections and classes of the active year a role assignment can be limited to."""
    _need(actor, "access.roles.read")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        sections = conn.execute(text("SELECT upper(code) code,label FROM school_sections WHERE school_id=:s AND enabled ORDER BY label"),
                                {"s": str(actor.school_id)}).mappings().all()
        classes = conn.execute(text("""SELECT upper(c.code) code,c.label,upper(s.code) section FROM school_classes c
              JOIN school_sections s ON s.id=c.section_id JOIN academic_years y ON y.id=c.academic_year_id AND y.status='ACTIVE'
              WHERE c.school_id=:s AND c.enabled ORDER BY s.label,c.label"""), {"s": str(actor.school_id)}).mappings().all()
    return {"sections": [dict(r) for r in sections], "classes": [dict(r) for r in classes]}


@router.get("/journal")
def journal(limit: int = Query(50, ge=1, le=200), actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """Read-only rights history: transparency for the school's leadership, no action required."""
    if "access.roles.read" not in actor.permissions and "audit.school.read" not in actor.permissions:
        raise HTTPException(403, "Permission requise: audit.school.read")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        rows = conn.execute(text("""SELECT e.occurred_at created_at,e.action,e.reason,e.new_json new_data,e.old_json old_data,e.actor_user_id
              FROM audit_events e WHERE e.school_id=:sid AND e.action LIKE 'ACCESS_%' ORDER BY e.occurred_at DESC LIMIT :lim"""),
                            {"sid": str(actor.school_id), "lim": limit}).mappings().all()
    cards = _user_cards(services, {str(r["actor_user_id"]) for r in rows if r["actor_user_id"]})
    items = []
    for r in rows:
        item = _json(dict(r))
        item["actor"] = cards.get(str(r["actor_user_id"]), {}).get("full_name")
        item.pop("actor_user_id", None)
        items.append(item)
    return {"items": items}


# --------------------------------------------------------------------------------------- roles
class RoleInput(BaseModel):
    label: str = Field(min_length=3, max_length=120)
    description: str = Field(default="", max_length=600)
    capabilities: list[str] = Field(default_factory=list, max_length=400)
    clone_from_role_id: UUID | None = None


def _validated_caps(conn, requested: list[str]) -> list[str]:
    allowed = _school_capabilities(conn)
    unknown = sorted(set(requested) - set(allowed))
    if unknown:
        raise HTTPException(422, f"Permissions non attribuables par une école : {', '.join(unknown[:5])}")
    return sorted(set(requested))


@router.post("/roles", status_code=201)
def create_role(b: RoleInput, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, MANAGER_CAPABILITY)

    def action(conn):
        caps = list(b.capabilities)
        base = None
        if b.clone_from_role_id:
            base = _role(conn, b.clone_from_role_id)
            caps = sorted(set(caps) | set(_role_caps(conn, base["id"])))
        caps = _validated_caps(conn, caps)
        code = "CUSTOM_" + uuid4().hex[:10].upper()
        rid = conn.execute(text("""INSERT INTO rbac_roles(school_id,code,label,description,level,kind,status,created_by_user_id)
              VALUES(:s,:c,:l,:d,'SCHOOL','SCHOOL_CUSTOM','ACTIVE',:u) RETURNING id"""),
                           {"s": str(actor.school_id), "c": code, "l": b.label.strip(), "d": b.description.strip(), "u": str(actor.user_id)}).scalar_one()
        for cap in caps:
            conn.execute(text("INSERT INTO rbac_role_capabilities(role_id,capability_code) VALUES(:r,:c)"), {"r": str(rid), "c": cap})
        out = {"id": str(rid), "code": code, "label": b.label.strip(), "capabilities": caps,
               "cloned_from": base["label"] if base else None, "version": 1}
        _audit(conn, actor, "ACCESS_ROLE_CREATED", "rbac_role", rid, out)
        return 201, out

    return _idempotent(services, actor, idempotency_key, "ACCESS_ROLE_CREATE", b.model_dump(mode="json"), action)


@router.put("/roles/{role_id}")
def update_role(role_id: UUID, b: RoleInput, if_match: str | None = Header(None, alias="If-Match"),
                idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, MANAGER_CAPABILITY)

    def action(conn):
        role = _role(conn, role_id, for_update=True)
        if role["kind"] != "SCHOOL_CUSTOM" or str(role["school_id"]) != str(actor.school_id):
            raise HTTPException(409, "Les rôles standards ne se modifient pas : clonez-le pour l'adapter")
        if role["status"] != "ACTIVE":
            raise HTTPException(409, "Rôle archivé")
        if if_match is None or str(role["version"]) != if_match.strip('"'):
            raise HTTPException(409, "Rôle modifié par un autre utilisateur : rechargez")
        holders = conn.execute(text("SELECT 1 FROM rbac_assignments WHERE role_id=:r AND membership_id=:m AND active=true LIMIT 1"),
                               {"r": str(role_id), "m": str(actor.membership_id)}).first()
        if holders:
            raise HTTPException(403, "Refusé : vous ne pouvez pas modifier un rôle que vous détenez vous-même")
        before = _role_caps(conn, role_id)
        caps = _validated_caps(conn, b.capabilities)
        conn.execute(text("DELETE FROM rbac_role_capabilities WHERE role_id=:r"), {"r": str(role_id)})
        for cap in caps:
            conn.execute(text("INSERT INTO rbac_role_capabilities(role_id,capability_code) VALUES(:r,:c)"), {"r": str(role_id), "c": cap})
        conn.execute(text("UPDATE rbac_roles SET label=:l,description=:d,version=version+1,updated_at=now() WHERE id=:r"),
                     {"l": b.label.strip(), "d": b.description.strip(), "r": str(role_id)})
        _assert_managers_remain(conn, actor.school_id)
        out = {"id": str(role_id), "label": b.label.strip(), "capabilities": caps, "version": int(role["version"]) + 1,
               "added": sorted(set(caps) - set(before)), "removed": sorted(set(before) - set(caps))}
        _audit(conn, actor, "ACCESS_ROLE_UPDATED", "rbac_role", role_id, out, old={"label": role["label"], "capabilities": before})
        return 200, out

    return _idempotent(services, actor, idempotency_key, "ACCESS_ROLE_UPDATE", {"role": str(role_id), **b.model_dump(mode="json")}, action)


class ReasonInput(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/roles/{role_id}/archive")
def archive_role(role_id: UUID, b: ReasonInput, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                 actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, MANAGER_CAPABILITY)

    def action(conn):
        role = _role(conn, role_id, for_update=True)
        if role["kind"] != "SCHOOL_CUSTOM" or str(role["school_id"]) != str(actor.school_id):
            raise HTTPException(409, "Seuls les rôles propres à l'école peuvent être archivés")
        n = conn.execute(text("SELECT count(*) FROM rbac_assignments WHERE role_id=:r AND active=true"), {"r": str(role_id)}).scalar_one()
        if n:
            raise HTTPException(409, f"Rôle encore attribué à {n} personne(s) : retirez d'abord ces attributions")
        conn.execute(text("UPDATE rbac_roles SET status='ARCHIVED',version=version+1,updated_at=now() WHERE id=:r"), {"r": str(role_id)})
        out = {"id": str(role_id), "status": "ARCHIVED"}
        _audit(conn, actor, "ACCESS_ROLE_ARCHIVED", "rbac_role", role_id, out, reason=b.reason)
        return 200, out

    return _idempotent(services, actor, idempotency_key, "ACCESS_ROLE_ARCHIVE", {"role": str(role_id), **b.model_dump()}, action)


# --------------------------------------------------------------------------------------- assignments
class ScopeInput(BaseModel):
    type: Literal["SCHOOL", "SECTION", "CLASS"] = "SCHOOL"
    value: str | None = Field(default=None, max_length=64)


class AssignInput(BaseModel):
    role_id: UUID
    scopes: list[ScopeInput] = Field(default_factory=lambda: [ScopeInput()], min_length=1, max_length=20)
    valid_until: datetime | None = None
    reason: str = Field(min_length=3, max_length=500)


@router.post("/members/{membership_id}/roles", status_code=201)
def assign(membership_id: UUID, b: AssignInput, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
           actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, "access.permissions.assign")
    if any(s.type != "SCHOOL" for s in b.scopes):
        _need(actor, "access.scopes.assign")
    if str(membership_id) == str(actor.membership_id):
        raise HTTPException(403, "Refusé : personne ne peut s'attribuer des droits à soi-même")
    if b.valid_until is not None and b.valid_until <= datetime.now(timezone.utc):
        raise HTTPException(422, "La date de fin doit être dans le futur")

    def action(conn):
        m = conn.execute(text("SELECT user_id,active FROM school_memberships WHERE id=:m AND school_id=:s"),
                         {"m": str(membership_id), "s": str(actor.school_id)}).mappings().first()
        if not m:
            raise HTTPException(404, "Membre introuvable dans cette école")
        if not m["active"]:
            raise HTTPException(409, "Ce membre est désactivé")
        role = _role(conn, b.role_id)
        if role["status"] != "ACTIVE" or (role["kind"] == "SCHOOL_CUSTOM" and str(role["school_id"]) != str(actor.school_id)):
            raise HTTPException(404, "Rôle introuvable")
        scopes = []
        for s in b.scopes:
            if s.type == "SCHOOL":
                scopes.append(("SCHOOL", None))
                continue
            value = (s.value or "").strip().upper()
            lookup = SECTION_EXISTS if s.type == "SECTION" else CLASS_EXISTS
            if not value or not conn.execute(lookup,
                                             {"s": str(actor.school_id), "v": value}).first():
                raise HTTPException(422, f"Périmètre inconnu dans cette école : {s.type} {s.value}")
            scopes.append((s.type, value))
        dup = conn.execute(text("SELECT 1 FROM rbac_assignments WHERE membership_id=:m AND role_id=:r AND active=true AND (valid_until IS NULL OR valid_until>now())"),
                           {"m": str(membership_id), "r": str(b.role_id)}).first()
        if dup:
            raise HTTPException(409, "Ce rôle est déjà attribué à ce membre : retirez-le pour changer son périmètre")
        aid = conn.execute(text("""INSERT INTO rbac_assignments(user_id,role_id,school_id,membership_id,valid_until,granted_by_user_id,reason)
              VALUES(:u,:r,:s,:m,:vu,:by,:reason) RETURNING id"""),
                           {"u": str(m["user_id"]), "r": str(b.role_id), "s": str(actor.school_id), "m": str(membership_id),
                            "vu": b.valid_until, "by": str(actor.user_id), "reason": b.reason}).scalar_one()
        for t, v in sorted(set(scopes), key=lambda x: (x[0], x[1] or "")):
            conn.execute(text("INSERT INTO rbac_assignment_scopes(assignment_id,scope_type,scope_value) VALUES(:a,:t,:v)"), {"a": str(aid), "t": t, "v": v})
        out = {"assignment_id": str(aid), "membership_id": str(membership_id), "role_id": str(b.role_id), "role_label": role["label"],
               "scopes": [{"type": t, "value": v} for t, v in scopes], "valid_until": b.valid_until.isoformat() if b.valid_until else None}
        _audit(conn, actor, "ACCESS_ROLE_ASSIGNED", "rbac_assignment", aid, out, reason=b.reason)
        return 201, out

    return _idempotent(services, actor, idempotency_key, "ACCESS_ROLE_ASSIGN", {"membership": str(membership_id), **b.model_dump(mode="json")}, action)


@router.post("/assignments/{assignment_id}/revoke")
def revoke(assignment_id: UUID, b: ReasonInput, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
           actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, "access.permissions.assign")

    def action(conn):
        a = conn.execute(text("""SELECT a.id,a.membership_id,a.active,r.label FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id
              WHERE a.id=:a AND a.school_id=:s FOR UPDATE OF a"""), {"a": str(assignment_id), "s": str(actor.school_id)}).mappings().first()
        if not a:
            raise HTTPException(404, "Attribution introuvable")
        if str(a["membership_id"]) == str(actor.membership_id):
            raise HTTPException(403, "Refusé : personne ne modifie ses propres droits")
        if not a["active"]:
            return 200, {"assignment_id": str(assignment_id), "status": "REVOKED"}
        conn.execute(text("UPDATE rbac_assignments SET active=false,version=version+1,updated_at=now() WHERE id=:a"), {"a": str(assignment_id)})
        _assert_managers_remain(conn, actor.school_id)
        out = {"assignment_id": str(assignment_id), "membership_id": str(a["membership_id"]), "role_label": a["label"], "status": "REVOKED"}
        _audit(conn, actor, "ACCESS_ROLE_REVOKED", "rbac_assignment", assignment_id, out, reason=b.reason)
        return 200, out

    return _idempotent(services, actor, idempotency_key, "ACCESS_ROLE_REVOKE", {"assignment": str(assignment_id), **b.model_dump()}, action)
