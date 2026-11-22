"""Teachers, course assignments, class titulars and the conduct scale (V2 lot 3a, owner 2026-11-22).

GET  /pedagogy/teachers                               members whose role lets them teach (rôle Enseignant or a school role
                                                      built on it), with what they hold
GET  /pedagogy/teaching                               classes of the active year: titular + every course of the programme
                                                      in use with its teacher
PUT  /pedagogy/teaching/{class_id}/courses/{course}   {membership_id | null}
POST /pedagogy/teaching/{class_id}/assign-all         {membership_id} one teacher for every course still free (primaire)
PUT  /pedagogy/teaching/{class_id}/titular            {membership_id | null} — one titular per class, a teacher may hold
                                                      several classes (owner); powers effective in maternelle / primaire
GET  /pedagogy/my-teaching                            the teacher's own classes, courses and titular classes
GET  /pedagogy/conduct/scale  ·  PUT /pedagogy/conduct/scale    the school's conduct scale (points licence)
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
from edusync.modules.access.api.router import _user_cards
from edusync.modules.pedagogy.api.calendar import active_year
from edusync.modules.pedagogy.domain import conduct as cd
from edusync.modules.school_modules.api.guard import require_pedagogy
from edusync.shared.application.context import ActorContext

router = APIRouter(tags=["Pédagogie (V2) — enseignants et conduite"])
READ, MANAGE, OWN, CONDUCT = "pedagogy.referential.read", "pedagogy.teaching.manage", "pedagogy.teaching.own.read", "pedagogy.conduct.configure"
TEACH_CAP = OWN                      # a member may teach when one of his active roles grants this right
AUTO_TITULAR_SECTIONS = ("MATERNELLE", "PRIMAIRE")


def _distinct_labels(items: list[dict]) -> None:
    """Two courses of one class may share a name (« Expression Orale » in Congolese languages and in French): the
    sub-domain of the bulletin is added in brackets so that nobody confuses them."""
    seen: dict[str, int] = {}
    for i in items:
        seen[i["label"]] = seen.get(i["label"], 0) + 1
    for i in items:
        if seen[i["label"]] > 1 and i.get("subdomain"):
            i["label"] = f"{i['label']} ({i['subdomain'].capitalize()})"
        i.pop("subdomain", None)


class MemberIn(BaseModel):
    membership_id: UUID | None = None


class RuleIn(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    label: str = Field(min_length=3, max_length=120)
    points: int
    grave: bool = False
    active: bool = True


class SettingsIn(BaseModel):
    late_threshold: int = 5
    late_penalty: int = 5
    alert_below: int = 50


class ScaleIn(BaseModel):
    rules: list[RuleIn] = Field(min_length=1, max_length=60)
    settings: SettingsIn


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


class _Tx:
    """Tenant transaction that also carries the services (names are resolved through the platform pool)."""
    def __init__(self, services: AppServices, actor: ActorContext):
        self.services, self.cm = services, services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id)

    def __enter__(self):
        conn = self.cm.__enter__()
        conn.info["services"] = self.services
        return conn

    def __exit__(self, *exc):
        return self.cm.__exit__(*exc)


def _tx(services: AppServices, actor: ActorContext):
    return _Tx(services, actor)


def _audit(conn, actor: ActorContext, action: str, entity_id: UUID, old=None, new=None) -> None:
    PostgresAuditRepository(conn).append(AuditRecord(action=action, entity_type="PedagogyTeaching", entity_id=entity_id,
                                                     actor_user_id=actor.user_id, school_id=actor.school_id, source=actor.source,
                                                     reason=None, old_data=old, new_data=new, correlation_id=uuid4()))


TEACHERS_SQL = """SELECT m.id AS membership_id, m.user_id,
      (SELECT count(*) FROM pedagogy_teaching_assignments t WHERE t.membership_id=m.id) AS courses,
      (SELECT count(*) FROM pedagogy_class_titulars c WHERE c.membership_id=m.id) AS titular_of
    FROM school_memberships m
    WHERE m.school_id=:s AND m.active AND EXISTS (
      SELECT 1 FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id AND r.status='ACTIVE'
      JOIN rbac_role_capabilities rc ON rc.role_id=a.role_id AND rc.capability_code=:cap
      WHERE a.membership_id=m.id AND a.school_id=m.school_id AND a.active AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now()))
    ORDER BY m.id"""


def _names(conn, user_ids) -> dict[str, dict]:
    """Display names of members already proven to belong to this school (tenant RLS on users shows only one's own row;
    the platform pool resolves exactly these ids — same rule as « Accès et rôles »)."""
    return _user_cards(conn.info["services"], {str(u) for u in user_ids if u}) if user_ids else {}


def _teachers(conn, actor: ActorContext) -> dict[str, dict]:
    rows = conn.execute(text(TEACHERS_SQL), {"s": str(actor.school_id), "cap": TEACH_CAP}).mappings().all()
    cards = _names(conn, {r["user_id"] for r in rows})
    out = [{"membership_id": str(r["membership_id"]), "full_name": cards.get(str(r["user_id"]), {}).get("full_name", "Membre"),
            "email": cards.get(str(r["user_id"]), {}).get("email", ""), "courses": r["courses"], "titular_of": r["titular_of"]} for r in rows]
    return {o["membership_id"]: o for o in sorted(out, key=lambda o: o["full_name"].lower())}


@router.get("/teachers")
def teachers(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
             _module: ActorContext = Depends(require_pedagogy)):
    _need(actor, MANAGE)
    with _tx(services, actor) as conn:
        return list(_teachers(conn, actor).values())


def _classes(conn, actor: ActorContext, year_id, sections: set[str] | None, class_id: UUID | None = None) -> list[dict]:
    rows = conn.execute(text("""SELECT c.id,c.label,c.code,s.code AS section_code,s.label AS section_label,l.ref_class_code,rc.label AS ref_label,
          (SELECT p.id FROM pedagogy_programmes p WHERE p.school_id=c.school_id AND p.academic_year_id=c.academic_year_id
             AND p.ref_class_code=l.ref_class_code AND p.status='VALIDATED') AS programme_id,
          t.membership_id AS titular_id, tm.user_id AS titular_user
        FROM school_classes c JOIN school_sections s ON s.id=c.section_id
        LEFT JOIN pedagogy_class_links l ON l.class_id=c.id LEFT JOIN ref_classes rc ON rc.code=l.ref_class_code
        LEFT JOIN pedagogy_class_titulars t ON t.class_id=c.id
        LEFT JOIN school_memberships tm ON tm.id=t.membership_id
        WHERE c.school_id=:s AND c.academic_year_id=:y AND c.enabled AND (CAST(:id AS uuid) IS NULL OR c.id=CAST(:id AS uuid))
        ORDER BY s.code, (c.reference_code LIKE 'H%') NULLS LAST, c.reference_code NULLS LAST, c.code"""),
        {"s": str(actor.school_id), "y": str(year_id), "id": str(class_id) if class_id else None}).mappings().all()
    out = [dict(r) for r in rows if sections is None or str(r["section_code"]).upper() in sections]
    cards = _names(conn, {r["titular_user"] for r in out})
    for r in out:
        r["titular_name"] = cards.get(str(r["titular_user"]), {}).get("full_name", "Membre") if r["titular_user"] else None
    return out


def _courses(conn, actor: ActorContext, class_row: dict) -> list[dict]:
    if not class_row["programme_id"]:
        return []
    rows = conn.execute(text("""SELECT l.course_code,k.label,l.subdomain,l.sort_order,a.membership_id,m.user_id
        FROM pedagogy_programme_lines l JOIN ref_courses k ON k.code=l.course_code
        LEFT JOIN pedagogy_teaching_assignments a ON a.class_id=:c AND a.course_code=l.course_code
        LEFT JOIN school_memberships m ON m.id=a.membership_id
        WHERE l.programme_id=:p ORDER BY l.sort_order"""), {"c": str(class_row["id"]), "p": str(class_row["programme_id"])}).mappings()
    rows = rows.all()
    cards = _names(conn, {r["user_id"] for r in rows})
    out = [{"course_code": r["course_code"], "label": r["label"], "subdomain": r["subdomain"],
            "teacher": {"membership_id": str(r["membership_id"]), "full_name": cards.get(str(r["user_id"]), {}).get("full_name", "Membre")}
            if r["membership_id"] else None} for r in rows]
    _distinct_labels(out)
    return out


def _class_view(conn, actor: ActorContext, r: dict) -> dict:
    courses = _courses(conn, actor, r)
    return {"class_id": str(r["id"]), "label": r["label"], "section_code": r["section_code"], "section_label": r["section_label"],
            "ref_class_code": r["ref_class_code"], "ref_label": r["ref_label"], "has_programme": bool(r["programme_id"]),
            "titular": {"membership_id": str(r["titular_id"]), "full_name": r["titular_name"]} if r["titular_id"] else None,
            "titular_effective": str(r["section_code"]).upper() in AUTO_TITULAR_SECTIONS,
            "courses": courses, "assigned": sum(1 for c in courses if c["teacher"])}


@router.get("/teaching")
def teaching(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
             _module: ActorContext = Depends(require_pedagogy)):
    _need(actor, MANAGE)
    with _tx(services, actor) as conn:
        year = active_year(conn, actor)
        items = [_class_view(conn, actor, r) for r in _classes(conn, actor, year["id"], _sections(actor, MANAGE))]
        teachers_ = list(_teachers(conn, actor).values())
    total = sum(len(i["courses"]) for i in items)
    return {"year": {"id": str(year["id"]), "label": year["label"]}, "teachers": teachers_, "items": items,
            "summary": {"classes": len(items), "with_titular": sum(1 for i in items if i["titular"]), "courses": total,
                        "assigned": sum(i["assigned"] for i in items), "without_programme": sum(1 for i in items if not i["has_programme"]),
                        "teachers": len(teachers_)}}


def _target(conn, actor: ActorContext, class_id: UUID) -> dict:
    year = active_year(conn, actor)
    rows = _classes(conn, actor, year["id"], _sections(actor, MANAGE), class_id)
    if not rows:
        raise HTTPException(404, "Classe introuvable dans votre périmètre")
    return rows[0]


def _teacher(conn, actor: ActorContext, membership_id: UUID | None) -> dict | None:
    if membership_id is None:
        return None
    t = _teachers(conn, actor).get(str(membership_id))
    if t is None:
        raise HTTPException(409, "Cette personne n’a pas le rôle Enseignant : attribuez-le d’abord dans Accès et rôles.")
    return t


@router.put("/teaching/{class_id}/courses/{course_code}")
def assign_course(class_id: UUID, course_code: str, body: MemberIn, actor: ActorContext = Depends(require_school_actor),
                  services: AppServices = Depends(get_services), _module: ActorContext = Depends(require_pedagogy)):
    _need(actor, MANAGE)
    course = course_code.strip().upper()
    with _tx(services, actor) as conn:
        cls = _target(conn, actor, class_id)
        if course not in {c["course_code"] for c in _courses(conn, actor, cls)}:
            raise HTTPException(404, "Ce cours n’est pas au programme en service de cette classe")
        teacher = _teacher(conn, actor, body.membership_id)
        old = conn.execute(text("SELECT membership_id FROM pedagogy_teaching_assignments WHERE class_id=:c AND course_code=:k"),
                           {"c": str(class_id), "k": course}).scalar()
        if teacher is None:
            conn.execute(text("DELETE FROM pedagogy_teaching_assignments WHERE class_id=:c AND course_code=:k AND school_id=:s"),
                         {"c": str(class_id), "k": course, "s": str(actor.school_id)})
        else:
            conn.execute(text("""INSERT INTO pedagogy_teaching_assignments(class_id,course_code,school_id,membership_id,assigned_by)
                VALUES(:c,:k,:s,:m,:u) ON CONFLICT (class_id,course_code) DO UPDATE SET membership_id=EXCLUDED.membership_id,
                  assigned_by=EXCLUDED.assigned_by, assigned_at=now()"""),
                {"c": str(class_id), "k": course, "s": str(actor.school_id), "m": teacher["membership_id"], "u": str(actor.user_id)})
        _audit(conn, actor, "PEDAGOGY_COURSE_ASSIGNED" if teacher else "PEDAGOGY_COURSE_UNASSIGNED", class_id,
               old={"course": course, "membership_id": str(old) if old else None},
               new={"class": cls["label"], "course": course, "membership_id": teacher["membership_id"] if teacher else None})
        return _class_view(conn, actor, _target(conn, actor, class_id))


@router.post("/teaching/{class_id}/assign-all")
def assign_all(class_id: UUID, body: MemberIn, actor: ActorContext = Depends(require_school_actor),
               services: AppServices = Depends(get_services), _module: ActorContext = Depends(require_pedagogy)):
    """One teacher for every course still without teacher (the usual case in maternelle and primaire)."""
    _need(actor, MANAGE)
    with _tx(services, actor) as conn:
        cls = _target(conn, actor, class_id)
        teacher = _teacher(conn, actor, body.membership_id)
        if teacher is None:
            raise HTTPException(422, "Choisissez l’enseignant")
        free = [c["course_code"] for c in _courses(conn, actor, cls) if not c["teacher"]]
        if not cls["programme_id"]:
            raise HTTPException(409, "Mettez d’abord le programme de cette classe en service (onglet Programmes).")
        for course in free:
            conn.execute(text("""INSERT INTO pedagogy_teaching_assignments(class_id,course_code,school_id,membership_id,assigned_by)
                VALUES(:c,:k,:s,:m,:u) ON CONFLICT (class_id,course_code) DO NOTHING"""),
                {"c": str(class_id), "k": course, "s": str(actor.school_id), "m": teacher["membership_id"], "u": str(actor.user_id)})
        if free:
            _audit(conn, actor, "PEDAGOGY_COURSES_ASSIGNED_ALL", class_id, new={"class": cls["label"], "membership_id": teacher["membership_id"], "courses": free})
        view = _class_view(conn, actor, _target(conn, actor, class_id))
    return {**view, "newly_assigned": len(free)}


@router.put("/teaching/{class_id}/titular")
def set_titular(class_id: UUID, body: MemberIn, actor: ActorContext = Depends(require_school_actor),
                services: AppServices = Depends(get_services), _module: ActorContext = Depends(require_pedagogy)):
    _need(actor, MANAGE)
    with _tx(services, actor) as conn:
        cls = _target(conn, actor, class_id)
        teacher = _teacher(conn, actor, body.membership_id)
        if teacher is None:
            conn.execute(text("DELETE FROM pedagogy_class_titulars WHERE class_id=:c AND school_id=:s"), {"c": str(class_id), "s": str(actor.school_id)})
        else:
            conn.execute(text("""INSERT INTO pedagogy_class_titulars(class_id,school_id,membership_id,assigned_by) VALUES(:c,:s,:m,:u)
                ON CONFLICT (class_id) DO UPDATE SET membership_id=EXCLUDED.membership_id, assigned_by=EXCLUDED.assigned_by, assigned_at=now()"""),
                {"c": str(class_id), "s": str(actor.school_id), "m": teacher["membership_id"], "u": str(actor.user_id)})
        _audit(conn, actor, "PEDAGOGY_TITULAR_SET" if teacher else "PEDAGOGY_TITULAR_REMOVED", class_id,
               old={"membership_id": str(cls["titular_id"]) if cls["titular_id"] else None},
               new={"class": cls["label"], "membership_id": teacher["membership_id"] if teacher else None})
        return _class_view(conn, actor, _target(conn, actor, class_id))


@router.get("/my-teaching")
def my_teaching(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
                _module: ActorContext = Depends(require_pedagogy)):
    _need(actor, OWN)
    with _tx(services, actor) as conn:
        year = active_year(conn, actor)
        rows = conn.execute(text("""SELECT c.id,c.label,s.code AS section_code,s.label AS section_label,a.course_code,k.label AS course_label,
              (SELECT pl.subdomain FROM pedagogy_class_links lk JOIN pedagogy_programmes p ON p.school_id=c.school_id AND p.academic_year_id=c.academic_year_id
                 AND p.ref_class_code=lk.ref_class_code AND p.status='VALIDATED'
               JOIN pedagogy_programme_lines pl ON pl.programme_id=p.id AND pl.course_code=a.course_code WHERE lk.class_id=c.id) AS subdomain
            FROM pedagogy_teaching_assignments a JOIN school_classes c ON c.id=a.class_id JOIN school_sections s ON s.id=c.section_id
            JOIN ref_courses k ON k.code=a.course_code
            WHERE a.school_id=:s AND a.membership_id=:m AND c.academic_year_id=:y ORDER BY s.code,c.label,k.label"""),
            {"s": str(actor.school_id), "m": str(actor.membership_id), "y": str(year["id"])}).mappings().all()
        titular = conn.execute(text("""SELECT c.id,c.label,s.code AS section_code FROM pedagogy_class_titulars t
            JOIN school_classes c ON c.id=t.class_id JOIN school_sections s ON s.id=c.section_id
            WHERE t.school_id=:s AND t.membership_id=:m AND c.academic_year_id=:y ORDER BY c.label"""),
            {"s": str(actor.school_id), "m": str(actor.membership_id), "y": str(year["id"])}).mappings().all()
    classes: dict[str, dict] = {}
    for r in rows:
        item = classes.setdefault(str(r["id"]), {"class_id": str(r["id"]), "label": r["label"], "section_label": r["section_label"], "courses": []})
        item["courses"].append({"course_code": r["course_code"], "label": r["course_label"], "subdomain": r["subdomain"]})
    for item in classes.values():
        _distinct_labels(item["courses"])
    return {"year": {"id": str(year["id"]), "label": year["label"]}, "classes": list(classes.values()),
            "titular_of": [{"class_id": str(t["id"]), "label": t["label"], "effective": str(t["section_code"]).upper() in AUTO_TITULAR_SECTIONS} for t in titular]}


def _scale(conn, actor: ActorContext) -> dict:
    rules = [dict(r) for r in conn.execute(text("""SELECT code,label,points,grave,active FROM pedagogy_conduct_rules WHERE school_id=:s
        ORDER BY sort_order, code"""), {"s": str(actor.school_id)}).mappings()]
    settings = conn.execute(text("SELECT late_rule_code,late_threshold,late_penalty,alert_below FROM pedagogy_conduct_settings WHERE school_id=:s"),
                            {"s": str(actor.school_id)}).mappings().first()
    saved = bool(rules)
    if not saved:
        rules = [{"code": r.code, "label": r.label, "points": r.points, "grave": r.grave, "active": True} for r in cd.DEFAULT_RULES]
    return {"saved": saved, "start": cd.START, "rules": rules, "settings": dict(settings) if settings else dict(cd.DEFAULT_SETTINGS),
            "mentions": [{"code": c, "from": f, "label": label} for c, f, label in cd.MENTIONS], "can_configure": CONDUCT in actor.permissions}


@router.get("/conduct/scale")
def conduct_scale(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
                  _module: ActorContext = Depends(require_pedagogy)):
    _need(actor, READ)
    with _tx(services, actor) as conn:
        return _scale(conn, actor)


@router.put("/conduct/scale")
def save_conduct_scale(body: ScaleIn, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
                       _module: ActorContext = Depends(require_pedagogy)):
    _need(actor, CONDUCT)
    codes = [r.code.strip().upper() for r in body.rules]
    if len(set(codes)) != len(codes):
        raise HTTPException(422, "Deux faits ont le même code")
    try:
        for r, code in zip(body.rules, codes):
            cd.check_rule(code, r.label, r.points)
        cd.check_settings(body.settings.late_threshold, body.settings.late_penalty, body.settings.alert_below)
    except cd.ConductError as exc:
        raise HTTPException(422, str(exc)) from exc
    with _tx(services, actor) as conn:
        old = _scale(conn, actor)
        for i, (r, code) in enumerate(zip(body.rules, codes), start=1):
            conn.execute(text("""INSERT INTO pedagogy_conduct_rules(school_id,code,label,points,grave,active,sort_order,updated_by)
                VALUES(:s,:c,:l,:p,:g,:a,:o,:u) ON CONFLICT (school_id,code) DO UPDATE SET label=EXCLUDED.label, points=EXCLUDED.points,
                  grave=EXCLUDED.grave, active=EXCLUDED.active, sort_order=EXCLUDED.sort_order, updated_by=EXCLUDED.updated_by, updated_at=now()"""),
                {"s": str(actor.school_id), "c": code, "l": " ".join(r.label.split()), "p": r.points, "g": r.grave, "a": r.active, "o": i, "u": str(actor.user_id)})
        # a fact removed from the list is deactivated, never deleted (facts already reported keep their meaning)
        conn.execute(text("UPDATE pedagogy_conduct_rules SET active=false, updated_at=now() WHERE school_id=:s AND NOT (code = ANY(:codes))"),
                     {"s": str(actor.school_id), "codes": codes})
        late_code = "RETARD" if "RETARD" in codes else codes[0]
        conn.execute(text("""INSERT INTO pedagogy_conduct_settings(school_id,late_rule_code,late_threshold,late_penalty,alert_below,updated_by)
            VALUES(:s,:lc,:lt,:lp,:ab,:u) ON CONFLICT (school_id) DO UPDATE SET late_rule_code=EXCLUDED.late_rule_code,
              late_threshold=EXCLUDED.late_threshold, late_penalty=EXCLUDED.late_penalty, alert_below=EXCLUDED.alert_below,
              updated_by=EXCLUDED.updated_by, updated_at=now(), version=pedagogy_conduct_settings.version+1"""),
            {"s": str(actor.school_id), "lc": late_code, "lt": body.settings.late_threshold, "lp": body.settings.late_penalty,
             "ab": body.settings.alert_below, "u": str(actor.user_id)})
        PostgresAuditRepository(conn).append(AuditRecord(action="PEDAGOGY_CONDUCT_SCALE_SAVED", entity_type="PedagogyConductScale",
            entity_id=actor.school_id, actor_user_id=actor.user_id, school_id=actor.school_id, source=actor.source, reason=None,
            old_data={"rules": old["rules"], "settings": old["settings"]}, new_data=body.model_dump(), correlation_id=uuid4()))
        return _scale(conn, actor)
