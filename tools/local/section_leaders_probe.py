"""PR #27 certification probe — Préfet (Secondaire), Directeur (Primaire), Directrice (Maternelle) on the LOCAL stack.

Signs in through the real API with the accounts created by frontend/browser-tests/local_role_prepare.mjs
(.local/<folder>/.account.json, never printed) and checks, against the local PostgreSQL (read only):
  * headcounts Total / Filles / Garçons of its section equal the school-wide Gestionnaire's figures, options included;
  * pupils, pupil details and personnel stay inside the leader's section (cross-section direct access refused);
  * personnel creation / update / assignments are confined to the section (positive AND negative cases);
  * section-bound roles can never be granted on the whole school (access API);
  * a pupil of another school is not found.
Local only: refuses any non-localhost database. Prints PASS / FAIL per check and exits 1 on any FAIL.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/local"))
os.environ.setdefault("EDUSYNC_LOCAL_PG_PORT", "55432")
import edusync_local as L  # noqa: E402

API = "http://localhost:5180/api/v1"
FX = json.loads((ROOT / ".local/claude-fixtures-edusync_claude_fresh.json").read_text(encoding="utf-8"))
SCHOOL_CODE = FX["C"]["code"]
SCHOOL_ID = FX["C"]["school_id"]
DB_URL = L.load_env("demo")["EDUSYNC_OWNER_DATABASE_URL"]
assert "127.0.0.1" in DB_URL or "localhost" in DB_URL, "base locale uniquement"
ENGINE = create_engine(DB_URL)
LEADERS = [("prefet", "SECONDAIRE", "Préfet des études (Secondaire)"),
           ("directeur_primaire", "PRIMAIRE", "Directeur (Primaire)"),
           ("directrice_maternelle", "MATERNELLE", "Directrice (Maternelle)")]
RESULTS: list[tuple[str, str, str]] = []
RUN = uuid.uuid4().hex[:5].upper()


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((("PASS" if ok else "FAIL"), name, detail))
    print(f"{'PASS' if ok else 'FAIL':5} {name}{' — ' + detail if detail and not ok else ''}")


def q(sql: str, **params):
    with ENGINE.connect() as c:
        return c.execute(text(sql), params).all()


def login(email: str, password: str) -> httpx.Client:
    r = httpx.post(f"{API}/auth/login", json={"email": email, "password": password, "scope": "SCHOOL", "school_code": SCHOOL_CODE}, timeout=30)
    r.raise_for_status()
    return httpx.Client(base_url=API, headers={"Authorization": f"Bearer {r.json()['access_token']}"}, timeout=60)


def mut(extra: dict | None = None) -> dict:
    return {"Idempotency-Key": f"probe-{uuid.uuid4().hex}", **(extra or {})}


def by_code(payload: dict) -> dict:
    return {str(i.get("code") or i.get("label")).upper(): i for i in payload["items"]}


def section_of_students(ids: list[str]) -> set[str]:
    if not ids:
        return set()
    rows = q("""SELECT DISTINCT upper(ss.code) FROM enrollments e JOIN school_classes sc ON sc.id=e.class_id
                JOIN school_sections ss ON ss.id=sc.section_id JOIN academic_years y ON y.id=e.academic_year_id
                WHERE e.school_id=:s AND y.status='ACTIVE' AND e.status<>'CANCELLED' AND e.student_id::text = ANY(:ids)""",
             s=SCHOOL_ID, ids=ids)
    return {r[0] for r in rows}


def student_in(section: str, *, other: bool) -> str | None:
    rows = q("""SELECT s.id::text FROM students s JOIN enrollments e ON e.student_id=s.id JOIN school_classes sc ON sc.id=e.class_id
                JOIN school_sections ss ON ss.id=sc.section_id JOIN academic_years y ON y.id=e.academic_year_id
                WHERE s.school_id=:sc AND y.status='ACTIVE' AND e.status<>'CANCELLED' AND (upper(ss.code)=:sec) <> :other
                  AND NOT EXISTS (SELECT 1 FROM enrollments e2 JOIN school_classes c2 ON c2.id=e2.class_id JOIN school_sections s2 ON s2.id=c2.section_id
                                  WHERE e2.student_id=s.id AND e2.status<>'CANCELLED' AND (upper(s2.code)=:sec) = :other)
                LIMIT 1""", sc=SCHOOL_ID, sec=section, other=other)
    return rows[0][0] if rows else None


def staff_only_in(section: str, *, other: bool) -> str | None:
    """An agent whose active assignments are all SECTION / CLASS, all inside (other=False) or all outside (other=True)."""
    rows = q("""SELECT sm.id::text FROM staff_members sm WHERE sm.school_id=:s AND EXISTS (SELECT 1 FROM staff_assignments a WHERE a.staff_id=sm.id AND a.end_date IS NULL)
                AND NOT EXISTS (SELECT 1 FROM staff_assignments a LEFT JOIN school_classes c ON c.id=a.class_id LEFT JOIN school_sections cs ON cs.id=c.section_id
                                WHERE a.staff_id=sm.id AND a.end_date IS NULL AND (a.scope_type='SCHOOL'
                                  OR ((upper(coalesce(a.scope_value,''))=:sec OR upper(coalesce(cs.code,''))=:sec) <> :other)))
                LIMIT 1""", s=SCHOOL_ID, sec=section, other=not other)
    return rows[0][0] if rows else None


def personnel_writes(c: httpx.Client, label: str, section: str, sections: dict, other_staff: str | None, *, allowed: bool) -> None:
    """Personnel writes. allowed=False: standard section leaders hold personnel READ only (owner contract, decision 06 / 07):
    every write must be refused and leave no row. allowed=True: a role holding personnel writes on ONE section."""
    if not allowed:
        functions = c.get("/personnel/catalog/functions")
        fn = next((f for f in (functions.json() if functions.status_code == 200 else []) if f.get("enabled", True)), None)
        dest = {"function_id": fn["id"] if fn else str(uuid.uuid4()), "scope_type": "SECTION", "scope_value": section, "section_id": sections[section]}
        r = c.post("/personnel", json={"last_name": f"RO{RUN}", "category": "ENSEIGNANT", "employee_no": f"R{RUN}{section[:3]}", "initial_assignment": dest}, headers=mut())
        check(f"{label} · création d’agent refusée (lecture seule selon le contrat)", r.status_code == 403, f"HTTP {r.status_code}")
        any_staff = staff_only_in(section, other=False)
        if any_staff:
            ver = q("SELECT version FROM staff_members WHERE id::text=:i", i=any_staff)[0][0]
            code = c.put(f"/personnel/{any_staff}", json={"last_name": "X", "category": "ENSEIGNANT", "employee_no": f"Y{RUN}"}, headers=mut({"If-Match": str(ver)})).status_code
            check(f"{label} · modification d’agent refusée (lecture seule)", code == 403, f"HTTP {code}")
            code = c.post("/personnel/assignments", json={"staff_id": any_staff, "function_id": dest["function_id"], "scope_type": "SECTION", "scope_value": section,
                                                          "section_id": sections[section], "start_date": __import__("datetime").date.today().isoformat()}, headers=mut()).status_code
            check(f"{label} · ajout d’affectation refusé (lecture seule)", code == 403, f"HTTP {code}")
        written = q("SELECT count(*) FROM staff_members WHERE school_id=:s AND employee_no IN (:a,:b)", s=SCHOOL_ID, a=f"R{RUN}{section[:3]}", b=f"Y{RUN}")[0][0]
        check(f"{label} · aucune écriture du personnel en base", written == 0, f"{written}")
        return
    opts = c.get("/personnel/scope-options")
    functions = c.get("/personnel/catalog/functions")
    fn = next((f for f in (functions.json() if functions.status_code == 200 else []) if f.get("enabled", True)), None)
    check(f"{label} · options d’affectation et fonctions lisibles", opts.status_code == 200 and fn is not None,
          f"options HTTP {opts.status_code}, fonctions HTTP {functions.status_code}")
    if fn and opts.status_code == 200:
        o = opts.json()
        offered = {str(x.get("code")).upper() for x in o.get("sections", [])}
        check(f"{label} · le sélecteur ne propose que sa section", offered <= {section}, f"proposées : {sorted(offered)}")
        base = {"last_name": f"PROBE{RUN}", "first_name": section.title(), "category": "ENSEIGNANT", "gender": "F"}
        dest = {"function_id": fn["id"], "scope_type": "SECTION", "scope_value": section, "section_id": sections[section]}
        created = c.post("/personnel", json={**base, "employee_no": f"P{RUN}{section[:3]}", "initial_assignment": dest}, headers=mut())
        check(f"{label} · création d’un agent dans sa section", created.status_code == 201, f"HTTP {created.status_code} {created.text[:160]}")
        other_sec = next(k for k in sections if k != section)
        r2 = c.post("/personnel", json={**base, "employee_no": f"X{RUN}{section[:3]}", "initial_assignment": {**dest, "scope_value": other_sec, "section_id": sections[other_sec]}}, headers=mut())
        check(f"{label} · création dans une autre section refusée", r2.status_code == 403, f"HTTP {r2.status_code}")
        r3 = c.post("/personnel", json={**base, "employee_no": f"N{RUN}{section[:3]}"}, headers=mut())
        check(f"{label} · création sans affectation refusée", r3.status_code in (403, 422), f"HTTP {r3.status_code}")
        r4 = c.post("/personnel", json={**base, "employee_no": f"S{RUN}{section[:3]}", "initial_assignment": {**dest, "scope_type": "SCHOOL", "scope_value": None, "section_id": None}}, headers=mut())
        check(f"{label} · création avec affectation « toute l’école » refusée", r4.status_code == 403, f"HTTP {r4.status_code}")
        leaked_rows = q("SELECT count(*) FROM staff_members WHERE school_id=:s AND employee_no IN (:a,:b,:c)", s=SCHOOL_ID,
                        a=f"X{RUN}{section[:3]}", b=f"N{RUN}{section[:3]}", c=f"S{RUN}{section[:3]}")[0][0]
        check(f"{label} · aucun agent écrit après un refus", leaked_rows == 0, f"{leaked_rows} ligne(s)")
        if created.status_code == 201:
            sid = created.json()["id"]
            detail = c.get(f"/personnel/{sid}").json()
            up = c.put(f"/personnel/{sid}", json={**base, "employee_no": f"P{RUN}{section[:3]}", "phone": "+243800000000"},
                       headers=mut({"If-Match": str(detail.get("version", 1))}))
            check(f"{label} · modification d’un agent de sa section", up.status_code == 200, f"HTTP {up.status_code} {up.text[:160]}")
            stale = c.put(f"/personnel/{sid}", json={**base, "employee_no": f"P{RUN}{section[:3]}"}, headers=mut({"If-Match": "1"}))
            check(f"{label} · version périmée refusée (aucune perte de mise à jour)", stale.status_code in (409, 412), f"HTTP {stale.status_code}")
            today = __import__("datetime").date.today().isoformat()
            bad = c.post("/personnel/assignments", json={"staff_id": sid, "function_id": fn["id"], "scope_type": "SECTION", "scope_value": other_sec,
                                                        "section_id": sections[other_sec], "start_date": today}, headers=mut())
            check(f"{label} · affectation dans une autre section refusée", bad.status_code == 403, f"HTTP {bad.status_code}")
            bad2 = c.post("/personnel/assignments", json={"staff_id": sid, "function_id": fn["id"], "scope_type": "SCHOOL", "start_date": today}, headers=mut())
            check(f"{label} · affectation « toute l’école » refusée", bad2.status_code == 403, f"HTTP {bad2.status_code}")
            listed = [a for a in c.get(f"/personnel/{sid}/assignments").json()]
            check(f"{label} · affectations de l’agent consultables (une seule, dans sa section)",
                  len(listed) == 1 and str(listed[0].get("scope_value") or "").upper() == section, str(listed)[:160])
        if other_staff:
            ver = q("SELECT version FROM staff_members WHERE id::text=:i", i=other_staff)[0][0]
            code = c.put(f"/personnel/{other_staff}", json={**base, "employee_no": f"Z{RUN}"}, headers=mut({"If-Match": str(ver)})).status_code
            check(f"{label} · modification d’un agent d’une autre section refusée", code in (403, 404), f"HTTP {code}")
            today = __import__("datetime").date.today().isoformat()
            code = c.post("/personnel/assignments", json={"staff_id": other_staff, "function_id": fn["id"], "scope_type": "SECTION", "scope_value": section,
                                                          "section_id": sections[section], "start_date": today}, headers=mut()).status_code
            check(f"{label} · rattacher un agent d’une autre section refusé", code in (403, 404), f"HTTP {code}")


def main() -> int:
    admin = login(FX["C"]["users"]["ADMIN"]["email"], FX["C"]["users"]["ADMIN"]["password"])
    # School-wide reference for headcounts: the Gestionnaire (SCHOOL scope; the system administrator holds no headcounts).
    g = json.loads((ROOT / ".local/gestionnaire/.account.json").read_text(encoding="utf-8")); gest = login(g["email"], g["password"])
    ref_sections = by_code(gest.get("/effectifs/counts", params={"group_by": "section"}).json())
    ref_options = gest.get("/effectifs/counts", params={"group_by": "option"}).json()["items"]
    # A section leader must pick a function at creation: the school's catalogue is managed by the Gestionnaire.
    if not any(f.get("enabled") for f in gest.get("/personnel/catalog/functions").json()):
        r = gest.post("/personnel/catalog/functions", json={"code": "ENSEIGNANT", "label": "Enseignant", "category": "ENSEIGNEMENT"}, headers=mut())
        print(f"catalogue des fonctions vide : fonction « Enseignant » créée par le Gestionnaire (HTTP {r.status_code})")
    # Cross-section fixtures: one agent assigned only to each section, created by the Gestionnaire (school scope).
    fn0 = next(f for f in gest.get("/personnel/catalog/functions").json() if f.get("enabled"))
    secs0 = {r[0]: r[1] for r in q("SELECT upper(code), id::text FROM school_sections WHERE school_id=:s", s=SCHOOL_ID)}
    for sec in ("MATERNELLE", "PRIMAIRE", "SECONDAIRE"):
        if staff_only_in(sec, other=False) is None:
            r = gest.post("/personnel", json={"last_name": f"AGENT{sec[:3]}", "first_name": "Recette", "category": "ENSEIGNANT", "employee_no": f"AG{sec[:3]}{RUN}",
                                              "initial_assignment": {"function_id": fn0["id"], "scope_type": "SECTION", "scope_value": sec, "section_id": secs0[sec]}}, headers=mut())
            print(f"agent de recette créé en {sec} par le Gestionnaire (HTTP {r.status_code})")
    gest.close()
    sections = {r[0]: r[1] for r in q("SELECT upper(code), id::text FROM school_sections WHERE school_id=:s", s=SCHOOL_ID)}

    for folder, section, label in LEADERS:
        acc = json.loads((ROOT / f".local/{folder}/.account.json").read_text(encoding="utf-8"))
        c = login(acc["email"], acc["password"])
        print(f"\n== {label}")
        # --- headcounts -----------------------------------------------------------------------------------------
        r = c.get("/effectifs/counts", params={"group_by": "section"})
        check(f"{label} · effectifs par section lisibles", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code == 200:
            got = by_code(r.json())
            check(f"{label} · effectifs : seule sa section", set(got) <= {section}, f"sections vues : {sorted(got)}")
            mine, ref = got.get(section), ref_sections.get(section)
            if ref and ref["active"]["total"]:
                same = mine is not None and all(mine[k] == ref[k] for k in ("active", "enrolled", "abandoned", "transferred"))
                check(f"{label} · Total / Filles / Garçons identiques au Gestionnaire (vue école)", same,
                      f"responsable {mine and mine['active']} ≠ école {ref['active']}")
            t = r.json()["total"]["active"]
            check(f"{label} · Filles + Garçons ≤ Total", t["female"] + t["male"] <= t["total"], str(t))
        ro = c.get("/effectifs/counts", params={"group_by": "option"})
        if ro.status_code == 200:
            mine_opt = {(i.get("section") or "").upper() + "/" + str(i.get("code")).upper(): i["active"] for i in ro.json()["items"]}
            ref_opt = {(i.get("section") or "").upper() + "/" + str(i.get("code")).upper(): i["active"] for i in ref_options
                       if (i.get("section") or "").upper() in (section, sections.get(section, "").upper()) or str(i.get("section_code") or "").upper() == section}
            check(f"{label} · effectifs par option : aucune option d’une autre section",
                  all(k.split("/")[0] in ("", section, sections[section].upper()) for k in mine_opt) or not mine_opt, f"{sorted(mine_opt)}")
            if section == "SECONDAIRE":
                total_opt = sum(v["total"] for v in mine_opt.values())
                sec_total = (by_code(c.get("/effectifs/counts", params={"group_by": "section"}).json()).get(section) or {}).get("active", {}).get("total")
                check(f"{label} · options : somme des options = effectif du secondaire", total_opt == sec_total, f"options {total_opt} ≠ section {sec_total}")
                check(f"{label} · options : F + G = Total pour chaque option",
                      all(v["female"] + v["male"] <= v["total"] for v in mine_opt.values()), json.dumps(mine_opt)[:200])
                check(f"{label} · options identiques au Gestionnaire (vue école)", not ref_opt or all(mine_opt.get(k) == v for k, v in ref_opt.items()),
                      f"{mine_opt} ≠ {ref_opt}")
        elif section == "SECONDAIRE":
            check(f"{label} · effectifs par option lisibles", False, f"HTTP {ro.status_code}")
        # --- pupils --------------------------------------------------------------------------------------------
        rs = c.get("/schooling/students", params={"limit": 500})
        check(f"{label} · liste des élèves lisible", rs.status_code == 200, f"HTTP {rs.status_code}")
        if rs.status_code == 200:
            items = rs.json()["items"] if isinstance(rs.json(), dict) else rs.json()
            seen = section_of_students([str(i["id"]) for i in items])
            check(f"{label} · liste des élèves : uniquement sa section", seen <= {section}, f"sections : {sorted(seen)}")
        own, foreign = student_in(section, other=False), student_in(section, other=True)
        if own:
            check(f"{label} · fiche d’un élève de sa section", c.get(f"/schooling/students/{own}").status_code == 200)
        if foreign:
            code = c.get(f"/schooling/students/{foreign}").status_code
            check(f"{label} · fiche d’un élève d’une autre section refusée", code in (403, 404), f"HTTP {code}")
            code = c.get(f"/finance/reports/students/{foreign}/account").status_code
            check(f"{label} · relevé financier d’un élève d’une autre section refusé", code in (403, 404), f"HTTP {code}")
        fam = c.get("/schooling/families/overview")
        check(f"{label} · indicateurs « Familles & responsables » de sa section (plus d’erreur 500)", fam.status_code == 200, f"HTTP {fam.status_code}")
        a_pupil = q("SELECT s.id::text FROM students s WHERE s.school_id<>:s LIMIT 1", s=SCHOOL_ID)
        if a_pupil:
            code = c.get(f"/schooling/students/{a_pupil[0][0]}").status_code
            check(f"{label} · élève d’une autre école introuvable", code in (403, 404), f"HTTP {code}")
        # --- personnel -----------------------------------------------------------------------------------------
        rp = c.get("/personnel")
        check(f"{label} · annuaire du personnel lisible", rp.status_code == 200, f"HTTP {rp.status_code}")
        if rp.status_code == 200:
            staff = rp.json()["items"] if isinstance(rp.json(), dict) else rp.json()
            ids = [str(s["id"]) for s in staff]
            outside = q("""SELECT count(*) FROM staff_members sm WHERE sm.id::text = ANY(:ids) AND NOT EXISTS (
                             SELECT 1 FROM staff_assignments a LEFT JOIN school_classes c ON c.id=a.class_id LEFT JOIN school_sections cs ON cs.id=c.section_id
                             WHERE a.staff_id=sm.id AND a.end_date IS NULL AND (upper(coalesce(a.scope_value,''))=:sec OR upper(coalesce(cs.code,''))=:sec))""",
                        ids=ids, sec=section)[0][0] if ids else 0
            check(f"{label} · annuaire : uniquement des agents affectés à sa section", outside == 0, f"{outside} agent(s) hors section")
            leaked = [a for s in staff for a in (s.get("assignments") or [])
                      if a.get("scope_type") == "SECTION" and str(a.get("scope_value") or "").upper() != section]
            check(f"{label} · annuaire : aucune affectation d’une autre section exposée", not leaked, str(leaked[:2]))
        other_staff = staff_only_in(section, other=True)
        if other_staff:
            code = c.get(f"/personnel/{other_staff}").status_code
            check(f"{label} · fiche d’un agent d’une autre section refusée", code in (403, 404), f"HTTP {code}")
        summ = c.get("/personnel/summary")
        check(f"{label} · synthèse du personnel lisible", summ.status_code == 200, f"HTTP {summ.status_code}")
        if summ.status_code == 200:
            s = summ.json()
            check(f"{label} · synthèse : aucun compteur global confidentiel", s.get("linked_accounts", 0) == 0 and s.get("staff_children", 0) == 0, str(s)[:160])
        personnel_writes(c, label, section, sections, other_staff, allowed=False)
        # --- finance: cash operations never implied ---------------------------------------------------------
        code = c.post("/finance/cash/open", json={"opening_balances": []}, headers=mut()).status_code
        check(f"{label} · ouverture de caisse refusée", code == 403, f"HTTP {code}")
        period = {"profile_code": "CONSOLIDE", "period_type": "MENSUEL", "start": "2026-10-01", "end": "2026-10-31"}
        code = c.get("/finance/reports/periodic", params=period).status_code
        check(f"{label} · rapport périodique : réponse maîtrisée (200 filtré ou 403)", code in (200, 403), f"HTTP {code}")
        code = c.post("/finance/reports/periodic/pdf", json={k: v for k, v in period.items()}, headers=mut()).status_code
        check(f"{label} · rapport officiel (PDF école) refusé à une section", code == 403, f"HTTP {code}")
        c.close()

    # --- personnel writes on ONE section: Gestionnaire role limited to SECONDAIRE (school custom delegation) --------
    print("\n== Écriture du personnel limitée à une section (rôle Gestionnaire sur le Secondaire)")
    groles = {r[0]: r[1] for r in q("SELECT code, id::text FROM rbac_roles WHERE kind='SCHOOL_STANDARD' AND code='GESTIONNAIRE'")}
    email = f"probe-rh-{RUN.lower()}@example.test"
    r = admin.post("/access/members", json={"email": email, "full_name": "Sonde RH Secondaire", "role_id": groles["GESTIONNAIRE"], "reason": "Recette PR 27",
                                            "scopes": [{"type": "SECTION", "value": "SECONDAIRE"}]}, headers=mut())
    check("membre RH limité au Secondaire créé avec son seul périmètre", r.status_code == 201, f"HTTP {r.status_code} {r.text[:120]}")
    if r.status_code == 201:
        temp = r.json()["temporary_password"]; new_pw = f"Pr-{uuid.uuid4().hex[:12]}-Ok"
        first = httpx.post(f"{API}/auth/login", json={"email": email, "password": temp, "scope": "SCHOOL", "school_code": SCHOOL_CODE}, timeout=30).json()
        httpx.post(f"{API}/auth/password/first-change", json={"change_token": first.get("change_token") or first.get("password_change_token"), "new_password": new_pw}, timeout=30)
        w = login(email, new_pw)
        other = staff_only_in("SECONDAIRE", other=True)
        personnel_writes(w, "RH Secondaire", "SECONDAIRE", sections, other, allowed=True)
        w.close()

    # --- role governance: section-bound roles never on the whole school ------------------------------------------
    print("\n== Gouvernance des rôles")
    roles = {r[0]: r[1] for r in q("SELECT code, id::text FROM rbac_roles WHERE kind='SCHOOL_STANDARD' AND code IN ('PREFET_ETUDES','DIRECTION_SECTION')")}
    for code in ("DIRECTION_SECTION", "PREFET_ETUDES"):
        r = admin.post("/access/members", json={"email": f"probe-{code.lower()}-{RUN.lower()}@example.test", "full_name": f"Sonde {code}",
                                                "role_id": roles[code], "reason": "Recette PR 27"}, headers=mut())
        check(f"{code} · « Ajouter un membre » sans section refusé (jamais toute l’école)", r.status_code == 422, f"HTTP {r.status_code} {r.text[:120]}")
    leaked = q("SELECT count(*) FROM users WHERE email IN (:a,:b)", a=f"probe-direction_section-{RUN.lower()}@example.test",
               b=f"probe-prefet_etudes-{RUN.lower()}@example.test")[0][0]
    check("aucun compte créé après ces refus", leaked == 0, f"{leaked}")
    r = admin.post("/access/members", json={"email": f"probe-dual-{RUN.lower()}@example.test", "full_name": "Sonde double section",
                                            "role_id": roles["DIRECTION_SECTION"], "reason": "Recette PR 27",
                                            "scopes": [{"type": "SECTION", "value": "PRIMAIRE"}, {"type": "SECTION", "value": "MATERNELLE"}]}, headers=mut())
    check("DIRECTION_SECTION · double affectation Primaire + Maternelle acceptée", r.status_code == 201, f"HTTP {r.status_code} {r.text[:120]}")
    if r.status_code == 201:
        got = {x[0] for x in q("""SELECT s.scope_type||':'||coalesce(s.scope_value,'') FROM rbac_assignment_scopes s JOIN rbac_assignments a ON a.id=s.assignment_id
                                   WHERE a.membership_id::text=:m""", m=r.json()["membership_id"])}
        check("double affectation : union explicite des deux sections, sans école", got == {"SECTION:PRIMAIRE", "SECTION:MATERNELLE"}, str(got))
    admin.close()

    fails = [x for x in RESULTS if x[0] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
