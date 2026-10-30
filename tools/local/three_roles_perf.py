"""Reasonable performance measurement — Intendance and secondary reads (certification 2026-10-30). ISOLATED local database.

Loads a realistic volume in one school (5 000 consumables, 50 000 stock movements, 2 000 assets, 3 000 pupils), then
times the REAL routes in-process (median of 5 calls) and prints the PostgreSQL plan of the main queries (index usage).
No threshold is claimed: the figures are measurements on this machine, reported as such.

    python tools/local/isolated_db.py env edusync_cert_3roles -- ../.venv/Scripts/python.exe ../tools/local/three_roles_perf.py
"""
from __future__ import annotations

import json
import os
import statistics
import time
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

URL = os.environ["EDUSYNC_OWNER_DATABASE_URL"]
assert os.environ.get("CI") == "true" and ("127.0.0.1" in URL or "localhost" in URL)

from edusync.bootstrap.app import create_app  # noqa: E402
from edusync.bootstrap.dependencies import require_school_actor  # noqa: E402
from edusync.shared.application.context import ActorContext  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REG = json.loads((ROOT / "contracts/CAPABILITY_REGISTRY.json").read_text(encoding="utf-8"))
E = create_engine(URL, future=True)
SID, YID, UID, MID = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def load() -> None:
    with E.begin() as c:
        c.execute(text("INSERT INTO schools(id,code,name) VALUES(:i,:c,'Perf')"), {"i": SID, "c": f"PERF-{SID.hex[:8]}"})
        c.execute(text("INSERT INTO academic_years(id,school_id,code,label,start_date,end_date,status) VALUES(:i,:s,'P','P','2026-09-01','2027-07-01','ACTIVE')"), {"i": YID, "s": SID})
        c.execute(text("INSERT INTO users(id,email,full_name,password_hash,active,version) VALUES(:i,:e,'Perf','x',true,1)"), {"i": UID, "e": f"perf-{UID.hex[:8]}@example.test"})
        c.execute(text("INSERT INTO school_memberships(id,school_id,user_id,active,version) VALUES(:i,:s,:u,true,1)"), {"i": MID, "s": SID, "u": UID})
        c.execute(text("""INSERT INTO inventory_items(school_id,code,label,item_kind,unit,quantity,low_threshold)
            SELECT :s,'IT'||g,'Article '||g,'CONSUMABLE','pièce',(g%50),10 FROM generate_series(1,5000) g"""), {"s": SID})
        c.execute(text("""INSERT INTO inventory_item_movements(school_id,item_id,movement_type,quantity_delta,reason,actor_user_id)
            SELECT :s,i.id,'RECEIPT',1,'charge',:u FROM inventory_items i, generate_series(1,10) g WHERE i.school_id=:s"""), {"s": SID, "u": UID})
        t = c.execute(text("INSERT INTO inventory_asset_types(school_id,code,label) VALUES(:s,'T','Type') RETURNING id"), {"s": SID}).scalar_one()
        c.execute(text("INSERT INTO inventory_assets(school_id,asset_type_id,quantity,status) SELECT :s,:t,1,'GOOD' FROM generate_series(1,2000)"), {"s": SID, "t": t})
        sec = c.execute(text("INSERT INTO school_sections(school_id,code,label) VALUES(:s,'SECONDAIRE','Secondaire') RETURNING id"), {"s": SID}).scalar_one()
        cls = c.execute(text("INSERT INTO school_classes(school_id,academic_year_id,section_id,code,label) VALUES(:s,:y,:sec,'S1','S1') RETURNING id"), {"s": SID, "y": YID, "sec": sec}).scalar_one()
        fam = c.execute(text("INSERT INTO families(school_id,code,display_name) VALUES(:s,'F','F') RETURNING id"), {"s": SID}).scalar_one()
        c.execute(text("""INSERT INTO students(school_id,family_id,matricule,last_name,middle_name,first_name)
            SELECT :s,:f,'P'||g,'NOM'||g,'POST','PRENOM' FROM generate_series(1,3000) g"""), {"s": SID, "f": fam})
        c.execute(text("INSERT INTO enrollments(school_id,student_id,academic_year_id,class_id,status) SELECT :s,id,:y,:c,'VALIDATED' FROM students WHERE school_id=:s"), {"s": SID, "y": YID, "c": cls})
        c.execute(text("ANALYZE"))


def actor(role: str, scope=("SCHOOL", None)) -> ActorContext:
    caps = frozenset(REG["standard_roles"][role]["capabilities"])
    return ActorContext(user_id=UID, school_id=SID, membership_id=MID, permissions=caps, capability_scopes=tuple((c, *scope) for c in caps))


def main() -> None:
    load()
    app = create_app(); cur = {}
    app.dependency_overrides[require_school_actor] = lambda: cur["a"]
    client = TestClient(app, raise_server_exceptions=False); client.__enter__()
    routes = [("INTENDANT", "/api/v1/stewardship/stock?limit=100"), ("INTENDANT", "/api/v1/stewardship/stock?limit=100&offset=4800"),
              ("INTENDANT", "/api/v1/stewardship/stock/movements?limit=100"), ("INTENDANT", "/api/v1/stewardship/stock/low-alerts?limit=100"),
              ("INTENDANT", "/api/v1/stewardship/assets?limit=100"), ("INTENDANT", "/api/v1/stewardship/dashboard"),
              ("INTENDANT", "/api/v1/stewardship/stock/export.xlsx"), ("DIRECTEUR_ETUDES", "/api/v1/schooling/students?limit=100"),
              ("DIRECTEUR_ETUDES", "/api/v1/effectifs/counts?group_by=section")]
    print(f"{'route':<62} {'médiane':>8} {'max':>8}  statut  octets")
    for role, path in routes:
        cur["a"] = actor(role, ("SECTION", "SECONDAIRE") if role.startswith("DIRECTEUR") else ("SCHOOL", None))
        times, status, size = [], None, 0
        for _ in range(5):
            t = time.perf_counter(); r = client.get(path); times.append((time.perf_counter() - t) * 1000); status, size = r.status_code, len(r.content)
        print(f"{role[:9]+' '+path:<62} {statistics.median(times):7.0f}ms {max(times):7.0f}ms  {status}  {size}")
    print("\nPlans PostgreSQL (EXPLAIN ANALYZE) :")
    plans = {"mouvements récents": "SELECT * FROM inventory_item_movements WHERE school_id=:s ORDER BY created_at DESC LIMIT 100",
             "alertes de stock": "SELECT id FROM inventory_items WHERE school_id=:s AND enabled AND quantity<=low_threshold ORDER BY quantity LIMIT 100",
             "historique d'un article": "SELECT * FROM inventory_item_movements WHERE school_id=:s AND item_id=(SELECT id FROM inventory_items WHERE school_id=:s LIMIT 1) ORDER BY created_at DESC LIMIT 50"}
    with E.connect() as c:
        for name, q in plans.items():
            plan = [r[0] for r in c.execute(text("EXPLAIN ANALYZE " + q), {"s": SID})]
            uses = [p.strip() for p in plan if "Index" in p or "Seq Scan" in p][:2]
            total = next((p for p in plan if p.startswith("Execution Time")), "")
            print(f"  {name:<24} {total:<28} {' | '.join(uses)[:150]}")
    client.__exit__(None, None, None)


if __name__ == "__main__":
    main()
