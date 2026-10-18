"""Scale probe of the schools directory: +N synthetic schools in ONE transaction that is rolled back (the local data is
never modified), then EXPLAIN ANALYZE of the real directory queries (count, first page, search, filtered page).
Usage: EDUSYNC_LOCAL_PG_PORT=54432 python tools/local/schools_scale_probe.py [N]"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend/src")); sys.path.insert(0, str(ROOT / "tools/local"))
import edusync_local as L  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from edusync.modules.platform.application import schools_directory as d  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
env = L.load_env("demo")
eng = create_engine(env["EDUSYNC_PLATFORM_DATABASE_URL"])
with eng.connect() as c:
    tx = c.begin()
    try:
        t0 = time.perf_counter()
        c.execute(text("""INSERT INTO schools(code,name,status,province,city,contact_name)
            SELECT 'SCALE-' || g, 'École synthétique ' || g || CASE WHEN g % 7 = 0 THEN ' Sainte-Thérèse' ELSE '' END,
                   CASE WHEN g % 10 = 0 THEN 'SUSPENDED' ELSE 'ACTIVE' END, 'Kinshasa', 'Kinshasa', 'Promoteur ' || g
              FROM generate_series(1, :n) g"""), {"n": N})
        c.execute(text("ANALYZE schools"))
        total = c.execute(text("SELECT count(*) FROM schools")).scalar_one()
        print(f"{N} écoles synthétiques insérées en {time.perf_counter() - t0:.1f} s (total {total}, transaction annulée à la fin)")
        for label, kw in (("première page (tri nom)", dict(q=None, status=None, config=None, sort="name")),
                          ("recherche « sainte therese »", dict(q="sainte therese", status=None, config=None, sort="name")),
                          ("filtre suspendues, tri création", dict(q=None, status="SUSPENDED", config=None, sort="created")),
                          ("filtre configuration À finaliser", dict(q=None, status=None, config="INCOMPLETE", sort="name"))):
            t0 = time.perf_counter()
            r = d.list_schools(c, needs_admin=False, cursor=None, limit=25, **kw)
            ms = (time.perf_counter() - t0) * 1000
            t1 = time.perf_counter()
            r2 = d.list_schools(c, needs_admin=False, cursor=r["next_cursor"], limit=25, **kw) if r["next_cursor"] else None
            ms2 = (time.perf_counter() - t1) * 1000
            print(f"  {label:<36} total={r['total']:>5}  page 1 : {ms:6.0f} ms  page 2 : {ms2:6.0f} ms  ({len(r['items'])} lignes)")
        search, words = d._search_sql("sainte therese")
        plan = c.execute(text("EXPLAIN ANALYZE SELECT id FROM schools s WHERE " + search), words).scalars().all()
        print("  plan de la recherche :", " | ".join(p.strip() for p in plan if "Index" in p or "Bitmap" in p or "Seq Scan" in p or "Execution" in p))
    finally:
        tx.rollback()
with eng.connect() as c:
    print("après annulation : ", c.execute(text("SELECT count(*) FROM schools WHERE code LIKE 'SCALE-%'")).scalar_one(), "école synthétique restante")
