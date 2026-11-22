"""Grade entry (V2 lot 3b, owner 2026-11-22). Parent project: only the teacher of the course enters its grades; the préfet
and the directors follow and read (no entry) and steer through the calendar (close / reopen a period).

GET  /pedagogy/grades/sheet?class_id&course_code[&period]   the class list for one course and period, with the marks
PUT  /pedagogy/grades/cell                                  one mark (what was typed: « 14 », « a », « d », empty) —
                                                            saved at once; a replay of the same value changes nothing;
                                                            a different value over a newer version → 409 (no silent overwrite)
POST /pedagogy/grades/paste                                 a pasted column fills the EMPTY cells in class order
GET  /pedagogy/grades/progress                              follow-up for the directors: marks entered per class and course
"""
from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from edusync.adapters.postgres_repositories import PostgresAuditRepository
from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.modules.audit.domain.audit import AuditRecord
from edusync.modules.pedagogy.api.calendar import active_year, period_states
from edusync.modules.pedagogy.domain import grades as gd
from edusync.modules.school_modules.api.guard import require_pedagogy
from edusync.shared.application.context import ActorContext

router = APIRouter(tags=["Pédagogie (V2) — cotes"])
ENTER, READ = "pedagogy.grades.enter", "pedagogy.grades.read"
ENROLLED = ("VALIDATED", "COMPLETED")
PERIOD_COLUMNS = "l.max_p1,l.max_p2,l.max_ex1,l.max_p3,l.max_p4,l.max_ex2,l.max_p5,l.max_p6,l.max_ex3"


class CellIn(BaseModel):
    class_id: UUID
    course_code: str = Field(min_length=2, max_length=96)
    period: str = Field(min_length=2, max_length=4)
    student_id: UUID
    input: str = Field(default="", max_length=12)
    expected_version: int | None = None          # the version the teacher saw; None = the cell was empty for him
    source: str = Field(default="WEB", pattern="^(WEB|OFFLINE)$")


class PasteIn(BaseModel):
    class_id: UUID
    course_code: str = Field(min_length=2, max_length=96)
    period: str = Field(min_length=2, max_length=4)
    text: str = Field(min_length=1, max_length=20000)


def _tx(services: AppServices, actor: ActorContext):
    return services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id)


def _sections(actor: ActorContext, capability: str) -> set[str] | None:
    scopes = actor.scopes_for(capability)
    if not scopes or any(t == "SCHOOL" for t, _ in scopes):
        return None
    return {str(v).upper() for t, v in scopes if t == "SECTION" and v}


def _context(conn, actor: ActorContext, class_id: UUID, course: str) -> dict:
    """Class of the active year + its programme line for the course + who may enter / read."""
    year = active_year(conn, actor)
    c = conn.execute(text("""SELECT c.id,c.label,s.code AS section_code,rc.structure,l.ref_class_code,
          (SELECT p.id FROM pedagogy_programmes p WHERE p.school_id=c.school_id AND p.academic_year_id=c.academic_year_id
             AND p.ref_class_code=l.ref_class_code AND p.status='VALIDATED') AS programme_id
        FROM school_classes c JOIN school_sections s ON s.id=c.section_id
        LEFT JOIN pedagogy_class_links l ON l.class_id=c.id LEFT JOIN ref_classes rc ON rc.code=l.ref_class_code
        WHERE c.id=:c AND c.school_id=:s AND c.academic_year_id=:y"""), {"c": str(class_id), "s": str(actor.school_id), "y": str(year["id"])}).mappings().first()
    if c is None:
        raise HTTPException(404, "Classe introuvable")
    if not c["programme_id"]:
        raise HTTPException(409, "Le programme de cette classe n’est pas encore en service.")
    line = conn.execute(text("SELECT l.course_code,k.label,l.has_exam," + PERIOD_COLUMNS + """ FROM pedagogy_programme_lines l
        JOIN ref_courses k ON k.code=l.course_code WHERE l.programme_id=:p AND l.course_code=:k"""),
        {"p": str(c["programme_id"]), "k": course}).mappings().first()
    if line is None:
        raise HTTPException(404, "Ce cours n’est pas au programme de cette classe")
    teaches = conn.execute(text("SELECT 1 FROM pedagogy_teaching_assignments WHERE class_id=:c AND course_code=:k AND membership_id=:m"),
                           {"c": str(class_id), "k": course, "m": str(actor.membership_id)}).first() is not None
    can_enter = ENTER in actor.permissions and teaches
    secs = _sections(actor, READ)
    can_read = can_enter or (READ in actor.permissions and (secs is None or str(c["section_code"]).upper() in secs))
    if not can_read:
        raise HTTPException(403, "Seul l’enseignant de ce cours, ou la direction, consulte ces cotes")
    periods = period_states(conn, actor, year, c["structure"])
    maxima = {code: int(line[col]) for code, col in gd.COLUMN_OF.items()}
    return {"year": year, "class": dict(c), "line": dict(line), "maxima": maxima, "periods": periods, "can_enter": can_enter}


def _pupils(conn, actor: ActorContext, ctx: dict) -> list[dict]:
    rows = conn.execute(text("""SELECT st.id,st.last_name,st.middle_name,st.first_name FROM enrollments e JOIN students st ON st.id=e.student_id
        WHERE e.school_id=:s AND e.class_id=:c AND e.academic_year_id=:y AND e.status IN ('VALIDATED','COMPLETED')
        ORDER BY st.last_name, st.middle_name NULLS FIRST, st.first_name"""),
        {"s": str(actor.school_id), "c": str(ctx["class"]["id"]), "y": str(ctx["year"]["id"])}).mappings()
    return [{"student_id": str(r["id"]), "name": " ".join(x for x in (r["last_name"], r["middle_name"], r["first_name"]) if x)} for r in rows]


def _marks(conn, actor: ActorContext, ctx: dict, period: str) -> dict[str, dict]:
    rows = conn.execute(text("""SELECT id,student_id,status,value,version FROM pedagogy_grades
        WHERE school_id=:s AND class_id=:c AND course_code=:k AND period_code=:p"""),
        {"s": str(actor.school_id), "c": str(ctx["class"]["id"]), "k": ctx["line"]["course_code"], "p": period}).mappings()
    return {str(r["student_id"]): dict(r) for r in rows}


def _period(ctx: dict, wanted: str | None) -> str:
    """Asked period, else the one going on today, else the most recent still open, else the first one with points —
    the teacher lands on the column he is filling, never on an old one."""
    usable = [code for code in gd.COLUMN_OF if ctx["maxima"][code] > 0 and (ctx["line"]["has_exam"] or not code.startswith("EX"))]
    if wanted:
        if wanted not in usable:
            raise HTTPException(404, "Pas de cote pour cette période dans le programme")
        return wanted
    ongoing = [c for c in usable if ctx["periods"].get(c, {}).get("state") == "ONGOING"]
    open_ = [c for c in usable if ctx["periods"].get(c, {}).get("allowed")]
    return (ongoing or open_[-1:] or usable or ["P1"])[0]


def _sheet(conn, actor: ActorContext, ctx: dict, period: str) -> dict:
    marks = _marks(conn, actor, ctx, period)
    maximum = ctx["maxima"][period]
    pupils = []
    for p in _pupils(conn, actor, ctx):
        m = marks.get(p["student_id"])
        value = m["value"] if m else None
        pupils.append({**p, "status": m["status"] if m else None, "value": value, "version": m["version"] if m else None,
                       "failing": gd.is_failing(value, maximum)})
    state = ctx["periods"].get(period, {"state": "DRAFT", "allowed": False, "label": period})
    columns = [{"code": code, "label": ctx["periods"].get(code, {}).get("label", code), "max": ctx["maxima"][code],
                "state": ctx["periods"].get(code, {}).get("state", "DRAFT"), "allowed": bool(ctx["periods"].get(code, {}).get("allowed"))}
               for code in gd.COLUMN_OF if ctx["maxima"][code] > 0 and (ctx["line"]["has_exam"] or not code.startswith("EX"))]
    filled = sum(1 for p in pupils if p["status"])
    return {"class": {"id": str(ctx["class"]["id"]), "label": ctx["class"]["label"]},
            "course": {"code": ctx["line"]["course_code"], "label": ctx["line"]["label"], "has_exam": ctx["line"]["has_exam"]},
            "period": {"code": period, "label": state.get("label", period), "max": maximum, "state": state["state"], "allowed": state["allowed"]},
            "periods": columns, "can_enter": ctx["can_enter"] and state["allowed"], "pupils": pupils,
            "progress": {"filled": filled, "total": len(pupils)}}


@router.get("/grades/sheet")
def sheet(class_id: UUID, course_code: str, period: str | None = Query(default=None, max_length=4),
          actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
          _module: ActorContext = Depends(require_pedagogy)):
    with _tx(services, actor) as conn:
        ctx = _context(conn, actor, class_id, course_code.strip().upper())
        return _sheet(conn, actor, ctx, _period(ctx, period.strip().upper() if period else None))


def _guard_entry(ctx: dict, period: str) -> None:
    # the column itself first: a clear reason beats a calendar message (« ce cours n’a pas d’examen »)
    if period not in gd.COLUMN_OF:
        raise HTTPException(404, "Période inconnue")
    if period.startswith("EX") and not ctx["line"]["has_exam"]:
        raise HTTPException(422, "Ce cours n’a pas d’examen")
    if ctx["maxima"][period] <= 0:
        raise HTTPException(404, "Pas de cote pour cette période dans le programme")
    if not ctx["can_enter"]:
        raise HTTPException(403, "Seul l’enseignant de ce cours saisit ses cotes")
    state = ctx["periods"].get(period)
    if not state:
        raise HTTPException(409, "Le calendrier pédagogique n’est pas encore validé : la saisie n’est pas ouverte.")
    if not state["allowed"]:
        why = {"UPCOMING": "cette période n’a pas encore commencé", "CLOSED": "la saisie de cette période est clôturée",
               "DRAFT": "le calendrier n’est pas encore validé"}.get(state["state"], "la saisie est fermée")
        raise HTTPException(409, f"Saisie impossible : {why}.")


def _write(conn, actor: ActorContext, ctx: dict, period: str, student_id: str, status: str | None, value: int | None,
           expected: int | None, source: str, current: dict | None) -> dict:
    maximum = ctx["maxima"][period]
    try:
        gd.check(status, value, maximum, has_exam=ctx["line"]["has_exam"], period=period)
    except gd.GradeError as exc:
        raise HTTPException(422, str(exc)) from exc
    if current is not None and current["status"] == status and current["value"] == value:
        return current                                                     # same mark again (offline replay): nothing changes
    if current is not None and expected != current["version"]:
        raise HTTPException(409, {"code": "GRADE_CONFLICT", "message": "Cette cote vient d’être modifiée ailleurs : vérifiez-la.",
                                  "current": {"status": current["status"], "value": current["value"], "version": current["version"]}})
    if current is None and status is None:
        return {"status": None, "value": None, "version": None}
    if current is None:
        row = conn.execute(text("""INSERT INTO pedagogy_grades(school_id,academic_year_id,class_id,student_id,course_code,period_code,status,value,max_value,entered_by)
            VALUES(:s,:y,:c,:st,:k,:p,:status,:v,:mx,:m) RETURNING id,status,value,version"""),
            {"s": str(actor.school_id), "y": str(ctx["year"]["id"]), "c": str(ctx["class"]["id"]), "st": student_id, "k": ctx["line"]["course_code"],
             "p": period, "status": status, "v": value, "mx": maximum, "m": str(actor.membership_id)}).mappings().one()
    else:
        row = conn.execute(text("""UPDATE pedagogy_grades SET status=:status, value=:v, max_value=:mx, entered_by=:m, entered_at=now(), version=version+1
            WHERE id=:id RETURNING id,status,value,version"""), {"status": status, "v": value, "mx": maximum, "m": str(actor.membership_id), "id": str(current["id"])}).mappings().one()
    conn.execute(text("""INSERT INTO pedagogy_grade_history(school_id,grade_id,old_status,old_value,new_status,new_value,changed_by,source)
        VALUES(:s,:g,:os,:ov,:ns,:nv,:m,:src)"""), {"s": str(actor.school_id), "g": str(row["id"]), "os": current["status"] if current else None,
        "ov": current["value"] if current else None, "ns": status, "nv": value, "m": str(actor.membership_id), "src": source})
    return dict(row)


@router.put("/grades/cell")
def put_cell(body: CellIn, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
             _module: ActorContext = Depends(require_pedagogy)):
    period = body.period.strip().upper()
    with _tx(services, actor) as conn:
        ctx = _context(conn, actor, body.class_id, body.course_code.strip().upper())
        _guard_entry(ctx, period)
        if str(body.student_id) not in {p["student_id"] for p in _pupils(conn, actor, ctx)}:
            raise HTTPException(404, "Élève absent de cette classe")
        maximum = ctx["maxima"][period]
        try:
            status, value = gd.parse_cell(body.input, maximum)
        except gd.GradeError as exc:
            raise HTTPException(422, str(exc)) from exc
        current = conn.execute(text("""SELECT id,status,value,version FROM pedagogy_grades WHERE class_id=:c AND student_id=:st AND course_code=:k
            AND period_code=:p FOR UPDATE"""), {"c": str(body.class_id), "st": str(body.student_id), "k": ctx["line"]["course_code"], "p": period}).mappings().first()
        row = _write(conn, actor, ctx, period, str(body.student_id), status, value, body.expected_version, body.source, dict(current) if current else None)
    return {"student_id": str(body.student_id), "status": row["status"], "value": row["value"], "version": row["version"],
            "failing": gd.is_failing(row["value"], maximum)}


@router.post("/grades/paste")
def paste(body: PasteIn, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
          _module: ActorContext = Depends(require_pedagogy)):
    period = body.period.strip().upper()
    with _tx(services, actor) as conn:
        ctx = _context(conn, actor, body.class_id, body.course_code.strip().upper())
        _guard_entry(ctx, period)
        try:
            cells = gd.parse_pasted(body.text, ctx["maxima"][period])
        except gd.GradeError as exc:
            raise HTTPException(422, str(exc)) from exc
        pupils = _pupils(conn, actor, ctx)
        if len(cells) > len(pupils):
            raise HTTPException(422, f"{len(cells)} lignes collées pour {len(pupils)} élèves : vérifiez la liste.")
        marks = _marks(conn, actor, ctx, period)
        filled = skipped = 0
        for pupil, (status, value) in zip(pupils, cells):
            current = marks.get(pupil["student_id"])
            if status is None or (current and current["status"]):                  # never overwrite a mark already there
                skipped += 1 if status is not None else 0
                continue
            _write(conn, actor, ctx, period, pupil["student_id"], status, value, current["version"] if current else None, "PASTE", current)
            filled += 1
        PostgresAuditRepository(conn).append(AuditRecord(action="PEDAGOGY_GRADES_PASTED", entity_type="PedagogyGrades", entity_id=body.class_id,
            actor_user_id=actor.user_id, school_id=actor.school_id, source=actor.source, reason=None, old_data=None,
            new_data={"course": ctx["line"]["course_code"], "period": period, "filled": filled, "kept": skipped}, correlation_id=uuid4()))
        result = _sheet(conn, actor, ctx, period)
    return {**result, "pasted": {"filled": filled, "kept": skipped, "lines": len(cells)}}


@router.get("/grades/progress")
def progress(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
             _module: ActorContext = Depends(require_pedagogy)):
    """Directors' follow-up: for each class, how many courses have every pupil marked for the period now open."""
    try:
        actor.require(READ)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    secs = _sections(actor, READ)
    with _tx(services, actor) as conn:
        year = active_year(conn, actor)
        states = {s: period_states(conn, actor, year, s) for s in ("TRIMESTRIEL", "SEMESTRIEL")}
        # the period going on today, else the most recent still open (same choice as the teacher's sheet)
        current = {s: next((c for c, p in v.items() if p["state"] == "ONGOING" and not c.startswith("EX")), None)
                   or next((c for c, p in sorted(v.items(), key=lambda kv: -kv[1]["sort_order"]) if p["allowed"] and not c.startswith("EX")), None)
                   for s, v in states.items()}
        rows = conn.execute(text("""SELECT c.id,c.label,s.code AS section_code,s.label AS section_label,rc.structure,
              l.course_code,k.label AS course_label,
              (SELECT count(*) FROM enrollments e WHERE e.school_id=c.school_id AND e.class_id=c.id AND e.academic_year_id=c.academic_year_id
                 AND e.status IN ('VALIDATED','COMPLETED')) AS pupils
            FROM school_classes c JOIN school_sections s ON s.id=c.section_id
            JOIN pedagogy_class_links lk ON lk.class_id=c.id JOIN ref_classes rc ON rc.code=lk.ref_class_code
            JOIN pedagogy_programmes p ON p.school_id=c.school_id AND p.academic_year_id=c.academic_year_id AND p.ref_class_code=lk.ref_class_code AND p.status='VALIDATED'
            JOIN pedagogy_programme_lines l ON l.programme_id=p.id JOIN ref_courses k ON k.code=l.course_code
            WHERE c.school_id=:s AND c.academic_year_id=:y AND c.enabled
            ORDER BY s.code, c.label, l.sort_order"""), {"s": str(actor.school_id), "y": str(year["id"])}).mappings().all()
        counts = {(str(r[0]), r[1], r[2]): r[3] for r in conn.execute(text("""SELECT class_id,course_code,period_code,count(*) FROM pedagogy_grades
            WHERE school_id=:s AND academic_year_id=:y AND status IS NOT NULL GROUP BY 1,2,3"""), {"s": str(actor.school_id), "y": str(year["id"])})}
    classes: dict[str, dict] = {}
    for r in rows:
        if secs is not None and str(r["section_code"]).upper() not in secs:
            continue
        period = current.get(r["structure"])
        item = classes.setdefault(str(r["id"]), {"class_id": str(r["id"]), "label": r["label"], "section_label": r["section_label"],
                                                  "period": period, "pupils": r["pupils"], "courses": 0, "complete": 0, "started": 0})
        item["courses"] += 1
        done = counts.get((str(r["id"]), r["course_code"], period), 0) if period else 0
        item["complete"] += 1 if r["pupils"] and done >= r["pupils"] else 0
        item["started"] += 1 if done else 0
    return {"year": {"id": str(year["id"]), "label": year["label"]}, "current": current, "items": list(classes.values())}
