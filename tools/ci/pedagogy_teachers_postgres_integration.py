"""V2 lot 3a — teachers, course assignments, titulars, conduct scale — real HTTP + real PostgreSQL (owner, 2026-11-22).

Checks: only members holding the Enseignant role are teachers; one click gives every free course of a primary class to
its teacher; a course outside the programme in use is refused; a non-teacher can be neither assigned nor titular; one
titular per class but the same teacher may hold 2 classes (owner); titular powers effective in primaire only; the teacher
sees exactly his own classes and courses; a section-scoped member acts only in his section; the conduct scale starts
from EduSync's proposal, is saved, validated (no 0-point fact), a removed fact is deactivated (never deleted); audit.

    python tools/local/isolated_db.py env <db> -- ../.venv/Scripts/python.exe ../tools/ci/pedagogy_teachers_postgres_integration.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from three_roles_postgres_integration import CLIENT, RESULTS, actor_for, as_, check, one, school, sql  # noqa: E402
from pedagogy_referential_postgres_integration import grant_pedagogy, school_class  # noqa: E402


def with_role(role: str, A: dict, **kw):
    """A member holding the role for real (rbac_assignments): the teachers list reads the database."""
    actor = actor_for(role, A["id"], **kw)
    sql("""INSERT INTO rbac_assignments(user_id,role_id,school_id,membership_id) SELECT :u,r.id,:s,:m FROM rbac_roles r
           WHERE r.code=:c AND r.kind='SCHOOL_STANDARD'""", u=actor.user_id, s=A["id"], m=actor.membership_id, c=role)
    return actor


def run() -> None:
    print("\n== V2 lot 3a — enseignants, titulaires, barème de conduite (22/11/2026)")
    A = school("A")
    grant_pedagogy(A["id"])
    prefet = actor_for("PREFET_ETUDES", A["id"])
    p1 = school_class(A, "PRIMAIRE", "1re A", "P1")
    h1 = school_class(A, "SECONDAIRE", "1re CG A", "H1", "CG")
    h1b = school_class(A, "SECONDAIRE", "1re CG B", "H1", "CG")
    as_(prefet).post("/api/v1/pedagogy/class-links/accept-suggestions")
    as_(prefet).post("/api/v1/pedagogy/programmes/adopt-official", json={})
    t1, t2 = with_role("ENSEIGNANT", A), with_role("ENSEIGNANT", A)
    cashier = with_role("CAISSIER", A)

    r = as_(prefet).get("/api/v1/pedagogy/teachers")
    ids = {t["membership_id"] for t in r.json()} if r.status_code == 200 else set()
    check("enseignants : seuls les membres ayant le rôle Enseignant", ids == {str(t1.membership_id), str(t2.membership_id)}, r.text[:200])
    view = as_(prefet).get("/api/v1/pedagogy/teaching").json()
    items = {i["class_id"]: i for i in view["items"]}
    n_p1 = len(items[str(p1)]["courses"])
    check("vue des attributions : les cours du programme en service de chaque classe", n_p1 > 10 and items[str(p1)]["assigned"] == 0, n_p1)
    r = as_(prefet).post(f"/api/v1/pedagogy/teaching/{p1}/assign-all", json={"membership_id": str(t1.membership_id)})
    check("un clic : tous les cours de la 1re A à son enseignant", r.status_code == 200 and r.json()["newly_assigned"] == n_p1 and r.json()["assigned"] == n_p1, r.text[:160])
    check("rejouer : rien de plus", as_(prefet).post(f"/api/v1/pedagogy/teaching/{p1}/assign-all", json={"membership_id": str(t1.membership_id)}).json()["newly_assigned"] == 0)
    r = as_(prefet).put(f"/api/v1/pedagogy/teaching/{h1}/courses/FRANCAIS", json={"membership_id": str(t2.membership_id)})
    fr = next((c for c in r.json()["courses"] if c["course_code"] == "FRANCAIS"), {}) if r.status_code == 200 else {}
    check("1re CG A : le français à un autre enseignant", (fr.get("teacher") or {}).get("membership_id") == str(t2.membership_id), r.text[:160])
    check("cours hors programme : refusé", as_(prefet).put(f"/api/v1/pedagogy/teaching/{h1}/courses/ASTRONOMIE", json={"membership_id": str(t2.membership_id)}).status_code == 404)
    r = as_(prefet).put(f"/api/v1/pedagogy/teaching/{h1}/courses/DROIT", json={"membership_id": str(cashier.membership_id)})
    check("un non-enseignant (caissier) ne reçoit pas de cours, message clair", r.status_code == 409 and "rôle Enseignant" in r.text, r.text[:160])
    check("retirer l'attribution d'un cours", as_(prefet).put(f"/api/v1/pedagogy/teaching/{h1}/courses/FRANCAIS", json={"membership_id": None}).json()["assigned"] == 0)
    as_(prefet).put(f"/api/v1/pedagogy/teaching/{h1}/courses/FRANCAIS", json={"membership_id": str(t2.membership_id)})

    r = as_(prefet).put(f"/api/v1/pedagogy/teaching/{p1}/titular", json={"membership_id": str(t1.membership_id)})
    check("titulaire de la 1re A, pouvoirs effectifs au primaire", r.status_code == 200 and r.json()["titular"]["membership_id"] == str(t1.membership_id) and r.json()["titular_effective"], r.text[:160])
    a = as_(prefet).put(f"/api/v1/pedagogy/teaching/{h1}/titular", json={"membership_id": str(t2.membership_id)}).json()
    b = as_(prefet).put(f"/api/v1/pedagogy/teaching/{h1b}/titular", json={"membership_id": str(t2.membership_id)}).json()
    check("un même enseignant titulaire de 2 classes (décision du propriétaire)", a["titular"]["membership_id"] == b["titular"]["membership_id"] == str(t2.membership_id))
    check("au secondaire, titulariat sans pouvoirs effectifs (règle du projet père)", a["titular_effective"] is False)
    check("un caissier ne peut pas être titulaire", as_(prefet).put(f"/api/v1/pedagogy/teaching/{h1b}/titular", json={"membership_id": str(cashier.membership_id)}).status_code == 409)
    r = as_(prefet).put(f"/api/v1/pedagogy/teaching/{h1b}/titular", json={"membership_id": str(t1.membership_id)})
    check("changer de titulaire : un seul titulaire par classe", r.json()["titular"]["membership_id"] == str(t1.membership_id)
          and one("SELECT count(*) FROM pedagogy_class_titulars WHERE class_id=:c", c=h1b)[0] == 1)

    mine = as_(t1).get("/api/v1/pedagogy/my-teaching").json()
    check("l'enseignant voit SES classes et SES cours", [c["class_id"] for c in mine["classes"]] == [str(p1)] and len(mine["classes"][0]["courses"]) == n_p1, mine.get("classes", [])[:1])
    check("l'enseignant voit ses titulariats (2 classes)", {t["class_id"] for t in mine["titular_of"]} == {str(p1), str(h1b)}, mine.get("titular_of"))
    mine2 = as_(t2).get("/api/v1/pedagogy/my-teaching").json()
    check("le 2e enseignant ne voit que le français de la 1re CG A", [(c["class_id"], [x["course_code"] for x in c["courses"]]) for c in mine2["classes"]] == [(str(h1), ["FRANCAIS"])])
    check("l'enseignant n'attribue pas les cours", as_(t1).get("/api/v1/pedagogy/teaching").status_code == 403)
    check("le caissier ne voit pas les attributions", as_(cashier).get("/api/v1/pedagogy/teaching").status_code == 403)
    ds = actor_for("DIRECTION_SECTION", A["id"], scope=("SECTION", "PRIMAIRE"))
    check("directeur de section (primaire) : n'attribue pas au secondaire",
          as_(ds).put(f"/api/v1/pedagogy/teaching/{h1}/courses/DROIT", json={"membership_id": str(t1.membership_id)}).status_code == 404)
    check("directeur de section (primaire) : ne voit que le primaire", {i["section_code"] for i in as_(ds).get("/api/v1/pedagogy/teaching").json()["items"]} == {"PRIMAIRE"})

    sc = as_(prefet).get("/api/v1/pedagogy/conduct/scale").json()
    check("barème de conduite : proposition EduSync (9 faits, départ 100, mentions E…MA)",
          not sc["saved"] and len(sc["rules"]) == 9 and sc["start"] == 100 and [m["code"] for m in sc["mentions"]] == ["E", "TB", "B", "AB", "ME", "MA"], sc.get("saved"))
    rules = [dict(r) for r in sc["rules"] if r["code"] != "TENUE"]
    rules[0]["points"] = -1
    rules.append({"code": "TELEPHONE", "label": "Téléphone en classe", "points": -3, "grave": False, "active": True})
    dd = actor_for("DIRECTEUR_DISCIPLINE", A["id"])
    r = as_(dd).put("/api/v1/pedagogy/conduct/scale", json={"rules": rules, "settings": {"late_threshold": 4, "late_penalty": 5, "alert_below": 50}})
    saved = r.json() if r.status_code == 200 else {}
    check("le directeur de discipline règle le barème (retard −1, téléphone −3, 4 retards)",
          saved.get("saved") and next(x for x in saved["rules"] if x["code"] == "RETARD")["points"] == -1
          and any(x["code"] == "TELEPHONE" for x in saved["rules"]) and saved["settings"]["late_threshold"] == 4, r.text[:200])
    check("un fait jamais retenu (tenue) n'est pas créé", one("SELECT count(*) FROM pedagogy_conduct_rules WHERE school_id=:s AND code='TENUE'", s=A["id"])[0] == 0)
    as_(dd).put("/api/v1/pedagogy/conduct/scale", json={"rules": [r for r in rules if r["code"] != "TELEPHONE"],
                                                          "settings": {"late_threshold": 4, "late_penalty": 5, "alert_below": 50}})
    check("un fait retiré ensuite est désactivé, jamais supprimé",
          one("SELECT active FROM pedagogy_conduct_rules WHERE school_id=:s AND code='TELEPHONE'", s=A["id"]) == (False,))
    bad = [dict(rules[0], points=0)] + rules[1:]
    check("un fait à 0 point est refusé", as_(dd).put("/api/v1/pedagogy/conduct/scale", json={"rules": bad, "settings": {"late_threshold": 4, "late_penalty": 5, "alert_below": 50}}).status_code == 422)
    check("l'enseignant ne règle pas le barème", as_(t1).put("/api/v1/pedagogy/conduct/scale", json={"rules": rules, "settings": {}}).status_code == 403)
    check("l'enseignant lit le barème", as_(t1).get("/api/v1/pedagogy/conduct/scale").status_code == 200)
    audits = dict(sql("SELECT action,count(*) FROM audit_events WHERE school_id=:s AND action LIKE 'PEDAGOGY_%' AND entity_type IN ('PedagogyTeaching','PedagogyConductScale') GROUP BY 1", s=A["id"]).all())
    check("journal : attributions, titulaires, barème",
          audits.get("PEDAGOGY_COURSES_ASSIGNED_ALL") == 1 and audits.get("PEDAGOGY_TITULAR_SET") == 4 and audits.get("PEDAGOGY_CONDUCT_SCALE_SAVED") == 2
          and audits.get("PEDAGOGY_COURSE_UNASSIGNED") == 1, audits)


def main() -> int:
    run()
    CLIENT.__exit__(None, None, None)
    fails = [r for r in RESULTS if r[0] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
