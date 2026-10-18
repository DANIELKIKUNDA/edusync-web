"""Scale probe of the « Utilisateurs & accès » directory: +N synthetic accounts in ONE transaction that is rolled back
(the local data is never modified), then timings and EXPLAIN of the real directory queries (count, page, search, scope).
Usage: EDUSYNC_LOCAL_PG_PORT=54432 python tools/local/identities_scale_probe.py [N]"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend/src")); sys.path.insert(0, str(ROOT / "tools/local"))
import edusync_local as L  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from edusync.modules.platform.application import identities_directory as d  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
eng = create_engine(L.load_env("demo")["EDUSYNC_OWNER_DATABASE_URL"])
with eng.connect() as c:
    tx = c.begin()
    try:
        c.execute(text("""INSERT INTO users(email, full_name, password_hash, active)
            SELECT 'scale-' || g || '@example.test', 'Compte Synthétique ' || g, 'x', (g % 17) <> 0 FROM generate_series(1, :n) g"""), {"n": N})
        c.execute(text("ANALYZE users"))
        total = c.execute(text("SELECT count(*) FROM users")).scalar_one()
        print(f"comptes : {total}")
        for label, kw in (("première page", {}), ("recherche « synthetique 1234 »", {"q": "synthetique 1234"}),
                          ("filtre Écoles", {"scope": "SCHOOL"}), ("filtre Plateforme", {"scope": "PLATFORM"}),
                          ("filtre Désactivés", {"status": "DISABLED"})):
            args = {"q": None, "scope": None, "status": None, "school_id": None, "role": None, "active_only": False, "cursor": None, "limit": 25} | kw
            t0 = time.perf_counter(); page = d.list_identities(c, **args); ms = int((time.perf_counter() - t0) * 1000)
            print(f"{label:34s} total={page['total']:>6}  page={len(page['items']):>2}  {ms} ms (2 requêtes : total + page)")
            if page["next_cursor"]:
                t0 = time.perf_counter(); d.list_identities(c, **(args | {"cursor": page["next_cursor"]})); print(f"{'   page suivante (curseur)':34s} {int((time.perf_counter() - t0) * 1000)} ms")
        where, params = d._search("synthetique 1234")
        plan = [r[0] for r in c.execute(text("EXPLAIN ANALYZE SELECT u.id FROM users u WHERE " + " AND ".join(where)), params)]
        print("plan recherche :", next((p.strip() for p in plan if "idx_users_search_trgm" in p), "INDEX NON UTILISÉ"), "|", plan[-1].strip())
    finally:
        tx.rollback()
with eng.connect() as c:
    print("après annulation :", c.execute(text("SELECT count(*) FROM users WHERE email LIKE 'scale-%@example.test'")).scalar_one(), "compte synthétique restant")
