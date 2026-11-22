"""V2 lot 3b — grade entry and conduct facts — real HTTP + real PostgreSQL (owner, 2026-11-22).

Grades: only the teacher of the course enters (the préfet reads, never enters — parent project); « 14 », « a », empty;
over the maximum refused; an offline replay of the same value changes nothing; a stale version is a conflict, never a
silent overwrite; history kept; no exam column for a course without exam; a period not started / closed refuses entry;
a pasted column fills only the empty cells; directors' follow-up.
Conduct: computed from facts (100 − points, mention); a teacher reports for his classes only, never a serious fact; the
same Idempotency-Key replays without a second fact; a serious fact rings the managers; 5 lates add the penalty;
cancellation (author same day / director), adjustment (director), « à suivre »; a closed period is frozen.

    python tools/local/isolated_db.py env <db> -- ../.venv/Scripts/python.exe ../tools/ci/pedagogy_grades_postgres_integration.py
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_roles_postgres_integration as H  # noqa: E402
from three_roles_postgres_integration import CLIENT, RESULTS, actor_for, as_, check, one, school, sql  # noqa: E402
from pedagogy_referential_postgres_integration import grant_pedagogy, school_class  # noqa: E402
from pedagogy_teachers_postgres_integration import with_role  # noqa: E402


def pupils(A: dict, class_id, n: int) -> list[str]:
    out = []
    for i in range(n):
        sid, fam = uuid.uuid4(), uuid.uuid4()
        sql("INSERT INTO families(id,school_id,code,display_name) VALUES(:i,:s,:c,'Famille')", i=fam, s=A["id"], c=f"F-{fam.hex[:8]}")
        sql("""INSERT INTO students(id,school_id,family_id,matricule,last_name,middle_name,first_name,gender) VALUES(:i,:s,:f,:m,:l,'TEST','Ada','F')""",
            i=sid, s=A["id"], f=fam, m=f"M-{sid.hex[:10]}", l=f"ELEVE{i + 1}")
        sql("INSERT INTO enrollments(id,school_id,student_id,academic_year_id,class_id) VALUES(:i,:s,:st,:y,:c)", i=uuid.uuid4(), s=A["id"], st=sid, y=A["year"], c=class_id)
        out.append(str(sid))
    return out


def cell(actor, class_id, course, period, student, value, expected=None, source="WEB"):
    return as_(actor).put("/api/v1/pedagogy/grades/cell", json={"class_id": str(class_id), "course_code": course, "period": period,
                                                              "student_id": student, "input": value, "expected_version": expected, "source": source})


def run() -> None:
    print("\n== V2 lot 3b — saisie des cotes et faits de conduite (22/11/2026)")
    A = school("A")
    grant_pedagogy(A["id"])
    prefet = with_role("PREFET_ETUDES", A)
    p1 = school_class(A, "PRIMAIRE", "1re A", "P1")
    h1 = school_class(A, "SECONDAIRE", "1re CG A", "H1", "CG")
    as_(prefet).post("/api/v1/pedagogy/class-links/accept-suggestions")
    as_(prefet).post("/api/v1/pedagogy/programmes/adopt-official", json={})
    for cal in as_(prefet).get("/api/v1/pedagogy/calendars").json()["calendars"]:
        as_(prefet).put(f"/api/v1/pedagogy/calendars/{cal['structure']}", json={"periods": [{k: p[k] for k in ("code", "starts_on", "ends_on")} for p in cal["periods"]]})
        as_(prefet).post(f"/api/v1/pedagogy/calendars/{cal['structure']}/validate")
    t1, t2 = with_role("ENSEIGNANT", A), with_role("ENSEIGNANT", A)
    as_(prefet).post(f"/api/v1/pedagogy/teaching/{p1}/assign-all", json={"membership_id": str(t1.membership_id)})
    as_(prefet).put(f"/api/v1/pedagogy/teaching/{p1}/titular", json={"membership_id": str(t1.membership_id)})
    as_(prefet).put(f"/api/v1/pedagogy/teaching/{h1}/courses/FRANCAIS", json={"membership_id": str(t2.membership_id)})
    as_(prefet).put(f"/api/v1/pedagogy/teaching/{h1}/courses/ACTIVITES_COMPLEMENTAIRES_VISITES_GUIDEES", json={"membership_id": str(t2.membership_id)})
    kids, teens = pupils(A, p1, 3), pupils(A, h1, 3)

    r = as_(t1).get(f"/api/v1/pedagogy/grades/sheet?class_id={p1}&course_code=NUMERATION")
    sh = r.json() if r.status_code == 200 else {}
    period = (sh.get("period") or {}).get("code")
    check("fiche de cotes : la classe dans l'ordre, la période ouverte, le maximum du programme",
          r.status_code == 200 and len(sh["pupils"]) == 3 and sh["can_enter"] and sh["period"]["max"] == 20 and sh["pupils"][0]["name"].startswith("ELEVE1"), r.text[:200])
    r = cell(t1, p1, "NUMERATION", period, kids[0], "14")
    check("taper 14 : enregistré tout de suite", r.status_code == 200 and r.json()["value"] == 14 and r.json()["version"] == 1, r.text[:160])
    r = cell(t1, p1, "NUMERATION", period, kids[1], "25")
    check("25 sur 20 : refusé, message court « Maximum 20 »", r.status_code == 422 and "Maximum 20" in r.text, r.text[:160])
    r = cell(t1, p1, "NUMERATION", period, kids[1], "8")
    check("8 sur 20 : enregistré, marqué en rouge (sous la moitié)", r.json().get("failing") is True)
    r = cell(t1, p1, "NUMERATION", period, kids[0], "a", expected=1)
    check("« a » : élève absent, sans cote", r.json()["status"] == "ABSENT" and r.json()["value"] is None and r.json()["version"] == 2)
    r = cell(t1, p1, "NUMERATION", period, kids[0], "a", expected=1, source="OFFLINE")
    check("rejeu hors ligne de la même saisie : rien ne change, pas de conflit", r.status_code == 200 and r.json()["version"] == 2, r.text[:160])
    r = cell(t1, p1, "NUMERATION", period, kids[0], "12", expected=1)
    check("valeur différente sur une version dépassée : conflit, jamais d'écrasement silencieux",
          r.status_code == 409 and "GRADE_CONFLICT" in r.text and '"status":"ABSENT"' in r.text.replace(" ", ""), r.text[:200])
    r = cell(t1, p1, "NUMERATION", period, kids[0], "", expected=2)
    check("vider une cote : la ligne reste, l'historique aussi", r.json()["status"] is None and one(
        "SELECT count(*) FROM pedagogy_grade_history h JOIN pedagogy_grades g ON g.id=h.grade_id WHERE g.student_id=:s", s=kids[0])[0] == 3)
    check("un autre enseignant ne saisit pas ce cours", cell(t2, p1, "NUMERATION", period, kids[1], "10").status_code == 403)
    check("l'enseignant ne voit pas les cotes d'un cours qui n'est pas le sien",
          as_(t1).get(f"/api/v1/pedagogy/grades/sheet?class_id={h1}&course_code=FRANCAIS").status_code == 403)
    r = as_(prefet).get(f"/api/v1/pedagogy/grades/sheet?class_id={p1}&course_code=NUMERATION")
    check("le préfet consulte, sans saisir (projet père)", r.status_code == 200 and r.json()["can_enter"] is False)
    check("le préfet ne saisit pas", cell(prefet, p1, "NUMERATION", period, kids[1], "10").status_code == 403)

    sh = as_(t2).get(f"/api/v1/pedagogy/grades/sheet?class_id={h1}&course_code=ACTIVITES_COMPLEMENTAIRES_VISITES_GUIDEES").json()
    check("cours sans examen : aucune colonne d'examen proposée", not any(c["code"].startswith("EX") for c in sh["periods"]), [c["code"] for c in sh["periods"]])
    r = cell(t2, h1, "ACTIVITES_COMPLEMENTAIRES_VISITES_GUIDEES", "EX1", teens[0], "10")
    check("cours sans examen : cote d'examen refusée, raison claire", r.status_code == 422 and "pas d’examen" in r.text, r.text[:160])
    r = cell(t2, h1, "FRANCAIS", "P3", teens[0], "30")
    check("période pas encore commencée : saisie refusée avec la raison", r.status_code == 409 and "pas encore commencé" in r.text, r.text[:160])
    fp = as_(t2).get(f"/api/v1/pedagogy/grades/sheet?class_id={h1}&course_code=FRANCAIS").json()["period"]["code"]
    r = as_(t2).post("/api/v1/pedagogy/grades/paste", json={"class_id": str(h1), "course_code": "FRANCAIS", "period": fp, "text": "32\n\n35/40"})
    check("coller une colonne (32, vide, 35/40) : 2 cotes en une fois", r.status_code == 200 and r.json()["pasted"]["filled"] == 2, r.text[:200])
    r = as_(t2).post("/api/v1/pedagogy/grades/paste", json={"class_id": str(h1), "course_code": "FRANCAIS", "period": fp, "text": "9\n9\n9"})
    check("recoller : seules les cases vides sont remplies, aucune cote écrasée", r.json()["pasted"] == {"filled": 1, "kept": 2, "lines": 3}, r.json().get("pasted"))
    check("trop de lignes collées : refusé", as_(t2).post("/api/v1/pedagogy/grades/paste", json={"class_id": str(h1), "course_code": "FRANCAIS",
          "period": fp, "text": "1\n2\n3\n4"}).status_code == 422)
    pr = as_(prefet).get("/api/v1/pedagogy/grades/progress").json()
    h1row = next((i for i in pr["items"] if i["class_id"] == str(h1)), {})
    check("suivi de la direction : 1re CG A, le français est complet", h1row.get("complete", 0) >= 1 and h1row.get("started", 0) >= 1, h1row)

    cl = {c["class_id"] for c in as_(t1).get("/api/v1/pedagogy/conduct/classes").json()["items"]}
    check("conduite : l'enseignant ne voit que ses classes", cl == {str(p1)}, cl)
    cc = as_(t1).get(f"/api/v1/pedagogy/conduct/class/{p1}").json()
    check("au départ : 100 points, mention E ; faits graves non proposés à l'enseignant",
          all(p["points"] == 100 and p["mention"] == "E" for p in cc["pupils"]) and not any(r["grave"] for r in cc["rules"]), cc.get("summary"))
    key = {"Idempotency-Key": f"fact-{uuid.uuid4().hex}"}
    body = {"class_id": str(p1), "student_id": kids[0], "rule_code": "RETARD"}
    r = as_(t1).post("/api/v1/pedagogy/conduct/facts", json=body, headers=key)
    check("3 touches : un retard → 98 points", r.status_code == 201 and r.json()["points"] == 98, r.text[:160])
    r2 = as_(t1).post("/api/v1/pedagogy/conduct/facts", json=body, headers=key)
    check("même envoi rejoué (hors ligne) : un seul fait", r2.headers.get("Idempotent-Replayed") == "true"
          and one("SELECT count(*) FROM pedagogy_conduct_facts WHERE student_id=:s", s=kids[0])[0] == 1)
    check("l'enseignant ne signale pas un fait grave", as_(t1).post("/api/v1/pedagogy/conduct/facts", json={**body, "rule_code": "BAGARRE"}).status_code == 403)
    dd = with_role("DIRECTEUR_DISCIPLINE", A)
    r = as_(dd).post("/api/v1/pedagogy/conduct/facts", json={**body, "rule_code": "BAGARRE"})
    check("le directeur de discipline signale une bagarre → 83 points", r.status_code == 201 and r.json()["points"] == 83, r.text[:160])
    bells = one("SELECT count(*) FROM notifications WHERE user_id=:u AND category='CONDUITE'", u=prefet.user_id)[0]
    check("fait grave : le préfet est alerté aussitôt", bells == 1, bells)
    for _ in range(5):
        last = as_(t1).post("/api/v1/pedagogy/conduct/facts", json={"class_id": str(p1), "student_id": kids[1], "rule_code": "RETARD"})
    check("5 retards : 100 − 10 − 5 (retards répétés) = 85", last.json()["points"] == 85 and last.json()["repeated_late_penalties"] == 1, last.text[:160])
    fact_late = r.json()["recent"] if r.status_code == 201 else []
    own = as_(t1).get(f"/api/v1/pedagogy/conduct/class/{p1}").json()
    kid0 = next(p for p in own["pupils"] if p["student_id"] == kids[0])
    mine = next(f for f in kid0["recent"] if f["label"] == "Retard"); grave = next(f for f in kid0["recent"] if f["grave"])
    check("l'enseignant ne peut pas annuler le fait grave du directeur", not grave["can_cancel"]
          and as_(t1).post(f"/api/v1/pedagogy/conduct/facts/{grave['id']}/cancel", json={"reason": "Erreur d'élève"}).status_code == 403)
    r = as_(t1).post(f"/api/v1/pedagogy/conduct/facts/{mine['id']}/cancel", json={"reason": "Mauvais élève choisi"})
    check("l'auteur annule son propre fait le jour même (motif), rien n'est effacé",
          r.status_code == 200 and r.json()["points"] == 85 and one("SELECT cancelled_at IS NOT NULL FROM pedagogy_conduct_facts WHERE id=:i", i=mine["id"]) == (True,), r.text[:160])
    check("le directeur annule le fait grave", as_(dd).post(f"/api/v1/pedagogy/conduct/facts/{grave['id']}/cancel", json={"reason": "Bagarre non confirmée"}).json()["points"] == 100)
    cp = cc["period"]["code"]
    r = as_(dd).post("/api/v1/pedagogy/conduct/adjust", json={"class_id": str(p1), "student_id": kids[2], "period": cp, "points": -60, "reason": "Comportement grave répété hors classe"})
    check("ajustement exceptionnel du directeur : 40 points, élève à suivre", r.status_code == 200 and r.json()["points"] == 40 and r.json()["to_follow"], r.text[:160])
    check("l'enseignant n'ajuste pas", as_(t1).post("/api/v1/pedagogy/conduct/adjust", json={"class_id": str(p1), "student_id": kids[2], "period": cp, "points": 10, "reason": "Essai interdit"}).status_code == 403)
    check("liste « à suivre » de la classe : 1 élève", as_(t1).get(f"/api/v1/pedagogy/conduct/class/{p1}").json()["summary"]["to_follow"] == 1)
    as_(prefet).post(f"/api/v1/pedagogy/calendars/TRIMESTRIEL/periods/{cp}/close")
    r = as_(t1).post("/api/v1/pedagogy/conduct/facts", json={"class_id": str(p1), "student_id": kids[1], "rule_code": "RETARD"})
    check("période clôturée : la conduite est figée", r.status_code == 409 and "figée" in r.text, r.text[:160])
    if period == cp:
        check("période clôturée : la saisie des cotes aussi", cell(t1, p1, "NUMERATION", period, kids[2], "10").status_code == 409)


def main() -> int:
    run()
    CLIENT.__exit__(None, None, None)
    fails = [r for r in RESULTS if r[0] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
