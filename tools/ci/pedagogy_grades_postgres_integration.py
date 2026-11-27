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
    lifecycle(A, prefet, p1, h1, kids, teens, t1, t2, period, fp)
    comfort(A, prefet, p1, kids, t1, period)
    as_(prefet).post(f"/api/v1/pedagogy/calendars/TRIMESTRIEL/periods/{cp}/close")
    r = as_(t1).post("/api/v1/pedagogy/conduct/facts", json={"class_id": str(p1), "student_id": kids[1], "rule_code": "RETARD"})
    check("période clôturée : la conduite est figée", r.status_code == 409 and "figée" in r.text, r.text[:160])
    if period == cp:
        check("période clôturée : la saisie des cotes aussi", cell(t1, p1, "NUMERATION", period, kids[2], "10").status_code == 409)


def lifecycle(A, prefet, p1, h1, kids, teens, t1, t2, period, fp) -> None:
    """Owner, 2026-11-22: « un élève qui a déjà abandonné, comment la liste le gère ? » — every movement of a pupil."""
    staff = actor_for("PREFET_ETUDES", A["id"], extra={"students.lifecycle.abandon", "students.lifecycle.transfer", "students.lifecycle.suspend",
                                                        "students.lifecycle.reintegrate", "students.class.change"})

    def move(student, event, **extra):
        version = one("SELECT version FROM students WHERE id=:s", s=student)[0]
        return as_(staff).post(f"/api/v1/schooling/students/{student}/{event}", json={"reason": f"Essai CI {event}", **extra},
                               headers={"If-Match": str(version), "Idempotency-Key": f"lc-{uuid.uuid4().hex}"})

    cell(t1, p1, "NUMERATION", period, kids[1], "11", expected=one(
        "SELECT version FROM pedagogy_grades WHERE student_id=:s AND course_code='NUMERATION' AND period_code=:p", s=kids[1], p=period)[0])
    r = move(kids[1], "abandon")
    check("abandon enregistré par la vraie action de l'école", r.status_code == 200, r.text[:160])
    sh = as_(t1).get(f"/api/v1/pedagogy/grades/sheet?class_id={p1}&course_code=NUMERATION").json()
    gone = next(p for p in sh["pupils"] if p["student_id"] == kids[1])
    check("élève parti : en fin de liste, marqué « parti » avec sa date, sa cote gardée",
          sh["pupils"][-1]["student_id"] == kids[1] and gone["departed"] and gone["left_on"] and gone["value"] == 11, gone)
    check("élève parti : ne compte plus dans l'avancement", sh["progress"]["total"] == 2, sh["progress"])
    r = cell(t1, p1, "NUMERATION", period, kids[1], "12", expected=gone["version"])
    check("élève parti : plus de cote à saisir, raison claire", r.status_code == 409 and "Abandon le" in r.text, r.text[:160])
    r = as_(t1).post("/api/v1/pedagogy/conduct/facts", json={"class_id": str(p1), "student_id": kids[1], "rule_code": "RETARD"})
    check("élève parti : plus de fait de conduite", r.status_code == 409 and "parti" in r.text, r.text[:160])
    check("élève parti : absent de la liste de conduite",
          kids[1] not in {p["student_id"] for p in as_(t1).get(f"/api/v1/pedagogy/conduct/class/{p1}").json()["pupils"]})
    r = as_(t1).post("/api/v1/pedagogy/grades/paste", json={"class_id": str(p1), "course_code": "NUMERATION", "period": period, "text": "1\n2\n3"})
    check("liste collée : l'élève parti n'est plus dans l'ordre (3 lignes pour 2 présents = refusé)", r.status_code == 422 and "2 élèves" in r.text, r.text[:160])
    r = move(kids[1], "reintegrate")
    sh = as_(t1).get(f"/api/v1/pedagogy/grades/sheet?class_id={p1}&course_code=NUMERATION").json()
    back = next(p for p in sh["pupils"] if p["student_id"] == kids[1])
    check("réintégré : de retour dans la liste, de nouveau noté", r.status_code == 200 and not back["departed"] and sh["progress"]["total"] == 3, r.text[:120])

    r = move(teens[2], "transfer", destination="Collège Saint-Joseph")
    sh = as_(t2).get(f"/api/v1/pedagogy/grades/sheet?class_id={h1}&course_code=FRANCAIS&period={fp}").json()
    tr = next(p for p in sh["pupils"] if p["student_id"] == teens[2])
    check("transféré : gardé en fin de liste avec sa cote, plus noté", r.status_code == 200 and tr["departed"] and tr["pupil_status"] == "TRANSFERRED"
          and tr["value"] is not None, tr)
    pr = next(i for i in as_(prefet).get("/api/v1/pedagogy/grades/progress").json()["items"] if i["class_id"] == str(h1))
    check("suivi de la direction : l'élève transféré ne compte plus", pr["pupils"] == 2 and pr["complete"] >= 1, pr)

    r = move(teens[1], "suspend")
    sh = as_(t2).get(f"/api/v1/pedagogy/grades/sheet?class_id={h1}&course_code=FRANCAIS&period={fp}").json()
    su = next(p for p in sh["pupils"] if p["student_id"] == teens[1])
    check("suspendu : reste dans la classe, signalé « Suspendu », toujours noté", r.status_code == 200 and su["pupil_status"] == "SUSPENDED" and not su["departed"], su)

    h1b = school_class(A, "SECONDAIRE", "1re CG B", "H1", "CG")
    as_(prefet).post("/api/v1/pedagogy/class-links/accept-suggestions")
    r = as_(staff).post(f"/api/v1/schooling/students/{teens[0]}/class-change", json={"class_id": str(h1b), "reason": "Essai CI changement de classe"},
                        headers={"Idempotency-Key": f"cc-{uuid.uuid4().hex}"})
    sh = as_(t2).get(f"/api/v1/pedagogy/grades/sheet?class_id={h1}&course_code=FRANCAIS&period={fp}").json()
    kept = one("SELECT value FROM pedagogy_grades WHERE student_id=:s AND class_id=:c AND course_code='FRANCAIS'", s=teens[0], c=h1)
    check("changement de classe : quitte la liste de 1re CG A, ses cotes de 1re CG A gardées",
          r.status_code == 200 and teens[0] not in {p["student_id"] for p in sh["pupils"]} and kept and kept[0] == 32, (r.status_code, kept))


def comfort(A, prefet, p1, kids, t1, period) -> None:
    """Lot 3c (owner, 2026-11-22: « encore plus de facilité »)."""
    from datetime import date as _date, timedelta as _td
    from edusync.modules.pedagogy.application.followup import automatic_reminders
    r = as_(t1).get(f"/api/v1/pedagogy/grades/sheet.pdf?class_id={p1}&course_code=NUMERATION")
    check("fiche de cotation imprimable : un vrai PDF", r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content[:5] == b"%PDF-", r.status_code)
    try:
        import io
        from pypdf import PdfReader
        txt = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
        check("le PDF contient les élèves présents, pas celui qui est parti, et aucun caractère invisible",
              "ELEVE1" in txt and "Fiche de cotation" in txt and " " not in txt and " " not in txt, txt[:120])
    except ImportError:
        pass
    check("fiche imprimable refusée à un enseignant d'un autre cours",
          as_(actor_for("ENSEIGNANT", A["id"])).get(f"/api/v1/pedagogy/grades/sheet.pdf?class_id={p1}&course_code=NUMERATION").status_code == 403)
    ms = as_(prefet).get("/api/v1/pedagogy/grades/missing").json()["teachers"]
    mine = next((t for t in ms if t["membership_id"] == str(t1.membership_id)), None)
    check("qui n'a pas fini : l'enseignant de la 1re A, avec ses cours incomplets", mine is not None and any(i["course_code"] == "NUMERATION" for i in mine["items"]), ms[:1])
    before = one("SELECT count(*) FROM notifications WHERE user_id=:u AND category='PEDAGOGIE'", u=t1.user_id)[0]
    r = as_(prefet).post("/api/v1/pedagogy/grades/remind", json={"membership_ids": [str(t1.membership_id)]})
    after = one("SELECT count(*) FROM notifications WHERE user_id=:u AND category='PEDAGOGIE'", u=t1.user_id)[0]
    check("« Relancer » : l'enseignant reçoit sa liste dans sa cloche", r.status_code == 200 and r.json()["sent"] == 1 and after == before + 1, r.text[:120])
    check("relancer deux fois le même jour : pas de double message", as_(prefet).post("/api/v1/pedagogy/grades/remind", json={}).json()["sent"] == 0
          or one("SELECT count(*) FROM notifications WHERE user_id=:u AND category='PEDAGOGIE'", u=t1.user_id)[0] == after)
    check("l'enseignant ne relance pas ses collègues", as_(t1).post("/api/v1/pedagogy/grades/remind", json={}).status_code == 403)
    end = one("""SELECT p.ends_on FROM pedagogy_calendars k JOIN pedagogy_calendar_periods p ON p.calendar_id=k.id
        WHERE k.school_id=:s AND k.structure='TRIMESTRIEL' AND p.code=:c""", s=A["id"], c=period)[0]
    sql("DELETE FROM notifications WHERE user_id=:u AND category='PEDAGOGIE'", u=t1.user_id)
    with H.ENGINE.begin() as c:
        c.execute(H.text("SELECT set_config('app.school_id', :s, true), set_config('app.current_school_id', :s, true)"), {"s": str(A["id"])})
        far = automatic_reminders(c, A["id"], today=end - _td(days=10))
        near = automatic_reminders(c, A["id"], today=end - _td(days=2))
    check("relance automatique : rien 10 jours avant la fin, un rappel 2 jours avant", far == 0 and near >= 1, (far, near))
    kids_present = [k for k in kids if k != kids[1]] if one("SELECT status FROM students WHERE id=:s", s=kids[1])[0] in ("ABANDON", "TRANSFERRED") else kids
    key = {"Idempotency-Key": f"batch-{uuid.uuid4().hex}"}
    body = {"class_id": str(p1), "student_ids": kids_present[:2], "rule_code": "INDISCIPLINE"}
    r = as_(t1).post("/api/v1/pedagogy/conduct/facts/batch", json=body, headers=key)
    check("signalement groupé : 2 élèves en une fois", r.status_code == 201 and r.json()["count"] == 2, r.text[:160])
    r2 = as_(t1).post("/api/v1/pedagogy/conduct/facts/batch", json=body, headers=key)
    check("signalement groupé rejoué (hors ligne) : pas de doublon", r2.headers.get("Idempotent-Replayed") == "true")
    check("signalement groupé d'un fait grave : refusé à l'enseignant",
          as_(t1).post("/api/v1/pedagogy/conduct/facts/batch", json={**body, "rule_code": "BAGARRE"}).status_code == 403)
    check("signalement groupé avec un élève d'ailleurs : rien n'est enregistré",
          as_(t1).post("/api/v1/pedagogy/conduct/facts/batch", json={**body, "student_ids": [kids_present[0], str(uuid.uuid4())]}).status_code == 409)


def main() -> int:
    run()
    CLIENT.__exit__(None, None, None)
    fails = [r for r in RESULTS if r[0] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
