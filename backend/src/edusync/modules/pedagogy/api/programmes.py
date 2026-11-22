"""Programmes of the school (V2 lot 2, owner 2026-11-22). Pedagogy module + rights; the school year is the active one.

GET    /pedagogy/programmes                         every official class used by the school's classes, with its programme
POST   /pedagogy/programmes/adopt-official          one click: the official programme becomes the school's (validated)
POST   /pedagogy/programmes                         {ref_class_code} open a draft (copy of the programme in use, else the
                                                    official one, else empty for a class without official programme)
GET    /pedagogy/programmes/{id}                    lines (one number per term) + comparison with the official programme
PUT    /pedagogy/programmes/{id}/lines/{course}     add / change a course of a draft
DELETE /pedagogy/programmes/{id}/lines/{course}     remove an optional or added course of a draft
POST   /pedagogy/programmes/{id}/move               {course_code, direction: up|down}
POST   /pedagogy/programmes/{id}/validate           the draft replaces the programme in use (archived)
DELETE /pedagogy/programmes/{id}                    discard a draft
GET    /pedagogy/courses?q=                         official courses to add (search)
A section-scoped member (directeur de section) acts only on the classes of his section.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from edusync.adapters.postgres_repositories import PostgresAuditRepository
from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.modules.audit.domain.audit import AuditRecord
from edusync.modules.pedagogy.api.calendar import active_year
from edusync.modules.pedagogy.domain import programme as prog
from edusync.modules.pedagogy.domain.referential import CURRENT_VERSION, MAX_KEYS, totals
from edusync.modules.school_modules.api.guard import require_pedagogy
from edusync.shared.application.context import ActorContext

router = APIRouter(tags=["Pédagogie (V2) — programmes"])
READ, MANAGE = "pedagogy.referential.read", "pedagogy.programmes.manage"
SECTION_NAME = {"MAT": "MATERNELLE", "PRI": "PRIMAIRE", "SEC": "SECONDAIRE"}
LINE_COLS = "course_code,sort_order,source,mandatory,has_exam,calculable,domain,subdomain,max_p1,max_p2,max_ex1,max_p3,max_p4,max_ex2,max_p5,max_p6,max_ex3"
assert LINE_COLS.endswith(",".join(MAX_KEYS))


class AdoptIn(BaseModel):
    ref_class_codes: list[str] | None = Field(default=None, max_length=300)


class DraftIn(BaseModel):
    ref_class_code: str = Field(min_length=2, max_length=16)


class LineIn(BaseModel):
    term_points: list[int] = Field(min_length=2, max_length=3)
    has_exam: bool = True
    mandatory: bool = True


class MoveIn(BaseModel):
    course_code: str = Field(min_length=2, max_length=96)
    direction: Literal["up", "down"]


def _need(actor: ActorContext, capability: str) -> None:
    try:
        actor.require(capability)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


def _sections(actor: ActorContext, capability: str) -> set[str] | None:
    scopes = actor.scopes_for(capability)
    if not scopes or any(t == "SCHOOL" for t, _ in scopes):
        return None
    return {str(v).upper() for t, v in scopes if t == "SECTION" and v}


def _allowed(actor: ActorContext, capability: str, ref_section: str) -> bool:
    secs = _sections(actor, capability)
    return secs is None or SECTION_NAME.get(ref_section, ref_section) in secs


def _tx(services: AppServices, actor: ActorContext):
    return services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id)


def _audit(conn, actor: ActorContext, action: str, entity_id: UUID, new=None, old=None) -> None:
    PostgresAuditRepository(conn).append(AuditRecord(action=action, entity_type="PedagogyProgramme", entity_id=entity_id,
                                                     actor_user_id=actor.user_id, school_id=actor.school_id, source=actor.source,
                                                     reason=None, old_data=old, new_data=new, correlation_id=uuid4()))


def _official_lines(conn, ref_class: str) -> list[dict]:
    return [dict(r) for r in conn.execute(text("""SELECT course_code,sort_order,'OFFICIEL' AS source,mandatory,has_exam,calculable,domain,subdomain,
          max_p1,max_p2,max_ex1,max_p3,max_p4,max_ex2,max_p5,max_p6,max_ex3
        FROM ref_programme_lines WHERE version_code=:v AND class_code=:c ORDER BY sort_order"""), {"v": CURRENT_VERSION, "c": ref_class}).mappings()]


def _insert_lines(conn, actor: ActorContext, programme_id, structure: str, lines: list[dict]) -> None:
    for i, line in enumerate(lines, start=1):
        conn.execute(text("""INSERT INTO pedagogy_programme_lines(programme_id,school_id,course_code,sort_order,source,mandatory,has_exam,calculable,
              semester_structure,domain,subdomain,max_p1,max_p2,max_ex1,max_p3,max_p4,max_ex2,max_p5,max_p6,max_ex3)
            VALUES(:p,:s,:course_code,:o,:source,:mandatory,:has_exam,:calculable,:sem,:domain,:subdomain,
              :max_p1,:max_p2,:max_ex1,:max_p3,:max_p4,:max_ex2,:max_p5,:max_p6,:max_ex3)"""),
            {**line, "p": str(programme_id), "s": str(actor.school_id), "o": i, "sem": structure == "SEMESTRIEL"})


def _linked_classes(conn, actor: ActorContext, year_id) -> dict[str, dict]:
    """Official classes used by the school's classes of the year → {code: {label, structure, section, classes[]}}."""
    rows = conn.execute(text("""SELECT rc.code,rc.label,rc.structure,rc.section_code,c.label AS class_label,
          (SELECT count(*) FROM ref_programme_lines l WHERE l.version_code=:v AND l.class_code=rc.code) AS official_lines
        FROM pedagogy_class_links pl JOIN school_classes c ON c.id=pl.class_id JOIN ref_classes rc ON rc.code=pl.ref_class_code
        JOIN ref_sections rs ON rs.code=rc.section_code LEFT JOIN ref_options o ON o.code=rc.option_code
        WHERE pl.school_id=:s AND c.academic_year_id=:y
        ORDER BY rs.sort_order, o.sort_order NULLS FIRST, rc.level_order, c.label"""), {"s": str(actor.school_id), "y": str(year_id), "v": CURRENT_VERSION}).mappings()
    out: dict[str, dict] = {}
    for r in rows:
        item = out.setdefault(r["code"], {"ref_class_code": r["code"], "label": r["label"], "structure": r["structure"],
                                          "section_code": r["section_code"], "has_official": r["official_lines"] > 0, "classes": []})
        item["classes"].append(r["class_label"])
    return out


def _programme_rows(conn, actor: ActorContext, year_id) -> dict[str, dict]:
    rows = conn.execute(text("""SELECT p.id,p.ref_class_code,p.status,p.validated_at,p.created_at,
          (SELECT count(*) FROM pedagogy_programme_lines l WHERE l.programme_id=p.id) AS lines
        FROM pedagogy_programmes p WHERE p.school_id=:s AND p.academic_year_id=:y AND p.status<>'ARCHIVED'"""),
        {"s": str(actor.school_id), "y": str(year_id)}).mappings()
    out: dict[str, dict] = {}
    for r in rows:
        out.setdefault(r["ref_class_code"], {})[r["status"]] = {"id": str(r["id"]), "status": r["status"], "lines": r["lines"],
            "validated_at": r["validated_at"].isoformat() if r["validated_at"] else None}
    return out


@router.get("/programmes")
def programmes(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
               _module: ActorContext = Depends(require_pedagogy)):
    _need(actor, READ)
    with _tx(services, actor) as conn:
        year = active_year(conn, actor)
        linked = _linked_classes(conn, actor, year["id"])
        existing = _programme_rows(conn, actor, year["id"])
    secs = _sections(actor, READ)
    items = []
    for code, item in linked.items():
        if secs is not None and SECTION_NAME.get(item["section_code"]) not in secs:
            continue
        p = existing.get(code, {})
        items.append({**item, "in_use": p.get("VALIDATED"), "draft": p.get("DRAFT"),
                      "can_manage": MANAGE in actor.permissions and _allowed(actor, MANAGE, item["section_code"])})
    return {"year": {"id": str(year["id"]), "label": year["label"]}, "items": items,
            "summary": {"classes": len(items), "in_use": sum(1 for i in items if i["in_use"]), "drafts": sum(1 for i in items if i["draft"]),
                        "adoptable": sum(1 for i in items if not i["in_use"] and not i["draft"] and i["has_official"] and i["can_manage"]),
                        "without_official": sum(1 for i in items if not i["has_official"] and not i["in_use"])}}


@router.post("/programmes/adopt-official")
def adopt_official(body: AdoptIn | None = None, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
                   _module: ActorContext = Depends(require_pedagogy)):
    """The official programme becomes the school's programme in use, for every chosen class without one (safe to repeat)."""
    _need(actor, MANAGE)
    wanted = {c.strip().upper() for c in body.ref_class_codes} if body and body.ref_class_codes else None
    adopted = []
    with _tx(services, actor) as conn:
        year = active_year(conn, actor)
        existing = _programme_rows(conn, actor, year["id"])
        for code, item in _linked_classes(conn, actor, year["id"]).items():
            if (wanted is not None and code not in wanted) or not item["has_official"] or existing.get(code):
                continue
            if not _allowed(actor, MANAGE, item["section_code"]):
                continue
            pid = conn.execute(text("""INSERT INTO pedagogy_programmes(school_id,academic_year_id,ref_class_code,structure,status,based_on_version,
                  created_by,validated_by,validated_at) VALUES(:s,:y,:c,:t,'VALIDATED',:v,:u,:u,now()) RETURNING id"""),
                {"s": str(actor.school_id), "y": str(year["id"]), "c": code, "t": item["structure"], "v": CURRENT_VERSION, "u": str(actor.user_id)}).scalar()
            _insert_lines(conn, actor, pid, item["structure"], _official_lines(conn, code))
            adopted.append(code)
        if adopted:
            _audit(conn, actor, "PEDAGOGY_PROGRAMMES_ADOPTED", actor.school_id, new={"ref_classes": adopted, "version": CURRENT_VERSION})
    return {"adopted": len(adopted), "ref_class_codes": adopted}


def _load(conn, actor: ActorContext, programme_id: UUID, *, for_update: bool = False) -> dict:
    row = conn.execute(text("""SELECT p.id,p.ref_class_code,p.structure,p.status,p.academic_year_id,p.validated_at,p.replaces_id,rc.label,rc.section_code
        FROM pedagogy_programmes p JOIN ref_classes rc ON rc.code=p.ref_class_code WHERE p.id=:id AND p.school_id=:s""" + (" FOR UPDATE OF p" if for_update else "")),
        {"id": str(programme_id), "s": str(actor.school_id)}).mappings().first()
    if row is None:
        raise HTTPException(404, "Programme introuvable")
    return dict(row)


def _editable(conn, actor: ActorContext, programme_id: UUID) -> dict:
    _need(actor, MANAGE)
    p = _load(conn, actor, programme_id, for_update=True)
    if not _allowed(actor, MANAGE, p["section_code"]):
        raise HTTPException(404, "Programme introuvable dans votre périmètre")
    if p["status"] != "DRAFT":
        raise HTTPException(409, "Ce programme est en service : ouvrez une nouvelle version pour le modifier.")
    return p


def _view(conn, actor: ActorContext, programme_id: UUID) -> dict:
    p = _load(conn, actor, programme_id)
    lines = [dict(r) for r in conn.execute(text("SELECT " + LINE_COLS + """,k.label FROM pedagogy_programme_lines l JOIN ref_courses k ON k.code=l.course_code
        WHERE l.programme_id=:p ORDER BY l.sort_order"""), {"p": str(programme_id)}).mappings()]
    official = {r["course_code"]: r for r in _official_lines(conn, p["ref_class_code"])}
    for line in lines:
        maxima = [int(line[k]) for k in MAX_KEYS]
        line["term_points"] = prog.terms_from_maxima(p["structure"], maxima)
        line["modified"] = line["source"] == "OFFICIEL" and prog.differs_from_official(line, official.get(line["course_code"]))
    removed = [{"course_code": c, "label": conn.execute(text("SELECT label FROM ref_courses WHERE code=:c"), {"c": c}).scalar()}
               for c in official if c not in {l["course_code"] for l in lines}]
    return {"id": str(p["id"]), "ref_class_code": p["ref_class_code"], "label": p["label"], "structure": p["structure"], "status": p["status"],
            "validated_at": p["validated_at"].isoformat() if p["validated_at"] else None, "has_official": bool(official),
            "can_manage": MANAGE in actor.permissions and _allowed(actor, MANAGE, p["section_code"]),
            "lines": lines, "totals": totals(lines), "removed_official": removed,
            "terms": 3 if p["structure"] == "TRIMESTRIEL" else 2}


@router.post("/programmes")
def open_draft(body: DraftIn, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
               _module: ActorContext = Depends(require_pedagogy)):
    _need(actor, MANAGE)
    code = body.ref_class_code.strip().upper()
    with _tx(services, actor) as conn:
        year = active_year(conn, actor)
        item = _linked_classes(conn, actor, year["id"]).get(code)
        if item is None or not _allowed(actor, MANAGE, item["section_code"]):
            raise HTTPException(404, "Aucune classe de l’école n’est reliée à cette classe officielle")
        existing = _programme_rows(conn, actor, year["id"]).get(code, {})
        if existing.get("DRAFT"):
            return _view(conn, actor, UUID(existing["DRAFT"]["id"]))
        in_use = existing.get("VALIDATED")
        pid = conn.execute(text("""INSERT INTO pedagogy_programmes(school_id,academic_year_id,ref_class_code,structure,based_on_version,replaces_id,created_by)
            VALUES(:s,:y,:c,:t,:v,:r,:u) RETURNING id"""), {"s": str(actor.school_id), "y": str(year["id"]), "c": code, "t": item["structure"],
            "v": CURRENT_VERSION, "r": in_use["id"] if in_use else None, "u": str(actor.user_id)}).scalar()
        if in_use:
            lines = [dict(r) for r in conn.execute(text("SELECT " + LINE_COLS + " FROM pedagogy_programme_lines WHERE programme_id=:p ORDER BY sort_order"),
                                                   {"p": in_use["id"]}).mappings()]
        else:
            lines = _official_lines(conn, code)
        _insert_lines(conn, actor, pid, item["structure"], lines)
        _audit(conn, actor, "PEDAGOGY_PROGRAMME_DRAFT_OPENED", pid, new={"ref_class": code, "from": "in_use" if in_use else "official" if lines else "empty"})
        return _view(conn, actor, pid)


@router.get("/programmes/{programme_id}")
def programme(programme_id: UUID, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
              _module: ActorContext = Depends(require_pedagogy)):
    _need(actor, READ)
    with _tx(services, actor) as conn:
        view = _view(conn, actor, programme_id)
    return view


@router.put("/programmes/{programme_id}/lines/{course_code}")
def put_line(programme_id: UUID, course_code: str, body: LineIn, actor: ActorContext = Depends(require_school_actor),
             services: AppServices = Depends(get_services), _module: ActorContext = Depends(require_pedagogy)):
    course = course_code.strip().upper()
    with _tx(services, actor) as conn:
        p = _editable(conn, actor, programme_id)
        if conn.execute(text("SELECT 1 FROM ref_courses WHERE code=:c"), {"c": course}).first() is None:
            raise HTTPException(404, "Cours inconnu du référentiel officiel")
        try:
            maxima = prog.maxima_from_terms(p["structure"], body.term_points, body.has_exam)
            prog.check(p["structure"], course, maxima, body.has_exam)
        except prog.ProgrammeError as exc:
            raise HTTPException(422, str(exc)) from exc
        values = dict(zip(MAX_KEYS, maxima))
        current = conn.execute(text("SELECT source FROM pedagogy_programme_lines WHERE programme_id=:p AND course_code=:c"),
                               {"p": str(programme_id), "c": course}).first()
        if current is None:
            official = next((l for l in _official_lines(conn, p["ref_class_code"]) if l["course_code"] == course), None)
            last = conn.execute(text("SELECT coalesce(max(sort_order),0) FROM pedagogy_programme_lines WHERE programme_id=:p"), {"p": str(programme_id)}).scalar()
            line = {"course_code": course, "source": "OFFICIEL" if official else "ECOLE", "mandatory": body.mandatory, "has_exam": body.has_exam,
                    "calculable": True, "domain": official["domain"] if official else None, "subdomain": official["subdomain"] if official else None, **values}
            _insert_lines(conn, actor, programme_id, p["structure"], [line])
            conn.execute(text("UPDATE pedagogy_programme_lines SET sort_order=:o WHERE programme_id=:p AND course_code=:c"),
                         {"o": last + 1, "p": str(programme_id), "c": course})
        else:
            conn.execute(text("""UPDATE pedagogy_programme_lines SET mandatory=:m, has_exam=:e, max_p1=:max_p1, max_p2=:max_p2, max_ex1=:max_ex1,
                  max_p3=:max_p3, max_p4=:max_p4, max_ex2=:max_ex2, max_p5=:max_p5, max_p6=:max_p6, max_ex3=:max_ex3
                WHERE programme_id=:p AND course_code=:c"""), {"m": body.mandatory, "e": body.has_exam, "p": str(programme_id), "c": course, **values})
        _audit(conn, actor, "PEDAGOGY_PROGRAMME_LINE_SAVED", programme_id, new={"course": course, "term_points": body.term_points, "exam": body.has_exam})
        return _view(conn, actor, programme_id)


@router.delete("/programmes/{programme_id}/lines/{course_code}")
def delete_line(programme_id: UUID, course_code: str, actor: ActorContext = Depends(require_school_actor),
                services: AppServices = Depends(get_services), _module: ActorContext = Depends(require_pedagogy)):
    course = course_code.strip().upper()
    with _tx(services, actor) as conn:
        _editable(conn, actor, programme_id)
        line = conn.execute(text("SELECT source,mandatory FROM pedagogy_programme_lines WHERE programme_id=:p AND course_code=:c"),
                            {"p": str(programme_id), "c": course}).mappings().first()
        if line is None:
            raise HTTPException(404, "Cours absent de ce programme")
        try:
            prog.can_remove(dict(line))
        except prog.ProgrammeError as exc:
            raise HTTPException(409, str(exc)) from exc
        conn.execute(text("DELETE FROM pedagogy_programme_lines WHERE programme_id=:p AND course_code=:c"), {"p": str(programme_id), "c": course})
        _audit(conn, actor, "PEDAGOGY_PROGRAMME_LINE_REMOVED", programme_id, old={"course": course})
        return _view(conn, actor, programme_id)


@router.post("/programmes/{programme_id}/move")
def move_line(programme_id: UUID, body: MoveIn, actor: ActorContext = Depends(require_school_actor),
              services: AppServices = Depends(get_services), _module: ActorContext = Depends(require_pedagogy)):
    course = body.course_code.strip().upper()
    with _tx(services, actor) as conn:
        _editable(conn, actor, programme_id)
        order = [r[0] for r in conn.execute(text("SELECT course_code FROM pedagogy_programme_lines WHERE programme_id=:p ORDER BY sort_order"),
                                            {"p": str(programme_id)})]
        if course not in order:
            raise HTTPException(404, "Cours absent de ce programme")
        i = order.index(course); j = i - 1 if body.direction == "up" else i + 1
        if 0 <= j < len(order):
            order[i], order[j] = order[j], order[i]
            for n, c in enumerate(order, start=1):        # renumber (temporary offset avoids nothing: no unique index on order)
                conn.execute(text("UPDATE pedagogy_programme_lines SET sort_order=:o WHERE programme_id=:p AND course_code=:c"),
                             {"o": n, "p": str(programme_id), "c": c})
        return _view(conn, actor, programme_id)


@router.post("/programmes/{programme_id}/validate")
def validate_programme(programme_id: UUID, actor: ActorContext = Depends(require_school_actor),
                       services: AppServices = Depends(get_services), _module: ActorContext = Depends(require_pedagogy)):
    with _tx(services, actor) as conn:
        p = _editable(conn, actor, programme_id)
        n = conn.execute(text("SELECT count(*) FROM pedagogy_programme_lines WHERE programme_id=:p"), {"p": str(programme_id)}).scalar()
        if not n:
            raise HTTPException(409, "Ajoutez au moins un cours avant de valider.")
        old = conn.execute(text("""UPDATE pedagogy_programmes SET status='ARCHIVED', archived_at=now(), version=version+1
            WHERE school_id=:s AND academic_year_id=:y AND ref_class_code=:c AND status='VALIDATED' RETURNING id"""),
            {"s": str(actor.school_id), "y": str(p["academic_year_id"]), "c": p["ref_class_code"]}).scalar()
        conn.execute(text("""UPDATE pedagogy_programmes SET status='VALIDATED', validated_by=:u, validated_at=now(), version=version+1 WHERE id=:id"""),
                     {"u": str(actor.user_id), "id": str(programme_id)})
        _audit(conn, actor, "PEDAGOGY_PROGRAMME_VALIDATED", programme_id, new={"ref_class": p["ref_class_code"], "courses": n},
               old={"archived": str(old)} if old else None)
        return _view(conn, actor, programme_id)


@router.delete("/programmes/{programme_id}")
def discard_draft(programme_id: UUID, actor: ActorContext = Depends(require_school_actor),
                  services: AppServices = Depends(get_services), _module: ActorContext = Depends(require_pedagogy)):
    with _tx(services, actor) as conn:
        p = _editable(conn, actor, programme_id)
        conn.execute(text("DELETE FROM pedagogy_programmes WHERE id=:id AND status='DRAFT'"), {"id": str(programme_id)})
        _audit(conn, actor, "PEDAGOGY_PROGRAMME_DRAFT_DISCARDED", programme_id, old={"ref_class": p["ref_class_code"]})
    return {"discarded": True}


@router.get("/courses")
def courses(q: str = Query(default="", max_length=60), actor: ActorContext = Depends(require_school_actor),
            services: AppServices = Depends(get_services), _module: ActorContext = Depends(require_pedagogy)):
    _need(actor, READ)
    needle = "%" + " ".join(q.split()).lower() + "%"
    with _tx(services, actor) as conn:
        rows = conn.execute(text("""SELECT code,label FROM ref_courses WHERE lower(label) LIKE :q OR lower(code) LIKE :q
            ORDER BY (lower(label) LIKE :start) DESC, label LIMIT 30"""), {"q": needle, "start": needle[1:]}).mappings().all()
    return [dict(r) for r in rows]
