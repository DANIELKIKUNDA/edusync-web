"""Live probe — class states copied from the Desktop golden master (owner decisions 2026-10-14, O2 + O6).

Desktop reference: app/db/configuration.py::set_class_status / rename_class (EduSync École Offline 0.11.0-rc.1).
 * a class can be paused (INACTIVE) while it has students: they stay counted, visible and attached;
 * a paused class is offered neither for new enrollments nor as a normal class-change destination;
 * a class is archived only when it is empty; an archived class is read-only;
 * one capability (settings.classes.activate) for every state change, renaming is separate (settings.classes.rename).
Runs on school A of the isolated certification database, on classes created for the run (shared fixtures untouched).
"""
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import ensure_user, grant_test_role, owner, state, user_client  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


def k(extra=None):
    return {"Idempotency-Key": str(uuid4()), **(extra or {})}


A = state["A"]
run = uuid4().hex[:5].upper()
admin = user_client(A, "ADMIN")
ensure_user(A, "CLS_OPS", ())
grant_test_role(A, "CLS_OPS", "RECETTE_CLASSES_OPS", ("enrollments.create", "students.read", "students.class.change", "headcounts.read",
                                                         "headcounts.by_class.read", "settings.structure.read"))
ensure_user(A, "CLS_RENAME", ())
grant_test_role(A, "CLS_RENAME", "RECETTE_CLASSES_RENAME", ("settings.structure.read", "settings.classes.rename"))
ensure_user(A, "CLS_STATE", ())
grant_test_role(A, "CLS_STATE", "RECETTE_CLASSES_STATE", ("settings.structure.read", "settings.classes.activate"))
ops, renamer, stater = user_client(A, "CLS_OPS"), user_client(A, "CLS_RENAME"), user_client(A, "CLS_STATE")

year = next(y for y in admin.get("settings/academic-years").json() if y["status"] == "ACTIVE")


def new_class(suffix):
    r = admin.post("settings/classes", json={"academic_year_id": year["id"], "section_id": A["section_id"], "code": f"PRB{run}{suffix}",
                                              "label": f"Classe recette {run}{suffix}"}, headers=k())
    assert r.status_code == 201, r.text[:200]
    return r.json()


def get_class(cid):
    return next(c for c in admin.get("settings/classes", params={"year_id": year["id"]}).json() if c["id"] == cid)


def status(client, cls, value):
    return client.post(f"settings/classes/{cls['id']}/status", json={"status": value}, headers=k({"If-Match": str(cls["version"])}))


def enroll(class_id, name):
    return ops.post("schooling/enrollments/family", json={"primary_guardian": {"full_name": f"Tuteur {name}", "is_primary": True},
                                                          "children": [{"last_name": name, "middle_name": "Recette", "first_name": "Classe",
                                                                        "gender": "F", "class_id": class_id}]}, headers=k())


def class_count(label):
    items = ops.get("effectifs/counts", params={"group_by": "class"}).json()["items"]
    return sum(int(i["enrolled"]["total"]) if isinstance(i.get("enrolled"), dict) else int(i.get("enrolled_t", 0)) for i in items if i.get("label") == label)


# ---------- pause with students ----------
P = new_class("P")
e1 = enroll(P["id"], f"PAUSE{run}")
check("Élève inscrit dans la classe de recette", e1.status_code == 201, e1.status_code)
student = e1.json()["student_ids"][0]
before_total = ops.get("effectifs/overview").json()["active_students"]
before_class = class_count(P["label"])
r = status(admin, get_class(P["id"]), "INACTIVE")
cls = r.json() if r.status_code == 200 else {}
check("Mise en pause acceptée alors que la classe a un élève", r.status_code == 200 and cls.get("status") == "INACTIVE" and cls.get("enabled") is False, r.status_code)
check("Après la pause : élève toujours compté dans les effectifs (total et classe)",
      ops.get("effectifs/overview").json()["active_students"] == before_total and class_count(P["label"]) == before_class == 1, (before_total, before_class))
check("Après la pause : la classe reste listée dans les effectifs", any(c["id"] == P["id"] for c in ops.get("effectifs/classes").json()))
st = ops.get(f"schooling/students/{student}").json()
check("Après la pause : la fiche de l'élève garde sa classe", P["label"] in str(st) or P["id"] in str(st))
check("Après la pause : nombre d'élèves affiché par la classe = 1", get_class(P["id"]).get("student_count") == 1)

# ---------- not offered as destination ----------
e2 = enroll(P["id"], f"REFUS{run}")
check("Classe en pause : nouvelle inscription refusée", e2.status_code in (409, 422), e2.status_code)
other = enroll(A["class_id"], f"MOVE{run}")
mover = other.json()["student_ids"][0] if other.status_code == 201 else None
mv = ops.post(f"schooling/students/{mover}/class-change", json={"class_id": P["id"], "effective_date": date.today().isoformat(), "reason": "Recette pause"}, headers=k())
check("Classe en pause : changement de classe vers elle refusé", mover is not None and mv.status_code in (409, 422), mv.status_code)

# ---------- archive refused while students remain ----------
r = status(admin, get_class(P["id"]), "ARCHIVED")
check("Archivage refusé tant qu'il reste une inscription active", r.status_code in (409, 422) and "inscriptions actives" in r.text, r.status_code)

# ---------- direct API bypass: renaming never changes the state ----------
c = get_class(P["id"])
r = admin.put(f"settings/classes/{P['id']}", json={"code": c["code"], "label": c["label"], "enabled": True}, headers=k({"If-Match": str(c["version"])}))
check("API directe : un renommage avec enabled=true ne rouvre pas la classe (refusé)", r.status_code in (409, 422) and get_class(P["id"])["status"] == "INACTIVE", r.status_code)

# ---------- RBAC: rename and state are separate ----------
c = get_class(P["id"])
r = status(renamer, c, "ACTIVE")
check("Droit « renommer » seul : réactivation refusée (403)", r.status_code == 403, r.status_code)
r = renamer.put(f"settings/classes/{P['id']}", json={"code": c["code"], "label": c["label"] + " (renommée)"}, headers=k({"If-Match": str(c["version"])}))
check("Droit « renommer » seul : renommage accepté, statut inchangé", r.status_code == 200 and r.json().get("status") == "INACTIVE", r.status_code)
c = get_class(P["id"])
r = stater.put(f"settings/classes/{P['id']}", json={"code": c["code"], "label": c["label"] + " bis"}, headers=k({"If-Match": str(c["version"])}))
check("Droit « statut » seul : renommage refusé (403)", r.status_code == 403, r.status_code)
r = status(stater, c, "ACTIVE")
check("Droit « statut » seul : réactivation acceptée", r.status_code == 200 and r.json().get("status") == "ACTIVE" and r.json().get("enabled") is True, r.status_code)

# ---------- reactivated: normal destination again ----------
mv = ops.post(f"schooling/students/{mover}/class-change", json={"class_id": P["id"], "effective_date": date.today().isoformat(), "reason": "Recette réactivation"}, headers=k())
check("Après réactivation : changement de classe vers elle accepté", mv.status_code in (200, 201), mv.status_code)
check("Après réactivation : 2 élèves dans la classe, comptés", get_class(P["id"]).get("student_count") == 2 and class_count(get_class(P["id"])["label"]) == 2)

# ---------- archive an empty class: read-only afterwards ----------
E = new_class("E")
r = status(admin, get_class(E["id"]), "ARCHIVED")
check("Classe vide : archivage accepté", r.status_code == 200 and r.json().get("status") == "ARCHIVED" and r.json().get("archived_at"), r.status_code)
c = get_class(E["id"])
check("Classe archivée : plus de réactivation", status(admin, c, "ACTIVE").status_code in (409, 422))
r = admin.put(f"settings/classes/{E['id']}", json={"code": c["code"], "label": "Archivée renommée"}, headers=k({"If-Match": str(c["version"])}))
check("Classe archivée : plus de renommage", r.status_code in (409, 422), r.status_code)

# ---------- audit ----------
with owner.connect() as conn:
    rows = conn.execute(text("""SELECT old_json->>'status' AS old_s, new_json->>'status' AS new_s FROM audit_events
                                 WHERE action='SCHOOL_CLASS_STATUS_CHANGED' AND entity_id=:id ORDER BY occurred_at"""), {"id": P["id"]}).all()
    renamed = conn.execute(text("SELECT count(*) FROM audit_events WHERE action='SCHOOL_CLASS_UPDATED' AND entity_id=:id AND old_json IS NOT NULL"),
                           {"id": P["id"]}).scalar_one()
check("Audit : chaque changement d'état enregistré avec l'ancien et le nouveau statut",
      [(r.old_s, r.new_s) for r in rows] == [("ACTIVE", "INACTIVE"), ("INACTIVE", "ACTIVE")], [(r.old_s, r.new_s) for r in rows])
check("Audit : renommage enregistré avec l'état précédent", renamed >= 1, renamed)

ok = sum(r["pass"] for r in results)
out = Path(__file__).with_name("class-status-live.json")
import json  # noqa: E402
out.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"== {ok}/{len(results)} PASS -> {out.name}")
sys.exit(0 if ok == len(results) else 1)
