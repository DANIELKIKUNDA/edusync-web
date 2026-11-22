"""Pedagogical calendar (V2 lot 2, owner 2026-11-22). Pedagogy module + rights; the school year is the active one.

GET  /pedagogy/calendars                                   both calendars (saved, or proposed by EduSync when not yet saved)
PUT  /pedagogy/calendars/{structure}                       save the dates (a validated calendar needs a motif)
POST /pedagogy/calendars/{structure}/validate              préfet / directeur des études (pedagogy.calendar.manage)
POST /pedagogy/calendars/{structure}/periods/{code}/close  close grade entry for a period
POST /pedagogy/calendars/{structure}/periods/{code}/reopen reopen it (motif)
"""
from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from edusync.adapters.postgres_repositories import PostgresAuditRepository
from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.modules.audit.domain.audit import AuditRecord
from edusync.modules.pedagogy.domain import calendar as cal
from edusync.modules.school_modules.api.guard import require_pedagogy
from edusync.shared.application.context import ActorContext

router = APIRouter(tags=["Pédagogie (V2) — calendrier"])
READ, MANAGE = "pedagogy.referential.read", "pedagogy.calendar.manage"


class PeriodIn(BaseModel):
    code: str = Field(min_length=2, max_length=4)
    starts_on: date
    ends_on: date


class CalendarIn(BaseModel):
    periods: list[PeriodIn] = Field(min_length=6, max_length=9)
    reason: str | None = Field(default=None, max_length=500)


class ReasonIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


def _need(actor: ActorContext, capability: str) -> None:
    try:
        actor.require(capability)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


def _structure(value: str) -> str:
    s = value.strip().upper()
    if s not in cal.CODES:
        raise HTTPException(404, "Structure inconnue : TRIMESTRIEL ou SEMESTRIEL")
    return s


def _tx(services: AppServices, actor: ActorContext):
    return services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id)


def _audit(conn, actor: ActorContext, action: str, entity_id: UUID, reason: str | None = None, old=None, new=None) -> None:
    PostgresAuditRepository(conn).append(AuditRecord(action=action, entity_type="PedagogyCalendar", entity_id=entity_id,
                                                     actor_user_id=actor.user_id, school_id=actor.school_id, source=actor.source,
                                                     reason=reason, old_data=old, new_data=new, correlation_id=uuid4()))


def active_year(conn, actor: ActorContext) -> dict:
    row = conn.execute(text("""SELECT id,label,start_date,end_date FROM academic_years WHERE school_id=:s AND status='ACTIVE'"""),
                       {"s": str(actor.school_id)}).mappings().first()
    if row is None:
        raise HTTPException(409, "Aucune année scolaire active : activez d’abord l’année dans Paramètres › Années scolaires.")
    return dict(row)


def _needed_structures(conn, actor: ActorContext) -> list[str]:
    """The calendars the school needs, from its linked classes (both when nothing is linked yet)."""
    rows = {r[0] for r in conn.execute(text("""SELECT DISTINCT rc.structure FROM pedagogy_class_links l JOIN ref_classes rc ON rc.code=l.ref_class_code
        WHERE l.school_id=:s"""), {"s": str(actor.school_id)})}
    return [s for s in ("TRIMESTRIEL", "SEMESTRIEL") if s in rows] or ["TRIMESTRIEL", "SEMESTRIEL"]


def _calendar(conn, actor: ActorContext, year: dict, structure: str) -> dict:
    row = conn.execute(text("""SELECT id,status,validated_at,version,updated_at FROM pedagogy_calendars
        WHERE school_id=:s AND academic_year_id=:y AND structure=:t"""), {"s": str(actor.school_id), "y": str(year["id"]), "t": structure}).mappings().first()
    today = date.today()
    if row is None:
        periods = cal.propose(structure, year["start_date"], year["end_date"])
        closed: dict = {}
        status, saved = "DRAFT", False
    else:
        stored = conn.execute(text("""SELECT code,starts_on,ends_on,entry_closed_at FROM pedagogy_calendar_periods WHERE calendar_id=:c ORDER BY sort_order"""),
                              {"c": str(row["id"])}).mappings().all()
        periods = [cal.Period(p["code"], p["starts_on"], p["ends_on"]) for p in stored]
        closed = {p["code"]: p["entry_closed_at"] for p in stored}
        status, saved = row["status"], True
    gaps = cal.validate(structure, periods, year["start_date"], year["end_date"]) if periods else []
    validated = status == "VALIDATED"
    out_periods = []
    for p in periods:
        state = cal.entry_state(p, validated=validated, closed=bool(closed.get(p.code)), today=today)
        out_periods.append({"code": p.code, "label": cal.label(structure, p.code), "term": cal.term_of(p.code), "is_exam": p.is_exam,
                            "starts_on": p.starts_on.isoformat(), "ends_on": p.ends_on.isoformat(), "days": (p.ends_on - p.starts_on).days + 1,
                            "entry_state": state, "entry_allowed": cal.entry_allowed(state),
                            "entry_closed_at": closed[p.code].isoformat() if closed.get(p.code) else None})
    return {"structure": structure, "label": "Maternelle et primaire" if structure == "TRIMESTRIEL" else "Éducation de base et humanités",
            "saved": saved, "status": status, "version": row["version"] if row else 0,
            "validated_at": row["validated_at"].isoformat() if row and row["validated_at"] else None,
            "periods": out_periods, "gaps": gaps}


@router.get("/calendars")
def calendars(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
              _module: ActorContext = Depends(require_pedagogy)):
    _need(actor, READ)
    with _tx(services, actor) as conn:
        year = active_year(conn, actor)
        needed = _needed_structures(conn, actor)
        items = [_calendar(conn, actor, year, s) for s in needed]
    return {"year": {"id": str(year["id"]), "label": year["label"], "start_date": year["start_date"].isoformat(), "end_date": year["end_date"].isoformat()},
            "can_manage": MANAGE in actor.permissions, "calendars": items}


@router.put("/calendars/{structure}")
def save_calendar(structure: str, body: CalendarIn, actor: ActorContext = Depends(require_school_actor),
                  services: AppServices = Depends(get_services), _module: ActorContext = Depends(require_pedagogy)):
    _need(actor, MANAGE)
    structure = _structure(structure)
    periods = [cal.Period(p.code.strip().upper(), p.starts_on, p.ends_on) for p in body.periods]
    with _tx(services, actor) as conn:
        year = active_year(conn, actor)
        try:
            cal.validate(structure, periods, year["start_date"], year["end_date"])
        except cal.CalendarError as exc:
            raise HTTPException(422, str(exc)) from exc
        row = conn.execute(text("""SELECT id,status FROM pedagogy_calendars WHERE school_id=:s AND academic_year_id=:y AND structure=:t FOR UPDATE"""),
                           {"s": str(actor.school_id), "y": str(year["id"]), "t": structure}).mappings().first()
        reason = " ".join((body.reason or "").split())
        if row and row["status"] == "VALIDATED" and len(reason) < 5:
            raise HTTPException(409, "Calendrier déjà validé : indiquez le motif de la modification.")
        if row is None:
            cid = conn.execute(text("""INSERT INTO pedagogy_calendars(school_id,academic_year_id,structure,updated_by)
                VALUES(:s,:y,:t,:u) RETURNING id"""), {"s": str(actor.school_id), "y": str(year["id"]), "t": structure, "u": str(actor.user_id)}).scalar()
            old = None
        else:
            cid = row["id"]
            old = [dict(r) for r in conn.execute(text("SELECT code,starts_on::text,ends_on::text FROM pedagogy_calendar_periods WHERE calendar_id=:c ORDER BY sort_order"),
                                                  {"c": str(cid)}).mappings()]
            conn.execute(text("UPDATE pedagogy_calendars SET updated_by=:u, updated_at=now(), version=version+1 WHERE id=:c"),
                         {"u": str(actor.user_id), "c": str(cid)})
        order = cal.CODES[structure]
        for p in periods:
            conn.execute(text("""INSERT INTO pedagogy_calendar_periods(calendar_id,school_id,code,sort_order,starts_on,ends_on)
                VALUES(:c,:s,:code,:o,:a,:b) ON CONFLICT (calendar_id,code) DO UPDATE SET starts_on=EXCLUDED.starts_on, ends_on=EXCLUDED.ends_on"""),
                {"c": str(cid), "s": str(actor.school_id), "code": p.code, "o": order.index(p.code) + 1, "a": p.starts_on, "b": p.ends_on})
        _audit(conn, actor, "PEDAGOGY_CALENDAR_SAVED", cid, reason or None, old=old,
               new=[{"code": p.code, "starts_on": p.starts_on.isoformat(), "ends_on": p.ends_on.isoformat()} for p in periods])
        return _calendar(conn, actor, year, structure)


def _existing(conn, actor: ActorContext, year: dict, structure: str) -> dict:
    row = conn.execute(text("""SELECT id,status FROM pedagogy_calendars WHERE school_id=:s AND academic_year_id=:y AND structure=:t FOR UPDATE"""),
                       {"s": str(actor.school_id), "y": str(year["id"]), "t": structure}).mappings().first()
    if row is None:
        raise HTTPException(409, "Enregistrez d’abord les dates du calendrier.")
    return dict(row)


@router.post("/calendars/{structure}/validate")
def validate_calendar(structure: str, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services),
                      _module: ActorContext = Depends(require_pedagogy)):
    _need(actor, MANAGE)
    structure = _structure(structure)
    with _tx(services, actor) as conn:
        year = active_year(conn, actor)
        row = _existing(conn, actor, year, structure)
        if row["status"] != "VALIDATED":
            conn.execute(text("""UPDATE pedagogy_calendars SET status='VALIDATED', validated_by=:u, validated_at=now(), version=version+1 WHERE id=:c"""),
                         {"u": str(actor.user_id), "c": str(row["id"])})
            _audit(conn, actor, "PEDAGOGY_CALENDAR_VALIDATED", row["id"], new={"structure": structure})
        return _calendar(conn, actor, year, structure)


def _entry(structure: str, code: str, reason: str | None, close: bool, actor: ActorContext, services: AppServices):
    _need(actor, MANAGE)
    structure = _structure(structure)
    code = code.strip().upper()
    clean = " ".join((reason or "").split())
    if not close and len(clean) < 5:
        raise HTTPException(422, "Indiquez le motif de la réouverture (au moins 5 caractères).")
    with _tx(services, actor) as conn:
        year = active_year(conn, actor)
        row = _existing(conn, actor, year, structure)
        if row["status"] != "VALIDATED":
            raise HTTPException(409, "Validez d’abord le calendrier.")
        n = conn.execute(text("""UPDATE pedagogy_calendar_periods
                SET entry_closed_at=CASE WHEN :close THEN now() END, entry_closed_by=CASE WHEN :close THEN CAST(:u AS uuid) END
                WHERE calendar_id=:c AND code=:code"""),
            {"c": str(row["id"]), "code": code, "close": close, "u": str(actor.user_id)}).rowcount
        if not n:
            raise HTTPException(404, "Période inconnue")
        _audit(conn, actor, "PEDAGOGY_ENTRY_CLOSED" if close else "PEDAGOGY_ENTRY_REOPENED", row["id"], clean or None,
               new={"structure": structure, "period": code})
        return _calendar(conn, actor, year, structure)


@router.post("/calendars/{structure}/periods/{code}/close")
def close_entry(structure: str, code: str, body: ReasonIn | None = None, actor: ActorContext = Depends(require_school_actor),
                services: AppServices = Depends(get_services), _module: ActorContext = Depends(require_pedagogy)):
    return _entry(structure, code, body.reason if body else None, True, actor, services)


@router.post("/calendars/{structure}/periods/{code}/reopen")
def reopen_entry(structure: str, code: str, body: ReasonIn, actor: ActorContext = Depends(require_school_actor),
                 services: AppServices = Depends(get_services), _module: ActorContext = Depends(require_pedagogy)):
    return _entry(structure, code, body.reason, False, actor, services)
