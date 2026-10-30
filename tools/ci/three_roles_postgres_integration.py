"""Certification Intendant / Directeur des études / Directeur de discipline — real HTTP + real PostgreSQL (2026-10-30).

Runs the REAL application in-process (FastAPI TestClient, real services, tenant role with RLS, real transactions,
idempotency registry, object storage) against an ISOLATED, freshly migrated database. Only the authentication step is
replaced: each request carries an actor built from the canonical registry (role capabilities + scopes), exactly what
require_school_actor would load. Two schools (A, B), sections PRIMAIRE / SECONDAIRE, pupils, staff, stock, assets.

    python tools/local/isolated_db.py create edusync_cert_3roles
    python tools/local/isolated_db.py env edusync_cert_3roles -- ../.venv/Scripts/python.exe ../tools/ci/three_roles_postgres_integration.py

Refuses any non-localhost database and requires CI=true. Prints PASS / FAIL per check, exits 1 on any FAIL.
"""
from __future__ import annotations

import io
import json
import os
import threading
import uuid
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

URL = os.environ["EDUSYNC_OWNER_DATABASE_URL"]
assert os.environ.get("CI") == "true", "Disposable CI only"
assert "127.0.0.1" in URL or "localhost" in URL, "Remote databases forbidden"

from edusync.bootstrap.app import create_app  # noqa: E402
from edusync.bootstrap.dependencies import require_school_actor  # noqa: E402
from edusync.modules.documents.application import object_store  # noqa: E402
from edusync.shared.application.context import ActorContext  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REG = json.loads((ROOT / "contracts/CAPABILITY_REGISTRY.json").read_text(encoding="utf-8"))
ALIAS = {c["code"]: c["alias_of"] for c in REG["capabilities"] if c.get("alias_of")}
ENGINE = create_engine(URL, future=True)
RESULTS: list[tuple[str, str]] = []
RUN = uuid.uuid4().hex[:6].upper()


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(("PASS" if ok else "FAIL", name))
    print(f"{'PASS' if ok else 'FAIL':5} {name}{' — ' + str(detail)[:200] if detail and not ok else ''}")


def sql(q: str, **p):
    with ENGINE.begin() as c:
        return c.execute(text(q), p)


def one(q: str, **p):
    return sql(q, **p).first()


# ---------------------------------------------------------------------------------------------------------------- data
def school(tag: str) -> dict:
    sid, yid = uuid.uuid4(), uuid.uuid4()
    sql("INSERT INTO schools(id,code,name) VALUES(:i,:c,:n)", i=sid, c=f"T3R-{tag}-{RUN}", n=f"École {tag} {RUN}")
    sql("""INSERT INTO academic_years(id,school_id,code,label,start_date,end_date,status)
           VALUES(:i,:s,'2026-2027','2026-2027','2026-09-01','2027-07-01','ACTIVE')""", i=yid, s=sid)
    out = {"id": sid, "year": yid, "sections": {}, "classes": {}, "pupils": {}, "families": {}}
    for sec in ("PRIMAIRE", "SECONDAIRE"):
        sec_id, cls_id, fam, pupil = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        sql("INSERT INTO school_sections(id,school_id,code,label) VALUES(:i,:s,:c,:c)", i=sec_id, s=sid, c=sec)
        sql("INSERT INTO school_classes(id,school_id,academic_year_id,section_id,code,label) VALUES(:i,:s,:y,:sec,:c,:c)",
            i=cls_id, s=sid, y=yid, sec=sec_id, c=f"{sec[:3]}-1A")
        sql("INSERT INTO families(id,school_id,code,display_name) VALUES(:i,:s,:c,:n)", i=fam, s=sid, c=f"F-{sec[:3]}-{RUN}", n=f"Famille {sec}")
        sql("""INSERT INTO students(id,school_id,family_id,matricule,last_name,middle_name,first_name,gender)
               VALUES(:i,:s,:f,:m,'ELEVE','TEST',:fn,'F')""", i=pupil, s=sid, f=fam, m=f"M-{sec[:3]}-{RUN}-{tag}", fn=sec.title())
        sql("INSERT INTO enrollments(id,school_id,student_id,academic_year_id,class_id) VALUES(:i,:s,:st,:y,:c)",
            i=uuid.uuid4(), s=sid, st=pupil, y=yid, c=cls_id)
        out["sections"][sec], out["classes"][sec], out["pupils"][sec], out["families"][sec] = sec_id, cls_id, pupil, fam
    out["asset_type"] = uuid.uuid4()
    sql("INSERT INTO inventory_asset_types(id,school_id,code,label) VALUES(:i,:s,'BANC','Banc')", i=out["asset_type"], s=sid)
    return out


def actor_for(role: str, school_id, scope=("SCHOOL", None), extra: set[str] | None = None, drop: set[str] | None = None) -> ActorContext:
    caps = set(REG["standard_roles"][role]["capabilities"]) | (extra or set())
    caps -= (drop or set())
    caps |= {ALIAS[c] for c in caps if c in ALIAS}                      # alias held → its business capability
    uid, mid = uuid.uuid4(), uuid.uuid4()                                # a real account and membership (foreign keys)
    sql("INSERT INTO users(id,email,full_name,password_hash,active,version) VALUES(:i,:e,:n,'x',true,1)", i=uid, e=f"{role.lower()}-{uid.hex[:8]}@example.test", n=role.title())
    sql("INSERT INTO school_memberships(id,school_id,user_id,active,version) VALUES(:i,:s,:u,true,1)", i=mid, s=school_id, u=uid)
    return ActorContext(user_id=uid, school_id=school_id, membership_id=mid, permissions=frozenset(caps),
                        capability_scopes=tuple((c, scope[0], scope[1]) for c in sorted(caps)))


APP = create_app()
CURRENT: dict[str, ActorContext] = {}
APP.dependency_overrides[require_school_actor] = lambda: CURRENT["actor"]
CLIENT = TestClient(APP, raise_server_exceptions=False)
CLIENT.__enter__()


def as_(actor: ActorContext) -> TestClient:
    CURRENT["actor"] = actor
    return CLIENT


def key() -> dict:
    return {"Idempotency-Key": f"t3r-{uuid.uuid4().hex}"}


# ------------------------------------------------------------------------------------------------------------ intendant
def intendant(A: dict, B: dict) -> None:
    print("\n== INTENDANT — stock, inventaires, patrimoine, exports")
    ia, ib = actor_for("INTENDANT", A["id"]), actor_for("INTENDANT", B["id"])
    c = as_(ia)
    k = key()
    body = {"code": f"CRAIE{RUN}", "label": "Craie blanche", "unit": "boîte", "low_threshold": "6"}
    r1 = c.post("/api/v1/stewardship/items", json=body, headers=k); r2 = c.post("/api/v1/stewardship/items", json=body, headers=k)
    check("article créé (201)", r1.status_code == 201, r1.text)
    item = r1.json().get("id")
    check("idempotence : même clé → même article, une seule ligne", r2.status_code in (200, 201) and r2.json().get("id") == item
          and one("SELECT count(*) FROM inventory_items WHERE school_id=:s AND code=:c", s=A["id"], c=body["code"])[0] == 1, r2.text)
    r3 = c.post("/api/v1/stewardship/items", json={**body, "label": "Autre"}, headers=k)
    check("idempotence : même clé, autre contenu → 409", r3.status_code == 409, r3.status_code)
    check("code d'article en double → 409", c.post("/api/v1/stewardship/items", json=body, headers=key()).status_code == 409)

    def move(t, q, d=None, actor=ia):
        b = {"item_id": item, "movement_type": t, "quantity": str(q), "reason": "Recette certification"}
        if d: b["adjustment_direction"] = d
        return as_(actor).post("/api/v1/stewardship/stock/movements", json=b, headers=key())
    check("réception de 10 (201)", move("RECEIPT", 10).status_code == 201)
    check("sortie de 3 (201)", move("ISSUE", 3).status_code == 201)
    r = move("ISSUE", 20)
    check("sortie supérieure au stock refusée (409), stock inchangé", r.status_code == 409 and float(one("SELECT quantity FROM inventory_items WHERE id=:i", i=item)[0]) == 7, r.text)
    check("ajustement sans sens → 422", move("ADJUSTMENT", 1).status_code == 422)
    check("ajustement à la baisse de 2 (201)", move("ADJUSTMENT", 2, "DECREASE").status_code == 201)
    check("quantité finale = 5 et grand livre cohérent",
          float(one("SELECT quantity FROM inventory_items WHERE id=:i", i=item)[0]) == 5
          and float(one("SELECT sum(quantity_delta) FROM inventory_item_movements WHERE item_id=:i", i=item)[0]) == 5)
    no_issue = actor_for("INTENDANT", A["id"], drop={"inventory.stock.issue"})
    check("sortie sans le droit inventory.stock.issue → 403", move("ISSUE", 1, actor=no_issue).status_code == 403)
    mv = as_(ia).get("/api/v1/stewardship/stock/movements").json()
    check("mouvements consultables (3)", len([m for m in mv["items"] if str(m["item_id"]) == item]) == 3)
    low = as_(ia).get("/api/v1/stewardship/stock/low-alerts")
    check("alertes de stock faible : l'article (5 ≤ seuil 6) apparaît", low.status_code == 200 and any(str(i["id"]) == item for i in low.json()["items"]), low.text)
    check("alertes sans le droit → 403", as_(actor_for("INTENDANT", A["id"], drop={"inventory.stock.low_alerts.read"})).get("/api/v1/stewardship/stock/low-alerts").status_code == 403)

    # concurrency: two simultaneous issues of 4 on a stock of 5 → exactly one succeeds, never negative
    codes = []
    def issue4():
        cl = TestClient(APP, raise_server_exceptions=False)
        APP.dependency_overrides[require_school_actor] = lambda: ia
        codes.append(cl.post("/api/v1/stewardship/stock/movements", json={"item_id": item, "movement_type": "ISSUE", "quantity": "4", "reason": "Concurrence"}, headers=key()).status_code)
    ts = [threading.Thread(target=issue4) for _ in range(2)]
    [t.start() for t in ts]; [t.join() for t in ts]
    APP.dependency_overrides[require_school_actor] = lambda: CURRENT["actor"]
    q = float(one("SELECT quantity FROM inventory_items WHERE id=:i", i=item)[0])
    check("concurrence : 2 sorties simultanées de 4 sur 5 → une seule réussit, stock 1", sorted(codes) == [201, 409] and q == 1, f"{codes} → {q}")

    # physical count
    c = as_(ia)
    cnt = c.post("/api/v1/stewardship/counts", json={"notes": "Recette"}, headers=key()).json()["id"]
    check("écart sans justification → 422", c.post(f"/api/v1/stewardship/counts/{cnt}/lines", json={"item_id": item, "counted_quantity": "3"}).status_code == 422)
    check("comptage justifié enregistré", c.post(f"/api/v1/stewardship/counts/{cnt}/lines", json={"item_id": item, "counted_quantity": "3", "reason": "Casse constatée"}).status_code == 200)
    vals = []
    def validate():
        cl = TestClient(APP, raise_server_exceptions=False)
        APP.dependency_overrides[require_school_actor] = lambda: ia
        vals.append(cl.post(f"/api/v1/stewardship/counts/{cnt}/validate").status_code)
    ts = [threading.Thread(target=validate) for _ in range(2)]
    [t.start() for t in ts]; [t.join() for t in ts]
    APP.dependency_overrides[require_school_actor] = lambda: CURRENT["actor"]
    check("double validation simultanée → une seule (200 + 409)", sorted(vals) == [200, 409], vals)
    check("stock aligné sur le comptage (3) et un seul ajustement d'inventaire",
          float(one("SELECT quantity FROM inventory_items WHERE id=:i", i=item)[0]) == 3
          and one("SELECT count(*) FROM inventory_item_movements WHERE item_id=:i AND movement_type='COUNT_ADJUSTMENT'", i=item)[0] == 1)
    check("comptage validé non modifiable (409)", c.post(f"/api/v1/stewardship/counts/{cnt}/lines", json={"item_id": item, "counted_quantity": "3"}).status_code == 409)
    sql("UPDATE inventory_items SET enabled=false WHERE id=:i", i=item)
    cnt2 = c.post("/api/v1/stewardship/counts", json={}).json()["id"]
    check("article désactivé : comptage refusé (404) et mouvement refusé (404)",
          c.post(f"/api/v1/stewardship/counts/{cnt2}/lines", json={"item_id": item, "counted_quantity": "1", "reason": "x"}).status_code == 404 and move("RECEIPT", 1).status_code == 404)
    sql("UPDATE inventory_items SET enabled=true WHERE id=:i", i=item)

    # assets
    k = key()
    ab = {"asset_type_id": str(A["asset_type"]), "tag": f"BANC-{RUN}", "quantity": 4, "status": "GOOD"}
    a1 = c.post("/api/v1/stewardship/assets", json=ab, headers=k); a2 = c.post("/api/v1/stewardship/assets", json=ab, headers=k)
    asset = a1.json().get("id")
    check("immobilisation créée, idempotente (même clé → même bien, une ligne)", a1.status_code == 201 and a2.json().get("id") == asset
          and one("SELECT count(*) FROM inventory_assets WHERE school_id=:s AND asset_tag=:t", s=A["id"], t=ab["tag"])[0] == 1, a2.text)
    v = one("SELECT version FROM inventory_assets WHERE id=:i", i=asset)[0]
    up = c.put(f"/api/v1/stewardship/assets/{asset}", json={"tag": ab["tag"], "notes": "Pied réparé", "quantity": 5, "version": v})
    check("modification de la fiche (version) → événement UPDATE", up.status_code == 200 and one("SELECT count(*) FROM inventory_asset_events WHERE asset_id=:i AND event_type='UPDATE'", i=asset)[0] == 1, up.text)
    check("version périmée → 409", c.put(f"/api/v1/stewardship/assets/{asset}", json={"tag": ab["tag"], "notes": "x", "quantity": 5, "version": v}).status_code == 409)
    check("réparation ouverte puis clôturée (IN_REPAIR → GOOD)",
          c.post(f"/api/v1/stewardship/assets/{asset}/repairs", json={"reason": "Pied cassé"}).json().get("status") == "IN_REPAIR"
          and c.post(f"/api/v1/stewardship/assets/{asset}/repairs", json={"reason": "Réparé", "completed": True}).json().get("status") == "GOOD")
    rc = c.post(f"/api/v1/stewardship/assets/{asset}/repairs", json={"reason": "Contrôle", "completed": True})
    check("clôture sans réparation en cours → 409", rc.status_code == 409, f"{rc.status_code} {rc.text[:120]}")
    check("sortie du patrimoine (DISPOSED)", c.post(f"/api/v1/stewardship/assets/{asset}/status", json={"status": "DISPOSED", "reason": "Hors d'usage"}).status_code == 200)
    v = one("SELECT version FROM inventory_assets WHERE id=:i", i=asset)[0]
    check("bien sorti : modification refusée (409)", c.put(f"/api/v1/stewardship/assets/{asset}", json={"tag": "X", "notes": None, "quantity": 1, "version": v}).status_code == 409)
    check("bien sorti : réparation et changement d'état refusés (409)",
          c.post(f"/api/v1/stewardship/assets/{asset}/repairs", json={"reason": "Réparation demandée"}).status_code == 409
          and c.post(f"/api/v1/stewardship/assets/{asset}/status", json={"status": "GOOD", "reason": "Remise en service"}).status_code == 409)
    h = c.get(f"/api/v1/stewardship/assets/{asset}/history").json()["items"]
    check("historique complet du bien (CREATE, UPDATE, REPAIR ×2, STATUS)", sorted(e["event_type"] for e in h) == ["CREATE", "REPAIR", "REPAIR", "STATUS", "UPDATE"], [e["event_type"] for e in h])

    # exports
    from openpyxl import load_workbook
    x = c.get("/api/v1/stewardship/stock/export.xlsx")
    wb = load_workbook(io.BytesIO(x.content)) if x.status_code == 200 else None
    nums = [cell.value for row in wb.active.iter_rows(min_row=2) for cell in row if isinstance(cell.value, (int, float))] if wb else []
    check("export Excel du stock : fichier valide, quantités numériques", x.status_code == 200 and len(nums) > 0, x.status_code)
    xc = c.get(f"/api/v1/stewardship/counts/{cnt}/export.xlsx")
    check("export Excel du comptage valide", xc.status_code == 200 and xc.content[:2] == b"PK", xc.status_code)
    pdf1, pdf2 = c.get("/api/v1/stewardship/stock/print.pdf"), c.get(f"/api/v1/stewardship/counts/{cnt}/print.pdf")
    check("fiche de stock et impression du comptage en PDF", pdf1.content[:4] == b"%PDF" and pdf2.content[:4] == b"%PDF", f"{pdf1.status_code}/{pdf2.status_code}")
    noexp = actor_for("INTENDANT", A["id"], drop={"inventory.stock.export_xlsx", "inventory.counts.export", "inventory.counts.export_xlsx", "inventory.counts.print"})
    check("exports sans le droit → 403", as_(noexp).get("/api/v1/stewardship/stock/export.xlsx").status_code == 403
          and as_(noexp).get(f"/api/v1/stewardship/counts/{cnt}/export.xlsx").status_code == 403)

    # multi-school isolation
    cb = as_(ib)
    check("école B : article, comptage, bien de A introuvables (404) et absents des listes",
          cb.post("/api/v1/stewardship/stock/movements", json={"item_id": item, "movement_type": "RECEIPT", "quantity": "1", "reason": "intrusion"}, headers=key()).status_code == 404
          and cb.get(f"/api/v1/stewardship/counts/{cnt}").status_code == 404 and cb.get(f"/api/v1/stewardship/assets/{asset}/history").status_code == 404
          and cb.get(f"/api/v1/stewardship/counts/{cnt}/export.xlsx").status_code == 404
          and not any(str(i["id"]) == item for i in cb.get("/api/v1/stewardship/stock").json()["items"]))
    co = as_(ia).post("/api/v1/finance/cash/open", json={"opening_cdf": "0", "opening_usd": "0"}, headers=key()).status_code
    ip = as_(ia).patch("/api/v1/settings/identity", json={"name": "Nom modifié"}, headers={**key(), "If-Match": "1"}).status_code
    check("Intendant : ouverture de caisse et modification de l'identité de l'école refusées (403)", co == 403 and ip == 403, f"caisse {co}, identité {ip}")


# ------------------------------------------------------------------------------------------- directeurs (secondaire)
def directors(A: dict, B: dict) -> None:
    sec = ("SECTION", "SECONDAIRE")
    for role in ("DIRECTEUR_ETUDES", "DIRECTEUR_DISCIPLINE"):
        print(f"\n== {role} — périmètre SECTION=SECONDAIRE")
        d = actor_for(role, A["id"], scope=sec)
        c = as_(d)
        st = c.get("/api/v1/schooling/students", params={"limit": 500})
        ids = {str(s["id"]) for s in (st.json()["items"] if st.status_code == 200 else [])}
        check(f"{role} : liste des élèves = secondaire seulement", st.status_code == 200 and str(A["pupils"]["SECONDAIRE"]) in ids and str(A["pupils"]["PRIMAIRE"]) not in ids, st.text[:120])
        check(f"{role} : fiche d'un élève du primaire → 404", c.get(f"/api/v1/schooling/students/{A['pupils']['PRIMAIRE']}").status_code == 404)
        check(f"{role} : élève d'une autre école → 404", c.get(f"/api/v1/schooling/students/{B['pupils']['SECONDAIRE']}").status_code == 404)
        cnt = c.get("/api/v1/effectifs/counts", params={"group_by": "section"})
        secs = {str(i.get("code") or "").upper() for i in cnt.json().get("items", [])} if cnt.status_code == 200 else set()
        check(f"{role} : effectifs par section = SECONDAIRE seulement", cnt.status_code == 200 and secs <= {"SECONDAIRE"}, cnt.text[:120])
        opt = c.get("/api/v1/effectifs/counts", params={"group_by": "option"}).status_code
        check(f"{role} : effectifs par option {'autorisés' if role == 'DIRECTEUR_ETUDES' else 'refusés (droit absent)'}",
              opt == (200 if role == "DIRECTEUR_ETUDES" else 403), opt)
        # audit entity history (reserve of the handoff) — real SQL
        sql("""INSERT INTO audit_events(school_id,action,entity_type,entity_id,source,old_json,new_json)
               VALUES(:s,'STUDENT_PROFILE_UPDATED','Student',:e,'WEB','{"last_name":"OLD"}','{"last_name":"NEW"}')""", s=A["id"], e=A["pupils"]["PRIMAIRE"])
        sql("""INSERT INTO audit_events(school_id,action,entity_type,entity_id,source,old_json,new_json)
               VALUES(:s,'STUDENT_PROFILE_UPDATED','Student',:e,'WEB','{"last_name":"OLD"}','{"last_name":"NEW"}')""", s=A["id"], e=A["pupils"]["SECONDAIRE"])
        check(f"{role} : historique d'audit d'un élève du secondaire lisible", c.get(f"/api/v1/audit/entities/Student/{A['pupils']['SECONDAIRE']}").status_code == 200)
        check(f"{role} : historique d'audit d'un élève du primaire → 404 (old/new non divulgués)", c.get(f"/api/v1/audit/entities/Student/{A['pupils']['PRIMAIRE']}").status_code == 404)
        check(f"{role} : historique d'audit d'un paiement / d'un compte → 404",
              c.get(f"/api/v1/audit/entities/FinancePayment/{uuid.uuid4()}").status_code == 404 and c.get(f"/api/v1/audit/entities/school_membership/{uuid.uuid4()}").status_code == 404)
        check(f"{role} : aucune opération financière (ouverture de caisse) → 403", c.post("/api/v1/finance/cash/open", json={"opening_cdf": "0", "opening_usd": "0"}, headers=key()).status_code == 403)
        sec_id = str(A["sections"]["SECONDAIRE"])
        bulk = c.post("/api/v1/communications/send", json={"audience_type": "SECTION", "audience_ref": sec_id, "channels": ["SMS"], "body": "Réunion des parents",
                                                         "idempotency_key": f"t3r-{uuid.uuid4().hex}"}).status_code
        check(f"{role} : SMS groupé {'autorisé (pas 403)' if role == 'DIRECTEUR_DISCIPLINE' else 'refusé (403)'}", (bulk != 403) if role == "DIRECTEUR_DISCIPLINE" else bulk == 403, bulk)
        # identity correction
        pupil = A["pupils"]["SECONDAIRE"]; ver = one("SELECT version FROM students WHERE id=:i", i=pupil)[0]
        r = c.patch(f"/api/v1/schooling/students/{pupil}", json={"first_name": "Corrige"}, headers={**key(), "If-Match": str(ver)})
        if role == "DIRECTEUR_ETUDES":
            check("DIRECTEUR_ETUDES : correction d'identité refusée (403)", r.status_code == 403, r.status_code)
        else:
            check("DIRECTEUR_DISCIPLINE : correction d'identité d'un élève du secondaire (200) + audit",
                  r.status_code == 200 and one("SELECT first_name FROM students WHERE id=:i", i=pupil)[0] == "Corrige"
                  and one("SELECT count(*) FROM audit_events WHERE entity_id=:i AND action='STUDENT_PROFILE_UPDATED' AND actor_user_id IS NOT NULL", i=pupil)[0] >= 1, r.text[:150])
            check("DIRECTEUR_DISCIPLINE : version périmée → 409", c.patch(f"/api/v1/schooling/students/{pupil}", json={"first_name": "Encore"}, headers={**key(), "If-Match": str(ver)}).status_code == 409)
            ver = one("SELECT version FROM students WHERE id=:i", i=pupil)[0]
            check("DIRECTEUR_DISCIPLINE : identité + profil mélangés → 422",
                  c.patch(f"/api/v1/schooling/students/{pupil}", json={"first_name": "X", "address": "Y"}, headers={**key(), "If-Match": str(ver)}).status_code == 422)
            prim = A["pupils"]["PRIMAIRE"]; pv = one("SELECT version FROM students WHERE id=:i", i=prim)[0]
            r2 = c.patch(f"/api/v1/schooling/students/{prim}", json={"first_name": "Intrus"}, headers={**key(), "If-Match": str(pv)})
            check("DIRECTEUR_DISCIPLINE : élève du primaire hors périmètre → refusé, rien écrit",
                  r2.status_code in (403, 404) and one("SELECT first_name FROM students WHERE id=:i", i=prim)[0] == "Primaire", r2.status_code)


# ----------------------------------------------------------------------------------------- documents (signed links)
def documents(A: dict) -> None:
    print("\n== Liens documentaires signés — révocation immédiate")
    from edusync.bootstrap.settings import Settings
    settings = Settings()
    uid, mid, aid, gid, author = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    sql("INSERT INTO users(id,email,full_name,password_hash,active,version) VALUES(:i,:e,'Auteur','x',true,1)", i=author, e=f"auteur-{RUN.lower()}@example.test")
    sql("INSERT INTO users(id,email,full_name,password_hash,active,version) VALUES(:i,:e,'Intendant Lien','x',true,1)", i=uid, e=f"lien-{RUN.lower()}@example.test")
    sql("INSERT INTO school_memberships(id,school_id,user_id,active,version) VALUES(:i,:s,:u,true,1)", i=mid, s=A["id"], u=uid)
    role = one("SELECT id FROM rbac_roles WHERE code='INTENDANT' AND kind='SCHOOL_STANDARD'")[0]
    sql("INSERT INTO rbac_assignments(id,user_id,role_id,school_id,membership_id,reason) VALUES(:i,:u,:r,:s,:m,'Recette')", i=aid, u=uid, r=role, s=A["id"], m=mid)
    sql("INSERT INTO rbac_assignment_scopes(assignment_id,scope_type,scope_value) VALUES(:a,'SCHOOL',NULL)", a=aid)
    sql("""INSERT INTO generated_documents(id,school_id,document_code,format,title,object_key,sha256,byte_size,generated_by,logical_key,required_capability)
           VALUES(:i,:s,'inventory.stock','XLSX','Stock',:k,'00',1,:g,:l,'inventory.stock.read')""",
        i=gid, s=A["id"], k=f"schools/{A['id']}/t3r/{gid}.xlsx", g=author, l=f"t3r-{gid}")
    token, _ = object_store.sign_link(settings, document_id=str(gid), school_id=str(A["id"]), user_id=str(uid))
    url = f"/api/v1/documents/open?token={token}"
    first = CLIENT.get(url).status_code
    check("lien valide d'un membre autorisé : accès non refusé (200, ou 503 si l'objet est absent du stockage)", first in (200, 503), first)
    sql("UPDATE rbac_assignments SET active=false WHERE id=:a", a=aid)
    check("droit retiré pendant la validité du lien → 403", CLIENT.get(url).status_code == 403)
    sql("UPDATE rbac_assignments SET active=true WHERE id=:a", a=aid); sql("UPDATE school_memberships SET active=false WHERE id=:m", m=mid)
    check("appartenance à l'école retirée → 403", CLIENT.get(url).status_code == 403)
    sql("UPDATE school_memberships SET active=true WHERE id=:m", m=mid); sql("UPDATE users SET active=false WHERE id=:u", u=uid)
    check("compte désactivé → 403", CLIENT.get(url).status_code == 403)
    sql("UPDATE users SET active=true WHERE id=:u", u=uid)
    other, _ = object_store.sign_link(settings, document_id=str(gid), school_id=str(uuid.uuid4()), user_id=str(uid))
    check("lien signé pour une autre école → 403", CLIENT.get(f"/api/v1/documents/open?token={other}").status_code == 403)
    expired, _ = object_store.sign_link(settings, document_id=str(gid), school_id=str(A["id"]), user_id=str(uid), now=1.0)
    check("lien expiré → 403", CLIENT.get(f"/api/v1/documents/open?token={expired}").status_code == 403)
    check("signature altérée → 403", CLIENT.get(url[:-3] + ("AAA" if not url.endswith("AAA") else "BBB")).status_code == 403)


# --------------------------------------------------------------------------------------------------- communications
def communications(A: dict, B: dict) -> None:
    print("\n== Communications — audience, déduplication, périmètre, crédit SMS, historique")
    from edusync.modules.communications.application.messaging import request_message, resolve_audience
    # a family with one child in the primary AND one in the secondary (same primary guardian), plus single-section families
    fam, s_pri, s_sec = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    sql("INSERT INTO families(id,school_id,code,display_name) VALUES(:i,:s,:c,'Famille multi-sections')", i=fam, s=A["id"], c=f"F-MULTI-{RUN}")
    for st, sec in ((s_pri, "PRIMAIRE"), (s_sec, "SECONDAIRE")):
        sql("INSERT INTO students(id,school_id,family_id,matricule,last_name,middle_name,first_name) VALUES(:i,:s,:f,:m,'MULTI','ENFANT',:fn)",
            i=st, s=A["id"], f=fam, m=f"MM-{sec[:3]}-{RUN}", fn=sec.title())
        sql("INSERT INTO enrollments(id,school_id,student_id,academic_year_id,class_id,status) VALUES(:i,:s,:st,:y,:c,'VALIDATED')",
            i=uuid.uuid4(), s=A["id"], st=st, y=A["year"], c=A["classes"][sec])
    sql("UPDATE enrollments SET status='VALIDATED' WHERE school_id IN (:a,:b)", a=A["id"], b=B["id"])
    g = {}
    for name, sch, family in (("G_MULTI", A, fam), ("G_SEC", A, A["families"]["SECONDAIRE"]), ("G_PRI", A, A["families"]["PRIMAIRE"]), ("G_B", B, B["families"]["SECONDAIRE"])):
        gid = uuid.uuid4(); g[name] = gid
        # distinct numbers: the preview removes duplicate phone numbers (one SMS per number)
        sql("INSERT INTO guardians(id,school_id,full_name,phone) VALUES(:i,:s,:n,:ph)", i=gid, s=sch["id"], n=name, ph=f"+24381000{len(g):04d}")
        sql("INSERT INTO family_guardians(school_id,family_id,guardian_id,is_primary,active) VALUES(:s,:f,:g,true,true)", s=sch["id"], f=family, g=gid)
    dd = actor_for("DIRECTEUR_DISCIPLINE", A["id"], scope=("SECTION", "SECONDAIRE"))
    caps = {"SECTION": "communications.send.section", "CLASS": "communications.send.class", "INDIVIDUAL": "communications.send.individual"}
    with ENGINE.connect() as conn:
        def who(atype, ref, actor=dd):
            return sorted(str(r.ref) for r in resolve_audience(conn, actor, A["id"], atype, ref, caps[atype]))
        got = who("SECTION", A["sections"]["SECONDAIRE"])
        check("section secondaire : parent multi-sections et parent du secondaire, chacun une fois", got == sorted([str(g["G_MULTI"]), str(g["G_SEC"])]), got)
        check("aucun parent de l'école B ni parent du seul primaire", str(g["G_B"]) not in got and str(g["G_PRI"]) not in got)
        for atype, ref, label in (("SECTION", A["sections"]["PRIMAIRE"], "section primaire"), ("CLASS", A["classes"]["PRIMAIRE"], "classe du primaire"),
                                  ("INDIVIDUAL", s_pri, "élève du primaire"), ("SECTION", B["sections"]["SECONDAIRE"], "section d'une autre école")):
            try:
                who(atype, ref)
                check(f"audience hors périmètre refusée : {label}", False, "aucune erreur")
            except PermissionError:
                check(f"audience hors périmètre refusée : {label}", True)
        check("élève du secondaire d'une famille multi-sections : son responsable", who("INDIVIDUAL", s_sec) == [str(g["G_MULTI"])])
        school_actor = actor_for("GESTIONNAIRE", A["id"])
        allp = sorted(str(r.ref) for r in resolve_audience(conn, school_actor, A["id"], "SCHOOL", None, "communications.send.all_parents"))
        check("toute l'école (périmètre école) : 3 responsables de A, dédoublonnés", allp == sorted(str(g[k]) for k in ("G_MULTI", "G_SEC", "G_PRI")), allp)
    # SMS credit reservation and idempotency (real wallet function: row lock, idempotency key, no negative balance)
    sql("SELECT school_sms_wallet_apply(:s,'TOPUP',3,:k,NULL,NULL,NULL,'Recette')", s=A["id"], k=f"topup-{RUN}")
    k = f"t3r-msg-{RUN}"
    with ENGINE.begin() as conn:
        rec = resolve_audience(conn, dd, A["id"], "SECTION", A["sections"]["SECONDAIRE"], caps["SECTION"])
        args = dict(school_id=A["id"], kind="COMMUNIQUE", channels=["SMS"], body="Réunion des parents samedi", recipients=rec,
                    created_by=dd.user_id, audience_type="SECTION", audience_ref=A["sections"]["SECONDAIRE"])
        r1 = request_message(conn, idempotency_key=k, **args)
        r2 = request_message(conn, idempotency_key=k, **args)
    w = one("SELECT balance,reserved FROM school_sms_wallets WHERE school_id=:s", s=A["id"])
    check("envoi enregistré : 2 destinataires, crédit SMS réservé (2 sur 3)", r1["recipients"] == 2 and int(w[1]) == 2 and int(w[0]) == 3, f"{r1} {tuple(w)}")
    check("idempotence : même clé → message rejoué, aucune réservation en plus", r2["replayed"] and r2["id"] == r1["id"]
          and one("SELECT count(*) FROM communication_messages WHERE idempotency_key=:k", k=k)[0] == 1)
    try:
        with ENGINE.begin() as conn:
            request_message(conn, idempotency_key=f"t3r-msg2-{RUN}", **{**args, "body": "Autre message"})
        check("crédit insuffisant (1 disponible, 2 nécessaires) refusé", False, "aucune erreur")
    except Exception as e:  # noqa: BLE001
        check("crédit insuffisant (1 disponible, 2 nécessaires) refusé, rien enregistré", "SMS_INSUFFICIENT_CREDIT" in str(e)
              and one("SELECT count(*) FROM communication_messages WHERE idempotency_key=:k", k=f"t3r-msg2-{RUN}")[0] == 0, str(e)[:120])
    # history / deliveries: phone numbers of another section's message are never shown to a section-scoped reader
    pri_msg = uuid.uuid4()
    sql("""INSERT INTO communication_messages(id,school_id,kind,audience_type,audience_ref,body,created_by,idempotency_key,channels,recipient_count)
           VALUES(:i,:s,'COMMUNIQUE','SECTION',:r,'Message du primaire',NULL,:k,ARRAY['SMS'],1)""", i=pri_msg, s=A["id"], r=A["sections"]["PRIMAIRE"], k=f"t3r-pri-{RUN}")
    de = actor_for("DIRECTEUR_ETUDES", A["id"], scope=("SECTION", "SECONDAIRE"))
    hist = as_(de).get("/api/v1/communications/history")
    ids = {str(m["id"]) for m in hist.json().get("items", [])} if hist.status_code == 200 else set()
    check("historique : message du secondaire visible, message du primaire masqué", hist.status_code == 200 and r1["id"] in ids and str(pri_msg) not in ids, hist.text[:120])
    check("détail des livraisons d'un message du primaire → 404 (numéros non divulgués)", as_(de).get(f"/api/v1/communications/history/{pri_msg}/deliveries").status_code == 404)
    check("détail des livraisons d'un message du secondaire → 200", as_(de).get(f"/api/v1/communications/history/{r1['id']}/deliveries").status_code == 200)
    other = actor_for("DIRECTEUR_ETUDES", B["id"], scope=("SECTION", "SECONDAIRE"))
    check("école B : message de A introuvable", as_(other).get(f"/api/v1/communications/history/{r1['id']}/deliveries").status_code == 404)


# ----------------------------------------------------------------------------------- notifications and authentication
def notifications_and_auth(A: dict, B: dict) -> None:
    print("\n== Notifications (destinataire seulement) et authentification")
    dd = actor_for("DIRECTEUR_DISCIPLINE", A["id"], scope=("SECTION", "SECONDAIRE"))
    de = actor_for("DIRECTEUR_ETUDES", A["id"], scope=("SECTION", "SECONDAIRE"))
    nid = uuid.uuid4()
    sql("INSERT INTO notifications(id,school_id,user_id,category,title,body) VALUES(:i,:s,:u,'GENERAL','Conseil de discipline','Réunion lundi')",
        i=nid, s=A["id"], u=dd.user_id)
    mine = as_(dd).get("/api/v1/notifications/inbox")
    check("le destinataire voit sa notification", mine.status_code == 200 and str(nid) in mine.text, mine.status_code)
    other = as_(de).get("/api/v1/notifications/inbox")
    check("un autre membre ne la voit pas", other.status_code == 200 and str(nid) not in other.text)
    r = as_(de).post(f"/api/v1/notifications/{nid}/dismiss", headers=key())
    check("un autre membre ne peut pas l'acquitter (404) — non lue", r.status_code == 404 and one("SELECT read_at FROM notifications WHERE id=:i", i=nid)[0] is None, r.status_code)
    rb = as_(actor_for("DIRECTEUR_DISCIPLINE", B["id"], scope=("SECTION", "SECONDAIRE"))).post(f"/api/v1/notifications/{nid}/dismiss", headers=key())
    check("un membre d'une autre école ne peut pas l'acquitter (404)", rb.status_code == 404, rb.status_code)
    ok = as_(dd).post(f"/api/v1/notifications/{nid}/dismiss", headers=key())
    check("le destinataire l'acquitte (200)", ok.status_code == 200 and one("SELECT read_at FROM notifications WHERE id=:i", i=nid)[0] is not None, ok.status_code)
    nodismiss = actor_for("DIRECTEUR_DISCIPLINE", A["id"], scope=("SECTION", "SECONDAIRE"), drop={"notifications.internal.dismiss"})
    check("acquittement sans le droit → 403", as_(nodismiss).post(f"/api/v1/notifications/{nid}/dismiss", headers=key()).status_code == 403)
    # real authentication (no actor override): missing or forged token → 401
    saved = APP.dependency_overrides.pop(require_school_actor)
    try:
        for path in ("/api/v1/stewardship/stock", "/api/v1/schooling/students", f"/api/v1/audit/entities/Student/{A['pupils']['SECONDAIRE']}"):
            check(f"sans jeton → 401 : {path.split('/api/v1/')[1][:40]}", CLIENT.get(path).status_code == 401)
        check("jeton falsifié → 401", CLIENT.get("/api/v1/stewardship/stock", headers={"Authorization": "Bearer abc.def.ghi"}).status_code == 401)
    finally:
        APP.dependency_overrides[require_school_actor] = saved


# ------------------------------------------------------------------- directeurs : familles, personnel, exports, réglages
def directors_reads(A: dict) -> None:
    print("\n== Directeurs — familles, personnel, exports, fiche, réglages (lecture, secondaire)")
    from openpyxl import load_workbook
    fn = uuid.uuid4()
    sql("INSERT INTO staff_functions(id,school_id,code,label) VALUES(:i,:s,'ENS','Enseignant')", i=fn, s=A["id"])
    staff = {}
    for name, stype, sval in (("SEC", "SECTION", "SECONDAIRE"), ("PRI", "SECTION", "PRIMAIRE"), ("ECOLE", "SCHOOL", None)):
        sid = uuid.uuid4(); staff[name] = sid
        sql("INSERT INTO staff_members(id,school_id,employee_no,last_name) VALUES(:i,:s,:e,:n)", i=sid, s=A["id"], e=f"AG-{name}-{RUN}", n=f"AGENT{name}")
        sql("INSERT INTO staff_assignments(school_id,staff_id,function_id,scope_type,scope_value,section_id) VALUES(:s,:st,:f,:t,:v,:sec)",
            s=A["id"], st=sid, f=fn, t=stype, v=sval, sec=A["sections"][sval] if sval else None)
    for role in ("DIRECTEUR_ETUDES", "DIRECTEUR_DISCIPLINE"):
        d = actor_for(role, A["id"], scope=("SECTION", "SECONDAIRE"))
        c = as_(d)
        fam = c.get("/api/v1/schooling/families", params={"limit": 200})
        fids = {str(f["id"]) for f in (fam.json().get("items", []) if fam.status_code == 200 else [])}
        check(f"{role} : familles = celles du secondaire", fam.status_code == 200 and str(A["families"]["SECONDAIRE"]) in fids and str(A["families"]["PRIMAIRE"]) not in fids, fam.text[:120])
        check(f"{role} : fiche d'une famille du seul primaire → 404", c.get(f"/api/v1/schooling/families/{A['families']['PRIMAIRE']}").status_code == 404)
        # Canonical registry: migration 0024 (Point 9) removed every personnel.* right from both Directors
        # (« schooling-first »); the addendum still mentions « personnel du périmètre » — owner decision pending.
        per = c.get("/api/v1/personnel")
        check(f"{role} : personnel refusé (403), conforme au registre canonique (retrait du point 9)", per.status_code == 403, per.status_code)
        check(f"{role} : fiche d'un agent → 403", c.get(f"/api/v1/personnel/{staff['SEC']}").status_code == 403)
        x = c.get("/api/v1/schooling/exports/students.xlsx")
        text_cells = " ".join(str(cell.value) for row in load_workbook(io.BytesIO(x.content)).active.iter_rows() for cell in row if cell.value) if x.status_code == 200 else ""
        check(f"{role} : export Excel des élèves = secondaire seulement", x.status_code == 200 and f"M-SEC-{RUN}-A" in text_cells and f"M-PRI-{RUN}-A" not in text_cells, x.status_code)
        hx = c.get("/api/v1/effectifs/exports/counts.xlsx", params={"group_by": "section"})
        htxt = " ".join(str(cell.value) for row in load_workbook(io.BytesIO(hx.content)).active.iter_rows() for cell in row if cell.value) if hx.status_code == 200 else ""
        check(f"{role} : export des effectifs par section sans le primaire", hx.status_code == 200 and "PRIMAIRE" not in htxt.upper(), hx.status_code)
        check(f"{role} : fiche PDF d'un élève du primaire → 404", c.get(f"/api/v1/schooling/students/{A['pupils']['PRIMAIRE']}/profile.pdf").status_code == 404)
        pdf = c.get(f"/api/v1/schooling/students/{A['pupils']['SECONDAIRE']}/profile.pdf")
        check(f"{role} : fiche PDF d'un élève du secondaire", pdf.status_code == 200 and pdf.content[:4] == b"%PDF", pdf.status_code)
        check(f"{role} : réglages scolaires en lecture (années, sections, identité)",
              all(c.get(u).status_code == 200 for u in ("/api/v1/settings/academic-years", "/api/v1/settings/sections", "/api/v1/settings/overview")))
        check(f"{role} : aucune modification des réglages (identité de l'école) → 403",
              c.patch("/api/v1/settings/identity", json={"name": "Nom modifié"}, headers={**key(), "If-Match": "1"}).status_code == 403)
        fx = c.get("/api/v1/schooling/exports/families.xlsx").status_code
        check(f"{role} : export des familles {'autorisé' if role == 'DIRECTEUR_ETUDES' else 'refusé (droit absent)'}", fx == (200 if role == "DIRECTEUR_ETUDES" else 403), fx)


# ------------------------------------------------------------------------ compléments : chaque capacité active éprouvée
def complements(A: dict) -> None:
    print("\n== Compléments — lectures et éditions restantes de chaque rôle")
    ia = actor_for("INTENDANT", A["id"])
    c = as_(ia)
    for label, path in (("historique documentaire", "/api/v1/documents/history"), ("personnel (lecture)", "/api/v1/personnel"),
                        ("identité de l'école (lecture)", "/api/v1/settings/overview"), ("liste des biens", "/api/v1/stewardship/assets"),
                        ("liste des comptages", "/api/v1/stewardship/counts"), ("locaux", "/api/v1/stewardship/locations"),
                        ("stock des articles vendus", "/api/v1/stewardship/sale-stock"), ("notifications", "/api/v1/notifications/inbox")):
        code = c.get(path).status_code
        check(f"INTENDANT : {label} (200)", code == 200, code)
    item = c.post("/api/v1/stewardship/items", json={"code": f"EDIT{RUN}", "label": "Cahier", "unit": "pièce"}, headers=key()).json()["id"]
    v = one("SELECT version FROM inventory_items WHERE id=:i", i=item)[0]
    up = c.put(f"/api/v1/stewardship/items/{item}", json={"label": "Cahier 100 pages", "unit": "pièce", "low_threshold": "5"}, headers={"If-Match": str(v)})
    check("INTENDANT : fiche article modifiée (If-Match), quantité non modifiable par cette route", up.status_code == 200 and up.json().get("quantity") in ("0", "0.000", 0), up.text[:120])
    check("INTENDANT : fiche article, version périmée → 409",
          c.put(f"/api/v1/stewardship/items/{item}", json={"label": "X2", "unit": "pièce", "low_threshold": "5"}, headers={"If-Match": str(v)}).status_code == 409)
    check("INTENDANT : élèves et effectifs non accessibles (403)",
          c.get("/api/v1/schooling/students").status_code == 403 and c.get("/api/v1/effectifs/counts", params={"group_by": "section"}).status_code == 403)
    for role in ("DIRECTEUR_ETUDES", "DIRECTEUR_DISCIPLINE"):
        d = as_(actor_for(role, A["id"], scope=("SECTION", "SECONDAIRE")))
        for label, path, params in (("effectifs par classe", "/api/v1/effectifs/counts", {"group_by": "class"}), ("mouvements des effectifs", "/api/v1/effectifs/movements", {}),
                                    ("vue d'ensemble des effectifs", "/api/v1/effectifs/overview", {}), ("état des communications", "/api/v1/communications/readiness", {}),
                                    ("historique documentaire", "/api/v1/documents/history", {}), ("indicateurs familles", "/api/v1/schooling/families/overview", {})):
            code = d.get(path, params=params).status_code
            check(f"{role} : {label} (200)", code == 200, code)
        pupil = A["pupils"]["SECONDAIRE"]; ver = one("SELECT version FROM students WHERE id=:i", i=pupil)[0]
        r = d.patch(f"/api/v1/schooling/students/{pupil}", json={"address": f"Avenue {role[:5]}"}, headers={**key(), "If-Match": str(ver)})
        check(f"{role} : complément de profil (adresse) d'un élève du secondaire (200)", r.status_code == 200, r.text[:120])
        check(f"{role} : aucune opération d'inscription (403)",
              d.post("/api/v1/schooling/enrollments/family", json={"children": []}, headers=key()).status_code in (403, 422))


def main() -> int:
    A, B = school("A"), school("B")
    intendant(A, B)
    directors(A, B)
    directors_reads(A)
    communications(A, B)
    notifications_and_auth(A, B)
    complements(A)
    documents(A)
    CLIENT.__exit__(None, None, None)
    fails = [r for r in RESULTS if r[0] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
