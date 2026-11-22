"""Conduct facts — the conduct is COMPUTED (owner 2026-11-22: « rendre ça automatique »). V2 lot 3b.

GET  /pedagogy/conduct/classes                    the classes the member may report on (taught, titular, or his scope)
GET  /pedagogy/conduct/class/{class_id}[?period]  pupils with their computed conduct, mention, facts, « à suivre »
POST /pedagogy/conduct/facts                      report a fact in 3 taps (Idempotency-Key: offline replay safe)
POST /pedagogy/conduct/facts/{id}/cancel          the author the same day, or the discipline director (motif)
POST /pedagogy/conduct/adjust                     exceptional adjustment by the discipline director (motif)
A fact belongs to the simple period of its day (exam session → the period before); a closed period is frozen.
A serious fact alerts at once the members who manage conduct (bell + notification).
"""
from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from edusync.adapters.postgres_idempotency import PostgresIdempotencyRepository
from edusync.adapters.postgres_repositories import PostgresAuditRepository
from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.modules.audit.domain.audit import AuditRecord
from edusync.modules.pedagogy.api.calendar import active_year, period_states
from edusync.modules.pedagogy.domain import conduct as cd
from edusync.modules.pedagogy.domain.grades import conduct_period
from edusync.modules.school_modules.api.guard import require_pedagogy
from edusync.shared.application.context import ActorContext
from edusync.shared.application.idempotency import IdempotentExecutor
from edusync.shared.domain.concurrency import IdempotencyConflict, IdempotencyInProgress
from edusync.shared.infrastructure.realtime import note_inbox_changed

router = APIRouter(tags=["Pédagogie (V2) — conduite"])
REPORT, MANAGE = "pedagogy.conduct.report", "pedagogy.conduct.manage"
SIMPLE = ("P1", "P2", "P3", "P4", "P5", "P6")


class FactIn(BaseModel):
    class_id: UUID
    student_id: UUID
    rule_code: str = Field(min_length=2, max_length=32)
    note: str | None = Field(default=None, max_length=300)


class CancelIn(BaseModel):
    reason: str = Field(min_length=5, max_length=300)


class AdjustIn(BaseModel):
    class_id: UUID
    student_id: UUID
    period: str = Field(min_length=2, max_length=2)
    points: int = Field(ge=-100, le=100)
    reason: str = Field(min_length=5, max_length=300)


def _need(actor: ActorContext, capability: str) -> None:
    try:
        actor.require(capability)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


def _tx(services: AppServices, actor: ActorContext):
    return services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id)


def _sections(actor: ActorContext, capability: str) -> set[str] | None:
    scopes = actor.scopes_for(capability)
    if not scopes or any(t == "SCHOOL" for t, _ in scopes):
        return None
    return {str(v).upper() for t, v in scopes if t == "SECTION" and v}


def _scale(conn, actor: ActorContext) -> tuple[dict[str, cd.Rule], dict]:
    rows = conn.execute(text("SELECT code,label,points,grave FROM pedagogy_conduct_rules WHERE school_id=:s AND active ORDER BY sort_order"),
                        {"s": str(actor.school_id)}).mappings().all()
    rules = {r["code"]: cd.Rule(r["code"], r["label"], r["points"], r["grave"]) for r in rows} or {r.code: r for r in cd.DEFAULT_RULES}
    s = conn.execute(text("SELECT late_rule_code,late_threshold,late_penalty,alert_below FROM pedagogy_conduct_settings WHERE school_id=:s"),
                     {"s": str(actor.school_id)}).mappings().first()
    return rules, dict(s) if s else dict(cd.DEFAULT_SETTINGS)


def _manages(actor: ActorContext, section_code: str) -> bool:
    if MANAGE not in actor.permissions:
        return False
    secs = _sections(actor, MANAGE)
    return secs is None or section_code.upper() in secs


def _class(conn, actor: ActorContext, class_id: UUID) -> dict:
    """The class (active year) if the member may report on it: he teaches it, is its titular, or holds the right on its
    section (directors)."""
    year = active_year(conn, actor)
    c = conn.execute(text("""SELECT c.id,c.label,s.code AS section_code,rc.structure FROM school_classes c JOIN school_sections s ON s.id=c.section_id
        LEFT JOIN pedagogy_class_links l ON l.class_id=c.id LEFT JOIN ref_classes rc ON rc.code=l.ref_class_code
        WHERE c.id=:c AND c.school_id=:s AND c.academic_year_id=:y"""), {"c": str(class_id), "s": str(actor.school_id), "y": str(year["id"])}).mappings().first()
    if c is None:
        raise HTTPException(404, "Classe introuvable")
    _need(actor, REPORT)
    own = conn.execute(text("""SELECT 1 FROM pedagogy_teaching_assignments WHERE class_id=:c AND membership_id=:m
        UNION SELECT 1 FROM pedagogy_class_titulars WHERE class_id=:c AND membership_id=:m"""), {"c": str(class_id), "m": str(actor.membership_id)}).first()
    secs = _sections(actor, REPORT)
    is_teacher_only = "pedagogy.teaching.own.read" in actor.permissions and not ({"pedagogy.grades.read", MANAGE} & set(actor.permissions))
    in_scope = not is_teacher_only and (secs is None or str(c["section_code"]).upper() in secs)
    if not (own or in_scope):
        raise HTTPException(404, "Classe introuvable dans votre périmètre")
    if not c["structure"]:
        raise HTTPException(409, "Reliez d’abord cette classe à sa classe officielle (onglet Classes).")
    return {**dict(c), "year": year}


def _current_period(conn, actor: ActorContext, cls: dict, day: date) -> tuple[str, dict]:
    periods = period_states(conn, actor, cls["year"], cls["structure"])
    if not periods:
        raise HTTPException(409, "Le calendrier pédagogique n’est pas encore enregistré : aucune période en cours.")
    code = conduct_period(list(periods.values()), day)
    if code is None:
        raise HTTPException(409, "Aucune période en cours à cette date (vérifiez le calendrier).")
    return code, periods


def _pupils(conn, actor: ActorContext, cls: dict, *, with_departed: bool = False) -> list[dict]:
    """Pupils present in the class; a pupil who left (abandon, transfer) is no longer reported on (his facts stay)."""
    rows = conn.execute(text("""SELECT st.id,st.last_name,st.middle_name,st.first_name,st.status,
          (SELECT max(ev.effective_date) FROM student_status_events ev WHERE ev.school_id=st.school_id AND ev.student_id=st.id
             AND ev.event_type IN ('ABANDON','TRANSFER')) AS left_on
        FROM enrollments e JOIN students st ON st.id=e.student_id
        WHERE e.school_id=:s AND e.class_id=:c AND e.academic_year_id=:y AND e.status IN ('VALIDATED','COMPLETED')
        ORDER BY (st.status IN ('ABANDON','TRANSFERRED')), st.last_name, st.middle_name NULLS FIRST, st.first_name"""), {"s": str(actor.school_id), "c": str(cls["id"]), "y": str(cls["year"]["id"])}).mappings()
    return [{"student_id": str(r["id"]), "name": " ".join(x for x in (r["last_name"], r["middle_name"], r["first_name"]) if x),
             "suspended": r["status"] == "SUSPENDED"}
            for r in rows if with_departed or r["status"] not in ("ABANDON", "TRANSFERRED")]


def _conducts(conn, actor: ActorContext, cls: dict, period: str, student_id: str | None = None) -> dict[str, dict]:
    _, settings = _scale(conn, actor)
    facts: dict[str, list] = {}
    for f in conn.execute(text("""SELECT id,student_id,rule_code,rule_label,points,grave,note,occurred_on,reported_by,reported_at
            FROM pedagogy_conduct_facts WHERE school_id=:s AND academic_year_id=:y AND period_code=:p AND cancelled_at IS NULL
              AND (CAST(:st AS uuid) IS NULL OR student_id=CAST(:st AS uuid)) ORDER BY reported_at DESC"""),
            {"s": str(actor.school_id), "y": str(cls["year"]["id"]), "p": period, "st": student_id}).mappings():
        facts.setdefault(str(f["student_id"]), []).append(f)
    adjust = {str(r[0]): int(r[1]) for r in conn.execute(text("""SELECT student_id,sum(points) FROM pedagogy_conduct_adjustments
        WHERE school_id=:s AND academic_year_id=:y AND period_code=:p GROUP BY 1"""), {"s": str(actor.school_id), "y": str(cls["year"]["id"]), "p": period})}
    out = {}
    for sid in ({student_id} if student_id else {p["student_id"] for p in _pupils(conn, actor, cls)}):
        mine = facts.get(sid, [])
        result = cd.compute([{"code": f["rule_code"], "points": f["points"]} for f in mine], adjustment=adjust.get(sid, 0), **settings)
        today = date.today()
        out[sid] = {**result, "adjustment": adjust.get(sid, 0),
                    "recent": [{"id": str(f["id"]), "label": f["rule_label"], "points": f["points"], "grave": f["grave"], "note": f["note"],
                                "occurred_on": f["occurred_on"].isoformat(),
                                "can_cancel": (str(f["reported_by"]) == str(actor.membership_id) and f["reported_at"].date() == today) or _manages(actor, cls["section_code"])}
                               for f in mine[:10]]}
    return out


@router.get("/conduct/classes")
def conduct_classes(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
                    _module: ActorContext = Depends(require_pedagogy)):
    _need(actor, REPORT)
    with _tx(services, actor) as conn:
        year = active_year(conn, actor)
        rows = conn.execute(text("""SELECT c.id,c.label,s.code AS section_code,s.label AS section_label,
              EXISTS(SELECT 1 FROM pedagogy_teaching_assignments a WHERE a.class_id=c.id AND a.membership_id=:m) AS teaches,
              EXISTS(SELECT 1 FROM pedagogy_class_titulars t WHERE t.class_id=c.id AND t.membership_id=:m) AS titular
            FROM school_classes c JOIN school_sections s ON s.id=c.section_id JOIN pedagogy_class_links l ON l.class_id=c.id
            WHERE c.school_id=:s AND c.academic_year_id=:y AND c.enabled
            ORDER BY s.code, (c.reference_code LIKE 'H%') NULLS LAST, c.reference_code NULLS LAST, c.code"""),
            {"s": str(actor.school_id), "y": str(year["id"]), "m": str(actor.membership_id)}).mappings().all()
    secs = _sections(actor, REPORT)
    teacher_only = "pedagogy.teaching.own.read" in actor.permissions and not ({"pedagogy.grades.read", MANAGE} & set(actor.permissions))
    items = [{"class_id": str(r["id"]), "label": r["label"], "section_label": r["section_label"], "titular": r["titular"], "teaches": r["teaches"]}
             for r in rows if r["teaches"] or r["titular"] or (not teacher_only and (secs is None or str(r["section_code"]).upper() in secs))]
    items.sort(key=lambda i: (not i["titular"], not i["teaches"]))          # his own classes first
    return {"items": items}


@router.get("/conduct/class/{class_id}")
def conduct_class(class_id: UUID, period: str | None = Query(default=None, max_length=2), actor: ActorContext = Depends(require_school_actor),
                  services: AppServices = Depends(get_services), _module: ActorContext = Depends(require_pedagogy)):
    with _tx(services, actor) as conn:
        cls = _class(conn, actor, class_id)
        try:
            current, periods = _current_period(conn, actor, cls, date.today())
        except HTTPException:
            current, periods = None, period_states(conn, actor, cls["year"], cls["structure"])
        chosen = (period or current or "").upper()
        if chosen not in SIMPLE:
            raise HTTPException(409, "Aucune période en cours : le calendrier pédagogique doit être enregistré et validé.")
        rules, settings = _scale(conn, actor)
        conducts = _conducts(conn, actor, cls, chosen)
        pupils = [{**p, **conducts[p["student_id"]]} for p in _pupils(conn, actor, cls)]
        manages = _manages(actor, cls["section_code"])
    return {"class": {"id": str(cls["id"]), "label": cls["label"]}, "period": {"code": chosen, "label": periods.get(chosen, {}).get("label", chosen),
            "current": chosen == current, "closed": bool(periods.get(chosen, {}).get("closed"))},
            "periods": [{"code": c, "label": p["label"]} for c, p in periods.items() if c in SIMPLE],
            "rules": [{"code": r.code, "label": r.label, "points": r.points, "grave": r.grave} for r in rules.values() if manages or not r.grave],
            "settings": settings, "can_manage": manages, "pupils": pupils,
            "summary": {"pupils": len(pupils), "to_follow": sum(1 for p in pupils if p["to_follow"]), "facts": sum(p["facts"] for p in pupils)}}


def _alert(conn, actor: ActorContext, cls: dict, pupil_name: str, rule: cd.Rule) -> None:
    """A serious fact: the members who manage conduct are told at once (bell rings after the commit)."""
    rows = conn.execute(text("""SELECT DISTINCT m.user_id FROM school_memberships m
        JOIN rbac_assignments a ON a.membership_id=m.id AND a.active AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now())
        JOIN rbac_role_capabilities rc ON rc.role_id=a.role_id AND rc.capability_code=:cap
        WHERE m.school_id=:s AND m.active AND m.id<>:me"""), {"s": str(actor.school_id), "cap": MANAGE, "me": str(actor.membership_id)}).all()
    for (user_id,) in rows:
        conn.execute(text("""INSERT INTO notifications(school_id,user_id,category,severity,title,body,link_path)
            VALUES(:s,:u,'CONDUITE','WARNING',:t,:b,'/pedagogie')"""),
            {"s": str(actor.school_id), "u": str(user_id), "t": f"Fait grave : {rule.label}"[:180],
             "b": f"{pupil_name} ({cls['label']}) : {rule.label} ({rule.points} points)."[:2000]})
        note_inbox_changed(user_id, actor.school_id)


@router.post("/conduct/facts", status_code=201)
def report_fact(body: FactIn, response: Response, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
                _module: ActorContext = Depends(require_pedagogy)):
    key = (idempotency_key or "").strip() or f"fact-{uuid4()}"
    try:
        with _tx(services, actor) as conn:
            idem = IdempotentExecutor(PostgresIdempotencyRepository(conn))

            def action():
                cls = _class(conn, actor, body.class_id)
                rules, _ = _scale(conn, actor)
                rule = rules.get(body.rule_code.strip().upper())
                if rule is None:
                    raise HTTPException(404, "Fait inconnu du barème de l’école")
                if rule.grave and not _manages(actor, cls["section_code"]):
                    raise HTTPException(403, "Fait grave : seuls le directeur de discipline et le préfet le signalent.")
                pupil = next((p for p in _pupils(conn, actor, cls) if p["student_id"] == str(body.student_id)), None)
                if pupil is None:
                    gone = any(p["student_id"] == str(body.student_id) for p in _pupils(conn, actor, cls, with_departed=True))
                    raise HTTPException(409 if gone else 404, "Élève parti (abandon ou transfert) : plus de fait à signaler." if gone else "Élève absent de cette classe")
                period, periods = _current_period(conn, actor, cls, date.today())
                if periods[period]["closed"]:
                    raise HTTPException(409, "Période clôturée : la conduite est figée.")
                fid = conn.execute(text("""INSERT INTO pedagogy_conduct_facts(school_id,academic_year_id,class_id,student_id,period_code,rule_code,rule_label,points,grave,note,reported_by)
                    VALUES(:s,:y,:c,:st,:p,:r,:l,:pts,:g,:n,:m) RETURNING id"""),
                    {"s": str(actor.school_id), "y": str(cls["year"]["id"]), "c": str(cls["id"]), "st": str(body.student_id), "p": period, "r": rule.code,
                     "l": rule.label, "pts": rule.points, "g": rule.grave, "n": (body.note or "").strip() or None, "m": str(actor.membership_id)}).scalar()
                if rule.grave:
                    _alert(conn, actor, cls, pupil["name"], rule)
                conduct = _conducts(conn, actor, cls, period, str(body.student_id))[str(body.student_id)]
                return 201, {"fact_id": str(fid), "period": period, "student_id": str(body.student_id), "name": pupil["name"], **conduct}

            result = idem.execute(scope_key=str(actor.school_id), idempotency_key=key, operation="PEDAGOGY_CONDUCT_FACT",
                                  payload=body.model_dump(mode="json"), school_id=str(actor.school_id), actor_user_id=str(actor.user_id), action=action)
        response.status_code = result.status_code
        response.headers["Idempotent-Replayed"] = "true" if result.replayed else "false"
        return result.body
    except (IdempotencyConflict, IdempotencyInProgress) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/conduct/facts/{fact_id}/cancel")
def cancel_fact(fact_id: UUID, body: CancelIn, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
                _module: ActorContext = Depends(require_pedagogy)):
    with _tx(services, actor) as conn:
        f = conn.execute(text("""SELECT f.id,f.class_id,f.student_id,f.period_code,f.reported_by,f.reported_at,f.cancelled_at,f.rule_label,f.points
            FROM pedagogy_conduct_facts f WHERE f.id=:id AND f.school_id=:s FOR UPDATE"""), {"id": str(fact_id), "s": str(actor.school_id)}).mappings().first()
        if f is None:
            raise HTTPException(404, "Fait introuvable")
        cls = _class(conn, actor, f["class_id"])
        if f["cancelled_at"]:
            return {"cancelled": True}
        own_today = str(f["reported_by"]) == str(actor.membership_id) and f["reported_at"].date() == date.today()
        if not (own_today or _manages(actor, cls["section_code"])):
            raise HTTPException(403, "Seul l’auteur (le jour même) ou le directeur de discipline annule un fait.")
        if period_states(conn, actor, cls["year"], cls["structure"]).get(f["period_code"], {}).get("closed"):
            raise HTTPException(409, "Période clôturée : la conduite est figée.")
        conn.execute(text("UPDATE pedagogy_conduct_facts SET cancelled_at=now(), cancelled_by=:m, cancel_reason=:r WHERE id=:id"),
                     {"m": str(actor.membership_id), "r": " ".join(body.reason.split()), "id": str(fact_id)})
        PostgresAuditRepository(conn).append(AuditRecord(action="PEDAGOGY_CONDUCT_FACT_CANCELLED", entity_type="PedagogyConductFact", entity_id=fact_id,
            actor_user_id=actor.user_id, school_id=actor.school_id, source=actor.source, reason=body.reason, old_data={"fact": f["rule_label"], "points": f["points"]},
            new_data=None, correlation_id=uuid4()))
        conduct = _conducts(conn, actor, cls, f["period_code"], str(f["student_id"]))[str(f["student_id"])]
    return {"cancelled": True, "student_id": str(f["student_id"]), **conduct}


@router.post("/conduct/adjust")
def adjust(body: AdjustIn, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
           _module: ActorContext = Depends(require_pedagogy)):
    period = body.period.strip().upper()
    if period not in SIMPLE or body.points == 0:
        raise HTTPException(422, "Période P1 à P6 et points différents de 0")
    with _tx(services, actor) as conn:
        cls = _class(conn, actor, body.class_id)
        if not _manages(actor, cls["section_code"]):
            raise HTTPException(403, "Seul le directeur de discipline ajuste une conduite.")
        if str(body.student_id) not in {p["student_id"] for p in _pupils(conn, actor, cls)}:
            raise HTTPException(404, "Élève absent de cette classe")
        if period_states(conn, actor, cls["year"], cls["structure"]).get(period, {}).get("closed"):
            raise HTTPException(409, "Période clôturée : la conduite est figée.")
        conn.execute(text("""INSERT INTO pedagogy_conduct_adjustments(school_id,academic_year_id,student_id,period_code,points,reason,adjusted_by)
            VALUES(:s,:y,:st,:p,:pts,:r,:m)"""), {"s": str(actor.school_id), "y": str(cls["year"]["id"]), "st": str(body.student_id), "p": period,
            "pts": body.points, "r": " ".join(body.reason.split()), "m": str(actor.membership_id)})
        PostgresAuditRepository(conn).append(AuditRecord(action="PEDAGOGY_CONDUCT_ADJUSTED", entity_type="PedagogyConduct", entity_id=body.student_id,
            actor_user_id=actor.user_id, school_id=actor.school_id, source=actor.source, reason=body.reason, old_data=None,
            new_data={"period": period, "points": body.points}, correlation_id=uuid4()))
        conduct = _conducts(conn, actor, cls, period, str(body.student_id))[str(body.student_id)]
    return {"student_id": str(body.student_id), **conduct}
