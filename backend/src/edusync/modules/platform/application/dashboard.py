"""Platform dashboard (lot UX 2026-10-18): one read, capability-aware, single source of truth for every indicator.

Each figure is computed with the SAME definition as the detailed view it opens:
  * Écoles            = every school                       → /platform/schools-page (no filter), field `total`
  * Écoles actives    = schools with status ACTIVE         → /platform/schools-page?status=ACTIVE
  * Accès actifs      = active accounts holding at least one active school membership → /platform/access?active_only=true
  * Actions requises  = sum of the counts of the "À surveiller" items whose tone is "action" (same payload)
Nothing is shown that the actor's capabilities do not open: the recent activity needs platform.audit.read, technical
items need platform.health.read, team items need platform.collaborators.manage. Read-only; no business rule changes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

SCHOOL_ADMIN_ROLE = "ADMIN_SYSTEME_ECOLE"
TEAM_CAP = "platform.collaborators.manage"
OUTBOX_STUCK_SECONDS = 300
TREND_MONTHS = 12


def month_starts(now: datetime, months: int) -> list[datetime]:
    """First instant (UTC) of each of the last `months` months, oldest first, current month last."""
    y, m = now.year, now.month
    out = []
    for _ in range(months):
        out.append(datetime(y, m, 1, tzinfo=timezone.utc))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out[::-1]


def active_schools_trend(schools: list[dict], events: list[dict], now: datetime, months: int = TREND_MONTHS) -> list[dict]:
    """Active schools at the end of each month, rebuilt from the audited status changes.

    schools: {id, created_at, status}; events: {school_id, occurred_at, action in SCHOOL_SUSPENDED|SCHOOL_REACTIVATED}.
    A school is ACTIVE when created, then follows its audited suspensions / reactivations. A school without any audited
    change keeps its current status (data older than the audit trail). The current month is the live figure, so the
    last point always equals the "Écoles actives" indicator."""
    by_school: dict[str, list[tuple[datetime, str]]] = {}
    for e in events:
        by_school.setdefault(str(e["school_id"]), []).append((e["occurred_at"], "SUSPENDED" if e["action"] == "SCHOOL_SUSPENDED" else "ACTIVE"))
    for changes in by_school.values():
        changes.sort()
    starts = month_starts(now, months)
    points = []
    for i, start in enumerate(starts):
        current = i == len(starts) - 1
        end = now if current else starts[i + 1]
        active = 0
        for s in schools:
            if current:
                active += s["status"] == "ACTIVE"
                continue
            if s["created_at"] >= end:
                continue
            changes = by_school.get(str(s["id"]))
            if changes is None:
                state = s["status"]
            else:
                state = "ACTIVE"
                for at, st in changes:
                    if at < end:
                        state = st
            active += state == "ACTIVE"
        points.append({"month": start.strftime("%Y-%m"), "active": active})
    return points


def build_dashboard(c, permissions: set[str], *, backup: dict | None, active_managers: int | None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    schools = c.execute(text("""SELECT count(*) total, count(*) FILTER(WHERE status='ACTIVE') active,
        count(*) FILTER(WHERE status='SUSPENDED') suspended FROM schools""")).mappings().one()
    accesses = int(c.execute(text("""SELECT count(*) FROM users u WHERE u.active
        AND EXISTS (SELECT 1 FROM school_memberships m WHERE m.user_id=u.id AND m.active)""")).scalar_one())
    without_admin = int(c.execute(text("""SELECT count(*) FROM schools s WHERE s.status='ACTIVE' AND NOT EXISTS (
        SELECT 1 FROM school_memberships m JOIN rbac_assignments a ON a.membership_id=m.id AND a.active
        JOIN rbac_roles r ON r.id=a.role_id AND r.code=:admin WHERE m.school_id=s.id)"""), {"admin": SCHOOL_ADMIN_ROLE}).scalar_one())
    invitations = int(c.execute(text("""SELECT count(*) FROM account_tokens WHERE purpose='INVITATION' AND used_at IS NULL
        AND revoked_at IS NULL AND expires_at>now()""")).scalar_one())

    watch: list[dict] = []
    if without_admin:
        can_fix = "platform.school_admin.bootstrap" in permissions
        watch.append({"key": "schools_without_admin", "tone": "action" if can_fix else "info", "count": without_admin,
                      "title": f"{without_admin} école(s) active(s) sans administrateur",
                      "detail": "Créez l’administrateur initial pour que l’école puisse se configurer." if can_fix
                      else "Un Manager Système doit créer l’administrateur initial.",
                      "target": {"tab": "schools", "filter": "needs_admin"}})
    if active_managers is not None and active_managers < 2:
        watch.append({"key": "single_manager", "tone": "action", "count": 1, "title": "Un seul Manager Système actif",
                      "detail": "Ajoutez un second Manager pour pouvoir rétablir un accès perdu.", "target": {"tab": "team"}})
    if "platform.health.read" in permissions:
        q = c.execute(text("""SELECT count(*) FILTER(WHERE dead_lettered_at IS NULL AND created_at<now()-make_interval(secs=>:s)) stuck,
            count(*) FILTER(WHERE dead_lettered_at IS NOT NULL) dead FROM outbox_events WHERE published_at IS NULL"""),
            {"s": OUTBOX_STUCK_SECONDS}).mappings().one()
        if int(q["stuck"] or 0) or int(q["dead"] or 0):
            n = int(q["stuck"] or 0) + int(q["dead"] or 0)
            watch.append({"key": "outbox_stuck", "tone": "action", "count": n, "title": f"{n} événement(s) bloqué(s) dans la file de diffusion",
                          "detail": "La diffusion des événements prend du retard ou a mis des messages en quarantaine.", "target": {"tab": "diagnostics"}})
        if backup and backup.get("state") in ("DOWN", "DEGRADED"):
            watch.append({"key": "backup", "tone": "action", "count": 1, "title": "Sauvegarde automatique à vérifier",
                          "detail": backup.get("detail") or "", "target": {"tab": "diagnostics"}})
        elif backup and backup.get("state") == "NOT_CONFIGURED":
            watch.append({"key": "backup_not_configured", "tone": "info", "count": 0, "title": "Sauvegarde automatique non configurée",
                          "detail": backup.get("detail") or "", "target": {"tab": "diagnostics"}})
    if int(schools["suspended"] or 0):
        watch.append({"key": "schools_suspended", "tone": "info", "count": int(schools["suspended"]),
                      "title": f"{int(schools['suspended'])} école(s) suspendue(s)", "detail": "Accès fermé jusqu’à réactivation.",
                      "target": {"tab": "schools", "status": "SUSPENDED"}})
    if invitations:
        watch.append({"key": "pending_invitations", "tone": "info", "count": invitations, "title": f"{invitations} invitation(s) en attente",
                      "detail": "Comptes invités qui n’ont pas encore choisi leur mot de passe.", "target": {"tab": "access"}})

    school_rows = [dict(r) for r in c.execute(text("SELECT id, created_at, status FROM schools")).mappings()]
    events = [dict(r) for r in c.execute(text("""SELECT entity_id AS school_id, occurred_at, action FROM audit_events
        WHERE entity_type='School' AND action IN ('SCHOOL_SUSPENDED','SCHOOL_REACTIVATED')""")).mappings()]
    trend = active_schools_trend(school_rows, events, now)

    recent = None
    if "platform.audit.read" in permissions:
        recent = [dict(r) for r in c.execute(text("""SELECT a.id, a.occurred_at, a.action, a.entity_type, a.result, s.code school_code,
            s.name school_name, u.full_name actor FROM audit_events a LEFT JOIN schools s ON s.id=a.school_id
            LEFT JOIN users u ON u.id=a.actor_user_id ORDER BY a.occurred_at DESC, a.id DESC LIMIT 5""")).mappings()]

    return {
        "kpis": {"schools": int(schools["total"]), "active_schools": int(schools["active"]), "active_accesses": accesses,
                 "actions_required": sum(w["count"] for w in watch if w["tone"] == "action")},
        "watchlist": watch,
        "trend": {"months": trend, "has_data": any(p["active"] for p in trend)},
        "recent_activity": recent,
        "generated_at": now.isoformat(),
    }
