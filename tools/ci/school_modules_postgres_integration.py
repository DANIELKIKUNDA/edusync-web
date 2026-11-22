"""V2 lot 0 — modules of a school — real HTTP + real PostgreSQL (owner, 2026-11-22).

« Chaque école n'aura pas la V2 : on va la vendre séparément » ; « il faut permettre aux écoles existantes qui n'ont pas
de module de leur donner des modules ». Checks:
1. an existing school receives the eight V1 modules by migration 0123 — and running it again adds nothing;
2. a school created by the platform starts with the eight V1 modules, never with the pedagogy;
3. a school WITHOUT the pedagogy: /pedagogy/overview refused (403 MODULE_NOT_ACTIVE) for every role, /access/me lists
   its modules without ACADEMIC, and the V1 work goes on (no gating);
4. the platform: reading needs the right; activating needs the right AND a recent code (step-up); motif required;
5. activation → the school reaches the V2 route; withdrawal → refused again; history kept (REVOKED), audit written;
6. V1 modules can neither be withdrawn nor re-activated; a suspended school cannot receive a module; replay = same answer;
7. assigning a subscription to a school whose modules are already in service no longer fails (the module is kept).

    python tools/local/isolated_db.py env <db> -- ../.venv/Scripts/python.exe ../tools/ci/school_modules_postgres_integration.py

CI=true, localhost only (three_roles_postgres_integration). Exits 1 on any FAIL.
"""
from __future__ import annotations

import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_roles_postgres_integration as H  # noqa: E402
from three_roles_postgres_integration import APP, CLIENT, RESULTS, ROOT, actor_for, as_, check, one, school, sql  # noqa: E402
from edusync.bootstrap.dependencies import require_platform_actor  # noqa: E402
from edusync.shared.application.context import ActorContext  # noqa: E402

V1 = {"CORE_SCHOOL", "ENROLLMENT", "FINANCE", "RECOVERY", "REPORTS", "PERSONNEL", "DOCUMENTS", "COMMUNICATIONS"}
PLATFORM: dict[str, ActorContext] = {}
APP.dependency_overrides[require_platform_actor] = lambda: PLATFORM["actor"]
MIGRATION = (ROOT / "backend/migrations/0123_school_modules.sql").read_text(encoding="utf-8")


def platform(caps: set[str], *, stepped_up: bool) -> ActorContext:
    uid, sid = uuid.uuid4(), uuid.uuid4()
    sql("INSERT INTO users(id,email,full_name,password_hash,active,version) VALUES(:i,:e,'Plateforme','x',true,1)", i=uid, e=f"pf-{uid.hex[:8]}@example.test")
    sql("""INSERT INTO user_device_sessions(id,user_id,token_hash,user_version,mfa_stepup_at)
           VALUES(:i,:u,:h,1,CASE WHEN :up THEN now() END)""", i=sid, u=uid, h=uuid.uuid4().hex + uuid.uuid4().hex, up=stepped_up)
    return ActorContext(user_id=uid, school_id=None, membership_id=None, permissions=frozenset(caps), session_id=sid)


def as_platform(actor: ActorContext):
    PLATFORM["actor"] = actor
    return CLIENT


def active(school_id) -> set[str]:
    return {r[0] for r in sql("SELECT module_code FROM saas_entitlements WHERE school_id=:s AND status='ACTIVE'", s=school_id)}


def change(actor, school_id, code, kind, reason="Contrat pédagogie signé (test CI)", key=None):
    return as_platform(actor).post(f"/api/v1/platform/schools/{school_id}/modules/{code}/{kind}", json={"reason": reason},
                                   headers={"Idempotency-Key": key or f"mod-{uuid.uuid4().hex}"})


def run() -> None:
    print("\n== V2 lot 0 — modules des écoles (22/11/2026)")
    A, B = school("A"), school("B")
    check("avant la migration, l'école de test n'a aucun module", active(A["id"]) == set(), active(A["id"]))
    with H.ENGINE.begin() as c:                                   # replay the migration: A and B are « existing » schools
        c.exec_driver_sql(MIGRATION)
    check("migration 0123 : école existante → les 8 modules V1", active(A["id"]) == V1 and active(B["id"]) == V1, active(A["id"]))
    with H.ENGINE.begin() as c:
        c.exec_driver_sql(MIGRATION)
    n = one("SELECT count(*) FROM saas_entitlements WHERE school_id=:s", s=A["id"])[0]
    check("migration rejouée : aucun doublon", n == 8, n)
    check("aucune école ne reçoit la Pédagogie par la migration", "ACADEMIC" not in active(A["id"]))
    src = one("SELECT count(*) FROM saas_entitlements WHERE school_id=:s AND source='MIGRATION' AND subscription_id IS NULL", s=A["id"])[0]
    check("modules V1 marqués « déjà en service » (source MIGRATION, sans abonnement)", src == 8, src)

    manager = platform({"platform.schools.create", "platform.schools.read", "platform.school_modules.read", "platform.school_modules.manage"}, stepped_up=True)
    r = as_platform(manager).post("/api/v1/platform/schools", json={"name": f"École Nouvelle {H.RUN}", "province": "Kinshasa"},
                                  headers={"Idempotency-Key": f"new-{uuid.uuid4().hex}"})
    new_id = r.json().get("id") if r.status_code == 201 else None
    check("nouvelle école créée par la plateforme", r.status_code == 201, r.text[:200])
    check("nouvelle école → les 8 modules V1 dès la création, sans la Pédagogie", new_id and active(new_id) == V1, new_id and active(new_id))

    roles = {code: actor_for(code, A["id"]) for code in ("ADMIN_SYSTEME_ECOLE", "PROMOTEUR", "PREFET_ETUDES", "GESTIONNAIRE")}
    refused = {code: as_(a).get("/api/v1/pedagogy/overview") for code, a in roles.items()}
    check("école SANS Pédagogie : route V2 refusée pour tous les rôles (403 MODULE_NOT_ACTIVE)",
          all(x.status_code == 403 and "MODULE_NOT_ACTIVE" in x.text for x in refused.values()),
          {k: x.status_code for k, x in refused.items()})
    me = as_(roles["ADMIN_SYSTEME_ECOLE"]).get("/api/v1/access/me").json()
    check("/access/me : modules de l'école listés, sans la Pédagogie", set(me.get("modules", [])) == V1, me.get("modules"))
    check("école sans Pédagogie : le travail V1 continue (aucun blocage)",
          as_(roles["GESTIONNAIRE"]).get("/api/v1/schooling/families").status_code == 200)

    reader = platform({"platform.schools.read"}, stepped_up=True)
    check("lire les modules d'une école exige le droit", as_platform(reader).get(f"/api/v1/platform/schools/{A['id']}/modules").status_code == 403)
    collab = platform({"platform.schools.read", "platform.school_modules.read"}, stepped_up=True)
    view = as_platform(collab).get(f"/api/v1/platform/schools/{A['id']}/modules")
    body = view.json() if view.status_code == 200 else {}
    acad = next((m for m in body.get("modules", []) if m["code"] == "ACADEMIC"), {})
    check("fiche modules : V1 actifs, Pédagogie inactive, consultation seule pour le collaborateur",
          view.status_code == 200 and {m["code"] for m in body["modules"] if m["active"]} == V1 and acad.get("active") is False
          and body.get("can_manage") is False, view.text[:200])
    check("le collaborateur ne peut pas activer", change(collab, A["id"], "ACADEMIC", "activate").status_code == 403)
    no_code = platform({"platform.school_modules.manage"}, stepped_up=False)
    r = change(no_code, A["id"], "ACADEMIC", "activate")
    check("activer exige un code de confirmation récent (step-up)", r.status_code == 403 and "MFA_STEP_UP_REQUIRED" in r.text, r.text[:160])
    r = as_platform(manager).post(f"/api/v1/platform/schools/{A['id']}/modules/ACADEMIC/activate", json={"reason": "ok"},
                                  headers={"Idempotency-Key": f"mod-{uuid.uuid4().hex}"})
    check("motif obligatoire", r.status_code == 422, r.status_code)
    check("sans Idempotency-Key : refus", as_platform(manager).post(f"/api/v1/platform/schools/{A['id']}/modules/ACADEMIC/activate",
          json={"reason": "Contrat signé (test)"}).status_code == 400)

    k = f"mod-{uuid.uuid4().hex}"
    r = change(manager, A["id"], "ACADEMIC", "activate", key=k)
    check("activation de la Pédagogie pour l'école A", r.status_code == 200 and r.json().get("active") is True, r.text[:200])
    again = change(manager, A["id"], "ACADEMIC", "activate", key=k)
    check("même demande rejouée : même réponse, rien de plus",
          again.status_code == 200 and again.headers.get("Idempotent-Replayed") == "true"
          and one("SELECT count(*) FROM saas_entitlements WHERE school_id=:s AND module_code='ACADEMIC'", s=A["id"])[0] == 1, again.text[:120])
    check("activer deux fois : refus clair", change(manager, A["id"], "ACADEMIC", "activate").status_code == 409)
    ok = as_(roles["PREFET_ETUDES"]).get("/api/v1/pedagogy/overview")
    check("école A AVEC Pédagogie : la route V2 répond", ok.status_code == 200 and ok.json().get("active") is True, ok.text[:160])
    check("école B (sans Pédagogie) reste refusée", as_(actor_for("ADMIN_SYSTEME_ECOLE", B["id"])).get("/api/v1/pedagogy/overview").status_code == 403)
    check("/access/me de l'école A : ACADEMIC apparaît", "ACADEMIC" in as_(roles["ADMIN_SYSTEME_ECOLE"]).get("/api/v1/access/me").json().get("modules", []))
    audit = one("SELECT count(*) FROM audit_events WHERE school_id=:s AND action='SCHOOL_MODULE_ACTIVATED' AND reason LIKE 'Contrat%'", s=A["id"])[0]
    check("activation inscrite au journal d'audit, avec son motif", audit == 1, audit)

    r = change(manager, A["id"], "ACADEMIC", "withdraw", reason="Fin du contrat pédagogie (test CI)")
    check("retrait de la Pédagogie", r.status_code == 200 and r.json().get("active") is False, r.text[:200])
    check("après retrait : la route V2 est de nouveau refusée", as_(roles["PREFET_ETUDES"]).get("/api/v1/pedagogy/overview").status_code == 403)
    hist = one("SELECT status, ends_at IS NOT NULL FROM saas_entitlements WHERE school_id=:s AND module_code='ACADEMIC'", s=A["id"])
    check("historique conservé (ligne REVOKED datée, jamais supprimée)", hist and hist[0] == "REVOKED" and hist[1], hist)
    check("réactivation possible après un retrait", change(manager, A["id"], "ACADEMIC", "activate").status_code == 200)
    check("retrait journalisé", one("SELECT count(*) FROM audit_events WHERE school_id=:s AND action='SCHOOL_MODULE_WITHDRAWN'", s=A["id"])[0] == 1)

    r = change(manager, A["id"], "FINANCE", "withdraw")
    check("un module V1 ne se retire pas", r.status_code == 409 and "V1" in r.text, r.text[:160])
    check("un module V1 ne s'active pas à part", change(manager, A["id"], "FINANCE", "activate").status_code == 409)
    check("module inconnu : 404", change(manager, A["id"], "INCONNU", "activate").status_code == 404)
    check("école inconnue : 404", change(manager, uuid.uuid4(), "ACADEMIC", "activate").status_code == 404)
    sql("UPDATE schools SET status='SUSPENDED' WHERE id=:s", s=B["id"])
    r = change(manager, B["id"], "ACADEMIC", "activate")
    check("école suspendue : aucun module activé", r.status_code == 409 and "suspendue" in r.text, r.text[:160])
    sql("UPDATE schools SET status='ACTIVE' WHERE id=:s", s=B["id"])

    plan, ver = uuid.uuid4(), uuid.uuid4()           # a published plan that contains FINANCE, already in service at B
    sql("INSERT INTO saas_plans(id,code,name,status) VALUES(:i,:c,'Finances','ACTIVE')", i=plan, c=f"FIN-{H.RUN}-{plan.hex[:6]}")
    sql("""INSERT INTO saas_plan_versions(id,plan_id,version,billing_cycle,currency,amount,grace_days,effective_from,status)
           VALUES(:i,:p,1,'MONTHLY','USD',60,10,:f,'PUBLISHED')""", i=ver, p=plan, f=date.today())
    sql("INSERT INTO saas_plan_modules(plan_version_id,module_code) VALUES(:v,'FINANCE'),(:v,'CORE_SCHOOL')", v=ver)
    billing = platform({"platform.billing.read", "platform.billing.subscriptions.manage"}, stepped_up=True)
    r = as_platform(billing).post("/api/v1/platform/billing/subscriptions", headers={"Idempotency-Key": f"sub-{uuid.uuid4().hex}"},
                                  json={"school_id": str(B["id"]), "plan_version_id": str(ver), "starts_on": date.today().isoformat(),
                                        "initial_status": "PENDING_PAYMENT", "reason": "Essai lot 0 (CI)"})
    check("abonnement attribué à une école dont les modules sont déjà en service : plus d'échec", r.status_code in (200, 201), r.text[:200])
    n = one("SELECT count(*) FROM saas_entitlements WHERE school_id=:s AND module_code='FINANCE' AND status='ACTIVE'", s=B["id"])[0]
    check("le module déjà en service est conservé, sans doublon", n == 1, n)


def main() -> int:
    run()
    CLIENT.__exit__(None, None, None)
    fails = [r for r in RESULTS if r[0] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
