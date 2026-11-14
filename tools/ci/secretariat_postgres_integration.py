"""Certification Secrétariat — real HTTP + real PostgreSQL (2026-10-31).

Reuses the harness of tools/ci/three_roles_postgres_integration.py (REAL application in-process, tenant role with RLS,
real transactions, idempotency registry, object storage, actors built from the canonical registry). The Caissier holds
every Secrétariat capability (owner decision 2026-10-24) and is certified; this run proves the Secrétariat ALONE, without
any financial right: what it reads, prints, exports, completes and imports — and everything else refused, nothing written.

    python tools/local/isolated_db.py create edusync_cert_secretariat
    python tools/local/isolated_db.py env edusync_cert_secretariat -- ../.venv/Scripts/python.exe ../tools/ci/secretariat_postgres_integration.py

Refuses any non-localhost database and requires CI=true. Prints PASS / FAIL per check, exits 1 on any FAIL.
"""
from __future__ import annotations

import io
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from openpyxl import load_workbook  # noqa: E402

import three_roles_postgres_integration as H  # noqa: E402  (asserts CI + localhost, builds the app)
from three_roles_postgres_integration import actor_for, as_, check, key, one, school  # noqa: E402

ROLE = "SECRETARIAT"
REG_CAPS = set(H.REG["standard_roles"][ROLE]["capabilities"])


def is_pdf(r) -> bool:
    return r.status_code == 200 and r.content[:4] == b"%PDF"


def is_xlsx(r) -> bool:
    return r.status_code == 200 and r.content[:2] == b"PK"


def registry(A: dict) -> None:
    print("\n== Registre : périmètre du rôle")
    money = sorted(c for c in REG_CAPS if c.startswith(("finance.", "cash.")))
    check("aucun droit financier (le Caissier, lui, encaisse)", not money, money)
    check("aucun droit d'inscription ni de réinscription (couverts par le Caissier)", not REG_CAPS & {"enrollments.create", "enrollments.reenroll"})
    check("aucun droit d'envoi de message (le Secrétariat prépare les modèles)", not any(c.startswith("communications.send.") or c.startswith("communications.sms.") for c in REG_CAPS))
    check("le Caissier détient tous les droits du Secrétariat (décision du 24/10)", REG_CAPS <= set(H.REG["standard_roles"]["CAISSIER"]["capabilities"]))


def reads(A: dict) -> None:
    print("\n== Lectures (200)")
    c = as_(actor_for(ROLE, A["id"]))
    pupil, fam, y = A["pupils"]["SECONDAIRE"], A["families"]["SECONDAIRE"], A["year"]
    for label, path in [("annuaire des élèves", "/api/v1/schooling/students?limit=20"), ("fiche élève", f"/api/v1/schooling/students/{pupil}"),
                        ("familles", "/api/v1/schooling/families"), ("fiche famille", f"/api/v1/schooling/families/{fam}"),
                        ("vue des familles", "/api/v1/schooling/families/overview"),
                        ("effectifs par classe", f"/api/v1/effectifs/counts?group_by=class&scope=ALL&year_id={y}"),
                        ("effectifs par section", f"/api/v1/effectifs/counts?group_by=section&scope=ALL&year_id={y}"),
                        ("identité de l'école", "/api/v1/settings/overview"), ("années scolaires", "/api/v1/settings/academic-years/selector"),
                        ("classes", "/api/v1/settings/classes/selector"), ("réglages des documents", "/api/v1/settings/document-settings"),
                        ("historique des documents", "/api/v1/documents/history"), ("personnel", "/api/v1/personnel"),
                        ("modèles de messages", "/api/v1/communications/templates"), ("historique des messages", "/api/v1/communications/history"),
                        ("lots d'import d'élèves", "/api/v1/import/students/batches"), ("contrats d'import", "/api/v1/import/contracts"),
                        ("notifications", "/api/v1/notifications/inbox")]:
        code = c.get(path).status_code
        check(f"{ROLE} : lecture {label}", code == 200, f"HTTP {code} {path}")


def exports(A: dict) -> None:
    print("\n== Impressions et exports (fichiers réels)")
    c = as_(actor_for(ROLE, A["id"]))
    y, pupil = A["year"], A["pupils"]["SECONDAIRE"]
    check("annuaire des élèves PDF", is_pdf(c.get("/api/v1/schooling/exports/students.pdf")))
    check("annuaire des élèves Excel", is_xlsx(c.get("/api/v1/schooling/exports/students.xlsx")))
    check("annuaire des familles PDF", is_pdf(c.get("/api/v1/schooling/exports/families.pdf")))
    check("annuaire des familles Excel", is_xlsx(c.get("/api/v1/schooling/exports/families.xlsx")))
    check("fiche élève PDF", is_pdf(c.get(f"/api/v1/schooling/students/{pupil}/profile.pdf")))
    for g in ("class", "section"):
        check(f"effectifs par {g} PDF", is_pdf(c.get(f"/api/v1/effectifs/exports/counts.pdf?group_by={g}&scope=ALL&year_id={y}")))
        check(f"effectifs par {g} Excel", is_xlsx(c.get(f"/api/v1/effectifs/exports/counts.xlsx?group_by={g}&scope=ALL&year_id={y}")))
        check(f"effectifs par {g} impression", is_pdf(c.get(f"/api/v1/effectifs/print/counts.pdf?group_by={g}&scope=ALL&year_id={y}")))
    check("modèle officiel d'import des élèves", is_xlsx(c.get("/api/v1/documents/student-import-template.xlsx")))
    code = c.get(f"/api/v1/effectifs/exports/counts.pdf?group_by=option&scope=ALL&year_id={y}").status_code
    check("effectifs par option (droit non détenu) → 403", code == 403, code)
    noexp = as_(actor_for(ROLE, A["id"], drop={"students.directory.export", "students.directory.export_xlsx", "students.directory.print_pdf"}))
    check("droit d'export retiré par l'école → 403", noexp.get("/api/v1/schooling/exports/students.xlsx").status_code == 403)


def student_profile(A: dict) -> None:
    print("\n== Fiche élève : compléter oui, corriger l'identité non")
    c = as_(actor_for(ROLE, A["id"]))
    pupil = A["pupils"]["SECONDAIRE"]
    ver = one("SELECT version FROM students WHERE id=:i", i=pupil)[0]
    r = c.patch(f"/api/v1/schooling/students/{pupil}", json={"address": "Avenue du Secrétariat 12", "birth_place": "Lubumbashi"}, headers={**key(), "If-Match": str(ver)})
    check("profil complété (adresse, lieu de naissance) + audit", r.status_code == 200 and one("SELECT address FROM students WHERE id=:i", i=pupil)[0] == "Avenue du Secrétariat 12"
          and one("SELECT count(*) FROM audit_events WHERE entity_id=:i AND action='STUDENT_PROFILE_UPDATED'", i=pupil)[0] >= 1, r.text[:150])
    check("même version rejouée → 409 (modification concurrente détectée)",
          c.patch(f"/api/v1/schooling/students/{pupil}", json={"address": "Autre"}, headers={**key(), "If-Match": str(ver)}).status_code == 409)
    ver = one("SELECT version FROM students WHERE id=:i", i=pupil)[0]
    r = c.patch(f"/api/v1/schooling/students/{pupil}", json={"first_name": "Renomme"}, headers={**key(), "If-Match": str(ver)})
    check("correction d'identité (nom, prénom) refusée → 403, rien écrit", r.status_code == 403 and one("SELECT first_name FROM students WHERE id=:i", i=pupil)[0] != "Renomme", r.status_code)


def files_to_complete(A: dict) -> None:
    print("\n== Dossiers élèves à compléter (accueil du Secrétariat)")
    c = as_(actor_for(ROLE, A["id"]))
    q = "SELECT count(*) FROM students WHERE school_id=:s AND status='ACTIVE' AND profile_completeness<80"
    s = c.get("/api/v1/schooling/summary")
    check("le serveur compte les dossiers incomplets sur toute l'école (= comptage direct en base)",
          s.status_code == 200 and s.json().get("profiles_to_complete") == one(q, s=A["id"])[0], s.text[:150])
    from edusync.modules.access.application.projection import WIDGETS
    w = next(x for x in WIDGETS if x["id"] == "students.files")
    check("carte « Dossiers élèves à compléter » accordée au Secrétariat, pas à l'Intendant",
          set(w["all"]) <= REG_CAPS and not set(w["all"]) <= set(H.REG["standard_roles"]["INTENDANT"]["capabilities"]))


def personnel(A: dict) -> None:
    print("\n== Personnel : créer et modifier oui, suspendre non")
    c = as_(actor_for(ROLE, A["id"]))
    emp = f"SEC{H.RUN}"
    r = c.post("/api/v1/personnel", json={"employee_no": emp, "last_name": "MWAMBA", "first_name": "Grace", "category": "ADMINISTRATIF", "gender": "F"}, headers=key())
    check("agent créé (201) + audit", r.status_code == 201, r.text[:150])
    sid = r.json().get("id") if r.status_code == 201 else None
    if sid:
        check("création tracée dans le journal", one("SELECT count(*) FROM audit_events WHERE entity_id=:i", i=sid)[0] >= 1)
        dup = c.post("/api/v1/personnel", json={"employee_no": emp, "last_name": "DOUBLON", "category": "AUTRE"}, headers=key()).status_code
        check("matricule déjà utilisé → refusé (409/422)", dup in (409, 422), dup)
        ver = c.get(f"/api/v1/personnel/{sid}").json().get("version")
        u = c.put(f"/api/v1/personnel/{sid}", json={"employee_no": emp, "last_name": "MWAMBA", "first_name": "Grâce", "category": "ADMINISTRATIF", "phone": "+243810000001"},
                  headers={**key(), "If-Match": str(ver)})
        check("fiche agent modifiée (If-Match)", u.status_code == 200 and one("SELECT phone FROM staff_members WHERE id=:i", i=sid)[0] == "+243810000001", u.text[:150])
        check("version périmée → 409", c.put(f"/api/v1/personnel/{sid}", json={"employee_no": emp, "last_name": "X", "category": "AUTRE"}, headers={**key(), "If-Match": str(ver)}).status_code == 409)
        st = c.patch(f"/api/v1/personnel/{sid}/status", json={"status": "SUSPENDED", "reason": "Essai de recette"}, headers=key()).status_code
        check("suspendre un agent (droit non détenu) → 403", st == 403, st)
        check("départ d'un agent (droit non détenu) → 403", c.post(f"/api/v1/personnel/{sid}/exit", json={"reason": "Essai de recette"}, headers=key()).status_code == 403)
    nocreate = as_(actor_for(ROLE, A["id"], drop={"personnel.create"}))
    check("droit de création retiré par l'école → 403", nocreate.post("/api/v1/personnel", json={"employee_no": f"N{H.RUN}", "last_name": "NON", "category": "AUTRE"}, headers=key()).status_code == 403)


def templates(A: dict) -> None:
    print("\n== Communication : préparer les modèles, jamais envoyer")
    c = as_(actor_for(ROLE, A["id"]))
    code = f"RAPPEL_REUNION_{H.RUN}"
    r = c.post("/api/v1/communications/templates", json={"code": code, "label": "Rappel de réunion", "channel": "SMS", "body": "Réunion des parents le {{date}}."}, headers=key())
    check("modèle de message créé", r.status_code in (200, 201), r.text[:150])
    p = c.post("/api/v1/communications/templates/preview", json={"body": "Bonjour {{responsable}}, réunion le {{date}}.", "values": {"responsable": "Mme Kasongo", "date": "lundi"}})
    check("variable inconnue dans un modèle → refusée (rien d'incompréhensible n'atteint un parent)",
          c.post("/api/v1/communications/templates/preview", json={"body": "Bonjour {{inconnu}}", "values": {"inconnu": "x"}}).status_code == 422)
    check("aperçu d'un modèle (texte et nombre de SMS)", p.status_code == 200 and "Mme Kasongo" in p.json().get("text", "") and p.json().get("sms_units", 0) >= 1, p.text[:150])
    for aud, ref in (("INDIVIDUAL", str(A["pupils"]["SECONDAIRE"])), ("CLASS", str(A["classes"]["SECONDAIRE"])), ("SCHOOL", None)):
        s = c.post("/api/v1/communications/send", json={"audience_type": aud, "audience_ref": ref, "channels": ["SMS"], "body": "Essai", "idempotency_key": f"sec-{uuid.uuid4().hex}"}).status_code
        check(f"envoi ({aud}) refusé → 403", s == 403, s)
    check("aucun message parti", one("SELECT count(*) FROM communication_messages WHERE school_id=:s", s=A["id"])[0] == 0)


def student_import(A: dict) -> None:
    print("\n== Import des élèves : modèle officiel → analyse → exécution, rejeu sans doublon")
    c = as_(actor_for(ROLE, A["id"]))
    tpl = c.get("/api/v1/documents/student-import-template.xlsx")
    wb = load_workbook(io.BytesIO(tpl.content))
    meta = {str(r[0].value): str(r[1].value or "") for r in wb["_EDUSYNC_CONTRACT"].iter_rows(min_row=1, max_row=19, max_col=2) if r[0].value} if "_EDUSYNC_CONTRACT" in wb.sheetnames else {}
    sheet = meta.get("data_sheet") or next(n for n in wb.sheetnames if not n.startswith("_"))
    hrow = int(meta.get("header_row") or 5); ws = wb[sheet]
    for row in ws.iter_rows(min_row=hrow + 1, max_row=ws.max_row):
        for cell in row:
            cell.value = None
    cls = one("SELECT code FROM school_classes WHERE id=:i", i=A["classes"]["SECONDAIRE"])[0]
    # Contract 1.1 (owner, 2026-11-01): the real enrollment date is kept; an empty date means the day of the import.
    real_day = date.today() - timedelta(days=20)
    check("modèle 1.1 : colonne « Date inscription »", ws.cell(hrow, 15).value == "Date inscription" and meta.get("contract_version") == "1.1", str(ws.cell(hrow, 15).value))
    for i, (ln, fn) in enumerate((("KALENGA", "Divine"), ("ILUNGA", "Prince")), hrow + 1):
        for col, v in enumerate([ln, "IMPORT", fn, "F" if fn == "Divine" else "M", cls], 1):
            ws.cell(i, col, v)
    ws.cell(hrow + 1, 15, real_day.strftime("%d/%m/%Y"))
    future = io.BytesIO(); ws.cell(hrow + 2, 15, (date.today() + timedelta(days=3)).strftime("%d/%m/%Y")); wb.save(future); ws.cell(hrow + 2, 15).value = None
    fut = c.post(f"/api/v1/import/students/analyze?filename=eleves.xlsx&academic_year_id={A['year']}", content=future.getvalue())
    check("date d'inscription dans le futur → erreur, lot non exécutable", fut.status_code == 200 and fut.json()["error_rows"] == 1 and not fut.json()["can_execute"], fut.text[:200])
    buf = io.BytesIO(); wb.save(buf)
    before = one("SELECT count(*) FROM students WHERE school_id=:s", s=A["id"])[0]
    an = c.post(f"/api/v1/import/students/analyze?filename=eleves.xlsx&academic_year_id={A['year']}", content=buf.getvalue(),
                headers={"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"})
    check("analyse du fichier (aucune écriture d'élève)", an.status_code == 200 and one("SELECT count(*) FROM students WHERE school_id=:s", s=A["id"])[0] == before, an.text[:200])
    if an.status_code != 200:
        return
    bid = an.json().get("batch_id") or an.json().get("id")
    k = {"Idempotency-Key": f"sec-imp-{uuid.uuid4().hex}"}
    check("exécution sans confirmer les foyers séparés → 409", c.post(f"/api/v1/import/students/batches/{bid}/execute", json={"accept_warnings": True}, headers=k).status_code == 409)
    ex = c.post(f"/api/v1/import/students/batches/{bid}/execute", json={"accept_warnings": True, "confirm_separate_households": True}, headers=k)
    after = one("SELECT count(*) FROM students WHERE school_id=:s", s=A["id"])[0]
    check("import exécuté : 2 élèves créés", ex.status_code == 200 and after == before + 2, f"{ex.status_code} {ex.text[:150]} {before}→{after}")
    days = {r[0]: r[1] for r in H.sql("SELECT s.last_name,e.enrolled_on FROM students s JOIN enrollments e ON e.student_id=s.id WHERE s.school_id=:s AND s.middle_name='IMPORT'", s=A["id"]).all()}
    check("date d'inscription réelle conservée ; vide = jour de l'import", days.get("KALENGA") == real_day and days.get("ILUNGA") == date.today(), str(days))
    H.sql("UPDATE academic_years SET enrollment_start=:d WHERE id=:y", d=date(2026, 7, 1), y=A["year"])
    july = io.BytesIO(); ws.cell(hrow + 1, 1, "KALENGA2"); ws.cell(hrow + 2, 1, "ILUNGA2"); ws.cell(hrow + 1, 15, "15/07/2026"); ws.cell(hrow + 2, 15, "15/06/2026"); wb.save(july)
    jl = c.post(f"/api/v1/import/students/analyze?filename=eleves.xlsx&academic_year_id={A['year']}", content=july.getvalue()).json()
    codes = {p["row_number"]: [i["code"] for i in p["issues"]] for p in jl.get("preview", [])}
    check("inscription de juillet dans la période d'inscription : aucun avertissement ; avant la période : avertissement",
          codes.get(hrow + 1) == [] and codes.get(hrow + 2) == ["ENROLLMENT_DATE_OUTSIDE_YEAR"], str(codes))
    again = c.post(f"/api/v1/import/students/batches/{bid}/execute", json={"accept_warnings": True, "confirm_separate_households": True}, headers={"Idempotency-Key": f"sec-imp-{uuid.uuid4().hex}"})
    check("rejeu du même lot : aucun doublon", again.status_code == 200 and one("SELECT count(*) FROM students WHERE school_id=:s", s=A["id"])[0] == after, again.text[:150])
    noexec = as_(actor_for(ROLE, A["id"], drop={"migration.students.execute"}))
    check("droit d'exécution retiré → 403", noexec.post(f"/api/v1/import/students/batches/{bid}/execute", json={"confirm_separate_households": True}, headers=key()).status_code == 403)


def forbidden(A: dict) -> None:
    print("\n== Tout le reste : refusé (403), rien écrit")
    c = as_(actor_for(ROLE, A["id"]))
    Z = "00000000-0000-0000-0000-000000000000"
    tables = ("finance_payments", "finance_cash_sessions", "enrollments", "school_memberships", "inventory_items")
    count = lambda: {t: one(f"SELECT count(*) FROM {t} WHERE school_id=:s", s=A["id"])[0] for t in tables}
    before = count()
    for label, method, path, body in [
        ("ouvrir une caisse", "POST", "/api/v1/finance/cash/open", {"opening_cdf": "0", "opening_usd": "0"}),
        ("encaisser", "POST", "/api/v1/finance/checkout/collect", {"enrollment_id": Z, "charge_ids": [Z], "amount": "1", "currency": "CDF"}),
        ("inscrire une famille", "POST", "/api/v1/schooling/enrollments/family", {"children": [{"last_name": "T", "middle_name": "T", "first_name": "T", "class_id": str(A["classes"]["PRIMAIRE"]), "gender": "M"}]}),
        ("modifier l'identité de l'école", "PATCH", "/api/v1/settings/identity", {"name": "Autre nom"}),
        ("ajouter un membre", "POST", "/api/v1/access/members", {"email": f"x{uuid.uuid4().hex[:6]}@example.test", "full_name": "Sonde", "reason": "Recette"}),
        ("créer un article de stock", "POST", "/api/v1/stewardship/items", {"code": "X1", "label": "Craie", "unit": "boîte", "low_threshold": "1"}),
        ("analyser un import du personnel", "POST", f"/api/v1/import/staff/analyze?filename=x.xlsx&academic_year_id={A['year']}", None),
        ("exécuter une reprise financière", "POST", f"/api/v1/import/finance-history/batches/{Z}/execute", {"accept_warnings": False, "confirm_outside_cash": False}),
    ]:
        r = c.request(method, path, json=body, headers={**key(), "If-Match": "1"})
        check(f"refusé : {label}", r.status_code == 403, f"HTTP {r.status_code} {r.text[:100]}")
    for label, path in [("caisses", "/api/v1/finance/cash/day-summary"), ("mouvements d'élèves", f"/api/v1/effectifs/movements?scope=ALL&year_id={A['year']}"),
                        ("stock", "/api/v1/stewardship/stock"), ("comptes et accès", "/api/v1/access/members"), ("journal de l'établissement", "/api/v1/audit/events")]:
        code = c.get(path).status_code
        check(f"lecture non accordée : {label} → 403", code == 403, f"HTTP {code}")
    check("aucune écriture en base après ces refus", count() == before, f"{before} → {count()}")


def isolation(A: dict, B: dict) -> None:
    print("\n== Isolation entre écoles")
    c = as_(actor_for(ROLE, A["id"]))
    check("élève d'une autre école → 404", c.get(f"/api/v1/schooling/students/{B['pupils']['SECONDAIRE']}").status_code == 404)
    check("famille d'une autre école → 404", c.get(f"/api/v1/schooling/families/{B['families']['SECONDAIRE']}").status_code == 404)
    check("fiche PDF d'un élève d'une autre école → 404", c.get(f"/api/v1/schooling/students/{B['pupils']['SECONDAIRE']}/profile.pdf").status_code == 404)
    ver = one("SELECT version FROM students WHERE id=:i", i=B["pupils"]["SECONDAIRE"])[0]
    r = c.patch(f"/api/v1/schooling/students/{B['pupils']['SECONDAIRE']}", json={"address": "Intrusion"}, headers={**key(), "If-Match": str(ver)})
    check("compléter la fiche d'un élève d'une autre école → refusé, rien écrit", r.status_code in (403, 404) and (one("SELECT address FROM students WHERE id=:i", i=B["pupils"]["SECONDAIRE"])[0] or "") != "Intrusion", r.status_code)
    names = {x.get("matricule") for x in c.get("/api/v1/schooling/students?limit=200").json().get("items", [])}
    check("annuaire limité à l'école", not any(str(m).endswith("-B") for m in names), names)


def main() -> int:
    A, B = school("A"), school("B")
    registry(A)
    reads(A)
    exports(A)
    files_to_complete(A)
    student_profile(A)
    personnel(A)
    templates(A)
    student_import(A)
    forbidden(A)
    isolation(A, B)
    H.CLIENT.__exit__(None, None, None)
    fails = [r for r in H.RESULTS if r[0] == "FAIL"]
    print(f"\n{len(H.RESULTS) - len(fails)}/{len(H.RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
