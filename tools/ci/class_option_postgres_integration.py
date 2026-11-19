"""Rattacher une classe des Humanités à son option — real HTTP + real PostgreSQL (owner, 2026-11-19).

The APN classes were opened without their option, so « Par option » was empty in the headcounts. A class already opened
(pupils inside) can now be attached to an option of its section; the headcounts by option count it at once; a primary
class or an option of another section is refused; a stale version is refused; detaching works.

    python tools/local/isolated_db.py env <db> -- ../.venv/Scripts/python.exe ../tools/ci/class_option_postgres_integration.py

CI=true, localhost only (three_roles_postgres_integration). Exits 1 on any FAIL.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_roles_postgres_integration as H  # noqa: E402
from three_roles_postgres_integration import actor_for, as_, check, key, one, school, sql  # noqa: E402

S = "/api/v1/settings"


def run(A: dict) -> None:
    print("\n== Rattacher une classe à son option (19/11/2026)")
    sid, y = A["id"], A["year"]
    hum = uuid.uuid4()
    sql("""INSERT INTO school_classes(id,school_id,academic_year_id,section_id,reference_code,code,label)
           VALUES(:i,:s,:y,:sec,'H3','3SC','3e SC')""", i=hum, s=sid, y=y, sec=A["sections"]["SECONDAIRE"])
    pupil = uuid.uuid4()
    sql("""INSERT INTO students(id,school_id,family_id,matricule,last_name,middle_name,first_name,gender)
           VALUES(:i,:s,:f,:m,'OPTION','TEST','Élève','F')""", i=pupil, s=sid, f=A["families"]["SECONDAIRE"], m=f"OPT-{H.RUN}")
    sql("INSERT INTO enrollments(id,school_id,student_id,academic_year_id,class_id,status) VALUES(:i,:s,:st,:y,:c,'VALIDATED')",
        i=uuid.uuid4(), s=sid, st=pupil, y=y, c=hum)
    sc, other = uuid.uuid4(), uuid.uuid4()
    sql("INSERT INTO school_options(id,school_id,section_id,code,label,enabled) VALUES(:i,:s,:sec,'SC','Scientifique',true)",
        i=sc, s=sid, sec=A["sections"]["SECONDAIRE"])
    sql("INSERT INTO school_options(id,school_id,section_id,code,label,enabled) VALUES(:i,:s,:sec,'XP','Autre section',true)",
        i=other, s=sid, sec=A["sections"]["PRIMAIRE"])
    version = lambda cid: one("SELECT version FROM school_classes WHERE id=:i", i=cid)[0]  # noqa: E731

    c = as_(actor_for("GESTIONNAIRE", sid, extra={"settings.classes.rename", "headcounts.by_option.read"}))
    put = lambda cid, opt, ver: c.put(f"{S}/classes/{cid}/option", json={"option_id": str(opt) if opt else None},  # noqa: E731
                                     headers={**key(), "If-Match": str(ver)})
    r = put(hum, sc, version(hum))
    check("classe 3e SC (avec un élève) rattachée à l'option Scientifique", r.status_code == 200 and r.json().get("option_id") == str(sc), r.text[:200])
    r = c.get("/api/v1/effectifs/counts?group_by=option&scope=ALL")
    rows = r.json().get("items", []) if r.status_code == 200 else []
    check("effectifs par option : Scientifique compte l'élève", any(x.get("label") == "Scientifique" and x["active"]["total"] >= 1 for x in rows), rows)
    r = put(A["classes"]["PRIMAIRE"], sc, version(A["classes"]["PRIMAIRE"]))
    check("classe hors Humanités refusée", r.status_code in (400, 409, 422), r.status_code)
    r = put(hum, other, version(hum))
    check("option d'une autre section refusée", r.status_code in (400, 409, 422), r.status_code)
    r = put(hum, None, version(hum) - 1)
    check("version obsolète refusée", r.status_code in (409, 412), r.status_code)
    r = put(hum, None, version(hum))
    check("option retirée", r.status_code == 200 and r.json().get("option_id") is None, r.text[:200])
    n = as_(actor_for("CAISSIER", sid)).put(f"{S}/classes/{hum}/option", json={"option_id": str(sc)}, headers={**key(), "If-Match": str(version(hum))})
    check("sans le droit de modifier les classes → refusé", n.status_code == 403, n.status_code)


def main() -> int:
    A = school("A")
    run(A)
    H.CLIENT.__exit__(None, None, None)
    fails = [r for r in H.RESULTS if r[0] == "FAIL"]
    print(f"\n{len(H.RESULTS) - len(fails)}/{len(H.RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
