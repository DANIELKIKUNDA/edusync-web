"""School access governance — each school sets its own policy (owner decision 2026-10-02).

Standard roles are product baselines maintained by the platform. Since 2026-10-23 a school adjusts a standard role
WITHOUT copying it: `standard role + school GRANT − school REVOKE` (rbac_school_role_policies, migration 0085), so
the role keeps its identity and its future baseline updates. School-owned roles (SCHOOL_CUSTOM) remain for truly new
profiles. Members receive roles with a scope (school / section / class) and an optional end date. Separation of
duties is a set of constraints (ALLOW / WARN / REQUIRE_APPROVAL / BLOCK, application/policies.py); a change that
requires approval becomes a request decided by another access manager. Every change is in the audit journal.

Guardrails, enforced server-side for every school:
  * no self-service: nobody changes their own roles;
  * a school role can never carry a platform capability;
  * the school can never lose its last access manager (access.roles.manage), nor the protected base of a role;
  * standard roles are immutable; custom roles belong to one school only (RLS + trigger);
  * nobody hands over, through a role, an access-governance capability (access.*) they do not hold, nor acts on a
    member holding one they lack (N2 anti-escalation, 2026-10-14).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edusync.modules.access.domain.titles import role_title
from edusync.modules.access.application import policies, projection
from edusync.modules.iam.application import account_links
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


def _user_cards(services: AppServices, user_ids: set[str], school_id: UUID | None = None) -> dict[str, dict]:
    """Names/e-mails for user ids already proven to belong to this school (read under tenant RLS).

    Tenant RLS on users only exposes the caller's own row (privacy); the platform pool resolves
    display names for exactly these ids and nothing else."""
    ids = sorted(i for i in user_ids if i)
    if not ids:
        return {}
    with services.platform_db.platform_transaction() as conn:
        rows = conn.execute(text("""SELECT u.id,u.full_name,u.email,u.must_change_password,
              (CAST(:s AS uuid) IS NOT NULL AND (u.is_platform_admin
                OR EXISTS (SELECT 1 FROM school_memberships o WHERE o.user_id=u.id AND o.school_id<>CAST(:s AS uuid) AND o.active)
                OR EXISTS (SELECT 1 FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id
                           WHERE a.user_id=u.id AND a.school_id IS NULL AND a.active AND r.level='PLATFORM'))) AS shared
            FROM users u WHERE u.id=ANY(CAST(:ids AS uuid[]))"""), {"ids": ids, "s": str(school_id) if school_id else None}).mappings().all()
    # "shared": the account also opens another school or Atelier Pro (its password and name belong to its owner).
    return {str(r["id"]): {"full_name": r["full_name"], "email": str(r["email"]), "must_change_password": bool(r["must_change_password"]),
                           "shared_account": bool(r["shared"])} for r in rows}


def _school_capabilities(conn) -> dict[str, dict]:
    """Capabilities the rights editor offers: ACTIVE ones only (PLANNED, DEPRECATED and ALIAS are hidden, owner
    decision 4) and never a platform capability."""
    rows = conn.execute(text("""SELECT code,domain_name,group_name,label,risk,scope_types FROM capability_catalog
                                WHERE code NOT LIKE 'platform.%' AND NOT (scope_types ? 'PLATFORM') AND lifecycle='ACTIVE'
                                ORDER BY domain_name,group_name,code""")).mappings().all()
    return {r["code"]: dict(r) for r in rows}


def _hidden_caps(conn, caps) -> set[str]:
    """Capabilities of `caps` that the editor does not show (kept untouched when a role is saved)."""
    if not caps:
        return set()
    return {r[0] for r in conn.execute(text("SELECT code FROM capability_catalog WHERE code = ANY(:c) AND lifecycle<>'ACTIVE'"), {"c": list(caps)})}


def _assert_managers_remain(conn, school_id: UUID) -> None:
    policies.assert_managers_remain(conn, school_id)


# Standard leadership roles bound to sections (POINT3B scope policy): Préfet = Secondaire (database trigger 0009),
# Direction de section = Primaire / Maternelle or both. They are never granted on the whole school implicitly.
SECTION_BOUND_ROLES = frozenset({"PREFET_ETUDES", "DIRECTEUR_ETUDES", "DIRECTEUR_DISCIPLINE", "DIRECTION_SECTION"})


def _section_bound(role) -> bool:
    return role["kind"] == "SCHOOL_STANDARD" and role["code"] in SECTION_BOUND_ROLES


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


def _section_labels(conn, school_id) -> dict[str, str]:
    return {r[0]: r[1] for r in conn.execute(text("SELECT upper(code),label FROM school_sections WHERE school_id=:s"), {"s": str(school_id)})}


def _titled(code, kind, label, civility, scopes, labels: dict[str, str]) -> str:
    """Title of one role for one member (civility + sections of a section-bound role) — words only, never rights."""
    secs = [(str(s.get("value") or ""), labels.get(str(s.get("value") or "").upper())) for s in (scopes or []) if s.get("type") == "SECTION"]
    return role_title(code, kind, label, civility, secs)


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
        active = _active_only(conn)
        items = []
        for r in rows:
            item = {**_json(dict(r)), "editable": r["kind"] == "SCHOOL_CUSTOM", "adjustable": r["kind"] == "SCHOOL_STANDARD"}
            # what the role allows HERE (standard role + this school's policy), visible capabilities only
            caps = policies.role_effective(conn, actor.school_id, r["id"]) if r["kind"] == "SCHOOL_STANDARD" else set(r["capabilities"])
            item["capabilities"] = sorted(active(caps))
            item["adjustments"] = len(policies.active_policies(conn, actor.school_id, r["id"])) if r["kind"] == "SCHOOL_STANDARD" else 0
            items.append(item)
    return {"items": items}


@router.get("/members")
def members(q: str | None = Query(None, max_length=120), actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, "access.roles.read")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        rows = conn.execute(text("""SELECT m.id membership_id,m.user_id,m.active,m.civility,
              coalesce(json_agg(json_build_object('assignment_id',a.id,'role_id',r.id,'role_label',r.label,'role_kind',r.kind,'role_code',r.code,
                 'valid_until',a.valid_until,'scopes',(SELECT coalesce(json_agg(json_build_object('type',s.scope_type,'value',s.scope_value)),'[]')
                                                        FROM rbac_assignment_scopes s WHERE s.assignment_id=a.id)) ORDER BY r.label)
                 FILTER (WHERE a.id IS NOT NULL),'[]') roles
              FROM school_memberships m
              LEFT JOIN rbac_assignments a ON a.membership_id=m.id AND a.school_id=m.school_id AND a.active=true AND (a.valid_until IS NULL OR a.valid_until>now())
              LEFT JOIN rbac_roles r ON r.id=a.role_id
              WHERE m.school_id=:sid GROUP BY m.id,m.user_id,m.active,m.civility"""), {"sid": str(actor.school_id)}).mappings().all()
        labels = _section_labels(conn, actor.school_id)
    cards = _user_cards(services, {str(r["user_id"]) for r in rows}, actor.school_id)
    needle = (q or "").strip().lower()
    items = []
    for r in rows:
        card = cards.get(str(r["user_id"]), {"full_name": "Compte inconnu", "email": ""})
        item = {**_json(dict(r)), **card, "is_me": str(r["membership_id"]) == str(actor.membership_id)}
        item["roles"] = [{**x, "title": _titled(x.get("role_code"), x.get("role_kind"), x.get("role_label") or "", r["civility"], x.get("scopes"), labels)}
                         for x in (item.get("roles") or [])]
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
        hidden: set[str] = set()
        if b.clone_from_role_id:
            base = _role(conn, b.clone_from_role_id)
            base_caps = set(_role_caps(conn, base["id"])) if base["kind"] != "SCHOOL_STANDARD" else policies.role_effective(conn, actor.school_id, base["id"])
            hidden = _hidden_caps(conn, base_caps)
            caps = sorted(set(caps) | (base_caps - hidden))
        caps = sorted(set(_validated_caps(conn, caps)) | hidden)
        _assert_can_delegate(actor, caps)  # N2 anti-escalation: a role never carries more than its author holds
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
        caps = sorted(set(_validated_caps(conn, b.capabilities)) | _hidden_caps(conn, before))  # hidden ones are kept
        _assert_can_delegate(actor, set(caps) - set(before))  # N2 anti-escalation on the added capabilities
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
        out = {"id": str(role_id), "label": role["label"], "status": "ARCHIVED"}
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
    acknowledge_warnings: bool = False   # separation of duties: WARN constraints shown to and confirmed by the manager


def _role_caps_here(conn, actor: ActorContext, role: dict) -> set[str]:
    """What a role carries in this school: a standard role with the school's policy, a school role as defined."""
    if role["kind"] == "SCHOOL_STANDARD":
        return policies.role_effective(conn, actor.school_id, role["id"])
    return set(_role_caps(conn, role["id"]))


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
        return _assign_core(conn, actor, membership_id, b)

    return _idempotent(services, actor, idempotency_key, "ACCESS_ROLE_ASSIGN", {"membership": str(membership_id), **b.model_dump(mode="json")}, action)


def _assign_core(conn, actor: ActorContext, membership_id: UUID, b: AssignInput, *, approving: bool = False, request_id=None):
    """Assignment shared by the direct call and the approval of a request (the approver is then `actor`)."""
    m = conn.execute(text("SELECT user_id,active FROM school_memberships WHERE id=:m AND school_id=:s"),
                     {"m": str(membership_id), "s": str(actor.school_id)}).mappings().first()
    if not m:
        raise HTTPException(404, "Membre introuvable dans cette école")
    if not m["active"]:
        raise HTTPException(409, "Ce membre est désactivé")
    role = _role(conn, b.role_id)
    if role["status"] != "ACTIVE" or (role["kind"] == "SCHOOL_CUSTOM" and str(role["school_id"]) != str(actor.school_id)):
        raise HTTPException(404, "Rôle introuvable")
    role_caps = _role_caps_here(conn, actor, role)
    _assert_can_delegate(actor, role_caps)  # N2 anti-escalation: only what the assigner holds
    if _section_bound(role) and any(s.type == "SCHOOL" for s in b.scopes):
        raise HTTPException(422, f"Le rôle « {role['label']} » s’attribue sur une ou plusieurs sections, jamais sur toute l’école")
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
    verdict = policies.evaluate(conn, school_id=actor.school_id, actor=actor, added=role_caps, affected_members=[str(membership_id)],
                                self_hit="Vous êtes la personne concernée" if str(membership_id) == str(actor.membership_id) else None,
                                kind="ROLE_ASSIGNMENT", approving=approving)
    if verdict["effect"] == "BLOCK" or (verdict["effect"] == "WARN" and not (b.acknowledge_warnings or approving)):
        raise policies.sod_error(verdict)
    if verdict["effect"] == "REQUIRE_APPROVAL" and not approving:
        return 202, _create_request(conn, actor, "ROLE_ASSIGNMENT", {"membership_id": str(membership_id), **b.model_dump(mode="json")},
                                    verdict, b.reason, summary=f"Attribuer « {role['label']} »")
    aid = conn.execute(text("""INSERT INTO rbac_assignments(user_id,role_id,school_id,membership_id,valid_until,granted_by_user_id,reason)
          VALUES(:u,:r,:s,:m,:vu,:by,:reason) RETURNING id"""),
                       {"u": str(m["user_id"]), "r": str(b.role_id), "s": str(actor.school_id), "m": str(membership_id),
                        "vu": b.valid_until, "by": str(actor.user_id), "reason": b.reason}).scalar_one()
    try:
        for t, v in sorted(set(scopes), key=lambda x: (x[0], x[1] or "")):
            conn.execute(text("INSERT INTO rbac_assignment_scopes(assignment_id,scope_type,scope_value) VALUES(:a,:t,:v)"), {"a": str(aid), "t": t, "v": v})
    except DBAPIError as e:  # scope rules of a standard role (e.g. Préfet = Secondaire only) are database triggers
        raise HTTPException(422, "Périmètre refusé : " + str(getattr(e.orig, "diag", None) and e.orig.diag.message_primary or "non autorisé pour ce rôle")) from None
    out = {"assignment_id": str(aid), "membership_id": str(membership_id), "role_id": str(b.role_id), "role_label": role["label"],
           "scopes": [{"type": t, "value": v} for t, v in scopes], "valid_until": b.valid_until.isoformat() if b.valid_until else None}
    if verdict["rules"]:
        out["acknowledged_rules"] = [h["rule"] for h in verdict["rules"]]
    if request_id:
        out["request_id"] = str(request_id)
    _audit(conn, actor, "ACCESS_ROLE_ASSIGNED", "rbac_assignment", aid, out, reason=b.reason)
    return 201, out




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


# --------------------------------------------------------------------------------------- members (N2, 2026-10-14)
# The school administrates its own users with the capabilities its owner-approved role already holds
# (migration 0008). Account rows are global (one person may work in several schools), so these operations run on
# the IAM connection and every statement names the school explicitly. Owner decisions of 2026-10-14:
#  * a new account gets a temporary password, shown once, that must be replaced at the first sign-in;
#  * an e-mail already used elsewhere is attached to this school without touching its password;
#  * the administrator may reset a forgotten password (temporary again, sessions ended, audited);
#  * a password or a name is never changed on an account shared with another school or with Atelier Pro: it would
#    hand that other space to this school's administrator.
from edusync.shared.infrastructure.security import hash_password, new_temporary_password  # noqa: E402

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class MemberCreate(BaseModel):
    email: str = Field(min_length=5, max_length=320, pattern=EMAIL_PATTERN)
    full_name: str = Field(min_length=3, max_length=180)
    role_id: UUID | None = None
    # Scopes of that first role; omitted = whole school. Required (sections) for a section-bound leadership role.
    scopes: list[ScopeInput] | None = Field(default=None, min_length=1, max_length=20)
    reason: str = Field(min_length=3, max_length=500)
    # INVITATION: a single-use link e-mailed to the person (no password shown or sent); needs platform e-mail.
    delivery: str = Field(default="TEMPORARY_PASSWORD", pattern="^(TEMPORARY_PASSWORD|INVITATION)$")
    # Monsieur / Madame (owner, 2026-11-09): titles in the feminine (« Promotrice », « Directrice de la maternelle »).
    civility: str | None = Field(default=None, pattern="^(M|MME)$")


class MemberUpdate(BaseModel):
    full_name: str = Field(min_length=3, max_length=180)
    reason: str = Field(min_length=3, max_length=500)
    # M / MME, or NONE to clear; omitted = unchanged.
    civility: str | None = Field(default=None, pattern="^(M|MME|NONE)$")


def _member_caps(conn, school_id: UUID, membership_id) -> set[str]:
    """School capabilities currently held by a member (active roles with the school's policies, any scope)."""
    return policies.member_effective(conn, school_id, membership_id)


GOVERNANCE_PREFIX = "access."


def _governance(capabilities) -> set[str]:
    return {c for c in capabilities if c.startswith(GOVERNANCE_PREFIX)}


def _assert_can_delegate(actor: ActorContext, capabilities) -> None:
    """Anti-escalation on governance power: nobody hands over (through a role) an access-governance capability they
    do not hold themselves. Business capabilities (finance, schooling…) are what the access manager assigns without
    holding them: the owner-approved ADMIN_SYSTEME_ECOLE administers access, not cash (migration 0008)."""
    lacking = sorted(_governance(capabilities) - set(actor.permissions))
    if lacking and not actor.is_platform_admin:
        raise HTTPException(403, "Refusé : ce rôle donne des droits de gestion des accès que vous n’avez pas vous-même (" + ", ".join(lacking[:3]) + ("…" if len(lacking) > 3 else "") + ")")


def _account_shared(conn, user_id, school_id: UUID) -> bool:
    """The account also opens another school or the platform console."""
    return bool(conn.execute(text("""SELECT 1 FROM school_memberships WHERE user_id=:u AND school_id<>:s AND active
        UNION ALL SELECT 1 FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id
          WHERE a.user_id=:u AND a.school_id IS NULL AND a.active AND r.level='PLATFORM'
        UNION ALL SELECT 1 FROM users WHERE id=:u AND is_platform_admin LIMIT 1"""), {"u": str(user_id), "s": str(school_id)}).first())


def _target(conn, actor: ActorContext, membership_id: UUID) -> dict:
    row = conn.execute(text("""SELECT m.id, m.user_id, m.active, m.version FROM school_memberships m
        WHERE m.id=:m AND m.school_id=:s FOR UPDATE OF m"""), {"m": str(membership_id), "s": str(actor.school_id)}).mappings().first()
    if not row:
        raise HTTPException(404, "Membre introuvable dans cette école")
    if str(membership_id) == str(actor.membership_id):
        raise HTTPException(403, "Refusé : cette action ne s’applique pas à votre propre compte (utilisez « Sécurité et appareils »)")
    lacking = _governance(_member_caps(conn, actor.school_id, membership_id)) - set(actor.permissions)
    if lacking and not actor.is_platform_admin:
        raise HTTPException(403, "Refusé : ce membre détient des droits de gestion des accès que vous n’avez pas")
    return dict(row)


def _idempotent_iam(services: AppServices, actor: ActorContext, key: str | None, operation: str, payload: dict, action):
    if not (key or "").strip():
        raise HTTPException(400, "Idempotency-Key obligatoire")
    try:
        with services.platform_db.platform_transaction() as conn:
            result = IdempotentExecutor(PostgresIdempotencyRepository(conn)).execute(
                scope_key=str(actor.school_id), idempotency_key=key, operation=operation, payload=payload,
                school_id=str(actor.school_id), actor_user_id=str(actor.user_id), action=lambda: action(conn))
            return result.body
    except (IdempotencyConflict, IdempotencyInProgress) as e:
        raise HTTPException(409, str(e)) from e


def _revoke_member_sessions(conn, school_id: UUID, membership_id, reason: str) -> int:
    return conn.execute(text("""UPDATE user_device_sessions SET revoked_at=coalesce(revoked_at,now()),revoked_reason=coalesce(revoked_reason,:r)
        WHERE school_id=:s AND membership_id=:m AND revoked_at IS NULL"""), {"s": str(school_id), "m": str(membership_id), "r": reason}).rowcount


@router.post("/members", status_code=201)
def create_member(b: MemberCreate, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                  actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """New account with a temporary password (shown once), or an existing account attached without its password."""
    _need(actor, "access.users.create")
    if b.role_id:
        _need(actor, "access.permissions.assign")
    if b.scopes and any(s.type != "SCHOOL" for s in b.scopes):
        _need(actor, "access.scopes.assign")
    # Section / class codes are school data: checked in a tenant transaction (the member itself is written through the
    # platform connection, which has no access to school_sections).
    first_scopes = [("SCHOOL", None)]
    if b.scopes:
        first_scopes = []
        with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as tconn:
            for s in b.scopes:
                value = (s.value or "").strip().upper() if s.type != "SCHOOL" else None
                if s.type != "SCHOOL" and (not value or not tconn.execute(SECTION_EXISTS if s.type == "SECTION" else CLASS_EXISTS,
                                                                         {"s": str(actor.school_id), "v": value}).first()):
                    raise HTTPException(422, f"Périmètre inconnu dans cette école : {s.type} {s.value}")
                first_scopes.append((s.type, value))
    email = b.email.strip().lower()
    # The temporary password is never part of the idempotency payload nor of the audit.
    payload = {"email": email, "full_name": b.full_name.strip(), "role_id": str(b.role_id) if b.role_id else None, "reason": b.reason,
               "delivery": b.delivery, "scopes": [s.model_dump() for s in b.scopes] if b.scopes else None}
    invite = b.delivery == "INVITATION"
    if invite and not account_links.email_available(services.settings):
        raise HTTPException(409, "L’envoi d’e-mails n’est pas disponible sur la plateforme : utilisez un mot de passe provisoire")

    issued: dict = {}  # the temporary password lives only in this request, never in the idempotency registry

    def action(conn):
        temporary = None
        user = conn.execute(text("SELECT id, active, full_name FROM users WHERE lower(email::text)=:e FOR UPDATE"), {"e": email}).mappings().first()
        if user and not user["active"]:
            raise HTTPException(409, "Ce compte EduSync est désactivé : il ne peut pas être rattaché")
        if user:
            existing = conn.execute(text("SELECT id, active FROM school_memberships WHERE user_id=:u AND school_id=:s"),
                                    {"u": str(user["id"]), "s": str(actor.school_id)}).mappings().first()
            if existing:
                raise HTTPException(409, "Cette personne est déjà membre de l’école" + ("" if existing["active"] else " (désactivée : réactivez-la)"))
            uid, created = user["id"], False
        else:
            # Invitation: the account gets an unknown random password until the person chooses one through the link.
            temporary = None if invite else new_temporary_password()
            secret_pw = temporary or new_temporary_password() + new_temporary_password()
            uid = conn.execute(text("""INSERT INTO users(email,full_name,password_hash,active,is_platform_admin,version,must_change_password,password_set_by)
                VALUES(:e,:n,:p,true,false,1,:must,'SCHOOL') RETURNING id"""), {"e": email, "n": b.full_name.strip(), "p": hash_password(secret_pw),
                                                                       "must": not invite}).scalar_one()
            created = True
        mid = conn.execute(text("INSERT INTO school_memberships(id,school_id,user_id,active,created_at,version,civility) VALUES(gen_random_uuid(),:s,:u,true,now(),1,:c) RETURNING id"),
                           {"s": str(actor.school_id), "u": str(uid), "c": b.civility}).scalar_one()
        role_label = None
        if b.role_id:
            role = _role(conn, b.role_id)
            if role["status"] != "ACTIVE" or (role["kind"] == "SCHOOL_CUSTOM" and str(role["school_id"]) != str(actor.school_id)):
                raise HTTPException(404, "Rôle introuvable")
            _assert_can_delegate(actor, _role_caps_here(conn, actor, role))
            scopes = first_scopes
            if _section_bound(role) and any(t == "SCHOOL" for t, _ in scopes):
                raise HTTPException(422, f"Le rôle « {role['label']} » s’attribue sur une ou plusieurs sections : choisissez sa ou ses sections")
            aid = conn.execute(text("""INSERT INTO rbac_assignments(user_id,role_id,school_id,membership_id,granted_by_user_id,reason)
                VALUES(:u,:r,:s,:m,:by,:reason) RETURNING id"""), {"u": str(uid), "r": str(b.role_id), "s": str(actor.school_id), "m": str(mid),
                                                                    "by": str(actor.user_id), "reason": b.reason}).scalar_one()
            try:
                for t, v in sorted(set(scopes), key=lambda x: (x[0], x[1] or "")):
                    conn.execute(text("INSERT INTO rbac_assignment_scopes(assignment_id,scope_type,scope_value) VALUES(:a,:t,:v)"),
                                 {"a": str(aid), "t": t, "v": v})
            except DBAPIError as e:  # scope rules of a standard role (e.g. Préfet = Secondaire only) are database triggers
                raise HTTPException(422, "Périmètre refusé : " + str(getattr(e.orig, "diag", None) and e.orig.diag.message_primary or "non autorisé pour ce rôle")) from None
            role_label = role["label"]
        out = {"membership_id": str(mid), "email": email, "full_name": b.full_name.strip() if created else user["full_name"],
               "created": created, "attached_existing_account": not created, "role_label": role_label}
        if created and invite:
            raw = account_links.issue(conn, services.settings, user_id=uid, purpose=account_links.INVITATION, school_id=actor.school_id,
                                      membership_id=mid, created_by=actor.user_id)
            account_links.send_link_email(conn, services.settings, user_id=uid, email=email, full_name=b.full_name.strip(),
                                          purpose=account_links.INVITATION, raw=raw, school_id=actor.school_id, created_by=actor.user_id)
            out["invitation_sent"] = True
        _audit(conn, actor, "ACCESS_MEMBER_CREATED" if created else "ACCESS_MEMBER_ATTACHED", "school_membership", mid, out, reason=b.reason)
        issued["temporary_password"] = temporary
        return 201, out

    body = _idempotent_iam(services, actor, idempotency_key, "ACCESS_MEMBER_CREATE", payload, action)
    # Shown once to the administrator. A replay (lost response, double click) gets no password: reset it if needed.
    return {**body, "temporary_password": issued.get("temporary_password")}


@router.patch("/members/{membership_id}")
def update_member(membership_id: UUID, b: MemberUpdate, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                  actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, "access.users.update")

    def action(conn):
        m = _target(conn, actor, membership_id)
        old = conn.execute(text("SELECT full_name FROM users WHERE id=:u"), {"u": str(m["user_id"])}).scalar_one()
        renamed = (old or "").strip() != b.full_name.strip()
        # the civility belongs to this school's membership: it may be set even for an account shared with another space
        if renamed and _account_shared(conn, m["user_id"], actor.school_id):
            raise HTTPException(409, "Compte partagé avec un autre espace EduSync : seul son titulaire peut modifier son nom")
        if renamed:
            conn.execute(text("UPDATE users SET full_name=:n WHERE id=:u"), {"n": b.full_name.strip(), "u": str(m["user_id"])})
        out = {"membership_id": str(membership_id), "full_name": b.full_name.strip()}
        oldc = conn.execute(text("SELECT civility FROM school_memberships WHERE id=:m AND school_id=:s"), {"m": str(membership_id), "s": str(actor.school_id)}).scalar()
        if b.civility is not None:
            newc = None if b.civility == "NONE" else b.civility
            conn.execute(text("UPDATE school_memberships SET civility=:c WHERE id=:m AND school_id=:s"), {"c": newc, "m": str(membership_id), "s": str(actor.school_id)})
            out["civility"] = newc
        _audit(conn, actor, "ACCESS_MEMBER_UPDATED", "school_membership", membership_id, out, reason=b.reason, old={"full_name": old, "civility": oldc})
        return 200, out

    return _idempotent_iam(services, actor, idempotency_key, "ACCESS_MEMBER_UPDATE", {"membership": str(membership_id), **b.model_dump()}, action)


def _set_member_active(membership_id: UUID, active: bool, b: ReasonInput, key: str | None, actor: ActorContext, services: AppServices):
    _need(actor, "access.users.activate")

    def action(conn):
        m = _target(conn, actor, membership_id)
        if bool(m["active"]) == active:
            return 200, {"membership_id": str(membership_id), "active": active, "unchanged": True}
        # The membership version moves on: tokens of this school carry it and stop working at once.
        conn.execute(text("UPDATE school_memberships SET active=:a, version=version+1 WHERE id=:m AND school_id=:s"),
                     {"a": active, "m": str(membership_id), "s": str(actor.school_id)})
        revoked = 0
        if not active:
            _assert_managers_remain(conn, actor.school_id)
            revoked = _revoke_member_sessions(conn, actor.school_id, membership_id, "MEMBER_DEACTIVATED")
            # Push devices of this membership stop receiving; open invitations of this membership die.
            conn.execute(text("""UPDATE push_subscriptions SET revoked_at=now(), revoked_reason='MEMBER_DEACTIVATED'
                WHERE membership_id=:m AND revoked_at IS NULL"""), {"m": str(membership_id)})
            conn.execute(text("""UPDATE account_tokens SET revoked_at=now(), revoked_reason='MEMBER_DEACTIVATED'
                WHERE membership_id=:m AND used_at IS NULL AND revoked_at IS NULL"""), {"m": str(membership_id)})
        out = {"membership_id": str(membership_id), "active": active, "sessions_revoked": revoked}
        _audit(conn, actor, "ACCESS_MEMBER_ACTIVATED" if active else "ACCESS_MEMBER_DEACTIVATED", "school_membership", membership_id, out, reason=b.reason)
        return 200, out

    return _idempotent_iam(services, actor, key, "ACCESS_MEMBER_ACTIVATE" if active else "ACCESS_MEMBER_DEACTIVATE",
                           {"membership": str(membership_id), **b.model_dump()}, action)


@router.post("/members/{membership_id}/deactivate")
def deactivate_member(membership_id: UUID, b: ReasonInput, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                      actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """Ends this person's access to this school only (sessions of this school end now); the account stays valid elsewhere."""
    return _set_member_active(membership_id, False, b, idempotency_key, actor, services)


@router.post("/members/{membership_id}/activate")
def activate_member(membership_id: UUID, b: ReasonInput, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                    actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    return _set_member_active(membership_id, True, b, idempotency_key, actor, services)


@router.post("/members/{membership_id}/credentials-reset")
def reset_member_credentials(membership_id: UUID, b: ReasonInput, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                             actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """Forgotten password: a new temporary password (shown once, to be replaced at the next sign-in); every session of
    the account ends. Refused for an account shared with another school or with Atelier Pro."""
    _need(actor, "access.users.credentials.reset")
    if not (idempotency_key or "").strip():
        raise HTTPException(400, "Idempotency-Key obligatoire")
    # Not replayable on purpose: a lost response is answered by a new reset, never by re-sending an old password.
    with services.platform_db.platform_transaction() as conn:
        m = _target(conn, actor, membership_id)
        if not m["active"]:
            raise HTTPException(409, "Ce membre est désactivé : réactivez-le d’abord")
        if _account_shared(conn, m["user_id"], actor.school_id):
            raise HTTPException(409, "Compte partagé avec un autre espace EduSync : la réinitialisation revient à son titulaire ou à la plateforme")
        temporary = new_temporary_password()
        conn.execute(text("""UPDATE users SET password_hash=:p, version=version+1, must_change_password=true, password_set_by='SCHOOL' WHERE id=:u"""),
                     {"p": hash_password(temporary), "u": str(m["user_id"])})
        revoked = conn.execute(text("""UPDATE user_device_sessions SET revoked_at=coalesce(revoked_at,now()),revoked_reason=coalesce(revoked_reason,'PASSWORD_RESET')
            WHERE user_id=:u AND revoked_at IS NULL"""), {"u": str(m["user_id"])}).rowcount
        out = {"membership_id": str(membership_id), "sessions_revoked": revoked, "must_change_password": True}
        _audit(conn, actor, "ACCESS_MEMBER_CREDENTIALS_RESET", "school_membership", membership_id, out, reason=b.reason)
    return {**out, "temporary_password": temporary}


# --------------------------------------------------------------------------------------- school role policies (2026-10-23)
def _dumps(value) -> str:
    import json
    return json.dumps(_json(value), ensure_ascii=False)


def _create_request(conn, actor: ActorContext, kind: str, payload: dict, verdict: dict, reason: str, *, summary: str) -> dict:
    rid = conn.execute(text("""INSERT INTO rbac_change_requests(school_id,kind,payload,rules,reason,requested_by_user_id,requested_by_membership_id)
        VALUES(:s,:k,CAST(:p AS jsonb),CAST(:r AS jsonb),:reason,:u,:m) RETURNING id"""),
        {"s": str(actor.school_id), "k": kind, "p": _dumps({**payload, "summary": summary}), "r": _dumps(verdict["rules"]),
         "reason": reason, "u": str(actor.user_id), "m": str(actor.membership_id)}).scalar_one()
    out = {"status": "PENDING_APPROVAL", "request_id": str(rid), "kind": kind, "summary": summary, "rules": verdict["rules"],
           "message": "Demande enregistrée : un autre gestionnaire des accès doit l’approuver."}
    _audit(conn, actor, "ACCESS_CHANGE_REQUESTED", "rbac_change_request", rid, out, reason=reason)
    return out


def _holds_role(conn, actor: ActorContext, role_id) -> bool:
    return bool(conn.execute(text("""SELECT 1 FROM rbac_assignments WHERE role_id=:r AND membership_id=:m AND active
        AND (valid_until IS NULL OR valid_until>now()) LIMIT 1"""), {"r": str(role_id), "m": str(actor.membership_id)}).first())


def _active_only(conn):
    cat = policies.catalog(conn)
    return lambda caps: {c for c in caps if cat.get(c, {}).get("lifecycle") == "ACTIVE"}


class PolicyInput(BaseModel):
    capabilities: list[str] = Field(max_length=400)   # what the standard role must allow in this school (ACTIVE codes)
    reason: str = Field(min_length=5, max_length=500)
    acknowledge_warnings: bool = False


@router.get("/roles/{role_id}/policy")
def role_policy(role_id: UUID, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """A role in this school: platform baseline, school adjustments, protected base, effective result."""
    _need(actor, "access.roles.read")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        role = _role(conn, role_id)
        active = _active_only(conn)
        standard = role["kind"] == "SCHOOL_STANDARD"
        base = policies.baseline(conn, role_id)
        effective = policies.role_effective(conn, actor.school_id, role_id) if standard else base
        pol = policies.active_policies(conn, actor.school_id, role_id) if standard else []
        lock = policies.locked(conn, role_id)
        pending = conn.execute(text("""SELECT id,created_at,payload->>'summary' summary FROM rbac_change_requests
            WHERE school_id=:s AND status='PENDING' AND payload->>'role_id'=:r ORDER BY created_at"""),
                               {"s": str(actor.school_id), "r": str(role_id)}).mappings().all()
        holders = len(policies.holders(conn, actor.school_id, role_id))
        mine = _holds_role(conn, actor, role_id)
    cards = _user_cards(services, {str(p["created_by_user_id"]) for p in pol if p["created_by_user_id"]})
    return {"role": _json(role), "adjustable": standard, "holders": holders, "held_by_me": mine,
            "baseline": sorted(active(base)), "effective": sorted(active(effective)), "locked": sorted(lock),
            "policies": [{**_json({k: v for k, v in p.items() if k != "created_by_user_id"}),
                          "by": cards.get(str(p["created_by_user_id"]), {}).get("full_name")} for p in pol],
            "pending_requests": [_json(dict(r)) for r in pending]}


@router.put("/roles/{role_id}/policy")
def update_role_policy(role_id: UUID, b: PolicyInput, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                       actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """Adjust a standard role for this school (GRANT / REVOKE), keeping its identity. Separation of duties applies."""
    _need(actor, MANAGER_CAPABILITY)

    def action(conn):
        return _apply_policy(conn, actor, role_id, set(b.capabilities), b.reason, acknowledge=b.acknowledge_warnings)

    return _idempotent(services, actor, idempotency_key, "ACCESS_ROLE_POLICY", {"role": str(role_id), **b.model_dump(mode="json")}, action)


def _apply_policy(conn, actor: ActorContext, role_id: UUID, desired: set[str], reason: str, *, acknowledge: bool,
                  approving: bool = False, request_id=None):
    role = _role(conn, role_id)
    if role["status"] != "ACTIVE":
        raise HTTPException(409, "Rôle archivé")
    conn.execute(text("SELECT 1 FROM rbac_roles WHERE id=:id FOR UPDATE"), {"id": str(role_id)})
    plan = policies.plan_role_policy(conn, school_id=actor.school_id, role=role, desired=desired)
    if not plan["create"] and not plan["withdraw"]:
        return 200, {"role_id": str(role_id), "status": "UNCHANGED", "added": [], "removed": []}
    _assert_can_delegate(actor, plan["added"])
    verdict = policies.evaluate(conn, school_id=actor.school_id, actor=actor, added=set(plan["added"]),
                                affected_members=policies.holders(conn, actor.school_id, role_id),
                                self_hit="Vous détenez ce rôle" if _holds_role(conn, actor, role_id) else None,
                                kind="ROLE_POLICY", approving=approving)
    if verdict["effect"] == "BLOCK" or (verdict["effect"] == "WARN" and not (acknowledge or approving)):
        raise policies.sod_error(verdict)
    if verdict["effect"] == "REQUIRE_APPROVAL" and not approving:
        return 202, _create_request(conn, actor, "ROLE_POLICY", {"role_id": str(role_id), "capabilities": sorted(desired)}, verdict, reason,
                                    summary=f"Ajuster « {role['label']} » : +{len(plan['added'])} / −{len(plan['removed'])}")
    policies.apply_role_policy(conn, school_id=actor.school_id, role_id=role_id, plan=plan, reason=reason, user_id=actor.user_id, request_id=request_id)
    policies.assert_managers_remain(conn, actor.school_id)
    out = {"role_id": str(role_id), "role_label": role["label"], "status": "APPLIED", "added": plan["added"], "removed": plan["removed"],
           "grants": plan["grants"], "revokes": plan["revokes"], "acknowledged_rules": [h["rule"] for h in verdict["rules"]],
           "request_id": str(request_id) if request_id else None}
    _audit(conn, actor, "ACCESS_ROLE_POLICY_UPDATED", "rbac_role", role_id, out, reason=reason)
    return 200, out


# --------------------------------------------------------------------------------------- change requests
@router.get("/requests")
def change_requests(status: str = Query("PENDING", pattern="^(PENDING|ALL)$"), actor: ActorContext = Depends(require_school_actor),
                    services: AppServices = Depends(get_services)):
    _need(actor, "access.roles.read")
    only_pending = "AND status='PENDING'" if status == "PENDING" else ""
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        rows = conn.execute(text(f"""SELECT id,kind,payload,rules,status,reason,requested_by_user_id,decided_by_user_id,decided_at,decision_reason,created_at
              FROM rbac_change_requests WHERE school_id=:s {only_pending} ORDER BY created_at DESC LIMIT 100"""), {"s": str(actor.school_id)}).mappings().all()
    cards = _user_cards(services, {str(r["requested_by_user_id"]) for r in rows} | {str(r["decided_by_user_id"]) for r in rows if r["decided_by_user_id"]})
    items = []
    for r in rows:
        item = _json(dict(r))
        item["requested_by"] = cards.get(str(r["requested_by_user_id"]), {}).get("full_name")
        item["decided_by"] = cards.get(str(r["decided_by_user_id"]), {}).get("full_name") if r["decided_by_user_id"] else None
        item["mine"] = str(r["requested_by_user_id"]) == str(actor.user_id)
        item["can_decide"] = r["status"] == "PENDING" and not item["mine"] and MANAGER_CAPABILITY in actor.permissions
        item.pop("requested_by_user_id", None)
        item.pop("decided_by_user_id", None)
        items.append(item)
    return {"items": items}


class DecisionInput(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


def _request_for_update(conn, actor: ActorContext, request_id: UUID) -> dict:
    r = conn.execute(text("SELECT * FROM rbac_change_requests WHERE id=:id AND school_id=:s FOR UPDATE"),
                     {"id": str(request_id), "s": str(actor.school_id)}).mappings().first()
    if not r:
        raise HTTPException(404, "Demande introuvable")
    if r["status"] != "PENDING":
        raise HTTPException(409, "Demande déjà traitée")
    return dict(r)


SELF_APPROVAL = {"effect": "BLOCK", "rules": [{"rule": "SELF_ELEVATION", "label": "Personne n’approuve sa propre demande",
                                               "effect": "BLOCK", "detail": "Vous avez fait cette demande"}]}


@router.post("/requests/{request_id}/approve")
def approve_request(request_id: UUID, b: DecisionInput, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                    actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """A second access manager approves: never the requester (SELF_ELEVATION, also a database CHECK), never a change
    that elevates the approver's own rights. The change is re-evaluated against the current state when approved."""
    _need(actor, MANAGER_CAPABILITY)

    def action(conn):
        r = _request_for_update(conn, actor, request_id)
        if str(r["requested_by_user_id"]) == str(actor.user_id):
            raise policies.sod_error(SELF_APPROVAL)
        payload = r["payload"]
        if r["kind"] == "ROLE_POLICY":
            _, result = _apply_policy(conn, actor, UUID(payload["role_id"]), set(payload["capabilities"]), r["reason"],
                                      acknowledge=True, approving=True, request_id=request_id)
        else:
            body = AssignInput(**{k: v for k, v in payload.items() if k in AssignInput.model_fields})
            _, result = _assign_core(conn, actor, UUID(payload["membership_id"]), body, approving=True, request_id=request_id)
        conn.execute(text("""UPDATE rbac_change_requests SET status='APPROVED', decided_by_user_id=:u, decided_at=now(), decision_reason=:d WHERE id=:id"""),
                     {"u": str(actor.user_id), "d": b.reason, "id": str(request_id)})
        out = {"request_id": str(request_id), "status": "APPROVED", "result": result}
        _audit(conn, actor, "ACCESS_CHANGE_APPROVED", "rbac_change_request", request_id, out, reason=b.reason)
        return 200, out

    return _idempotent(services, actor, idempotency_key, "ACCESS_REQUEST_APPROVE", {"request": str(request_id), **b.model_dump()}, action)


@router.post("/requests/{request_id}/reject")
def reject_request(request_id: UUID, b: DecisionInput, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                   actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """Another manager rejects; the requester may withdraw (cancel) their own request."""
    _need(actor, MANAGER_CAPABILITY)

    def action(conn):
        r = _request_for_update(conn, actor, request_id)
        mine = str(r["requested_by_user_id"]) == str(actor.user_id)
        status = "CANCELLED" if mine else "REJECTED"
        conn.execute(text("""UPDATE rbac_change_requests SET status=:st, decided_by_user_id=:u, decided_at=now(), decision_reason=:d WHERE id=:id"""),
                     {"st": status, "u": str(actor.user_id), "d": b.reason, "id": str(request_id)})
        out = {"request_id": str(request_id), "status": status}
        _audit(conn, actor, f"ACCESS_CHANGE_{status}", "rbac_change_request", request_id, out, reason=b.reason)
        return 200, out

    return _idempotent(services, actor, idempotency_key, "ACCESS_REQUEST_REJECT", {"request": str(request_id), **b.model_dump()}, action)


# --------------------------------------------------------------------------------------- separation of duties
@router.get("/sod")
def sod_rules(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, "access.roles.read")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        items = policies.rules(conn, actor.school_id)
    return {"items": [_json(r) for r in items], "effects": policies.SEVERITY}


class SodInput(BaseModel):
    effect: Literal["ALLOW", "WARN", "REQUIRE_APPROVAL", "BLOCK"]
    reason: str = Field(min_length=5, max_length=500)


@router.put("/sod/{code}")
def update_sod(code: str, b: SodInput, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
               actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """The school sets its own level for an overridable constraint; critical rules (SELF_ELEVATION) are fixed."""
    _need(actor, MANAGER_CAPABILITY)

    def action(conn):
        rule = next((r for r in policies.rules(conn, actor.school_id) if r["code"] == code), None)
        if rule is None:
            raise HTTPException(404, "Règle introuvable")
        if not rule["school_overridable"]:
            raise HTTPException(409, "Règle critique : son niveau est fixé par la plateforme")
        conn.execute(text("""INSERT INTO rbac_school_sod_overrides(school_id,rule_code,effect,reason,updated_by_user_id)
            VALUES(:s,:c,:e,:r,:u) ON CONFLICT (school_id,rule_code) DO UPDATE SET effect=EXCLUDED.effect, reason=EXCLUDED.reason,
            updated_by_user_id=EXCLUDED.updated_by_user_id, updated_at=now(), version=rbac_school_sod_overrides.version+1"""),
                     {"s": str(actor.school_id), "c": code, "e": b.effect, "r": b.reason, "u": str(actor.user_id)})
        out = {"rule": code, "effect": b.effect, "previous": rule["effect"]}
        _audit(conn, actor, "ACCESS_SOD_RULE_UPDATED", "rbac_sod_rule", uuid4(), out, reason=b.reason)
        return 200, out

    return _idempotent(services, actor, idempotency_key, "ACCESS_SOD_UPDATE", {"rule": code, **b.model_dump()}, action)


# --------------------------------------------------------------------------------------- assisted conversion of a cloned role
def _member_roles(conn, actor: ActorContext, membership_id: str) -> list[str]:
    return [str(r[0]) for r in conn.execute(text("""SELECT role_id FROM rbac_assignments WHERE school_id=:s AND membership_id=:m AND active
        AND valid_from<=now() AND (valid_until IS NULL OR valid_until>now())"""), {"s": str(actor.school_id), "m": membership_id})]


def _member_exceptions(conn, actor: ActorContext, membership_id: str) -> set[str]:
    return {r[0] for r in conn.execute(text("""SELECT capability_code FROM rbac_exception_grants WHERE school_id=:s AND membership_id=:m
        AND active AND valid_from<=now() AND valid_until>now()"""), {"s": str(actor.school_id), "m": membership_id})}


def _conversion(conn, actor: ActorContext, custom_id: UUID, standard_id: UUID | None) -> dict:
    """Proof-based conversion of a SCHOOL_CUSTOM clone into « standard role + school policy ». Never automatic: every
    member holding either role is simulated; the conversion is refused if one of them would gain or lose an ACTIVE
    capability (format aliases follow their canonical *.export, PLANNED / DEPRECATED capabilities protect nothing)."""
    custom = _role(conn, custom_id)
    if custom["kind"] != "SCHOOL_CUSTOM" or str(custom["school_id"]) != str(actor.school_id) or custom["status"] != "ACTIVE":
        raise HTTPException(409, "Seul un rôle actif propre à l’école se convertit")
    active = _active_only(conn)
    custom_caps = active(_role_caps(conn, custom_id))
    standards = [dict(r) for r in conn.execute(text("""SELECT id,code,label,kind,school_id,status,description,version FROM rbac_roles
        WHERE kind='SCHOOL_STANDARD' AND status='ACTIVE'""")).mappings()]
    def score(r):
        base = active(policies.baseline(conn, r["id"]))
        return len(custom_caps & base) / max(1, len(custom_caps | base))
    candidates = sorted(({"id": str(r["id"]), "label": r["label"], "similarity": round(score(r), 3)} for r in standards), key=lambda x: -x["similarity"])
    wanted = str(standard_id) if standard_id else candidates[0]["id"]
    target = next((r for r in standards if str(r["id"]) == wanted), None)
    if target is None:
        raise HTTPException(404, "Rôle standard introuvable")
    plan = policies.plan_role_policy(conn, school_id=actor.school_id, role=target, desired=custom_caps)
    new_target = active((policies.baseline(conn, target["id"]) - set(plan["revokes"])) | set(plan["grants"]))
    members = sorted(set(policies.holders(conn, actor.school_id, custom_id)) | set(policies.holders(conn, actor.school_id, target["id"])))
    proof, blockers = [], []
    for mid in members:
        held = _member_roles(conn, actor, mid)
        before = active(policies.member_effective(conn, actor.school_id, mid))
        after = active(_member_exceptions(conn, actor, mid))
        for rid in held:
            after |= new_target if rid in (str(custom_id), str(target["id"])) else active(_role_caps_here(conn, actor, _role(conn, rid)))
        if str(custom_id) in held and str(target["id"]) in held:
            blockers.append({"membership_id": mid, "reason": "détient déjà le rôle standard et le rôle à convertir"})
        elif before != after:
            blockers.append({"membership_id": mid, "gained": sorted(after - before), "lost": sorted(before - after)})
        proof.append({"membership_id": mid, "identical": before == after, "before": sorted(before)})
    return {"custom": _json(custom), "target": _json(target), "candidates": candidates[:3],
            "plan": {"grants": plan["grants"], "revokes": plan["revokes"]},
            "members": [{k: v for k, v in m.items() if k != "before"} for m in proof], "blockers": blockers,
            "convertible": not blockers, "_proof": proof}


@router.get("/roles/{role_id}/conversion-preview")
def conversion_preview(role_id: UUID, standard_role_id: UUID | None = Query(None), actor: ActorContext = Depends(require_school_actor),
                       services: AppServices = Depends(get_services)):
    _need(actor, "access.roles.read")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        out = _conversion(conn, actor, role_id, standard_role_id)
    out.pop("_proof")
    return out


class ConvertInput(BaseModel):
    standard_role_id: UUID
    reason: str = Field(min_length=5, max_length=500)


@router.post("/roles/{role_id}/convert")
def convert_role(role_id: UUID, b: ConvertInput, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                 actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """Applies a conversion whose simulation proves nobody's effective capabilities change, reassigns the members (same
    scopes and end dates), archives the clone, then re-checks every member in the same transaction. Audited."""
    _need(actor, MANAGER_CAPABILITY)
    _need(actor, "access.permissions.assign")

    def action(conn):
        preview = _conversion(conn, actor, role_id, b.standard_role_id)
        if not preview["convertible"]:
            raise HTTPException(409, {"code": "CONVERSION_NOT_IDENTICAL", "message": "Conversion refusée : des droits effectifs changeraient",
                                      "blockers": preview["blockers"]})
        if _holds_role(conn, actor, role_id) or _holds_role(conn, actor, b.standard_role_id):
            raise policies.sod_error({"effect": "BLOCK", "rules": [{"rule": "SELF_ELEVATION", "label": "Personne ne convertit un rôle qu’il détient",
                                                                     "effect": "BLOCK", "detail": "Vous détenez l’un de ces rôles"}]})
        target = _role(conn, b.standard_role_id)
        active = _active_only(conn)
        plan = policies.plan_role_policy(conn, school_id=actor.school_id, role=target, desired=active(_role_caps(conn, role_id)))
        policies.apply_role_policy(conn, school_id=actor.school_id, role_id=target["id"], plan=plan, reason=b.reason, user_id=actor.user_id)
        moved = 0
        for a in conn.execute(text("""SELECT id,user_id,membership_id,valid_until FROM rbac_assignments WHERE role_id=:r AND school_id=:s AND active
                AND (valid_until IS NULL OR valid_until>now())"""), {"r": str(role_id), "s": str(actor.school_id)}).mappings().all():
            scopes = conn.execute(text("SELECT scope_type,scope_value FROM rbac_assignment_scopes WHERE assignment_id=:a"), {"a": str(a["id"])}).all()
            conn.execute(text("UPDATE rbac_assignments SET active=false,version=version+1,updated_at=now() WHERE id=:a"), {"a": str(a["id"])})
            nid = conn.execute(text("""INSERT INTO rbac_assignments(user_id,role_id,school_id,membership_id,valid_until,granted_by_user_id,reason)
                VALUES(:u,:r,:s,:m,:vu,:by,:reason) RETURNING id"""), {"u": str(a["user_id"]), "r": str(target["id"]), "s": str(actor.school_id),
                                                                     "m": str(a["membership_id"]), "vu": a["valid_until"], "by": str(actor.user_id),
                                                                     "reason": "Conversion assistée : " + b.reason}).scalar_one()
            for t, v in scopes:
                conn.execute(text("INSERT INTO rbac_assignment_scopes(assignment_id,scope_type,scope_value) VALUES(:a,:t,:v)"), {"a": str(nid), "t": t, "v": v})
            moved += 1
        conn.execute(text("UPDATE rbac_roles SET status='ARCHIVED',version=version+1,updated_at=now() WHERE id=:r"), {"r": str(role_id)})
        changed = [m["membership_id"] for m in preview["_proof"] if active(policies.member_effective(conn, actor.school_id, m["membership_id"])) != set(m["before"])]
        if changed:
            raise HTTPException(409, f"Conversion annulée : la vérification après application a détecté {len(changed)} différence(s)")
        policies.assert_managers_remain(conn, actor.school_id)
        out = {"custom_role_id": str(role_id), "standard_role_id": str(target["id"]), "members_moved": moved, "plan": preview["plan"],
               "proof": {"members_checked": len(preview["_proof"]), "identical": True}}
        _audit(conn, actor, "ACCESS_ROLE_CONVERTED", "rbac_role", role_id, out, reason=b.reason)
        return 200, out

    return _idempotent(services, actor, idempotency_key, "ACCESS_ROLE_CONVERT", {"role": str(role_id), **b.model_dump(mode="json")}, action)


# --------------------------------------------------------------------------------------- authoritative projection
@router.get("/me")
def access_me(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """What the signed-in member may see and do in this school (owner decision 8): effective capabilities and scopes,
    roles, navigation, dashboard widgets and shortcuts — computed here, never guessed by the browser."""
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        roles = conn.execute(text("""SELECT r.id,r.code,r.label,r.kind,a.valid_until,
              (SELECT coalesce(json_agg(json_build_object('type',s.scope_type,'value',s.scope_value) ORDER BY s.scope_type,s.scope_value),'[]')
                 FROM rbac_assignment_scopes s WHERE s.assignment_id=a.id) scopes,
              (SELECT count(*) FROM rbac_school_role_policies p WHERE p.active AND p.school_id=a.school_id AND p.role_id=r.id) adjustments
            FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id AND r.status='ACTIVE'
            WHERE a.membership_id=:m AND a.school_id=:s AND a.active AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now())
            ORDER BY CASE r.kind WHEN 'SCHOOL_STANDARD' THEN 0 ELSE 1 END, r.label"""),
                             {"m": str(actor.membership_id), "s": str(actor.school_id)}).mappings().all()
        lifecycle = {r[0]: r[1] for r in conn.execute(text("SELECT code, lifecycle FROM capability_catalog"))}
        civility = conn.execute(text("SELECT civility FROM school_memberships WHERE id=:m AND school_id=:s"),
                                {"m": str(actor.membership_id), "s": str(actor.school_id)}).scalar()
        labels = _section_labels(conn, actor.school_id)
    titles = [_titled(r["code"], r["kind"], r["label"], civility, r["scopes"] if isinstance(r["scopes"], list) else [], labels) for r in roles]
    caps = set(actor.permissions)
    scoped = sorted({(c, t, v) for c, t, v in actor.capability_scopes if t != "SCHOOL" and lifecycle.get(c) == "ACTIVE"})
    return {"membership_id": str(actor.membership_id), "school_id": str(actor.school_id),
            "roles": [{**_json(dict(r)), "standard": r["kind"] == "SCHOOL_STANDARD", "adjusted": r["adjustments"] > 0, "title": t} for r, t in zip(roles, titles)],
            # the words shown on the home page: « Promotrice », « Directrice de la maternelle »… (rights unchanged)
            "role_label": " · ".join(dict.fromkeys(titles)) or "Membre", "civility": civility,
            "permissions": sorted(c for c in caps if lifecycle.get(c) in ("ACTIVE", "ALIAS")),
            "scoped": [{"capability": c, "type": t, "value": v} for c, t, v in scoped],
            "navigation": projection.navigation(caps), "widgets": projection.widgets(caps, {c for c, t, _ in actor.capability_scopes if t == "SCHOOL"}), "actions": projection.actions(caps)}


@router.get("/dashboard")
def admin_dashboard(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """Data of the administration widgets, each section only when its capability is held."""
    caps = set(actor.permissions)
    out: dict[str, Any] = {}
    sid = {"s": str(actor.school_id)}
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        if "access.users.read" in caps:
            out["access.members"] = dict(conn.execute(text("""SELECT count(*) FILTER (WHERE m.active) active, count(*) FILTER (WHERE NOT m.active) inactive,
                  count(*) FILTER (WHERE m.active AND NOT EXISTS (SELECT 1 FROM rbac_assignments a WHERE a.membership_id=m.id AND a.active
                     AND (a.valid_until IS NULL OR a.valid_until>now()))) without_role,
                  (SELECT count(*) FROM rbac_assignments a WHERE a.school_id=:s AND a.active AND a.valid_until BETWEEN now() AND now()+interval '30 days') expiring
                FROM school_memberships m WHERE m.school_id=:s"""), sid).mappings().one())
        if "access.roles.manage" in caps:
            out["access.requests"] = {
                "pending": conn.execute(text("SELECT count(*) FROM rbac_change_requests WHERE school_id=:s AND status='PENDING'"), sid).scalar_one(),
                "adjusted_roles": conn.execute(text("SELECT count(DISTINCT role_id) FROM rbac_school_role_policies WHERE school_id=:s AND active"), sid).scalar_one()}
        if "settings.academic_year.read" in caps:
            years = conn.execute(text("SELECT label,status,start_date,end_date FROM academic_years WHERE school_id=:s ORDER BY start_date DESC LIMIT 3"), sid).mappings().all()
            out["settings.academic_year"] = {"years": [_json(dict(y)) for y in years], "active": next((y["label"] for y in years if y["status"] == "ACTIVE"), None)}
        if "settings.structure.read" in caps:
            out["settings.structure"] = dict(conn.execute(text("""SELECT (SELECT count(*) FROM school_sections WHERE school_id=:s AND enabled) sections,
                  (SELECT count(*) FROM school_classes c JOIN academic_years y ON y.id=c.academic_year_id AND y.status='ACTIVE'
                    WHERE c.school_id=:s AND c.enabled) classes"""), sid).mappings().one())
        if "audit.school.read" in caps:
            rows = conn.execute(text("""SELECT occurred_at,action,actor_user_id FROM audit_events WHERE school_id=:s
                  AND (action LIKE 'ACCESS_%' OR action LIKE 'SETTINGS_%' OR action LIKE 'ACADEMIC_YEAR_%') ORDER BY occurred_at DESC LIMIT 8"""), sid).mappings().all()
        else:
            rows = []
    if rows:
        names = _user_cards(services, {str(r["actor_user_id"]) for r in rows if r["actor_user_id"]})
        out["audit.recent"] = [{"at": _json(r["occurred_at"]), "action": r["action"], "actor": names.get(str(r["actor_user_id"]), {}).get("full_name")} for r in rows]
    elif "audit.school.read" in caps:
        out["audit.recent"] = []
    return out
