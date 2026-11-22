"""V2 lot 1 — official MINEDUC referential + class links — real HTTP + real PostgreSQL (owner, 2026-11-22).

Checks:
1. the referential is loaded at provisioning: 51 options, 215 classes, 485 courses, 130 programmes, 2 658 lines;
   loading again changes nothing;
2. the owner's corrections are in place and THE DATABASE refuses an exam that is not twice the period, or P5/P6/EX3 in
   a semester class;
3. without the pedagogy module every route is refused (403 MODULE_NOT_ACTIVE); with it, the right decides;
4. reading: options by group (9 / 13 / 29), a programme in bulletin order with its totals;
5. class links: suggestions (P1 → 1PR, H1 + CG → 1CG, legacy ELECTRONIQUE → EI, « Littéraire » → none), accept all,
   repeat = nothing more, manual link, unknown official class refused, other school's class invisible, unlink, audit;
6. a préfet limited to one section sees and links only the classes of that section.

    python tools/local/isolated_db.py env <db> -- ../.venv/Scripts/python.exe ../tools/ci/pedagogy_referential_postgres_integration.py
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_roles_postgres_integration as H  # noqa: E402
from three_roles_postgres_integration import CLIENT, RESULTS, actor_for, as_, check, one, school, sql  # noqa: E402
from edusync.modules.pedagogy.application.referential_loader import load_referential  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

V = "MINEDUC-2024-2025-V2"


def grant_pedagogy(school_id) -> None:
    sql("""INSERT INTO saas_entitlements(school_id,module_code,source,status,reason)
           VALUES(:s,'ACADEMIC','MANUAL','ACTIVE','Essai CI lot 1')""", s=school_id)


def school_class(A: dict, section: str, code: str, level: str | None, option_code: str | None = None) -> uuid.UUID:
    opt = None
    if option_code:
        opt = one("SELECT id FROM school_options WHERE school_id=:s AND code=:c", s=A["id"], c=option_code)
        opt = opt[0] if opt else None
        if opt is None:
            opt = uuid.uuid4()
            sql("INSERT INTO school_options(id,school_id,section_id,code,label) VALUES(:i,:s,:sec,:c,:c)",
                i=opt, s=A["id"], sec=A["sections"][section], c=option_code)
    cid = uuid.uuid4()
    sql("""INSERT INTO school_classes(id,school_id,academic_year_id,section_id,option_id,reference_code,code,label)
           VALUES(:i,:s,:y,:sec,:o,:r,:c,:c)""", i=cid, s=A["id"], y=A["year"], sec=A["sections"][section], o=opt, r=level, c=code)
    return cid


def bad_line(**over) -> bool:
    """True when the database refuses the line."""
    vals = dict(v=V, cls="1SC", course="ACTUALITES", sort=99, ex=True, sem=True, p1=10, p2=10, e1=20, p3=10, p4=10, e2=20, p5=0, p6=0, e3=0)
    vals.update(over)
    try:
        with H.ENGINE.begin() as c:
            c.execute(H.text("""INSERT INTO ref_programme_lines(version_code,class_code,course_code,sort_order,mandatory,has_exam,calculable,
                semester_structure,max_p1,max_p2,max_ex1,max_p3,max_p4,max_ex2,max_p5,max_p6,max_ex3)
                VALUES(:v,:cls,:course,:sort,true,:ex,true,:sem,:p1,:p2,:e1,:p3,:p4,:e2,:p5,:p6,:e3)"""), vals)
            raise RuntimeError("rollback")      # never keep the probe line
    except IntegrityError:
        return True
    except RuntimeError:
        return False


def run() -> None:
    print("\n== V2 lot 1 — référentiel officiel MINEDUC (22/11/2026)")
    counts = one("""SELECT (SELECT count(*) FROM ref_options),(SELECT count(*) FROM ref_classes),(SELECT count(*) FROM ref_courses),
        (SELECT count(DISTINCT class_code) FROM ref_programme_lines WHERE version_code=:v),(SELECT count(*) FROM ref_programme_lines WHERE version_code=:v)""", v=V)
    check("référentiel chargé : 51 options, 215 classes, 485 cours, 130 programmes, 2 658 lignes", tuple(counts) == (51, 215, 485, 130, 2658), counts)
    with H.ENGINE.begin() as c:
        msg = load_referential(c)
    check("chargement rejoué : rien ne change", "déjà à jour" in msg, msg)
    groups = dict(sql("SELECT option_group,count(*) FROM ref_options GROUP BY 1").all())
    check("options : 9 générales, 13 Technique groupe 1, 29 Technique groupe 2", groups == {"GENERAL": 9, "GROUPE_1": 13, "GROUPE_2": 29}, groups)
    hydro = one("SELECT max_ex1,max_ex2 FROM ref_programme_lines WHERE class_code='2HYDRO' AND course_code='FRANCAIS'")
    sc3 = one("SELECT max_ex1,max_ex2 FROM ref_programme_lines WHERE class_code='3SC' AND course_code='GEOLOGIE_ECOLOGIE'")
    check("corrections du propriétaire : 2HYDRO Français EX1 = 100, 3SC Géologie EX = 40", tuple(hydro) == (100, 100) and tuple(sc3) == (40, 40), (hydro, sc3))
    wrong = one("""SELECT count(*) FROM ref_programme_lines WHERE has_exam AND NOT (max_ex1=2*max_p1 AND max_ex2=2*max_p3 AND max_ex3=2*max_p5)""")[0]
    check("toutes les lignes avec examen : examen = double de la période", wrong == 0, wrong)
    check("la base refuse un examen qui n'est pas le double de la période", bad_line(e1=10))
    check("la base refuse P5 / EX3 dans une classe semestrielle", bad_line(p5=10, e3=20))
    check("la base refuse des points d'examen à un cours sans examen", bad_line(ex=False))
    check("contrôle : une ligne correcte est acceptée", not bad_line())

    A, B = school("A"), school("B")
    prefet = actor_for("PREFET_ETUDES", A["id"])
    r = as_(prefet).get("/api/v1/pedagogy/referential")
    check("école SANS module Pédagogie : référentiel refusé (403 MODULE_NOT_ACTIVE)", r.status_code == 403 and "MODULE_NOT_ACTIVE" in r.text, r.status_code)
    grant_pedagogy(A["id"])
    r = as_(prefet).get("/api/v1/pedagogy/referential")
    body = r.json() if r.status_code == 200 else {}
    check("école AVEC module : le préfet lit le référentiel", r.status_code == 200 and body["version"]["code"] == V, r.text[:200])
    check("référentiel : 3 groupes d'options (9 / 13 / 29) et 215 classes",
          [len(g["options"]) for g in body.get("groups", [])] == [9, 13, 29] and len(body.get("classes", [])) == 215)
    without = sorted(c["code"] for c in body.get("classes", []) if not c["has_programme"])
    check("classes sans programme signalées (maternelle, 3NOR, 4NOR, 20 options : 85)", len(without) == 85 and "1MAT" in without and "3NOR" in without, len(without))
    r = as_(prefet).get("/api/v1/pedagogy/referential/classes/1SC")
    p = r.json() if r.status_code == 200 else {}
    check("programme 1re Sciences : 18 cours dans l'ordre du bulletin, total P1 = 360",
          r.status_code == 200 and len(p["lines"]) == 18 and p["lines"][0]["sort_order"] == 1 and p["totals"]["max_p1"] == 360, r.text[:200])
    check("classe semestrielle : 6 colonnes (P1 P2 EX1 P3 P4 EX2)", p.get("columns") == ["max_p1", "max_p2", "max_ex1", "max_p3", "max_p4", "max_ex2"])
    pr = as_(prefet).get("/api/v1/pedagogy/referential/classes/1PR").json()
    check("primaire : trimestriel, 9 colonnes", len(pr.get("columns", [])) == 9 and pr["class"]["structure"] == "TRIMESTRIEL")
    check("classe officielle inconnue : 404", as_(prefet).get("/api/v1/pedagogy/referential/classes/9ZZ").status_code == 404)
    check("rôle sans le droit (caissier) : refus", as_(actor_for("CAISSIER", A["id"])).get("/api/v1/pedagogy/referential").status_code == 403)

    p1 = school_class(A, "PRIMAIRE", "1re A", "P1")
    h1cg = school_class(A, "SECONDAIRE", "1re CG", "H1", "CG")
    h2el = school_class(A, "SECONDAIRE", "2e Électronique", "H2", "ELECTRONIQUE")
    lit = school_class(A, "SECONDAIRE", "3e Littéraire", "H3", "LITTERAIRE")
    other = school_class(B, "PRIMAIRE", "1re B", "P1")
    r = as_(prefet).get("/api/v1/pedagogy/class-links")
    items = {i["class_id"]: i for i in r.json().get("items", [])} if r.status_code == 200 else {}
    sug = lambda cid: (items.get(str(cid)) or {}).get("suggestion") and items[str(cid)]["suggestion"]["ref_class_code"]  # noqa: E731
    check("suggestions : P1 → 1PR, H1 + CG → 1CG, ancienne option ELECTRONIQUE → 2EI", (sug(p1), sug(h1cg), sug(h2el)) == ("1PR", "1CG", "2EI"),
          (sug(p1), sug(h1cg), sug(h2el)))
    check("« Littéraire » (non officielle) : aucune suggestion inventée", sug(lit) is None)
    check("classe d'une autre école invisible", str(other) not in items)
    r = as_(prefet).post("/api/v1/pedagogy/class-links/accept-suggestions")
    check("accepter les suggestions : 3 classes reliées", r.status_code == 200 and r.json()["linked"] == 3, r.text[:200])
    check("accepter à nouveau : rien de plus", as_(prefet).post("/api/v1/pedagogy/class-links/accept-suggestions").json()["linked"] == 0)
    r = as_(prefet).put(f"/api/v1/pedagogy/class-links/{lit}", json={"ref_class_code": "3LP"})
    check("relier à la main « 3e Littéraire » → 3LP", r.status_code == 200 and r.json()["changed"], r.text[:160])
    check("classe officielle inconnue refusée", as_(prefet).put(f"/api/v1/pedagogy/class-links/{lit}", json={"ref_class_code": "9ZZ"}).status_code == 404)
    check("classe d'une autre école : 404", as_(prefet).put(f"/api/v1/pedagogy/class-links/{other}", json={"ref_class_code": "1PR"}).status_code == 404)
    summary = as_(prefet).get("/api/v1/pedagogy/class-links").json()["summary"]
    check("résumé : 4 classes reliées sur 6 (2 classes de test sans niveau)", summary["linked"] == 4 and summary["classes"] == 6, summary)
    r = as_(prefet).delete(f"/api/v1/pedagogy/class-links/{lit}")
    check("retirer une correspondance", r.status_code == 200 and r.json()["changed"], r.text[:120])
    audits = dict(sql("""SELECT action,count(*) FROM audit_events WHERE school_id=:s AND action LIKE 'PEDAGOGY_CLASS%' GROUP BY 1""", s=A["id"]).all())
    check("journal d'audit : suggestions acceptées, liaison, retrait",
          audits.get("PEDAGOGY_CLASS_SUGGESTIONS_ACCEPTED") == 1 and audits.get("PEDAGOGY_CLASS_LINKED") == 1 and audits.get("PEDAGOGY_CLASS_UNLINKED") == 1, audits)
    check("le promoteur lit mais ne relie pas",
          as_(actor_for("PROMOTEUR", A["id"])).put(f"/api/v1/pedagogy/class-links/{lit}", json={"ref_class_code": "3LP"}).status_code == 403)

    section_prefet = actor_for("PREFET_ETUDES", A["id"], scope=("SECTION", "PRIMAIRE"))
    seen = {i["class_id"] for i in as_(section_prefet).get("/api/v1/pedagogy/class-links").json().get("items", [])}
    check("préfet limité au primaire : ne voit que les classes du primaire", str(p1) in seen and str(h1cg) not in seen, len(seen))
    check("préfet limité au primaire : ne relie pas une classe du secondaire",
          as_(section_prefet).put(f"/api/v1/pedagogy/class-links/{lit}", json={"ref_class_code": "3LP"}).status_code == 404)
    check("école B sans module : correspondances refusées",
          as_(actor_for("ADMIN_SYSTEME_ECOLE", B["id"])).get("/api/v1/pedagogy/class-links").status_code == 403)
    nav = lambda actor: [n["key"] for n in as_(actor).get("/api/v1/access/me").json().get("navigation", [])]  # noqa: E731
    check("menu « Pédagogie » : présent pour l'école A (module), absent pour l'école B",
          "pedagogy" in nav(prefet) and "pedagogy" not in nav(actor_for("PREFET_ETUDES", B["id"])))
    check("menu « Pédagogie » absent pour un rôle sans le droit (caissier)", "pedagogy" not in nav(actor_for("CAISSIER", A["id"])))
    ov = as_(prefet).get("/api/v1/pedagogy/overview").json()
    check("aperçu : version du référentiel chargée", ov.get("referential") == V, ov)


def main() -> int:
    run()
    CLIENT.__exit__(None, None, None)
    fails = [r for r in RESULTS if r[0] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
