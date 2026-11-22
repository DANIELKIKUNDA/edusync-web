"""Pedagogy — official referential and class links (V2 lot 1, owner 2026-11-22). Every route: pedagogy module + right.

GET    /pedagogy/referential                     options (by group), classes, which classes have a programme
GET    /pedagogy/referential/classes/{code}      one official class: its programme (bulletin order, maxima, totals)
GET    /pedagogy/class-links                     classes of the active year → official class (link or suggestion)
PUT    /pedagogy/class-links/{class_id}          link a class (pedagogy.class_links.manage)
DELETE /pedagogy/class-links/{class_id}          remove a link
POST   /pedagogy/class-links/accept-suggestions  link every unlinked class that has a suggestion
A section-scoped member (préfet of one section) sees and links only the classes of his section(s).
"""
from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from edusync.adapters.postgres_repositories import PostgresAuditRepository
from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.modules.audit.domain.audit import AuditRecord
from edusync.modules.pedagogy.domain.referential import CURRENT_VERSION, GROUP_LABEL, MAX_KEYS, suggest_official_class, totals
from edusync.modules.school_modules.api.guard import require_pedagogy
from edusync.shared.application.context import ActorContext

router = APIRouter(tags=["Pédagogie (V2) — référentiel"])
# constant column list (no value is ever interpolated in SQL)
LINE_MAXIMA = "l.max_p1,l.max_p2,l.max_ex1,l.max_p3,l.max_p4,l.max_ex2,l.max_p5,l.max_p6,l.max_ex3"
assert LINE_MAXIMA == ",".join("l." + k for k in MAX_KEYS)
READ, MANAGE = "pedagogy.referential.read", "pedagogy.class_links.manage"


class LinkBody(BaseModel):
    ref_class_code: str = Field(min_length=2, max_length=16)


def _need(actor: ActorContext, capability: str) -> None:
    try:
        actor.require(capability)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


def _sections(actor: ActorContext, capability: str) -> set[str] | None:
    """None = whole school; else the section codes the member may act on."""
    scopes = actor.scopes_for(capability)
    if not scopes or any(t == "SCHOOL" for t, _ in scopes):
        return None
    return {str(v).upper() for t, v in scopes if t == "SECTION" and v}


def _tx(services: AppServices, actor: ActorContext):
    return services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id)


def _audit(conn, actor: ActorContext, action: str, entity_id: UUID, old=None, new=None) -> None:
    PostgresAuditRepository(conn).append(AuditRecord(action=action, entity_type="PedagogyClassLink", entity_id=entity_id,
                                                     actor_user_id=actor.user_id, school_id=actor.school_id, source=actor.source,
                                                     reason=None, old_data=old, new_data=new, correlation_id=uuid4()))


@router.get("/referential")
def referential(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
        _module: ActorContext = Depends(require_pedagogy)):
    _need(actor, READ)
    with _tx(services, actor) as conn:
        version = conn.execute(text("SELECT code,reference_year,published_on FROM ref_programme_versions WHERE code=:v"),
                               {"v": CURRENT_VERSION}).mappings().first()
        sections = conn.execute(text("SELECT code,label FROM ref_sections ORDER BY sort_order")).mappings().all()
        options = conn.execute(text("SELECT code,sigle,label,option_group FROM ref_options ORDER BY sort_order")).mappings().all()
        classes = conn.execute(text("""SELECT c.code,c.label,c.section_code,c.option_code,c.cycle,c.structure,c.level_order,
              (SELECT count(*) FROM ref_programme_lines l WHERE l.version_code=:v AND l.class_code=c.code) AS courses
            FROM ref_classes c JOIN ref_sections s ON s.code=c.section_code LEFT JOIN ref_options o ON o.code=c.option_code
            ORDER BY s.sort_order, o.sort_order NULLS FIRST, c.level_order"""), {"v": CURRENT_VERSION}).mappings().all()
    if version is None:
        raise HTTPException(503, "Référentiel officiel non chargé")
    return {"version": {**dict(version), "published_on": version["published_on"].isoformat()},
            "sections": [dict(s) for s in sections],
            "groups": [{"code": g, "label": label, "options": [dict(o) for o in options if o["option_group"] == g]} for g, label in GROUP_LABEL.items()],
            "classes": [{**dict(c), "has_programme": c["courses"] > 0} for c in classes]}


@router.get("/referential/classes/{code}")
def referential_class(code: str, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
        _module: ActorContext = Depends(require_pedagogy)):
    _need(actor, READ)
    with _tx(services, actor) as conn:
        cls = conn.execute(text("""SELECT c.code,c.label,c.section_code,c.cycle,c.structure,o.code AS option_code,o.sigle,o.label AS option_label,o.option_group
            FROM ref_classes c LEFT JOIN ref_options o ON o.code=c.option_code WHERE c.code=:c"""), {"c": code.strip().upper()}).mappings().first()
        if cls is None:
            raise HTTPException(404, "Classe officielle introuvable")
        lines = conn.execute(text("SELECT l.sort_order,l.course_code,k.label,l.domain,l.subdomain,l.mandatory,l.has_exam,l.calculable,"
            + LINE_MAXIMA + """ FROM ref_programme_lines l JOIN ref_courses k ON k.code=l.course_code
            WHERE l.version_code=:v AND l.class_code=:c ORDER BY l.sort_order"""), {"v": CURRENT_VERSION, "c": cls["code"]}).mappings().all()
    rows = [dict(r) for r in lines]
    return {"version": CURRENT_VERSION, "class": dict(cls), "lines": rows, "totals": totals(rows),
            "columns": list(MAX_KEYS) if cls["structure"] == "TRIMESTRIEL" else list(MAX_KEYS[:6])}


def _school_classes(conn, actor: ActorContext, sections: set[str] | None, class_id: UUID | None = None) -> list[dict]:
    params: dict = {"s": str(actor.school_id), "id": str(class_id) if class_id else None}
    rows = conn.execute(text("""SELECT c.id,c.code,c.label,c.reference_code,s.code AS section_code,s.label AS section_label,
          o.code AS option_code,o.label AS option_label,l.ref_class_code,l.linked_at,l.version AS link_version,rc.label AS ref_label,
          (SELECT count(*) FROM ref_programme_lines pl WHERE pl.version_code=:v AND pl.class_code=l.ref_class_code) AS ref_courses
        FROM school_classes c JOIN academic_years y ON y.id=c.academic_year_id JOIN school_sections s ON s.id=c.section_id
        LEFT JOIN school_options o ON o.id=c.option_id LEFT JOIN pedagogy_class_links l ON l.class_id=c.id
        LEFT JOIN ref_classes rc ON rc.code=l.ref_class_code
        WHERE c.school_id=:s AND (CASE WHEN CAST(:id AS uuid) IS NULL THEN y.status='ACTIVE' AND c.enabled ELSE c.id=CAST(:id AS uuid) END)
        ORDER BY s.code, (c.reference_code LIKE 'H%') NULLS LAST, c.reference_code NULLS LAST, c.code   -- 7e/8e EB before the humanities"""), {**params, "v": CURRENT_VERSION}).mappings().all()
    return [dict(r) for r in rows if sections is None or str(r["section_code"]).upper() in sections]


@router.get("/class-links")
def class_links(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
        _module: ActorContext = Depends(require_pedagogy)):
    _need(actor, READ)
    with _tx(services, actor) as conn:
        rows = _school_classes(conn, actor, _sections(actor, READ))
        sigles = {r[0] for r in conn.execute(text("SELECT sigle FROM ref_options"))}
        labels = {r[0]: (r[1], r[2]) for r in conn.execute(text(
            "SELECT c.code,c.label,(SELECT count(*) FROM ref_programme_lines l WHERE l.version_code=:v AND l.class_code=c.code) FROM ref_classes c"),
            {"v": CURRENT_VERSION})}
    items = []
    for r in rows:
        suggestion = None if r["ref_class_code"] else suggest_official_class(r["reference_code"], r["option_code"], sigles)
        suggestion = suggestion if suggestion in labels else None
        linked = r["ref_class_code"]
        items.append({"class_id": str(r["id"]), "code": r["code"], "label": r["label"], "level": r["reference_code"],
                      "section_code": r["section_code"], "section_label": r["section_label"], "option_code": r["option_code"],
                      "option_label": r["option_label"],
                      "link": {"ref_class_code": linked, "label": r["ref_label"], "linked_at": r["linked_at"].isoformat(),
                               "has_programme": r["ref_courses"] > 0, "version": r["link_version"]} if linked else None,
                      "suggestion": {"ref_class_code": suggestion, "label": labels[suggestion][0], "has_programme": labels[suggestion][1] > 0} if suggestion else None})
    linked_n = sum(1 for i in items if i["link"])
    return {"version": CURRENT_VERSION, "can_manage": MANAGE in actor.permissions, "items": items,
            "summary": {"classes": len(items), "linked": linked_n, "to_confirm": sum(1 for i in items if not i["link"] and i["suggestion"]),
                        "without_suggestion": sum(1 for i in items if not i["link"] and not i["suggestion"]),
                        "without_programme": sum(1 for i in items if i["link"] and not i["link"]["has_programme"])}}


def _one_class(conn, actor: ActorContext, class_id: UUID) -> dict:
    rows = _school_classes(conn, actor, _sections(actor, MANAGE), class_id)
    if not rows:
        raise HTTPException(404, "Classe introuvable dans votre périmètre")
    return rows[0]


@router.put("/class-links/{class_id}")
def link_class(class_id: UUID, body: LinkBody, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
        _module: ActorContext = Depends(require_pedagogy)):
    _need(actor, MANAGE)
    code = body.ref_class_code.strip().upper()
    with _tx(services, actor) as conn:
        cls = _one_class(conn, actor, class_id)
        if conn.execute(text("SELECT 1 FROM ref_classes WHERE code=:c"), {"c": code}).first() is None:
            raise HTTPException(404, "Classe officielle introuvable")
        if cls["ref_class_code"] == code:
            return {"class_id": str(class_id), "ref_class_code": code, "changed": False}
        conn.execute(text("""INSERT INTO pedagogy_class_links(class_id,school_id,ref_class_code,linked_by)
            VALUES(:id,:s,:c,:u) ON CONFLICT (class_id) DO UPDATE SET ref_class_code=EXCLUDED.ref_class_code,
              linked_by=EXCLUDED.linked_by, linked_at=now(), version=pedagogy_class_links.version+1"""),
            {"id": str(class_id), "s": str(actor.school_id), "c": code, "u": str(actor.user_id)})
        _audit(conn, actor, "PEDAGOGY_CLASS_LINKED", class_id, old={"ref_class_code": cls["ref_class_code"]},
               new={"class": cls["code"], "ref_class_code": code})
    return {"class_id": str(class_id), "ref_class_code": code, "changed": True}


@router.delete("/class-links/{class_id}")
def unlink_class(class_id: UUID, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
        _module: ActorContext = Depends(require_pedagogy)):
    _need(actor, MANAGE)
    with _tx(services, actor) as conn:
        cls = _one_class(conn, actor, class_id)
        if not cls["ref_class_code"]:
            return {"class_id": str(class_id), "changed": False}
        conn.execute(text("DELETE FROM pedagogy_class_links WHERE class_id=:id AND school_id=:s"), {"id": str(class_id), "s": str(actor.school_id)})
        _audit(conn, actor, "PEDAGOGY_CLASS_UNLINKED", class_id, old={"class": cls["code"], "ref_class_code": cls["ref_class_code"]})
    return {"class_id": str(class_id), "changed": True}


@router.post("/class-links/accept-suggestions")
def accept_suggestions(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
        _module: ActorContext = Depends(require_pedagogy)):
    """Links every class of the member's scope that has a suggestion and no link yet. Safe to repeat."""
    _need(actor, MANAGE)
    with _tx(services, actor) as conn:
        sigles = {r[0] for r in conn.execute(text("SELECT sigle FROM ref_options"))}
        official = {r[0] for r in conn.execute(text("SELECT code FROM ref_classes"))}
        done = []
        for r in _school_classes(conn, actor, _sections(actor, MANAGE)):
            code = None if r["ref_class_code"] else suggest_official_class(r["reference_code"], r["option_code"], sigles)
            if code and code in official:
                conn.execute(text("""INSERT INTO pedagogy_class_links(class_id,school_id,ref_class_code,linked_by) VALUES(:id,:s,:c,:u)
                    ON CONFLICT (class_id) DO NOTHING"""), {"id": str(r["id"]), "s": str(actor.school_id), "c": code, "u": str(actor.user_id)})
                done.append({"class": r["code"], "ref_class_code": code})
        if done:
            _audit(conn, actor, "PEDAGOGY_CLASS_SUGGESTIONS_ACCEPTED", actor.school_id, new={"linked": done})
    return {"linked": len(done), "items": done}
