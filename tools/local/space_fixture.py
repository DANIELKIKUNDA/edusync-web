"""Local fixture for checking the change of space by hand: gives the restricted platform support account of the
fixtures memberships in N active schools (two roles in the first), or removes them.
Usage: EDUSYNC_LOCAL_PG_PORT=54432 python tools/local/space_fixture.py add [N]   |   ... remove
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/local"))
import edusync_local as L  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

env = L.load_env("demo")
owner = create_engine(env["EDUSYNC_OWNER_DATABASE_URL"])
FX = json.loads((ROOT / ".local/claude-fixtures-edusync_claude_fresh.json").read_text(encoding="utf-8"))
UID = FX["N1_TEAM"]["u2"]["id"]
TAG = "space_fixture"

with owner.begin() as c:
    if sys.argv[1] == "remove":
        mids = [r[0] for r in c.execute(text("SELECT DISTINCT membership_id FROM rbac_assignments WHERE user_id=:u AND reason=:t"), {"u": UID, "t": TAG})]
        c.execute(text("DELETE FROM rbac_assignments WHERE user_id=:u AND reason=:t"), {"u": UID, "t": TAG})
        if mids:
            c.execute(text("DELETE FROM user_device_sessions WHERE membership_id=ANY(:m)"), {"m": mids})
            c.execute(text("DELETE FROM school_memberships WHERE id=ANY(:m)"), {"m": mids})
        print(f"retiré : {len(mids)} appartenances")
    else:
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 2
        roles = dict(c.execute(text("SELECT code, id FROM rbac_roles WHERE school_id IS NULL AND level='SCHOOL' AND status='ACTIVE' AND code IN ('CAISSIER','SECRETARIAT')")).all())
        schools = c.execute(text("""SELECT id, code FROM schools s WHERE status='ACTIVE' AND NOT EXISTS
            (SELECT 1 FROM school_memberships m WHERE m.school_id=s.id AND m.user_id=:u) ORDER BY code LIMIT :n"""), {"u": UID, "n": n}).all()
        for i, (sid, code) in enumerate(schools):
            mid = c.execute(text("INSERT INTO school_memberships(id,school_id,user_id,active,created_at,version) VALUES(gen_random_uuid(),:s,:u,true,now(),1) RETURNING id"),
                            {"s": sid, "u": UID}).scalar()
            for rc in (("CAISSIER", "SECRETARIAT") if i == 0 else ("CAISSIER",)):
                c.execute(text("""INSERT INTO rbac_assignments(id,user_id,role_id,school_id,membership_id,active,valid_from,version,created_at,updated_at,reason)
                    VALUES(gen_random_uuid(),:u,:r,:s,:m,true,now()-interval '1 minute',1,now(),now(),:t)"""), {"u": UID, "r": roles[rc], "s": sid, "m": mid, "t": TAG})
        print("ajouté : " + ", ".join(code for _, code in schools))
