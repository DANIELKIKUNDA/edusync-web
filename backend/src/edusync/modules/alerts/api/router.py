from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.shared.application.context import ActorContext

router = APIRouter(tags=["Supervision"])

VISIBLE = """i.school_id=:s AND i.required_capability=ANY(CAST(:caps AS text[])) AND
 (i.scope_type IS NULL OR i.scope_value IS NULL OR
  NOT EXISTS (SELECT 1 FROM rbac_assignments a JOIN rbac_role_capabilities rc ON rc.role_id=a.role_id
    WHERE a.school_id=:s AND a.user_id=:u AND a.active AND rc.capability_code=i.required_capability
      AND EXISTS (SELECT 1 FROM rbac_assignment_scopes x WHERE x.assignment_id=a.id AND x.scope_type=i.scope_type)
      AND NOT EXISTS (SELECT 1 FROM rbac_assignment_scopes x WHERE x.assignment_id=a.id AND x.scope_type=i.scope_type
                      AND upper(x.scope_value)=upper(i.scope_value))))"""


def _params(actor: ActorContext):
    return {"s": str(actor.school_id), "u": str(actor.user_id), "caps": list(actor.permissions)}


@router.get("/supervision/incidents")
def incidents(state: str = "active", domain: str | None = None, severity: str | None = None,
              actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    if "notifications.internal.read" not in actor.permissions:
        raise HTTPException(403, "Votre compte ne peut pas consulter les alertes.")
    if state not in ("active", "resolved", "all"): raise HTTPException(422, "État invalide")
    p = {**_params(actor), "domain": domain, "severity": severity, "state": state}
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        rows = c.execute(text("SELECT i.* FROM supervision_incidents i WHERE " + VISIBLE + """
          AND (:state='all' OR (:state='active' AND i.condition_status='OPEN') OR (:state='resolved' AND i.condition_status='RESOLVED'))
          AND (CAST(:domain AS text) IS NULL OR i.domain=:domain) AND (CAST(:severity AS text) IS NULL OR i.severity=:severity)
          ORDER BY CASE i.severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END,i.last_seen_at DESC LIMIT 200"""), p).mappings().all()
        counts = c.execute(text("""SELECT count(*) FILTER(WHERE i.condition_status='OPEN') active,
          count(*) FILTER(WHERE i.condition_status='OPEN' AND i.severity='CRITICAL') critical,
          count(*) FILTER(WHERE i.condition_status='OPEN' AND i.response_status='NEW') new
          FROM supervision_incidents i WHERE """ + VISIBLE), _params(actor)).mappings().one()
    return {"items": [dict(r) for r in rows], "counts": dict(counts)}


def _transition(incident_id: UUID, actor: ActorContext, services: AppServices, action: str):
    p = {**_params(actor), "id": str(incident_id)}
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        row = c.execute(text("SELECT i.id,i.condition_status,i.response_status FROM supervision_incidents i WHERE i.id=:id AND " + VISIBLE + " FOR UPDATE"), p).mappings().first()
        if not row: raise HTTPException(404, "Alerte introuvable dans votre périmètre")
        if action == "ack":
            c.execute(text("""UPDATE supervision_incidents SET response_status='ACKNOWLEDGED',acknowledged_at=now(),acknowledged_by=:u
              WHERE id=:id AND response_status='NEW'"""), p)
        elif action == "progress":
            c.execute(text("""UPDATE supervision_incidents SET response_status='IN_PROGRESS',acknowledged_at=coalesce(acknowledged_at,now()),
              acknowledged_by=coalesce(acknowledged_by,CAST(:u AS uuid)) WHERE id=:id AND condition_status='OPEN'"""), p)
        else:
            if row["condition_status"] == "OPEN": raise HTTPException(409, "L'anomalie existe encore : traitez-la avant de la fermer.")
            c.execute(text("UPDATE supervision_incidents SET response_status='CLOSED',closed_at=now(),closed_by=:u WHERE id=:id"), p)
    return {"id": str(incident_id), "action": action}


@router.post("/supervision/incidents/{incident_id}/acknowledge")
def acknowledge(incident_id: UUID, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    return _transition(incident_id, actor, services, "ack")

@router.post("/supervision/incidents/{incident_id}/start")
def start(incident_id: UUID, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    return _transition(incident_id, actor, services, "progress")

@router.post("/supervision/incidents/{incident_id}/close")
def close(incident_id: UUID, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    return _transition(incident_id, actor, services, "close")

@router.post("/supervision/evaluate")
def evaluate_now(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    if "notifications.internal.configure" not in actor.permissions:
        raise HTTPException(403, "Évaluation réservée à la supervision de l'école")
    from edusync.modules.alerts.application.supervision import evaluate_school
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        return evaluate_school(c, actor.school_id, services=services)
