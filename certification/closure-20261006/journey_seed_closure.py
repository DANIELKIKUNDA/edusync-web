"""Seeds one-off charges for the closure UI journeys (owner role, demo database only).

No tariff->charge generator exists yet (owner decision), so obligations are fixtures; every payment in
the journey goes through the UI. Writes .local/closure/journey-seed.json (labels, student names).
"""
import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import DB_URL, ROOT, state, sql  # noqa: E402

assert DB_URL.endswith("/edusync_claude_fresh")
A = state["A"]
tag = uuid4().hex[:5].upper()
kids = []
for eid in A["family"]["enrollment_ids"][:2]:
    r = sql("""SELECT s.matricule,s.last_name,s.first_name FROM enrollments e JOIN students s ON s.id=e.student_id WHERE e.id=:e""", {"e": eid})[0]
    kids.append({"enrollment_id": eid, "query": r["matricule"], "name": f"{r['last_name']}", "first": r["first_name"]})


def charge(eid, label, amount=10000):
    return str(sql("""INSERT INTO finance_charges(school_id,enrollment_id,label,currency,net_amount,periodicity)
                      VALUES(:s,:e,:l,'CDF',:a,'ONE_OFF') RETURNING id""", {"s": A["school_id"], "e": eid, "l": label, "a": amount})[0]["id"])


c1, c2 = kids
c1["single"] = f"Recette UI {tag} · Uniforme"; charge(c1["enrollment_id"], c1["single"], 15000)
c1["basket"] = f"Recette UI {tag} · Cantine"; charge(c1["enrollment_id"], c1["basket"], 8000)
c2["basket"] = f"Recette UI {tag} · Transport"; charge(c2["enrollment_id"], c2["basket"], 12000)
c2["lost"] = f"Recette UI {tag} · Sortie"; c2["lostId"] = charge(c2["enrollment_id"], c2["lost"], 5000)
out = ROOT / ".local" / "closure" / "journey-seed.json"
out.write_text(json.dumps({"tag": tag, "child1": c1, "child2": c2}, ensure_ascii=False, indent=2), encoding="utf-8")
print("seeded", tag, c1["name"], c2["name"])
