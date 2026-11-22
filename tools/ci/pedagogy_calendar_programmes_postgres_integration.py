"""V2 lot 2 — pedagogical calendar and school programmes — real HTTP + real PostgreSQL (owner, 2026-11-22).

Checks:
1. calendars: proposed by EduSync from the school year (both structures when nothing is linked, then only the needed one);
   saved, refused when inconsistent (outside the year, overlap), holiday gap shown; validated by the préfet; a change
   after validation needs a motif; grade entry closed / reopened (motif) per period; audit;
2. programmes: one click adopts the official programmes (validated); a class without official programme is not invented;
   a new version is a draft copy; one number per term → maxima (exam = 2 × period); the database refuses a broken line;
   a compulsory official course cannot be removed, an optional one can; order changes; validating archives the old
   version; another school / no module / no right → refused; a directeur de section acts only in his section.

    python tools/local/isolated_db.py env <db> -- ../.venv/Scripts/python.exe ../tools/ci/pedagogy_calendar_programmes_postgres_integration.py
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_roles_postgres_integration as H  # noqa: E402
from three_roles_postgres_integration import CLIENT, RESULTS, actor_for, as_, check, one, school, sql  # noqa: E402
from pedagogy_referential_postgres_integration import grant_pedagogy, school_class  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402


def run() -> None:
    print("\n== V2 lot 2 — calendrier et programmes (22/11/2026)")
    A, B = school("A"), school("B")
    grant_pedagogy(A["id"])
    prefet = actor_for("PREFET_ETUDES", A["id"])
    r = as_(prefet).get("/api/v1/pedagogy/calendars")
    cals = r.json().get("calendars", []) if r.status_code == 200 else []
    check("sans classe reliée : deux calendriers proposés (trimestriel et semestriel)", [c["structure"] for c in cals] == ["TRIMESTRIEL", "SEMESTRIEL"], r.text[:200])
    tri = cals[0] if cals else {}
    check("calendrier proposé : 9 périodes du 1er septembre au 1er juillet, rien d'enregistré",
          not tri.get("saved") and len(tri.get("periods", [])) == 9 and tri["periods"][0]["starts_on"] == "2026-09-01"
          and tri["periods"][-1]["ends_on"] == "2027-07-01" and tri["gaps"] == [], tri.get("periods", [])[:1])

    p1 = school_class(A, "PRIMAIRE", "1re A", "P1")
    h1 = school_class(A, "SECONDAIRE", "1re CG", "H1", "CG")
    school_class(A, "SECONDAIRE", "1re CG B", "H1", "CG")
    as_(prefet).post("/api/v1/pedagogy/class-links/accept-suggestions")
    sem = next(c for c in as_(prefet).get("/api/v1/pedagogy/calendars").json()["calendars"] if c["structure"] == "SEMESTRIEL")
    periods = [{"code": p["code"], "starts_on": p["starts_on"], "ends_on": p["ends_on"]} for p in sem["periods"]]
    bad = [dict(p, ends_on="2027-08-15") if p["code"] == "EX2" else p for p in periods]
    r = as_(prefet).put("/api/v1/pedagogy/calendars/SEMESTRIEL", json={"periods": bad})
    check("date hors de l'année scolaire refusée, message clair", r.status_code == 422 and "en dehors de l’année scolaire" in r.text, r.text[:160])
    overlap = [dict(p, starts_on=periods[0]["ends_on"]) if p["code"] == "P2" else p for p in periods]
    check("chevauchement refusé", as_(prefet).put("/api/v1/pedagogy/calendars/SEMESTRIEL", json={"periods": overlap}).status_code == 422)
    holiday = [dict(p, starts_on="2027-02-15") if p["code"] == "P3" else p for p in periods]
    r = as_(prefet).put("/api/v1/pedagogy/calendars/SEMESTRIEL", json={"periods": holiday})
    saved = r.json() if r.status_code == 200 else {}
    check("calendrier enregistré ; vacances visibles (jours non couverts), jamais bloquantes",
          r.status_code == 200 and saved["saved"] and saved["status"] == "DRAFT" and len(saved["gaps"]) == 1, r.text[:200])
    check("le caissier ne prépare pas le calendrier",
          as_(actor_for("CAISSIER", A["id"])).put("/api/v1/pedagogy/calendars/SEMESTRIEL", json={"periods": periods}).status_code == 403)
    r = as_(prefet).post("/api/v1/pedagogy/calendars/SEMESTRIEL/validate")
    check("le préfet valide le calendrier", r.status_code == 200 and r.json()["status"] == "VALIDATED", r.text[:160])
    de = actor_for("DIRECTEUR_ETUDES", A["id"])
    check("le directeur des études peut aussi valider", as_(de).post("/api/v1/pedagogy/calendars/SEMESTRIEL/validate").status_code == 200)
    r = as_(prefet).put("/api/v1/pedagogy/calendars/SEMESTRIEL", json={"periods": periods})
    check("modifier un calendrier validé exige un motif", r.status_code == 409 and "motif" in r.text, r.text[:160])
    r = as_(prefet).put("/api/v1/pedagogy/calendars/SEMESTRIEL", json={"periods": periods, "reason": "Vacances déplacées par la province"})
    check("avec motif : modification acceptée, calendrier toujours validé", r.status_code == 200 and r.json()["status"] == "VALIDATED" and r.json()["gaps"] == [])
    r = as_(prefet).post("/api/v1/pedagogy/calendars/SEMESTRIEL/periods/P1/close")
    p1_state = next(p for p in r.json()["periods"] if p["code"] == "P1") if r.status_code == 200 else {}
    check("saisie de la 1re période clôturée", p1_state.get("entry_state") == "CLOSED" and not p1_state.get("entry_allowed"), p1_state)
    check("réouverture sans motif refusée", as_(prefet).post("/api/v1/pedagogy/calendars/SEMESTRIEL/periods/P1/reopen", json={}).status_code == 422)
    r = as_(prefet).post("/api/v1/pedagogy/calendars/SEMESTRIEL/periods/P1/reopen", json={"reason": "Cotes oubliées de 2 élèves"})
    check("réouverture avec motif", r.status_code == 200 and next(p for p in r.json()["periods"] if p["code"] == "P1")["entry_closed_at"] is None)
    audits = dict(sql("SELECT action,count(*) FROM audit_events WHERE school_id=:s AND action LIKE 'PEDAGOGY_%' AND entity_type='PedagogyCalendar' GROUP BY 1", s=A["id"]).all())
    check("journal : enregistrements, validations, clôture, réouverture",
          audits.get("PEDAGOGY_CALENDAR_SAVED") == 2 and audits.get("PEDAGOGY_CALENDAR_VALIDATED") == 1 and audits.get("PEDAGOGY_ENTRY_CLOSED") == 1
          and audits.get("PEDAGOGY_ENTRY_REOPENED") == 1, audits)

    r = as_(prefet).get("/api/v1/pedagogy/programmes")
    data = r.json() if r.status_code == 200 else {}
    codes = {i["ref_class_code"]: i for i in data.get("items", [])}
    check("programmes : une ligne par classe officielle utilisée (1PR, 1CG), classes de l'école listées",
          set(codes) == {"1PR", "1CG"} and len(codes["1CG"]["classes"]) == 2 and data["summary"]["adoptable"] == 2, data.get("summary"))
    r = as_(prefet).post("/api/v1/pedagogy/programmes/adopt-official", json={})
    check("un clic : les programmes officiels deviennent ceux de l'école (validés)", r.status_code == 200 and r.json()["adopted"] == 2, r.text[:160])
    check("adopter à nouveau : rien de plus", as_(prefet).post("/api/v1/pedagogy/programmes/adopt-official", json={}).json()["adopted"] == 0)
    in_use = as_(prefet).get("/api/v1/pedagogy/programmes").json()["items"]
    cg = next(i for i in in_use if i["ref_class_code"] == "1CG")
    view = as_(prefet).get(f"/api/v1/pedagogy/programmes/{cg['in_use']['id']}").json()
    check("programme 1CG en service : 18 cours, P1 = 480 points, aucun écart avec l'officiel",
          len(view["lines"]) == 18 and view["totals"]["max_p1"] == 480 and not any(l["modified"] for l in view["lines"]), view.get("totals"))
    r = as_(prefet).put(f"/api/v1/pedagogy/programmes/{cg['in_use']['id']}/lines/DROIT", json={"term_points": [20, 20]})
    check("un programme en service ne se modifie pas directement", r.status_code == 409, r.status_code)

    r = as_(prefet).post("/api/v1/pedagogy/programmes", json={"ref_class_code": "1CG"})
    draft = r.json() if r.status_code == 200 else {}
    check("nouvelle version : brouillon copié du programme en service", draft.get("status") == "DRAFT" and len(draft.get("lines", [])) == 18, r.text[:160])
    did = draft.get("id")
    r = as_(prefet).put(f"/api/v1/pedagogy/programmes/{did}/lines/DROIT", json={"term_points": [20, 30], "has_exam": True})
    droit = next((l for l in r.json()["lines"] if l["course_code"] == "DROIT"), {}) if r.status_code == 200 else {}
    check("un nombre par semestre : 20 et 30 → examens 40 et 60, cours marqué « modifié »",
          [droit.get(k) for k in ("max_p1", "max_p2", "max_ex1", "max_p3", "max_p4", "max_ex2")] == [20, 20, 40, 30, 30, 60] and droit.get("modified"), droit)
    r = as_(prefet).put(f"/api/v1/pedagogy/programmes/{did}/lines/ASTRONOMIE", json={"term_points": [10, 10]})
    check("ajouter un cours qui n'existe pas au référentiel : refusé", r.status_code == 404)
    extra = one("SELECT code FROM ref_courses WHERE code NOT IN (SELECT course_code FROM ref_programme_lines WHERE class_code='1CG') ORDER BY code LIMIT 1")[0]
    r = as_(prefet).put(f"/api/v1/pedagogy/programmes/{did}/lines/{extra}", json={"term_points": [10, 10], "has_exam": False, "mandatory": False})
    added = next((l for l in r.json()["lines"] if l["course_code"] == extra), {}) if r.status_code == 200 else {}
    check("ajouter un cours de l'école (sans examen) : en fin de liste, marqué « ajout de l'école »",
          added.get("source") == "ECOLE" and added.get("max_ex1") == 0 and r.json()["lines"][-1]["course_code"] == extra, r.text[:160])
    check("retirer un cours obligatoire du programme officiel : refusé",
          as_(prefet).delete(f"/api/v1/pedagogy/programmes/{did}/lines/FRANCAIS").status_code == 409)
    check("retirer la religion (facultative) : accepté", as_(prefet).delete(f"/api/v1/pedagogy/programmes/{did}/lines/RELIGION").status_code == 200)
    r = as_(prefet).post(f"/api/v1/pedagogy/programmes/{did}/move", json={"course_code": extra, "direction": "up"})
    check("changer l'ordre : le cours remonte d'un rang", r.status_code == 200 and r.json()["lines"][-2]["course_code"] == extra)
    try:
        with H.ENGINE.begin() as c:
            c.execute(H.text("UPDATE pedagogy_programme_lines SET max_ex1=max_p1 WHERE programme_id=:p AND course_code='DROIT'"), {"p": did})
        refused = False
    except IntegrityError:
        refused = True
    check("la base refuse un examen qui n'est pas le double de la période (programme de l'école)", refused)
    r = as_(prefet).post(f"/api/v1/pedagogy/programmes/{did}/validate")
    check("valider la nouvelle version", r.status_code == 200 and r.json()["status"] == "VALIDATED", r.text[:160])
    st = dict(sql("SELECT status,count(*) FROM pedagogy_programmes WHERE school_id=:s AND ref_class_code='1CG' GROUP BY 1", s=A["id"]).all())
    check("l'ancienne version est archivée, une seule en service", st == {"VALIDATED": 1, "ARCHIVED": 1}, st)

    nop = school_class(A, "MATERNELLE" if "MATERNELLE" in A["sections"] else "PRIMAIRE", "Classe sans programme", None)
    as_(prefet).put(f"/api/v1/pedagogy/class-links/{nop}", json={"ref_class_code": "3NOR"})
    r = as_(prefet).post("/api/v1/pedagogy/programmes/adopt-official", json={})
    check("classe sans programme officiel (3NOR) : rien n'est inventé à l'adoption", r.json()["adopted"] == 0)
    r = as_(prefet).post("/api/v1/pedagogy/programmes", json={"ref_class_code": "3NOR"})
    check("3NOR : brouillon vide pour construire le programme de l'école", r.status_code == 200 and r.json()["lines"] == [] and not r.json()["has_official"], r.text[:120])
    check("valider un programme vide : refusé", as_(prefet).post(f"/api/v1/pedagogy/programmes/{r.json()['id']}/validate").status_code == 409)
    check("abandonner le brouillon", as_(prefet).delete(f"/api/v1/pedagogy/programmes/{r.json()['id']}").status_code == 200)

    ds = actor_for("DIRECTION_SECTION", A["id"], scope=("SECTION", "PRIMAIRE"))
    seen = {i["ref_class_code"] for i in as_(ds).get("/api/v1/pedagogy/programmes").json()["items"]}
    check("directeur de section (primaire) : ne voit que les programmes du primaire", "1PR" in seen and "1CG" not in seen, seen)
    check("directeur de section : n'ouvre pas une version du secondaire",
          as_(ds).post("/api/v1/pedagogy/programmes", json={"ref_class_code": "1CG"}).status_code == 404)
    check("programme d'une autre école : invisible",
          as_(actor_for("PREFET_ETUDES", B["id"])).get(f"/api/v1/pedagogy/programmes/{did}").status_code == 403)
    grant_pedagogy(B["id"])
    check("même avec le module, l'école B ne voit pas le programme de l'école A",
          as_(actor_for("PREFET_ETUDES", B["id"])).get(f"/api/v1/pedagogy/programmes/{did}").status_code == 404)
    check("cours du référentiel : recherche", any(c["code"] == "FRANCAIS" for c in as_(prefet).get("/api/v1/pedagogy/courses?q=fran").json()))


def main() -> int:
    run()
    CLIENT.__exit__(None, None, None)
    fails = [r for r in RESULTS if r[0] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
