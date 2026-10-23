"""School role policies and separation of duties (owner decisions 2026-10-23, migration 0085).

A school adjusts a STANDARD role without copying it: `standard role + school GRANT − school REVOKE`. The standard
role keeps its identity (dashboard, statistics, support) and keeps receiving the platform's baseline updates.

Separation of duties is a set of constraints, each with an effect ALLOW < WARN < REQUIRE_APPROVAL < BLOCK:
  * SELF_ELEVATION (BLOCK, not overridable): nobody adjusts a role they hold, assigns themselves, or approves a request
    they made or that elevates their own rights;
  * GOVERNANCE_GRANT (REQUIRE_APPROVAL by default): adding an access.* capability to a role needs a second manager;
  * PAIR rules (WARN by default): a change that makes one person hold both capabilities of a sensitive pair.
A school may change the effect of an overridable rule (audited). WARN needs an explicit acknowledgement;
REQUIRE_APPROVAL creates a change request decided by another access manager.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text

from edusync.adapters.rbac_effective import ALIAS_EXPANSION, ASSIGNMENT_CAPABILITIES

SEVERITY = ["ALLOW", "WARN", "REQUIRE_APPROVAL", "BLOCK"]
MANAGER_CAPABILITY = "access.roles.manage"


def worst(effects) -> str:
    return max(effects, key=SEVERITY.index, default="ALLOW")


def baseline(conn, role_id) -> set[str]:
    return {r[0] for r in conn.execute(text("SELECT capability_code FROM rbac_role_capabilities WHERE role_id=:r"), {"r": str(role_id)})}


def catalog(conn) -> dict[str, dict]:
    return {r["code"]: dict(r) for r in conn.execute(text(
        """SELECT code,domain_name,group_name,label,risk,lifecycle,alias_of,school_adjustable,scope_types
           FROM capability_catalog WHERE code NOT LIKE 'platform.%'""")).mappings()}


def locked(conn, role_id) -> set[str]:
    return {r[0] for r in conn.execute(text("SELECT capability_code FROM rbac_role_constraints WHERE role_id=:r AND kind='LOCKED'"), {"r": str(role_id)})}


def active_policies(conn, school_id, role_id) -> list[dict]:
    return [dict(r) for r in conn.execute(text("""SELECT id,capability_code,effect,reason,created_at,created_by_user_id,request_id
        FROM rbac_school_role_policies WHERE active AND school_id=:s AND role_id=:r ORDER BY capability_code"""),
        {"s": str(school_id), "r": str(role_id)}).mappings()]


def role_effective(conn, school_id, role_id) -> set[str]:
    """Capabilities a standard role carries in this school (baseline − REVOKE + GRANT; aliases not expanded)."""
    caps = baseline(conn, role_id)
    cat = catalog(conn)
    for p in active_policies(conn, school_id, role_id):
        if p["effect"] == "REVOKE":
            caps -= {p["capability_code"]} | {c for c, k in cat.items() if k["alias_of"] == p["capability_code"]}
        else:
            caps.add(p["capability_code"])
    return caps


def member_effective(conn, school_id, membership_id) -> set[str]:
    """Effective capabilities of one member (all active roles, policies, exceptions, aliases) — same SQL as login."""
    return {r[0] for r in conn.execute(text(f"""
        WITH held(code) AS (
            SELECT ac.capability_code FROM rbac_assignments a
              JOIN rbac_roles r ON r.id=a.role_id AND r.status='ACTIVE'
              CROSS JOIN LATERAL ({ASSIGNMENT_CAPABILITIES}) ac
             WHERE a.school_id=:s AND a.membership_id=:m AND a.active AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now())
            UNION SELECT eg.capability_code FROM rbac_exception_grants eg
             WHERE eg.school_id=:s AND eg.membership_id=:m AND eg.active AND eg.valid_from<=now() AND eg.valid_until>now()
        ){ALIAS_EXPANSION}"""), {"s": str(school_id), "m": str(membership_id)})}


def holders(conn, school_id, role_id) -> list[str]:
    return [str(r[0]) for r in conn.execute(text("""SELECT DISTINCT a.membership_id FROM rbac_assignments a
        JOIN school_memberships m ON m.id=a.membership_id AND m.active
        WHERE a.school_id=:s AND a.role_id=:r AND a.active AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now())"""),
        {"s": str(school_id), "r": str(role_id)})]


def rules(conn, school_id) -> list[dict]:
    out = []
    for r in conn.execute(text("""SELECT r.code,r.kind,r.effect default_effect,r.school_overridable,r.label,r.description,r.capabilities,r.match_prefix,
            o.effect override_effect,o.reason override_reason,o.updated_at,o.version
          FROM rbac_sod_rules r LEFT JOIN rbac_school_sod_overrides o ON o.rule_code=r.code AND o.school_id=:s ORDER BY r.code"""),
            {"s": str(school_id)}).mappings():
        item = dict(r)
        item["effect"] = item["override_effect"] if (item["school_overridable"] and item["override_effect"]) else item["default_effect"]
        out.append(item)
    return out


def _hit(rule, effect, detail) -> dict:
    return {"rule": rule["code"], "label": rule["label"], "effect": effect, "detail": detail}


def evaluate(conn, *, school_id, actor, added: set[str], affected_members: list[str], self_hit: str | None,
             kind: str, approving: bool = False) -> dict:
    """Constraints raised by a change that ADDS `added` capabilities to `affected_members`.
    kind: 'ROLE_POLICY' (role adjusted for the whole school) or 'ROLE_ASSIGNMENT' (one member)."""
    hits = []
    all_rules = rules(conn, school_id)
    by_code = {r["code"]: r for r in all_rules}
    if self_hit:
        hits.append(_hit(by_code["SELF_ELEVATION"], "BLOCK", self_hit))
    for rule in all_rules:
        if rule["kind"] == "CAPABILITY_GRANT" and kind == "ROLE_POLICY" and not approving:
            matched = sorted(c for c in added if rule["match_prefix"] and c.startswith(rule["match_prefix"]))
            if matched and rule["effect"] != "ALLOW":
                hits.append(_hit(rule, rule["effect"], "Capacités ajoutées : " + ", ".join(matched)))
        elif rule["kind"] == "PAIR" and rule["effect"] != "ALLOW":
            a, b = rule["capabilities"]
            for mid in affected_members:
                before = member_effective(conn, school_id, mid)
                after = before | added
                if a in after and b in after and not (a in before and b in before):
                    hits.append(_hit(rule, rule["effect"], f"{len(affected_members)} personne(s) concernée(s)" if kind == "ROLE_POLICY" else "Cette personne"))
                    break
    return {"effect": worst(h["effect"] for h in hits), "rules": hits}


def plan_role_policy(conn, *, school_id, role: dict, desired: set[str]) -> dict:
    """Policies needed so that `role` carries `desired` (ACTIVE capabilities). Hidden baseline capabilities (PLANNED,
    DEPRECATED, ALIAS) are untouched: they are not in the editor and protect nothing (or follow their canonical)."""
    if role["kind"] != "SCHOOL_STANDARD":
        raise HTTPException(409, "Seul un rôle standard s’ajuste par politique d’école ; un rôle propre à l’école se modifie directement")
    cat = catalog(conn)
    base = baseline(conn, role["id"])
    visible_base = {c for c in base if cat.get(c, {}).get("lifecycle") == "ACTIVE"}
    unknown = sorted(c for c in desired if c not in cat or cat[c]["lifecycle"] != "ACTIVE" or not (cat[c]["school_adjustable"] or c in base))
    if unknown:
        raise HTTPException(422, "Capacités non ajustables par une école : " + ", ".join(unknown[:5]))
    grants = desired - base
    revokes = visible_base - desired
    blocked = sorted(revokes & locked(conn, role["id"]))
    if blocked:
        raise HTTPException(409, "Refusé : ces capacités forment le socle protégé de ce rôle : " + ", ".join(blocked[:5]))
    current = {(p["capability_code"], p["effect"]): p for p in active_policies(conn, school_id, role["id"])}
    target = {(c, "GRANT") for c in grants} | {(c, "REVOKE") for c in revokes}
    effective_now = role_effective(conn, school_id, role["id"])
    effective_next = (base - revokes - {c for c, k in cat.items() if k["alias_of"] in revokes}) | grants
    return {"create": sorted(target - set(current)), "withdraw": [current[k] for k in sorted(set(current) - target)],
            "added": sorted({c for c in effective_next - effective_now if cat.get(c, {}).get("lifecycle") == "ACTIVE"}),
            "removed": sorted({c for c in effective_now - effective_next if cat.get(c, {}).get("lifecycle") == "ACTIVE"}),
            "grants": sorted(grants), "revokes": sorted(revokes)}


def apply_role_policy(conn, *, school_id, role_id, plan: dict, reason: str, user_id, request_id=None) -> None:
    for p in plan["withdraw"]:
        conn.execute(text("""UPDATE rbac_school_role_policies SET active=false, revoked_at=now(), revoked_by_user_id=:u, revoke_reason=:r
            WHERE id=:id AND active"""), {"id": str(p["id"]), "u": str(user_id), "r": reason})
    for code, effect in plan["create"]:
        conn.execute(text("""INSERT INTO rbac_school_role_policies(school_id,role_id,capability_code,effect,reason,created_by_user_id,request_id)
            VALUES(:s,:r,:c,:e,:reason,:u,:req)"""), {"s": str(school_id), "r": str(role_id), "c": code, "e": effect, "reason": reason,
                                                      "u": str(user_id), "req": str(request_id) if request_id else None})


def assert_managers_remain(conn, school_id: UUID) -> None:
    """The school always keeps at least one active member holding the access manager capability (policies included)."""
    left = conn.execute(text(f"""SELECT count(DISTINCT a.membership_id) FROM rbac_assignments a
          JOIN rbac_roles r ON r.id=a.role_id AND r.status='ACTIVE'
          JOIN school_memberships m ON m.id=a.membership_id AND m.active=true
          CROSS JOIN LATERAL ({ASSIGNMENT_CAPABILITIES}) ac
          WHERE a.school_id=:sid AND a.active=true AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now())
            AND ac.capability_code=:cap"""), {"cap": MANAGER_CAPABILITY, "sid": str(school_id)}).scalar_one()
    if left == 0:
        raise HTTPException(409, "Refusé : l'école doit garder au moins un gestionnaire des accès")


def sod_error(result: dict, *, status: int = 409) -> HTTPException:
    code = {"BLOCK": "SOD_BLOCKED", "WARN": "SOD_WARNING", "REQUIRE_APPROVAL": "SOD_APPROVAL_REQUIRED"}[result["effect"]]
    message = {"SOD_BLOCKED": "Refusé : séparation des tâches", "SOD_WARNING": "À confirmer : séparation des tâches",
               "SOD_APPROVAL_REQUIRED": "Approbation requise"}[code]
    return HTTPException(status, {"code": code, "message": message + " — " + "; ".join(h["label"] for h in result["rules"]), "rules": result["rules"]})
